package fabricaot.metal;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.function.Supplier;
import com.mojang.blaze3d.buffers.*;
import com.mojang.blaze3d.pipeline.*;
import com.mojang.blaze3d.shaders.ShaderSource;
import com.mojang.blaze3d.systems.*;
import com.mojang.blaze3d.textures.*;
import org.lwjgl.system.MemoryUtil;

/** Experimental Metal resources and precompiled vanilla pipelines.
 * Unsupported attachment, query and transfer forms fail at their named boundaries. */
final class MetalDevice implements GpuDeviceBackend {
    long context;
    private final String renderer;
    private final Set<AutoCloseable> resources=new HashSet<>();
    private final ResourceBudget budget=new ResourceBudget(System.getProperty(ResourceBudget.PROPERTY));
    private ShaderIndex shaderIndex;
    private final ShaderSource defaultShaderSource;
    private final Map<MetalPipeline.Key,MetalPipeline> pipelines=new HashMap<>();
    private final Map<RenderPipeline,MetalPipeline> pipelineInstances=new IdentityHashMap<>();
    MetalRenderPass activePass;
    final BufferHazardTracker bufferHazards=new BufferHazardTracker();
    private long unprotectedWrites, protectedWrites, largeBufferWaits;
    private long largeWaitNanos, cloneFallbackWaits, cloneFallbackWaitNanos;
    void waitForGpu(){MetalNative.synchronize(context);bufferHazards.completed();}
    void waitForCpuWrite(boolean cloneFallback){
        long start=System.nanoTime();
        waitForGpu();
        long elapsed=System.nanoTime()-start;
        if(cloneFallback){cloneFallbackWaits++;cloneFallbackWaitNanos+=elapsed;}
        else largeWaitNanos+=elapsed;
    }
    void recordBufferWrite(boolean protectedWrite,boolean largeWait){
        if(protectedWrite)protectedWrites++;else unprotectedWrites++;
        if(largeWait)largeBufferWaits++;
    }
    private int hazardSampleFrames;

