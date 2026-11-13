package fabricaot.metal;
import java.nio.*;
import java.util.*;
import java.util.function.Supplier;
import com.mojang.blaze3d.buffers.*;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.blaze3d.systems.*;
import com.mojang.blaze3d.textures.*;
import org.lwjgl.system.MemoryUtil;

/** Transfers synchronize shared storage before CPU access. Game draw pipelines remain explicit. */
final class MetalCommandEncoder implements CommandEncoderBackend {
    private final MetalDevice device;
    MetalCommandEncoder(MetalDevice device){this.device=device;}
    public boolean isInRenderPass(){return device.activePass!=null;}
    public RenderPassBackend createRenderPass(Supplier<String> label,GpuTextureView color,OptionalInt clear){return createRenderPass(label,color,clear,null,OptionalDouble.empty());}
    public RenderPassBackend createRenderPass(Supplier<String> label,GpuTextureView color,OptionalInt clear,GpuTextureView depth,OptionalDouble depthClear){
        device.outsidePass();MetalTextureView c=device.view(color),d=depth==null?null:device.view(depth);
        MetalNative.beginPass(device.context,c.handle,clear.isPresent(),clear.orElse(0),d==null?0:d.handle,depthClear.isPresent(),depthClear.orElse(1));
        MetalRenderPass pass=new MetalRenderPass(device);device.activePass=pass;return pass;
    }
    public void clearColorTexture(GpuTexture texture,int color){device.outsidePass();MetalNative.clearTextures(device.context,device.texture(texture).handle,color,0,1);}
    public void clearDepthTexture(GpuTexture texture,double depth){device.outsidePass();MetalNative.clearTextures(device.context,0,0,device.texture(texture).handle,depth);}
    public void clearColorAndDepthTextures(GpuTexture color,int argb,GpuTexture depth,double value){device.outsidePass();MetalNative.clearTextures(device.context,device.texture(color).handle,argb,device.texture(depth).handle,value);}
    public void clearColorAndDepthTextures(GpuTexture color,int argb,GpuTexture depth,double value,int x,int y,int width,int height){
        device.outsidePass();
        MetalTexture c=device.texture(color),d=device.texture(depth);
        TextureSpec.rectangle(c.getWidth(0),c.getHeight(0),x,y,width,height);
        if(x==0&&y==0&&width==c.getWidth(0)&&height==c.getHeight(0)){
            MetalNative.clearTextures(device.context,c.handle,argb,d.handle,value);
        }else{
            MetalNative.clearRectangle(device.context,c.handle,argb,d.handle,value,x,y,width,height);
        }
    }
    private void prepareCpuWrite(MetalDevice.MetalBuffer buffer){
        // Small buffers are CPU-written and GPU-read. Give each write its own
        // backing storage so already-encoded draws keep their original data.
        // Large buffers retain the bounded-memory synchronous path.
        if(buffer.size()<=64*1024){
            long previous=buffer.handle;
            long replacement=MetalNative.cloneBuffer(device.context,previous,buffer.size());
            if(replacement!=0){
                buffer.handle=replacement;
                MetalNative.release(previous);
            }else MetalNative.synchronize(device.context);
        }else MetalNative.synchronize(device.context);
    }
    public void writeToBuffer(GpuBufferSlice slice,ByteBuffer data){
        device.outsidePass();MetalDevice.MetalBuffer buffer=device.buffer(slice.buffer());
        TextureSpec.range(buffer.size(),slice.offset(),slice.length());
        if(data.remaining()>slice.length())throw new IllegalArgumentException("Write exceeds buffer slice");
        if(buffer.mappings!=0)throw new IllegalStateException("Writing a mapped buffer");
        prepareCpuWrite(buffer);
        MemoryUtil.memByteBuffer(MetalNative.bufferAddress(buffer.handle)+slice.offset(),data.remaining()).put(data.duplicate());
    }
    public GpuBuffer.MappedView mapBuffer(GpuBufferSlice slice,boolean read,boolean write){
        device.outsidePass();MetalDevice.MetalBuffer buffer=device.buffer(slice.buffer());
        if(!read&&!write)throw new IllegalArgumentException("Map must allow read or write");
        TextureSpec.range(buffer.size(),slice.offset(),slice.length());
        if(slice.length()>Integer.MAX_VALUE||buffer.mappings!=0)throw new IllegalStateException("Buffer map too large or already mapped");
        if(write&&!read)prepareCpuWrite(buffer);
        else MetalNative.synchronize(device.context);
        ByteBuffer bytes=MemoryUtil.memByteBuffer(MetalNative.bufferAddress(buffer.handle)+slice.offset(),(int)slice.length()).order(ByteOrder.nativeOrder());
        ByteBuffer view=write?bytes:bytes.asReadOnlyBuffer().order(ByteOrder.nativeOrder());buffer.mappings++;
        return new GpuBuffer.MappedView(){private boolean closed;
            public ByteBuffer data(){if(closed)throw new IllegalStateException("Mapped view closed");return view;}
            public void close(){if(!closed){closed=true;buffer.mappings--;}}
        };
    }
    public void copyToBuffer(GpuBufferSlice source,GpuBufferSlice destination){
        device.outsidePass();MetalDevice.MetalBuffer s=device.buffer(source.buffer()),d=device.buffer(destination.buffer());
        if(source.length()>destination.length())throw new IllegalArgumentException("Copy exceeds destination slice");
        TextureSpec.range(s.size(),source.offset(),source.length());TextureSpec.range(d.size(),destination.offset(),source.length());
        if(s.mappings!=0||d.mappings!=0)throw new IllegalStateException("Copy uses mapped buffer");
        MetalNative.synchronize(device.context);
        org.lwjgl.system.libc.LibCString.nmemmove(MetalNative.bufferAddress(d.handle)+destination.offset(),MetalNative.bufferAddress(s.handle)+source.offset(),source.length());
    }
    public void writeToTexture(GpuTexture texture,ByteBuffer source,NativeImage.Format format,int mip,int layer,int x,int y,int width,int height){
        device.outsidePass();MetalTexture t=device.texture(texture);t.region(mip,layer,x,y,width,height);
        long bytes=Math.multiplyExact(Math.multiplyExact((long)width,height),format.components());
        if(bytes>source.remaining())throw new IllegalArgumentException("Texture upload buffer is too short");
        ByteBuffer direct=source;
        if(!source.isDirect()){direct=ByteBuffer.allocateDirect((int)bytes);direct.put(source.duplicate().limit(source.position()+(int)bytes)).flip();}
        MetalNative.writeTexture(device.context,t.handle,mip,layer,x,y,width,height,MemoryUtil.memAddress(direct),Math.multiplyExact(width,format.components()),format.components());
    }
    public void writeToTexture(GpuTexture texture,NativeImage source,int mip,int layer,int x,int y,int width,int height,int sourceX,int sourceY){
        device.outsidePass();MetalTexture t=device.texture(texture);t.region(mip,layer,x,y,width,height);
        if(source.isClosed())throw new IllegalStateException("NativeImage closed");
        TextureSpec.rectangle(source.getWidth(),source.getHeight(),sourceX,sourceY,width,height);
        int components=source.format().components(),stride=Math.multiplyExact(source.getWidth(),components);
        long offset=Math.addExact(Math.multiplyExact((long)sourceY,stride),Math.multiplyExact((long)sourceX,components));
        MetalNative.writeTexture(device.context,t.handle,mip,layer,x,y,width,height,Math.addExact(source.getPointer(),offset),stride,components);
    }
    public void copyTextureToBuffer(GpuTexture texture,GpuBuffer buffer,long offset,Runnable callback,int mip){copyTextureToBuffer(texture,buffer,offset,callback,mip,0,0,texture.getWidth(mip),texture.getHeight(mip));}
    public void copyTextureToBuffer(GpuTexture texture,GpuBuffer buffer,long offset,Runnable callback,int mip,int x,int y,int width,int height){
        device.outsidePass();MetalTexture t=device.texture(texture);MetalDevice.MetalBuffer b=device.buffer(buffer);t.region(mip,0,x,y,width,height);
        long bytes=Math.multiplyExact(Math.multiplyExact((long)width,height),t.getFormat().pixelSize());TextureSpec.range(b.size(),offset,bytes);
        if(b.mappings!=0)throw new IllegalStateException("Readback destination is mapped");
        MetalNative.readTexture(device.context,t.handle,mip,x,y,width,height,b.handle,offset);
        // The initial transfer path waits for completion; callbacks execute on the caller's game thread.
        callback.run();
    }
    public void copyTextureToTexture(GpuTexture source,GpuTexture destination,int mip,int destX,int destY,int sourceX,int sourceY,int width,int height){
        device.outsidePass();MetalTexture s=device.texture(source),d=device.texture(destination);
        if(s==d)throw new IllegalArgumentException("Self texture copy is not supported");
        if(s.getFormat()!=d.getFormat())throw new IllegalArgumentException("Texture copy format mismatch");
        s.region(mip,0,sourceX,sourceY,width,height);d.region(mip,0,destX,destY,width,height);
        MetalNative.copyTexture(device.context,s.handle,d.handle,mip,sourceX,sourceY,destX,destY,width,height);
    }
    public void presentTexture(GpuTextureView texture){device.outsidePass();MetalTextureView view=device.view(texture);MetalNative.presentTexture(device.context,view.handle);}
    public GpuFence createFence(){
        device.outsidePass();long handle=MetalNative.createFence(device.context);
        GpuFence fence=new GpuFence(){private long pointer=handle;
            public boolean awaitCompletion(long timeout){if(pointer==0)throw new IllegalStateException("Fence closed");if(timeout<0)throw new IllegalArgumentException("Negative fence timeout");return MetalNative.awaitFence(pointer,timeout);}
            public void close(){if(pointer!=0){MetalNative.release(pointer);pointer=0;device.retire(this,0);}}
        };return device.track(fence);
    }
    public GpuQuery timerQueryBegin(){throw new UnsupportedOperationException("Metal GPU timer queries not implemented");}
    public void timerQueryEnd(GpuQuery query){throw new UnsupportedOperationException("Metal GPU timer queries not implemented");}
}
