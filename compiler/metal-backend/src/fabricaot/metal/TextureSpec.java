package fabricaot.metal;
import com.mojang.blaze3d.textures.TextureFormat;
/** Checked allocation and transfer arithmetic. Bounds are independent of the Metal driver. */
final class TextureSpec {
    static long byteSize(TextureFormat format,int width,int height,int layers,int mips,int usage){
        if(width<=0||height<=0||width>16384||height>16384||layers<=0||layers>2048||mips<=0||mips>32-Integer.numberOfLeadingZeros(Math.max(width,height)))
            throw new IllegalArgumentException("Invalid Metal texture dimensions/mip count");
        if((usage&16)!=0&&(width!=height||layers%6!=0))throw new IllegalArgumentException("Cubemap requires square faces in groups of six");
        long bytes=0;
        for(int mip=0;mip<mips;mip++)bytes=Math.addExact(bytes,Math.multiplyExact(Math.multiplyExact((long)Math.max(1,width>>mip),Math.max(1,height>>mip)),Math.multiplyExact((long)layers,format.pixelSize())));
        return bytes;
    }
    static int formatId(TextureFormat format){return switch(format){case RGBA8->0;case RED8->1;case RED8I->2;case DEPTH32->3;};}
    static void rectangle(int fullWidth,int fullHeight,int x,int y,int width,int height){
        if(x<0||y<0||width<=0||height<=0||width>fullWidth||height>fullHeight||x>fullWidth-width||y>fullHeight-height)
            throw new IllegalArgumentException("Texture transfer rectangle out of bounds");
    }
    static void range(long capacity,long offset,long length){
        if(offset<0||length<0||length>capacity||offset>capacity-length)throw new IllegalArgumentException("Buffer range out of bounds");
    }
}
