package fabricaot.graphics;
import java.nio.*;
import java.nio.file.Path;
import java.util.*;
import com.mojang.blaze3d.buffers.*;
import com.mojang.blaze3d.platform.*;
import com.mojang.blaze3d.systems.*;
import com.mojang.blaze3d.textures.*;
import fabricaot.metal.MetalBackend;

/** Real blaze3d resource API with GPU pixel roundtrips, then a first-party presentation pattern. */
public final class MetalResourceProbe {
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static void compare(CommandEncoder encoder,GpuDevice device,GpuTexture texture,int mip,byte[] expected){
        try(GpuBuffer output=device.createBuffer(()->"readback",GpuBuffer.USAGE_COPY_DST|GpuBuffer.USAGE_MAP_READ,expected.length)){
            int[] callbacks={0};encoder.copyTextureToBuffer(texture,output,0,()->callbacks[0]++,mip);
            check(callbacks[0]==1,"readback callback must run once after completion");
            try(GpuBuffer.MappedView view=encoder.mapBuffer(output,true,false)){
                check(view.data().isReadOnly(),"read-only map");
                for(int i=0;i<expected.length;i++)if(view.data().get(i)!=expected[i])throw new AssertionError("GPU pixel differs at byte "+i+" format="+texture.getFormat());
            }
        }
    }
    private static byte[] colorBytes(int count,int argb){byte[] data=new byte[count*4];for(int i=0;i<count;i++){data[i*4]=(byte)(argb>>16);data[i*4+1]=(byte)(argb>>8);data[i*4+2]=(byte)argb;data[i*4+3]=(byte)(argb>>24);}return data;}
    private static void resources(GpuDevice device){
        CommandEncoder encoder=device.createCommandEncoder();
        int bufferUsage=GpuBuffer.USAGE_COPY_DST|GpuBuffer.USAGE_COPY_SRC|GpuBuffer.USAGE_MAP_READ|GpuBuffer.USAGE_MAP_WRITE;
        try(GpuBuffer a=device.createBuffer(()->"source",bufferUsage,64);GpuBuffer b=device.createBuffer(()->"destination",bufferUsage,64)){
            byte[] pattern={9,17,33,65,99,111,127};encoder.writeToBuffer(a.slice(5,7),ByteBuffer.wrap(pattern));
            encoder.copyToBuffer(a.slice(5,7),b.slice(11,7));
            try(GpuBuffer.MappedView view=encoder.mapBuffer(b.slice(11,7),true,false)){for(int i=0;i<7;i++)check(view.data().get(i)==pattern[i],"unaligned buffer slice copy");}
        }
        for(TextureFormat format:new TextureFormat[]{TextureFormat.RGBA8,TextureFormat.RED8,TextureFormat.RED8I}){
            int usage=GpuTexture.USAGE_COPY_DST|GpuTexture.USAGE_COPY_SRC|GpuTexture.USAGE_TEXTURE_BINDING;
            try(GpuTexture input=device.createTexture("upload",usage,format,7,5,1,3);GpuTexture copied=device.createTexture("copy",usage,format,7,5,1,3)){
                for(int mip=0;mip<3;mip++){
                    int width=input.getWidth(mip),height=input.getHeight(mip);byte[] pixels=new byte[width*height*format.pixelSize()];
                    for(int i=0;i<pixels.length;i++)pixels[i]=(byte)(i*71+mip*19);
                    ByteBuffer upload=ByteBuffer.allocateDirect(pixels.length+9);upload.position(3);upload.put(pixels).flip().position(3);
                    encoder.writeToTexture(input,upload,format==TextureFormat.RGBA8?NativeImage.Format.RGBA:NativeImage.Format.LUMINANCE,mip,0,0,0,width,height);
                    encoder.copyTextureToTexture(input,copied,mip,0,0,0,0,width,height);compare(encoder,device,copied,mip,pixels);
                }
                try(GpuTextureView mip=device.createTextureView(input,1,1)){check(mip.getWidth(0)==3&&mip.getHeight(0)==2,"mip view size");}
            }
        }
        try(NativeImage source=new NativeImage(5,4,true);
            GpuTexture target=device.createTexture("NativeImage crop upload",GpuTexture.USAGE_COPY_DST|GpuTexture.USAGE_COPY_SRC,TextureFormat.RGBA8,3,2,1,1)){
            byte[] expected=new byte[3*2*4];
            for(int y=0;y<4;y++)for(int x=0;x<5;x++)source.setPixel(x,y,0xff000000|(x*31)<<16|(y*43)<<8|0x67);
            for(int y=0;y<2;y++)for(int x=0;x<3;x++){
                int argb=source.getPixel(x+1,y+1),i=(y*3+x)*4;
                expected[i]=(byte)(argb>>16);expected[i+1]=(byte)(argb>>8);expected[i+2]=(byte)argb;expected[i+3]=(byte)(argb>>24);
            }
            encoder.writeToTexture(target,source,0,0,0,0,3,2,1,1);compare(encoder,device,target,0,expected);
        }
        int attachmentUsage=GpuTexture.USAGE_COPY_SRC|GpuTexture.USAGE_COPY_DST|GpuTexture.USAGE_RENDER_ATTACHMENT;
        try(GpuTexture color=device.createTexture("color clear",attachmentUsage,TextureFormat.RGBA8,7,5,1,1);
            GpuTexture depth=device.createTexture("depth clear",attachmentUsage,TextureFormat.DEPTH32,7,5,1,1);
            GpuTextureView colorView=device.createTextureView(color);GpuTextureView depthView=device.createTextureView(depth)){
            encoder.clearColorTexture(color,0xff123456);compare(encoder,device,color,0,colorBytes(35,0xff123456));
            try(RenderPass pass=encoder.createRenderPass(()->"actual blaze3d clear pass",colorView,OptionalInt.of(0xffaa33cc),depthView,OptionalDouble.of(0.25))){
                pass.pushDebugGroup(()->"resource probe");pass.popDebugGroup();
                boolean rejected=false;try{encoder.clearColorTexture(color,0);}catch(IllegalStateException expected){rejected=true;}check(rejected,"transfer inside render pass was accepted");
            }
            compare(encoder,device,color,0,colorBytes(35,0xffaa33cc));
            byte[] depths=new byte[35*4];ByteBuffer view=ByteBuffer.wrap(depths).order(ByteOrder.nativeOrder());for(int i=0;i<35;i++)view.putFloat(0.25f);compare(encoder,device,depth,0,depths);
            encoder.clearDepthTexture(depth,1.0);try(GpuFence fence=encoder.createFence()){check(fence.awaitCompletion(2_000_000_000L),"GPU fence timeout");}
        }
        GpuTexture parent=device.createTexture("view lifetime",GpuTexture.USAGE_TEXTURE_BINDING,TextureFormat.RGBA8,4,4,1,1);
        GpuTextureView child=device.createTextureView(parent);parent.close();check(child.isClosed(),"view must reject use after parent close");child.close();
        System.out.println("METAL_RESOURCE_ROUNDTRIP_PASS formats=RGBA8,RED8,RED8I,DEPTH32 mips=3 unalignedRows=7 bufferSlices=unaligned fence=PASS");
    }
    public static void main(String[] args)throws Exception{
        RenderSystem.initRenderThread();GLX._initGlfw(new BackendOptions(false));MetalBackend backend=new MetalBackend();
        try(Window window=new Window(new WindowEventHandler(){public void resizeGui(){}public void cursorEntered(){}},new DisplayData(390,844,OptionalInt.empty(),OptionalInt.empty(),false),null,"Metal resource integration probe",backend)){
        GpuDevice device=backend.createDevice(window.handle(),null,null);
        try{
        RenderSystem.initRenderer(device);
        System.out.println("MINECRAFT_RENDER_SYSTEM_INITIALIZED backend="+device.getBackendName()+" device="+device.getRenderer());
        NativeImageProbe.run(Path.of("native-image-fixture.png"));
        resources(device);
        int usage=GpuTexture.USAGE_COPY_DST|GpuTexture.USAGE_COPY_SRC|GpuTexture.USAGE_TEXTURE_BINDING|GpuTexture.USAGE_RENDER_ATTACHMENT;
        int width=window.getWidth(),height=window.getHeight();
        try(GpuTexture image=device.createTexture("presentation pattern",usage,TextureFormat.RGBA8,width,height,1,1);GpuTextureView view=device.createTextureView(image)){
            byte[] data=new byte[width*height*4];int[] colors={0xffff3030,0xff30dd30,0xff3030ff,0xffffff30};
            for(int y=0;y<height;y++)for(int x=0;x<width;x++){int c=colors[(y>=height/2?2:0)+(x>=width/2?1:0)],i=(y*width+x)*4;data[i]=(byte)(c>>16);data[i+1]=(byte)(c>>8);data[i+2]=(byte)c;data[i+3]=(byte)255;}
            CommandEncoder encoder=device.createCommandEncoder();encoder.writeToTexture(image,ByteBuffer.wrap(data),NativeImage.Format.RGBA,0,0,0,0,width,height);
            encoder.presentTexture(view);device.presentFrame();System.out.println("METAL_RESOURCE_FRAME_READY (first-party resource fixture; game pipelines pending)");Thread.sleep(20000);
        }
        }finally{try{RenderSystem.getSamplerCache().close();}finally{device.close();}}
        }
        System.out.println("METAL_RESOURCE_PROBE_PASS");
    }
}
