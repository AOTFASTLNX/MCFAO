package fabricaot.metal;
import com.mojang.blaze3d.textures.GpuTextureView;
final class MetalTextureView extends GpuTextureView {
    final MetalTexture source;
    long handle;
    MetalTextureView(MetalTexture source,int base,int count,long handle){super(source,base,count);this.source=source;this.handle=handle;source.retainView();}
    void alive(){source.alive();if(handle==0)throw new IllegalStateException("Metal texture view closed");}
    public boolean isClosed(){return handle==0||source.isClosed();}
    public void close(){if(handle!=0){MetalNative.release(handle);handle=0;source.releaseView();source.owner.retire(this,0);}}
}
