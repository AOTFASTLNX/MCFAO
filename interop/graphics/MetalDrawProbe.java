package fabricaot.graphics;
import com.mojang.blaze3d.buffers.*;
import com.mojang.blaze3d.pipeline.*;
import com.mojang.blaze3d.platform.*;
import com.mojang.blaze3d.systems.*;
import com.mojang.blaze3d.textures.*;
import com.mojang.blaze3d.vertex.VertexFormat;
import fabricaot.metal.MetalBackend;
import net.minecraft.client.renderer.RenderPipelines;
import org.joml.Matrix4f;
import java.nio.*;
import java.util.*;

/** Real vanilla shaders, first-party geometry and GPU pixel assertions. This is not a menu. */
public final class MetalDrawProbe {
    private static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private static RenderPipeline pipeline(String name){return RenderPipelines.getStaticPipelines().stream().filter(p->p.getLocation().toString().equals("minecraft:pipeline/"+name)).findFirst().orElseThrow();}
    private static ByteBuffer matrix(int bytes){ByteBuffer b=ByteBuffer.allocateDirect(bytes).order(ByteOrder.nativeOrder());for(int i=0;i<4;i++)b.putFloat(i*20,1);return b;}
    private static ByteBuffer dynamic(){ByteBuffer b=matrix(160);for(int i=0;i<4;i++){b.putFloat(64+i*4,1);b.putFloat(96+i*20,1);}return b;}
    private static ByteBuffer vertices(boolean padded,boolean textured){
        int stride=textured?24:16;ByteBuffer b=ByteBuffer.allocateDirect((padded?8:4)*stride).order(ByteOrder.nativeOrder());if(padded)b.position(4*stride);
        float[][] points={{-1,-1,0,1},{1,-1,1,1},{1,1,1,0},{-1,1,0,0}};
        for(float[] p:points){b.putFloat(p[0]).putFloat(p[1]).putFloat(0.5f);if(textured)b.putFloat(p[2]).putFloat(p[3]);b.putInt(textured?-1:0xff00ff00);}
        b.flip();return b;
    }
    private static ByteBuffer indices(boolean padded){ByteBuffer b=ByteBuffer.allocateDirect((padded?8:6)*2).order(ByteOrder.nativeOrder());if(padded)b.putShort((short)0).putShort((short)0);for(int i:new int[]{0,1,2,2,3,0})b.putShort((short)i);return b.flip();}
    private static byte[] read(CommandEncoder encoder,GpuDevice device,GpuTexture target){
        byte[] bytes=new byte[64*64*4];try(GpuBuffer buffer=device.createBuffer(()->"draw readback",GpuBuffer.USAGE_COPY_DST|GpuBuffer.USAGE_MAP_READ,bytes.length)){
            encoder.copyTextureToBuffer(target,buffer,0,()->{},0);try(GpuBuffer.MappedView mapped=encoder.mapBuffer(buffer,true,false)){mapped.data().get(bytes);}
        }return bytes;
    }
    private static void pixel(byte[] data,int x,int y,int r,int g,int b,int a){int i=(y*64+x)*4;int[] expected={r,g,b,a};for(int c=0;c<4;c++)check(Math.abs(Byte.toUnsignedInt(data[i+c])-expected[c])<=1,"Pixel "+x+","+y+" component "+c+" actual="+Byte.toUnsignedInt(data[i+c])+" expected="+expected[c]);}
    private static void bindings(RenderPass pass,GpuBuffer projection,GpuBuffer transforms,GpuTextureView texture,GpuSampler sampler,GpuBuffer vertices,GpuBuffer indices){
        pass.setUniform("Projection",projection);pass.setUniform("DynamicTransforms",transforms);pass.bindTexture("Sampler0",texture,sampler);pass.setVertexBuffer(0,vertices);pass.setIndexBuffer(indices,VertexFormat.IndexType.SHORT);
    }
    private static void spriteAtlas(CommandEncoder encoder,GpuDevice device,GpuTexture target,GpuTextureView view,
                                    GpuTextureView depth,GpuTextureView sprite,GpuSampler sampler){
        // Match TextureAtlasSprite's GL-style projection at an asymmetric atlas location.
        ByteBuffer packed=ByteBuffer.allocateDirect(144).order(ByteOrder.nativeOrder());
        Std140Builder.intoBuffer(packed).putMat4f(new Matrix4f().ortho2D(0,64,0,64))
            .putMat4f(new Matrix4f().translation(8,12,0).scale(24,20,1))
            .putFloat(0).putFloat(0).putInt(0);
        packed.position(0);
        try(GpuBuffer uniform=device.createBuffer(()->"SpriteAnimationInfo",GpuBuffer.USAGE_UNIFORM,packed)){
            try(RenderPass pass=encoder.createRenderPass(()->"sprite atlas rows",view,OptionalInt.of(0xff000000),depth,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("animate_sprite_blit"));pass.setUniform("SpriteAnimationInfo",uniform);
                pass.bindTexture("Sprite",sprite,sampler);pass.draw(0,6);
            }
            byte[] pixels=read(encoder,device,target);
            pixel(pixels,14,17,255,0,0,128);pixel(pixels,26,17,0,255,0,255);
            pixel(pixels,14,27,0,0,255,255);pixel(pixels,26,27,255,255,0,255);
            pixel(pixels,14,47,0,0,0,255);
        }
        System.out.println("METAL_SPRITE_ATLAS_ORIGIN_PASS");
    }
    private static void lightmap(CommandEncoder encoder,GpuDevice device,GpuTexture target,GpuTextureView view,
                                 GpuTextureView depth){
        ByteBuffer packed=ByteBuffer.allocateDirect(96).order(ByteOrder.nativeOrder());
        Std140Builder.intoBuffer(packed).putFloat(0.8f).putFloat(0).putFloat(0).putFloat(0).putFloat(0).putFloat(0)
            .putVec3(1,1,1).putVec3(1,1,1).putVec3(0.1f,0.1f,0.1f).putVec3(0,0,0);
        packed.position(0);
        try(GpuBuffer uniform=device.createBuffer(()->"LightmapInfo",GpuBuffer.USAGE_UNIFORM,packed)){
            try(RenderPass pass=encoder.createRenderPass(()->"sky light rows",view,OptionalInt.of(0xff000000),depth,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("lightmap"));pass.setUniform("LightmapInfo",uniform);pass.draw(0,3);
            }
            byte[] pixels=read(encoder,device,target);
            pixel(pixels,32,1,26,26,26,255);
            pixel(pixels,32,62,230,230,230,255);
        }
        System.out.println("METAL_LIGHTMAP_SKY_ROWS_PASS");
    }
    private static void rectangleClear(CommandEncoder encoder,GpuDevice device,GpuTexture target,GpuTexture depth){
        encoder.clearColorAndDepthTextures(target,0xff102030,depth,0.75);
        encoder.clearColorAndDepthTextures(target,0x80f08010,depth,0.25,5,7,13,17);
        byte[] colors=read(encoder,device,target);
        pixel(colors,7,45,240,128,16,128);
        pixel(colors,7,10,16,32,48,255);
        pixel(colors,25,45,16,32,48,255);
        ByteBuffer depths=ByteBuffer.wrap(read(encoder,device,depth)).order(ByteOrder.nativeOrder());
        check(depths.getFloat((45*64+7)*4)==0.25f,"rectangle depth");
        check(depths.getFloat((10*64+7)*4)==0.75f,"preserved depth");
        System.out.println("METAL_SCISSORED_COLOR_DEPTH_CLEAR_PASS");
    }
    private static void guiTextFog(CommandEncoder encoder, GpuDevice device, GpuTexture target, GpuTextureView view,
                                   GpuTextureView depth, GpuTextureView sample, GpuSampler sampler,
                                   GpuBuffer projection, GpuBuffer transforms, GpuBuffer index) {
        ByteBuffer text = ByteBuffer.allocateDirect(4 * 28).order(ByteOrder.nativeOrder());
        for (float[] point : new float[][]{{-1,-1,0,1},{1,-1,1,1},{1,1,1,0},{-1,1,0,0}}) {
            text.putFloat(point[0]).putFloat(point[1]).putFloat(0.5f).putInt(-1);
            text.putFloat(point[2]).putFloat(point[3]).putShort((short) 240).putShort((short) 240);
        }
        text.flip();
        // Match the game's 40-byte payload. The text shader's Metal struct occupies 48 bytes.
        ByteBuffer fogData = ByteBuffer.allocateDirect(40).order(ByteOrder.nativeOrder());
        Std140Builder.intoBuffer(fogData).putVec4(0, 0, 1, 1)
            .putFloat(0).putFloat(1).putFloat(0).putFloat(1).putFloat(1).putFloat(1);
        fogData.rewind();
        try (GpuBuffer vertex = device.createBuffer(() -> "gui text vertices", GpuBuffer.USAGE_VERTEX, text);
             GpuBuffer fog = device.createBuffer(() -> "Fog", GpuBuffer.USAGE_UNIFORM, fogData)) {
            check(fog.size() == 40, "Fog logical size must remain 40 bytes");
            try (RenderPass pass = encoder.createRenderPass(() -> "gui text Fog", view, OptionalInt.of(0xff000000), depth, OptionalDouble.of(1))) {
                pass.setPipeline(pipeline("gui_text"));
                bindings(pass, projection, transforms, sample, sampler, vertex, index);
                pass.bindTexture("Sampler2", sample, sampler);
                pass.setUniform("Fog", fog);
                pass.drawIndexed(0, 0, 6, 1);
            }
            pixel(read(encoder, device, target), 48, 48, 0, 0, 255, 255);
        }
        System.out.println("METAL_GUI_TEXT_FOG_PASS");
    }
    private static void run(GpuDevice device)throws Exception{
        CommandEncoder encoder=device.createCommandEncoder();int attachmentUsage=GpuTexture.USAGE_RENDER_ATTACHMENT|GpuTexture.USAGE_COPY_SRC|GpuTexture.USAGE_COPY_DST;
        try(GpuTexture target=device.createTexture("vanilla shader result",attachmentUsage|GpuTexture.USAGE_TEXTURE_BINDING,TextureFormat.RGBA8,64,64,1,1);GpuTexture depth=device.createTexture("draw depth",attachmentUsage,TextureFormat.DEPTH32,64,64,1,1);
            GpuTextureView view=device.createTextureView(target);GpuTextureView depthView=device.createTextureView(depth);
            GpuTexture sample=device.createTexture("first-party RGBA pixels",GpuTexture.USAGE_COPY_DST|GpuTexture.USAGE_TEXTURE_BINDING,TextureFormat.RGBA8,2,2,1,1);GpuTextureView sampleView=device.createTextureView(sample);
            GpuSampler sampler=device.createSampler(AddressMode.CLAMP_TO_EDGE,AddressMode.CLAMP_TO_EDGE,FilterMode.NEAREST,FilterMode.NEAREST,1,OptionalDouble.empty());
            GpuBuffer projection=device.createBuffer(()->"Projection",GpuBuffer.USAGE_UNIFORM,matrix(64));GpuBuffer transforms=device.createBuffer(()->"DynamicTransforms",GpuBuffer.USAGE_UNIFORM,dynamic());
            GpuBuffer vertex=device.createBuffer(()->"quad",GpuBuffer.USAGE_VERTEX,vertices(false,true));GpuBuffer index=device.createBuffer(()->"quad indices",GpuBuffer.USAGE_INDEX,indices(false));
            GpuBuffer paddedVertex=device.createBuffer(()->"padded quad",GpuBuffer.USAGE_VERTEX,vertices(true,true));GpuBuffer paddedIndex=device.createBuffer(()->"padded indices",GpuBuffer.USAGE_INDEX,indices(true));
            GpuBuffer fan=device.createBuffer(()->"fan",GpuBuffer.USAGE_VERTEX,vertices(false,false))){
            for(RenderPipeline pipeline:RenderPipelines.getStaticPipelines()){
                check(device.precompilePipeline(pipeline).isValid(),"Invalid vanilla pipeline "+pipeline.getLocation());
                try(RenderPass pass=encoder.createRenderPass(()->"PSO warmup",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){pass.setPipeline(pipeline);}
            }
            System.out.println("VANILLA_METAL_PSO_PASS count="+RenderPipelines.getStaticPipelines().size());
            byte[] rgba={(byte)255,0,0,(byte)128,0,(byte)255,0,(byte)255,0,0,(byte)255,(byte)255,(byte)255,(byte)255,0,(byte)255};
            encoder.writeToTexture(sample,ByteBuffer.wrap(rgba),NativeImage.Format.RGBA,0,0,0,0,2,2);
            spriteAtlas(encoder,device,target,view,depthView,sampleView,sampler);
            lightmap(encoder,device,target,view,depthView);
            rectangleClear(encoder,device,target,depth);
            guiTextFog(encoder,device,target,view,depthView,sampleView,sampler,projection,transforms,index);
            for(boolean opaque:new boolean[]{false,true}){
                try(RenderPass pass=encoder.createRenderPass(()->"vanilla quad",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){
                    pass.setPipeline(pipeline(opaque?"gui_opaque_textured_background":"gui_textured"));bindings(pass,projection,transforms,sampleView,sampler,vertex,index);pass.drawIndexed(0,0,6,1);
                }
                byte[] data=read(encoder,device,target);pixel(data,16,16,opaque?255:128,0,0,opaque?128:255);pixel(data,48,16,0,255,0,255);pixel(data,16,48,0,0,255,255);pixel(data,48,48,255,255,0,255);
            }
            try(RenderPass pass=encoder.createRenderPass(()->"base vertex and instancing",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("gui_opaque_textured_background"));bindings(pass,projection,transforms,sampleView,sampler,paddedVertex,paddedIndex);pass.drawIndexed(4,2,6,2);
            }
            pixel(read(encoder,device,target),16,16,255,0,0,128);
            try(RenderPass pass=encoder.createRenderPass(()->"bottom-left scissor",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("gui_textured"));bindings(pass,projection,transforms,sampleView,sampler,vertex,index);pass.enableScissor(0,0,32,32);pass.drawIndexed(0,0,6,1);
            }
            byte[] clipped=read(encoder,device,target);pixel(clipped,16,16,0,0,0,255);pixel(clipped,16,48,0,0,255,255);
            try(RenderPass pass=encoder.createRenderPass(()->"vanilla triangle fan",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("debug_triangle_fan"));pass.setUniform("Projection",projection);pass.setUniform("DynamicTransforms",transforms);pass.setVertexBuffer(0,fan);pass.draw(0,4);
            }
            pixel(read(encoder,device,target),32,32,0,255,0,255);
            try(RenderPass pass=encoder.createRenderPass(()->"final vanilla shader frame",view,OptionalInt.of(0xff000000),depthView,OptionalDouble.of(1))){
                pass.setPipeline(pipeline("gui_textured"));bindings(pass,projection,transforms,sampleView,sampler,vertex,index);pass.drawIndexed(0,0,6,1);
            }
            System.out.println("METAL_VANILLA_DRAW_PASS indexed/normalized-vertex/UBO/texture/blend/cache/scissor/baseVertex/instancing/fan=PASS");
            encoder.presentTexture(view);device.presentFrame();Thread.sleep(20000);
        }
    }
    public static void main(String[] args)throws Exception{
        RenderSystem.initRenderThread();GLX._initGlfw(new BackendOptions(false));MetalBackend backend=new MetalBackend();
        try(Window window=new Window(new WindowEventHandler(){public void resizeGui(){}public void cursorEntered(){}},new DisplayData(390,844,OptionalInt.empty(),OptionalInt.empty(),false),null,"Vanilla shader draw diagnostics",backend)){
            GpuDevice device=backend.createDevice(window.handle(),null,null);
            try{RenderSystem.initRenderer(device);System.out.println("MINECRAFT_RENDER_SYSTEM_INITIALIZED backend="+device.getBackendName()+" device="+device.getRenderer());run(device);}
            finally{try{RenderSystem.getSamplerCache().close();}finally{device.close();}}
        }
        System.out.println("METAL_DRAW_PROBE_PASS");
    }
}