    MetalDevice(long window,ShaderSource source){defaultShaderSource=source;context=MetalNative.create(window);if(context==0)throw new IllegalStateException("Metal context allocation failed");renderer=MetalNative.deviceName(context);System.err.println("[Metal] device="+renderer+" resourceBudgetMiB="+budget.limitMiB());}
    void alive(){if(context==0)throw new IllegalStateException("Metal device closed");}
    void outsidePass(){alive();if(activePass!=null)throw new IllegalStateException("Operation inside an active Metal render pass");}
    void retire(AutoCloseable resource,long bytes){resources.remove(resource);if(bytes!=0)budget.release(bytes);}
    void refund(long bytes){budget.release(bytes);}
    <T extends AutoCloseable> T track(T resource){resources.add(resource);return resource;}
    MetalTexture texture(GpuTexture texture){if(!(texture instanceof MetalTexture m)||m.owner!=this)throw new IllegalArgumentException("Texture belongs to another backend/device");m.alive();return m;}
    MetalTextureView view(GpuTextureView view){if(!(view instanceof MetalTextureView m)||m.source.owner!=this)throw new IllegalArgumentException("Texture view belongs to another backend/device");m.alive();return m;}
    MetalBuffer buffer(GpuBuffer buffer){if(!(buffer instanceof MetalBuffer m)||m.owner!=this||m.isClosed())throw new IllegalArgumentException("Buffer closed or belongs to another backend/device");alive();return m;}
    long sampler(GpuSampler sampler){alive();if(!(sampler instanceof MetalSampler m)||!resources.contains(m)||m.handle==0)throw new IllegalArgumentException("Sampler closed or belongs to another device");return m.handle;}
    private UnsupportedOperationException unsupported(String api){return new UnsupportedOperationException("Metal backend not implemented: "+api);}
    public CommandEncoderBackend createCommandEncoder(){alive();return new MetalCommandEncoder(this);}
    public GpuSampler createSampler(AddressMode u,AddressMode v,FilterMode min,FilterMode mag,int anisotropy,OptionalDouble maxLod){
        alive();if(anisotropy<1||anisotropy>16)throw new IllegalArgumentException("anisotropy 1..16 required");
        long nativeSampler=MetalNative.createSampler(context,u==AddressMode.REPEAT,v==AddressMode.REPEAT,min==FilterMode.LINEAR,mag==FilterMode.LINEAR,anisotropy,maxLod.orElse(Double.MAX_VALUE));
        if(nativeSampler==0)throw new IllegalStateException("Metal sampler allocation failed");
        MetalSampler sampler=new MetalSampler(nativeSampler,u,v,min,mag,anisotropy,maxLod);resources.add(sampler);return sampler;
    }
    public GpuTexture createTexture(Supplier<String> label,int usage,TextureFormat format,int w,int h,int layers,int mips){return createTexture(label==null?"":label.get(),usage,format,w,h,layers,mips);}
    public GpuTexture createTexture(String label,int usage,TextureFormat format,int w,int h,int layers,int mips){
        alive();long bytes=TextureSpec.byteSize(Objects.requireNonNull(format),w,h,layers,mips,usage);budget.reserve(bytes);
        try{long handle=MetalNative.createTexture(context,TextureSpec.formatId(format),usage,w,h,layers,mips);
            if(handle==0)throw new OutOfMemoryError("MTLTexture allocation failed");
            return track(new MetalTexture(this,handle,usage,label,format,w,h,layers,mips,bytes));
        }catch(RuntimeException|Error e){budget.release(bytes);throw e;}
    }
    public GpuTextureView createTextureView(GpuTexture texture){return createTextureView(texture,0,texture.getMipLevels());}
    public GpuTextureView createTextureView(GpuTexture texture,int baseMip,int mips){
        MetalTexture t=texture(texture);
        if(baseMip<0||mips<=0||mips>t.getMipLevels()||baseMip>t.getMipLevels()-mips)throw new IllegalArgumentException("Texture view mip range out of bounds");
        long view=MetalNative.createTextureView(t.handle,baseMip,mips);if(view==0)throw new IllegalStateException("MTLTexture view creation failed");
        return track(new MetalTextureView(t,baseMip,mips,view));
    }
    public GpuBuffer createBuffer(Supplier<String> label,int usage,long size){
        alive();if(size<=0||size>256L*1024*1024)throw new IllegalArgumentException("Metal bootstrap buffer budget: 1..256 MiB");
        budget.reserve(size);
        try{long nativeBuffer=MetalNative.createBuffer(context,size);
            if(nativeBuffer==0)throw new OutOfMemoryError("MTLBuffer allocation failed");
            return track(new MetalBuffer(nativeBuffer,usage,size));
        }catch(RuntimeException|Error e){budget.release(size);throw e;}
    }
    public GpuBuffer createBuffer(Supplier<String> label,int usage,ByteBuffer data){
        Objects.requireNonNull(data);MetalBuffer buffer=(MetalBuffer)createBuffer(label,usage,data.remaining());
        ByteBuffer mapped=MemoryUtil.memByteBuffer(MetalNative.bufferAddress(buffer.handle),data.remaining());
        mapped.put(data.duplicate());return buffer;
    }
    public String getImplementationInformation(){return "FabricAOT Metal / "+renderer;}
    public List<String> getLastDebugMessages(){return List.of();}
    public boolean isDebuggingEnabled(){return false;}
    public String getVendor(){return "Apple";}
    public String getBackendName(){return "Metal";}
    public String getVersion(){return "G3 resources and precompiled vanilla draw pipelines";}
    public String getRenderer(){return renderer;}
    public int getMaxTextureSize(){return 16384;}
    public int getUniformOffsetAlignment(){return 256;}
    public CompiledRenderPipeline precompilePipeline(RenderPipeline pipeline,ShaderSource source){
        alive();MetalPipeline cached=pipelineInstances.get(pipeline);
        if(cached!=null&&cached.isValid()){if(source!=null)shaderIndex.program(pipeline,source,false);return cached;}
        MetalPipeline.Key key=MetalPipeline.Key.of(pipeline);cached=pipelines.get(key);
        if(cached!=null&&cached.isValid()){if(source!=null)shaderIndex.program(pipeline,source,false);pipelineInstances.put(pipeline,cached);return cached;}
        if(shaderIndex==null)shaderIndex=new ShaderIndex();
        // Diagnostics: a fresh compile of a pipeline the splash is drawing is exactly the
        // situation the preload contract exists to prevent, so name the pipeline and where the
        // source came from. The bundle is read-only, so this stays a stderr line.
        System.err.println("[MCFAO_SHADER] compile "+pipeline.getLocation()+" src="+(source!=null?"explicit":(defaultShaderSource!=null?"default":"none")));
        MetalPipeline compiled=track(new MetalPipeline(this,pipeline,shaderIndex.program(pipeline,source==null?defaultShaderSource:source,source==null)));pipelines.put(key,compiled);pipelineInstances.put(pipeline,compiled);return compiled;
    }
    public void clearPipelineCache(){outsidePass();System.err.println("[MCFAO_SHADER] clearPipelineCache from "+caller());for(MetalPipeline pipeline:List.copyOf(pipelines.values()))pipeline.close();pipelines.clear();pipelineInstances.clear();if(shaderIndex!=null)shaderIndex.clearSourceValidation();}
    private static String caller(){
        StackTraceElement[] trace=new Throwable().getStackTrace();
        StringBuilder text=new StringBuilder();
        for(int index=1;index<trace.length&&index<5;index++){
            if(text.length()!=0)text.append(" < ");
            text.append(trace[index].getClassName()).append('#').append(trace[index].getMethodName())
                .append(':').append(trace[index].getLineNumber());
        }
        return text.toString();
    }
    public List<String> getEnabledExtensions(){return List.of();}
    public int getMaxSupportedAnisotropy(){return 16;}
    public void setVsync(boolean enabled){alive();vsync=enabled;MetalNative.setDisplaySync(context,enabled);}
    private boolean vsync=true;
    public void presentFrame(){outsidePass();MetalNative.presentFrame(context);
        if(++hazardSampleFrames==300){
            System.err.println("[MetalBufferHazards] frames=300 direct_writes="+unprotectedWrites+" protected_writes="+protectedWrites+" large_waits="+largeBufferWaits
                +" large_wait_total_ms="+largeWaitNanos/1_000_000.0+" clone_fallback_waits="+cloneFallbackWaits+" clone_fallback_wait_total_ms="+cloneFallbackWaitNanos/1_000_000.0);
            hazardSampleFrames=0;unprotectedWrites=0;protectedWrites=0;largeBufferWaits=0;
            largeWaitNanos=0;cloneFallbackWaits=0;cloneFallbackWaitNanos=0;
        }
    }
    public boolean isZZeroToOne(){return true;}
    public void close(){
        if(context==0)return;
        outsidePass();waitForGpu();
        clearPipelineCache();
        for(AutoCloseable resource:List.copyOf(resources))try{resource.close();}catch(Exception e){throw new IllegalStateException("Metal resource release",e);}
        MetalNative.release(context);context=0;
    }
    void clearDiagnosticFrame(){alive();MetalNative.clearDiagnosticFrame(context,0.12f,0.38f,0.62f,1.0f);}
    final class MetalBuffer extends GpuBuffer {
        final MetalDevice owner=MetalDevice.this;
        long handle;
        int mappings;
        final BufferHazardTracker.State hazard=new BufferHazardTracker.State();
        MetalBuffer(long handle,int usage,long size){super(usage,size);this.handle=handle;}
        public boolean isClosed(){return handle==0;}
        public void close(){if(mappings!=0)throw new IllegalStateException("Closing mapped Metal buffer");if(handle!=0){MetalNative.release(handle);handle=0;retire(this,size());}}
    }
    private final class MetalSampler extends GpuSampler {
        private long handle;
        private final AddressMode u,v;private final FilterMode min,mag;
        private final int anisotropy;private final OptionalDouble maxLod;
        MetalSampler(long handle,AddressMode u,AddressMode v,FilterMode min,FilterMode mag,int anisotropy,OptionalDouble maxLod){this.handle=handle;this.u=u;this.v=v;this.min=min;this.mag=mag;this.anisotropy=anisotropy;this.maxLod=maxLod;}
        public AddressMode getAddressModeU(){return u;}public AddressMode getAddressModeV(){return v;}
        public FilterMode getMinFilter(){return min;}public FilterMode getMagFilter(){return mag;}
        public int getMaxAnisotropy(){return anisotropy;}public OptionalDouble getMaxLod(){return maxLod;}
        public void close(){if(handle!=0){MetalNative.release(handle);handle=0;resources.remove(this);}}
    }
}
