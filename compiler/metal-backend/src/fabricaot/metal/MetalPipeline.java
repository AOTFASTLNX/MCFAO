package fabricaot.metal;
import com.google.gson.*;
import com.mojang.blaze3d.pipeline.*;
import com.mojang.blaze3d.platform.*;
import com.mojang.blaze3d.vertex.*;
import java.util.*;

/** Immutable state key includes every pipeline field that affects rasterization or vertex fetch. */
final class MetalPipeline implements CompiledRenderPipeline,AutoCloseable {
    record Attribute(String name,VertexFormatElement.Type type,int count,boolean normalized,int offset) {}
    record Key(String program,List<Attribute> attributes,int stride,VertexFormat.Mode mode,ColorTargetState color,
               DepthStencilState depth,PolygonMode polygon,boolean cull,List<String> samplers,List<RenderPipeline.UniformDescription> uniforms) {
        static Key of(RenderPipeline pipeline){
            VertexFormat format=pipeline.getVertexFormat();List<Attribute> attributes=new ArrayList<>();
            for(VertexFormatElement element:format.getElements())attributes.add(new Attribute(format.getElementName(element),element.type(),element.count(),element.normalized(),format.getOffset(element)));
            return new Key(ShaderIndex.key(pipeline),List.copyOf(attributes),format.getVertexSize(),pipeline.getVertexFormatMode(),pipeline.getColorTargetState(),pipeline.getDepthStencilState(),pipeline.getPolygonMode(),pipeline.isCull(),List.copyOf(pipeline.getSamplers()),List.copyOf(pipeline.getUniforms()));
        }
    }
    final MetalDevice owner;
    final RenderPipeline source;
    final ShaderIndex.Program program;
    final Key key;
    long handle;
    MetalPipeline(MetalDevice owner,RenderPipeline source,ShaderIndex.Program program){
        this.owner=owner;this.source=source;this.program=program;this.key=Key.of(source);
        List<Integer> attributes=new ArrayList<>();
        for(JsonElement item:program.vertexInputs()){
            JsonObject input=item.getAsJsonObject();String name=input.get("name").getAsString();
            Attribute attribute=key.attributes().stream().filter(a->a.name().equals(name)).findFirst().orElseThrow(()->new IllegalArgumentException("Vertex format lacks "+name));
            attributes.add(input.get("location").getAsInt());attributes.add(attribute.type().ordinal());attributes.add(attribute.count());attributes.add(attribute.normalized()?1:0);attributes.add(attribute.offset());
        }
        ColorTargetState color=key.color();BlendFunction blend=color==null?null:color.blendFunction().orElse(null);DepthStencilState depth=key.depth();
        int mask=color==null?0:(color.writeRed()?1:0)|(color.writeGreen()?2:0)|(color.writeBlue()?4:0)|(color.writeAlpha()?8:0);
        int[] state={mask,blend==null?0:1,blend==null?1:factor(blend.sourceColor().name()),blend==null?0:factor(blend.destColor().name()),
            blend==null?1:factor(blend.sourceAlpha().name()),blend==null?0:factor(blend.destAlpha().name()),depth==null?0:depth.depthTest().ordinal(),
            depth!=null&&depth.writeDepth()?1:0,key.cull()?1:0,key.polygon()==PolygonMode.WIREFRAME?1:0,primitive(key.mode())};
        handle=MetalNative.createPipeline(owner.context,program.key(),attributes.stream().mapToInt(Integer::intValue).toArray(),key.stride(),state,depth==null?0:depth.depthBiasScaleFactor(),depth==null?0:depth.depthBiasConstant());
        if(handle==0)throw new IllegalStateException("Metal pipeline allocation failed: "+source.getLocation());
    }
    static int primitive(VertexFormat.Mode mode){return switch(mode){case POINTS->0;case DEBUG_LINES->1;case DEBUG_LINE_STRIP->2;case TRIANGLE_STRIP->4;case TRIANGLE_FAN->5;case TRIANGLES,QUADS,LINES->3;};}
    private static int factor(String name){return switch(name){
        case "ZERO"->0;case "ONE"->1;case "SRC_COLOR"->2;case "ONE_MINUS_SRC_COLOR"->3;case "SRC_ALPHA"->4;case "ONE_MINUS_SRC_ALPHA"->5;
        case "DST_COLOR"->6;case "ONE_MINUS_DST_COLOR"->7;case "DST_ALPHA"->8;case "ONE_MINUS_DST_ALPHA"->9;case "SRC_ALPHA_SATURATE"->10;
        case "CONSTANT_COLOR"->11;case "ONE_MINUS_CONSTANT_COLOR"->12;case "CONSTANT_ALPHA"->13;case "ONE_MINUS_CONSTANT_ALPHA"->14;
        default->throw new UnsupportedOperationException("Metal blend factor: "+name);
    };}
    public boolean isValid(){return handle!=0&&owner.context!=0;}
    public void close(){if(handle!=0){MetalNative.release(handle);handle=0;owner.retire(this,0);}}
}
