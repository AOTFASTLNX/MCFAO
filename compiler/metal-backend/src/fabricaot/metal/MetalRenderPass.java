package fabricaot.metal;
import java.util.Collection;
import java.util.*;
import java.util.function.Supplier;
import com.mojang.blaze3d.buffers.*;
import com.mojang.blaze3d.pipeline.RenderPipeline;
import com.mojang.blaze3d.systems.*;
import com.mojang.blaze3d.textures.*;
import com.mojang.blaze3d.vertex.VertexFormat;

/** Real attachment load/clear/store pass. Shader draw support is a separate implementation step. */
final class MetalRenderPass implements RenderPassBackend {
    private final MetalDevice device;
    private boolean closed;
    private int groups;
    private MetalPipeline pipeline;
    private MetalDevice.MetalBuffer vertex,index;
    private VertexFormat.IndexType indexType;
    private final Map<String,GpuBufferSlice> uniforms=new HashMap<>();
    private record TextureBinding(MetalTextureView texture,GpuSampler sampler) {}
    private final Map<String,TextureBinding> textures=new HashMap<>();
    private boolean skipped;
    private static final Set<String> skippedReported=new HashSet<>();
    MetalRenderPass(MetalDevice device){this.device=device;}
    private void alive(){device.alive();if(closed||device.activePass!=this)throw new IllegalStateException("Metal render pass closed");}
    private UnsupportedOperationException unsupported(String api){alive();return new UnsupportedOperationException("Metal game render pipeline not implemented: "+api);}
    public void pushDebugGroup(Supplier<String> name){alive();MetalNative.debugGroup(device.context,name.get(),true);groups++;}
    public void popDebugGroup(){alive();if(groups==0)throw new IllegalStateException("Debug group underflow");MetalNative.debugGroup(device.context,"",false);groups--;}
    public void setPipeline(RenderPipeline source){alive();
        // Registration already refused this pipeline (no precompiled program in the bundle), so
        // the pass it belongs to must not draw: a Mod keeps its pipeline object and calls it on
        // its own schedule, and throwing here would abort a pass that vanilla closes from a
        // finally block at best - at worst it strands device.activePass and the next clear in the
        // frame dies on "Close the existing render pass before creating a new one".
        if(!BundledPipelines.supports(source)){
            skipped=true;pipeline=null;
            if(skippedReported.add(source.getLocation().toString()))
                System.err.println("[MCFAO_SHADER] skipping draws for unsupported pipeline "+source.getLocation());
            return;
        }
        skipped=false;pipeline=(MetalPipeline)device.precompilePipeline(source,null);MetalNative.setPipeline(device.context,pipeline.handle);}
    public void bindTexture(String name,GpuTextureView texture,GpuSampler sampler){alive();device.sampler(sampler);textures.put(Objects.requireNonNull(name),new TextureBinding(device.view(texture),sampler));}
    public void setUniform(String name,GpuBuffer buffer){setUniform(name,buffer.slice());}
    public void setUniform(String name,GpuBufferSlice slice){alive();MetalDevice.MetalBuffer buffer=device.buffer(slice.buffer());TextureSpec.range(buffer.size(),slice.offset(),slice.length());uniforms.put(Objects.requireNonNull(name),slice);}
    public void enableScissor(int x,int y,int width,int height){alive();if(width<0||height<0)throw new IllegalArgumentException("Negative scissor extent");MetalNative.scissor(device.context,true,x,y,width,height);}
    public void disableScissor(){alive();MetalNative.scissor(device.context,false,0,0,0,0);}
    public void setVertexBuffer(int slot,GpuBuffer buffer){alive();if(slot!=0)throw unsupported("vertex stream slot "+slot);vertex=device.buffer(buffer);if(vertex.mappings!=0)throw new IllegalStateException("Vertex buffer is mapped");MetalNative.vertexBuffer(device.context,vertex.handle);}
    public void setIndexBuffer(GpuBuffer buffer,VertexFormat.IndexType type){alive();index=device.buffer(buffer);indexType=Objects.requireNonNull(type);}
    private void prepare(){
        alive();if(pipeline==null||!pipeline.isValid())throw new IllegalStateException("No live Metal pipeline selected");
        if(pipeline.program.vertexInputs().size()!=0&&(vertex==null||vertex.isClosed()))throw new IllegalStateException("Missing live vertex buffer");
        for(ShaderIndex.Binding binding:pipeline.program.bindings()){
            if(binding.kind().equals("uniform")||binding.bufferTexture()){
                GpuBufferSlice slice=uniforms.get(binding.name());if(slice==null)throw new IllegalStateException("Missing uniform "+binding.name()+" for "+pipeline.source.getLocation());
                MetalDevice.MetalBuffer buffer=device.buffer(slice.buffer());TextureSpec.range(buffer.size(),slice.offset(),slice.length());
                if(buffer.mappings!=0||slice.length()<binding.bytes())throw new IllegalStateException("Mapped or undersized uniform "+binding.name());
                if(binding.bufferTexture()){
                    var description=pipeline.source.getUniforms().stream().filter(v->v.name().equals(binding.name())).findFirst().orElseThrow(()->new IllegalStateException("Missing texel format "+binding.name()));
                    MetalNative.bindTexelBuffer(device.context,binding.stage(),binding.index(),TextureSpec.formatId(Objects.requireNonNull(description.textureFormat())),buffer.handle,slice.offset(),slice.length());
                }else MetalNative.bindUniform(device.context,binding.stage(),binding.index(),buffer.handle,slice.offset(),slice.length());
            }else{
                TextureBinding texture=textures.get(binding.name());if(texture==null)throw new IllegalStateException("Missing texture "+binding.name());texture.texture.alive();
                MetalNative.bindTexture(device.context,binding.stage(),binding.index(),binding.samplerIndex(),texture.texture.handle,device.sampler(texture.sampler));
            }
        }
    }
    public void drawIndexed(int baseVertex,int firstIndex,int indexCount,int instances){
        if(skipped)return;
        prepare();if(index==null||index.isClosed()||index.mappings!=0)throw new IllegalStateException("Missing live unmapped index buffer");
        if(firstIndex<0||indexCount<0||instances<0)throw new IllegalArgumentException("Negative indexed draw range");
        TextureSpec.range(index.size(),Math.multiplyExact((long)firstIndex,indexType.bytes),Math.multiplyExact((long)indexCount,indexType.bytes));
        if(indexCount!=0&&instances!=0)MetalNative.drawIndexed(device.context,pipeline.handle,index.handle,indexType==VertexFormat.IndexType.SHORT?0:1,firstIndex,indexCount,baseVertex,instances);
    }
    public <T> void drawMultipleIndexed(Collection<RenderPass.Draw<T>> draws,GpuBuffer buffer,VertexFormat.IndexType type,Collection<String> names,T value){
        alive();for(RenderPass.Draw<T> draw:draws){
            setVertexBuffer(draw.slot(),draw.vertexBuffer());
            setIndexBuffer(draw.indexBuffer()==null?buffer:draw.indexBuffer(),draw.indexBuffer()==null?type:draw.indexType());
            if(draw.uniformUploaderConsumer()!=null)draw.uniformUploaderConsumer().accept(value,this::setUniform);
            drawIndexed(draw.baseVertex(),draw.firstIndex(),draw.indexCount(),1);
        }
    }
    public void draw(int first,int count){
        if(skipped)return;
        prepare();if(first<0||count<0)throw new IllegalArgumentException("Negative draw range");
        if(vertex!=null&&pipeline.key.stride()!=0)TextureSpec.range(vertex.size(),Math.multiplyExact((long)first,pipeline.key.stride()),Math.multiplyExact((long)count,pipeline.key.stride()));
        if(count!=0)MetalNative.draw(device.context,pipeline.handle,first,count);
    }
    /** Closes the native pass and *always* releases {@code device.activePass}.
     *
     * <p>Vanilla closes passes from {@code try}/{@code finally} blocks, but a caller that swallows
     * an exception from inside the pass (a Mod drawing an unsupported pipeline, a failing uniform
     * upload) may never reach {@code close()} at all. The device only has one pass slot, so a
     * stranded slot turns the next {@code clearColorAndDepthTextures} or pass creation into a
     * fatal {@code IllegalStateException} far away from the real failure. Releasing the slot here
     * unconditionally keeps a nested {@code close()} (or one that races an already-failed device)
     * from wedging the frame.
     */
    public void close(){
        if(closed)return;
        closed=true;
        if(device.activePass==this)device.activePass=null;
        if(groups>0){while(groups>0){groups--;MetalNative.debugGroup(device.context,"",false);}}
        MetalNative.endPass(device.context);
    }
    public boolean isClosed(){return closed;}
}
