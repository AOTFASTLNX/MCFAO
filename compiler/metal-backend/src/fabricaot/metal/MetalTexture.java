package fabricaot.metal;
import com.mojang.blaze3d.textures.*;
final class MetalTexture extends GpuTexture {
    final MetalDevice owner;
    final long allocationBytes;
    long handle;
    private int views;
    MetalTexture(MetalDevice owner,long handle,int usage,String label,TextureFormat format,int width,int height,int layers,int mips,long bytes){
        super(usage,label,format,width,height,layers,mips);this.owner=owner;this.handle=handle;this.allocationBytes=bytes;
    }
    void alive(){owner.alive();if(handle==0)throw new IllegalStateException("Metal texture closed");}
    void region(int mip,int layer,int x,int y,int width,int height){
        alive();if(mip<0||mip>=getMipLevels()||layer<0||layer>=getDepthOrLayers())throw new IllegalArgumentException("Texture mip/layer out of bounds");
        TextureSpec.rectangle(getWidth(mip),getHeight(mip),x,y,width,height);
    }
    public boolean isClosed(){return handle==0;}
    void retainView(){alive();views++;}
    void releaseView(){if(--views==0&&handle==0)owner.refund(allocationBytes);}
    public void close(){if(handle!=0){MetalNative.release(handle);handle=0;owner.retire(this,views==0?allocationBytes:0);}}
}
