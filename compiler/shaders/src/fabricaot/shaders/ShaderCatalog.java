package fabricaot.shaders;
import com.google.gson.*;
import com.mojang.blaze3d.pipeline.RenderPipeline;
import com.mojang.blaze3d.preprocessor.GlslPreprocessor;
import com.mojang.blaze3d.vertex.*;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.client.renderer.ShaderDefines;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Build-only inventory using the real vanilla pipeline declarations and preprocessor. */
public final class ShaderCatalog {
    private static final Gson JSON=new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
    private static String hash(byte[] bytes)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}
    private static String hash(String text)throws Exception{return hash(text.getBytes(StandardCharsets.UTF_8));}
    public static String variantKey(String vertex,String fragment,ShaderDefines defines)throws Exception{
        return hash(vertex+"\n"+fragment+"\n"+new Gson().toJson(new TreeMap<>(defines.values()))+"\n"+new Gson().toJson(new TreeSet<>(defines.flags())));
    }
    private static String asset(String identifier,String suffix){
        String[] id=identifier.split(":",2);String namespace=id.length==1?"minecraft":id[0],path=id.length==1?id[0]:id[1];
        if(!namespace.matches("[a-z0-9_.-]+")||path.startsWith("/")||Arrays.asList(path.split("/")).contains(".."))throw new IllegalArgumentException("Invalid shader identifier: "+identifier);
        return "assets/"+namespace+"/shaders/"+path+suffix;
    }
    private static String read(ZipFile jar,String name)throws Exception{
        ZipEntry entry=jar.getEntry(name);if(entry==null)throw new IllegalArgumentException("Missing shader resource: "+name);
        return new String(jar.getInputStream(entry).readAllBytes(),StandardCharsets.UTF_8);
    }
    private static String process(ZipFile jar,String name,ShaderDefines defines)throws Exception{
        Set<String> imported=new HashSet<>();
        GlslPreprocessor preprocessor=new GlslPreprocessor(){
            public String applyImport(boolean relative,String value){
                try{
                    String resolved;
                    if(relative){
                        Path p=Path.of(name).getParent().resolve(value).normalize();resolved=p.toString().replace('\\','/');
                        if(!resolved.startsWith("assets/"))throw new IllegalArgumentException("Escaping relative shader import: "+value);
                    }else{
                        String[] id=value.split(":",2);resolved="assets/"+(id.length==1?"minecraft":id[0])+"/shaders/include/"+(id.length==1?id[0]:id[1]);
                        if(resolved.contains("..")||value.startsWith("/"))throw new IllegalArgumentException("Escaping shader include: "+value);
                    }
                    return imported.add(resolved)?read(jar,resolved):null;
                }catch(Exception error){throw new IllegalArgumentException("Shader import failed: "+value,error);}
            }
        };
        return GlslPreprocessor.injectDefines(String.join("",preprocessor.process(read(jar,name))),defines);
    }
    private static String program(ZipFile jar,Path out,String vertex,String fragment,ShaderDefines defines,Set<String> emitted,List<Map<String,Object>> programs)throws Exception{
        String key=variantKey(vertex,fragment,defines);
        if(emitted.add(key)){
            Path folder=out.resolve("variants/"+key);Files.createDirectories(folder);
            String vs=process(jar,asset(vertex,".vsh"),defines),fs=process(jar,asset(fragment,".fsh"),defines);
            Files.writeString(folder.resolve("shader.vert"),vs);Files.writeString(folder.resolve("shader.frag"),fs);
            Map<String,Object> entry=new LinkedHashMap<>();entry.put("key",key);entry.put("vertex",vertex);entry.put("fragment",fragment);
            entry.put("values",new TreeMap<>(defines.values()));entry.put("flags",new TreeSet<>(defines.flags()));
            entry.put("vertexSHA256",hash(vs));entry.put("fragmentSHA256",hash(fs));programs.add(entry);
        }
        return key;
    }
    public static void main(String[] args)throws Exception{
        if(args.length!=2)throw new IllegalArgumentException("client.jar output-directory");
        Path out=Path.of(args[1]);Files.createDirectories(out);
        List<Map<String,Object>> programs=new ArrayList<>(),pipelines=new ArrayList<>(),postPasses=new ArrayList<>();Map<String,String> raw=new TreeMap<>();Set<String> emitted=new HashSet<>();
        try(ZipFile jar=new ZipFile(args[0])){
            for(ZipEntry entry:Collections.list(jar.entries())){
                String name=entry.getName();
                if(!name.startsWith("assets/minecraft/shaders/")||!name.endsWith(".vsh")&&!name.endsWith(".fsh")&&!name.endsWith(".glsl"))continue;
                raw.put(name,hash(read(jar,name)));
            }
            for(RenderPipeline p:RenderPipelines.getStaticPipelines().stream().sorted(Comparator.comparing(v->v.getLocation().toString())).toList()){
                String vertex=p.getVertexShader().toString(),fragment=p.getFragmentShader().toString(),key=program(jar,out,vertex,fragment,p.getShaderDefines(),emitted,programs);
                VertexFormat format=p.getVertexFormat();List<Map<String,Object>> attributes=new ArrayList<>();
                for(VertexFormatElement e:format.getElements())attributes.add(Map.of("name",format.getElementName(e),"type",e.type().name(),"count",e.count(),"normalized",e.normalized(),"offset",format.getOffset(e)));
                List<Map<String,Object>> uniforms=new ArrayList<>();
                for(RenderPipeline.UniformDescription u:p.getUniforms()){
                    Map<String,Object> uniform=new LinkedHashMap<>();uniform.put("name",u.name());uniform.put("type",u.type().name());uniform.put("format",u.textureFormat()==null?null:u.textureFormat().name());uniforms.add(uniform);
                }
                Map<String,Object> pipeline=new LinkedHashMap<>();pipeline.put("id",p.getLocation().toString());pipeline.put("program",key);pipeline.put("samplers",p.getSamplers());pipeline.put("uniforms",uniforms);
                pipeline.put("attributes",attributes);pipeline.put("stride",format.getVertexSize());pipeline.put("mode",p.getVertexFormatMode().name());
                pipeline.put("colorTarget",p.getColorTargetState()==null?null:p.getColorTargetState().toString());pipeline.put("depthStencil",p.getDepthStencilState()==null?null:p.getDepthStencilState().toString());pipeline.put("polygon",p.getPolygonMode().name());pipeline.put("cull",p.isCull());pipelines.add(pipeline);
            }
            for(ZipEntry entry:Collections.list(jar.entries()))if(entry.getName().startsWith("assets/minecraft/post_effect/")&&entry.getName().endsWith(".json")){
                JsonArray passes=JsonParser.parseString(read(jar,entry.getName())).getAsJsonObject().getAsJsonArray("passes");int index=0;
                for(JsonElement item:passes){
                    JsonObject pass=item.getAsJsonObject();if(pass.has("defines"))throw new IllegalArgumentException("Unexpected post shader define schema");
                    String vertex=pass.get("vertex_shader").getAsString(),fragment=pass.get("fragment_shader").getAsString();
                    String key=program(jar,out,vertex,fragment,ShaderDefines.EMPTY,emitted,programs);
                    postPasses.add(Map.of("source",entry.getName(),"pass",index++,"program",key));
                }
            }
            // Every executable source also gets a define-free compile candidate, separately from real pipeline variants.
            for(String name:raw.keySet())if(name.endsWith(".vsh")||name.endsWith(".fsh")){
                Path target=out.resolve("standalone/"+name);Files.createDirectories(target.getParent());Files.writeString(target,process(jar,name,ShaderDefines.EMPTY));
            }
        }
        Map<String,Object> result=new LinkedHashMap<>();result.put("scope","vanilla static pipelines, all bundled post-chain passes and executable source files; excludes replacement resource packs/Mods");result.put("rawSources",raw);result.put("programs",programs);result.put("pipelines",pipelines);result.put("postPasses",postPasses);
        Files.writeString(out.resolve("catalog.json"),JSON.toJson(result)+"\n");System.out.println("SHADER_CATALOG_PASS sources="+raw.size()+" pipelines="+pipelines.size()+" programs="+programs.size());
    }
}
