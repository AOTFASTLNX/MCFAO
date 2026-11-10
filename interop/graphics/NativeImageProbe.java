package fabricaot.graphics;
import com.mojang.blaze3d.platform.NativeImage;
import java.nio.*;
import java.nio.file.*;
import java.util.*;
import org.lwjgl.stb.*;
import org.lwjgl.system.*;

/** First-party pixels through real Minecraft PNG write/read/resize; no proprietary assets. */
public final class NativeImageProbe {
    private static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    public static void run(Path path)throws Exception {
        int[] colors={0xff123456,0x804488cc,0x00112233,0xffaabbcc,0xff102030,0xffcc4411};
        try(NativeImage image=new NativeImage(3,2,true)){
            for(int i=0;i<colors.length;i++)image.setPixel(i%3,i/3,colors[i]);
            image.writeToFile(path);
        }
        byte[] png=Files.readAllBytes(path);
        check(png.length>40,"PNG callback wrote no data");
        try(NativeImage decoded=NativeImage.read(png)){
            check(decoded.getWidth()==3&&decoded.getHeight()==2,"PNG dimensions");
            for(int i=0;i<colors.length;i++)check(decoded.getPixel(i%3,i/3)==colors[i],"PNG color/alpha mismatch "+i);
        }
        try(NativeImage source=new NativeImage(4,3,true);NativeImage scaled=new NativeImage(7,5,true)){
            source.fillRect(0,0,4,3,0xff336699);
            source.resizeSubRectTo(1,1,2,2,scaled);
            for(int y=0;y<5;y++)for(int x=0;x<7;x++)check(scaled.getPixel(x,y)==0xff336699,"Resize stride/subrectangle");
            try{STBImageResize.nstbir_resize_uint8_linear(source.getPointer(),0,2,0,scaled.getPointer(),7,5,0,4);throw new AssertionError("Invalid resize accepted");}
            catch(IllegalArgumentException expected){}
            try(STBIWriteCallback callback=new STBIWriteCallback(){public void invoke(long user,long data,int size){throw new IllegalStateException("callback fixture");}}){
                try{STBImageWrite.nstbi_write_png_to_func(callback.address(),0,4,3,4,source.getPointer(),0);throw new AssertionError("Callback exception swallowed");}
                catch(IllegalStateException expected){check(expected.getMessage().equals("callback fixture"),"Wrong callback exception");}
            }
        }
        try(MemoryStack stack=MemoryStack.stackPush()){
            ByteBuffer invalid=stack.calloc(16);IntBuffer x=stack.mallocInt(1),y=stack.mallocInt(1),n=stack.mallocInt(1);
            check(STBImage.stbi_load_from_memory(invalid,x,y,n,4)==null,"Corrupt image accepted");
            check(STBImage.stbi_failure_reason()!=null,"Missing decode failure reason");
        }
        List<STBIWriteCallback> callbacks=new ArrayList<>();
        try{
            for(int i=0;i<32;i++)callbacks.add(new STBIWriteCallback(){public void invoke(long user,long data,int size){}});
            try(STBIWriteCallback excess=new STBIWriteCallback(){public void invoke(long user,long data,int size){}}){throw new AssertionError("STB callback capacity ignored");}
            catch(IllegalStateException expected){check(expected.getMessage().contains("exhausted"),"Wrong callback capacity failure");}
        }finally{for(STBIWriteCallback callback:callbacks)callback.free();}
        System.out.println("MINECRAFT_NATIVE_IMAGE_PASS png=write/read RGBA/alpha=exact resize=subrectangle callback=static/exception/capacity corrupt=reject");
    }
    public static void main(String[] args)throws Exception {run(Path.of("native-image-fixture.png"));}
}
