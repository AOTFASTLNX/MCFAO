package fabricaot.metal;
import com.google.gson.*;
import com.mojang.blaze3d.pipeline.RenderPipeline;
import com.mojang.blaze3d.preprocessor.GlslPreprocessor;
import com.mojang.blaze3d.shaders.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Read-only index generated from the user's owned vanilla shader corpus. */
final class ShaderIndex {
    record Binding(String name,int stage,String kind,int index,int samplerIndex,long bytes,boolean bufferTexture) {}
    record Program(String key,List<Binding> bindings,JsonArray vertexInputs,JsonObject metadata) {}
    private final Map<String,JsonObject> programs=new HashMap<>();
    private final Set<String> verifiedSources=new HashSet<>();
    private final Path directory;
    ShaderIndex(){
        String nativeDirectory=System.getProperty("org.lwjgl.librarypath");
        if(nativeDirectory==null)throw new IllegalStateException("Missing signed graphics directory");
        directory=Path.of(nativeDirectory).resolve("fabricaot-shaders");
        try{
            JsonObject root=JsonParser.parseString(Files.readString(directory.resolve("index.json"))).getAsJsonObject();
            if(root.get("schema").getAsInt()!=1)throw new IllegalStateException("Unsupported shader index schema");
            for(JsonElement item:root.getAsJsonArray("programs")){
                JsonObject entry=item.getAsJsonObject();String key=entry.get("key").getAsString();
                if(!key.matches("[0-9a-f]{64}")||!entry.get("status").getAsString().equals("TRANSLATED")||programs.put(key,entry)!=null)throw new IllegalStateException("Invalid precompiled shader entry");
            }
        }catch(Exception error){throw new IllegalStateException("Precompiled shader bundle unavailable: "+directory,error);}
    }
    static String hash(String data){return hash(data.getBytes(StandardCharsets.UTF_8));}
    private static String hash(byte[] bytes){
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}
        catch(Exception error){throw new IllegalStateException("SHA-256 unavailable",error);}
    }
    static String key(RenderPipeline pipeline){
        Gson json=new Gson();return hash(pipeline.getVertexShader()+"\n"+pipeline.getFragmentShader()+"\n"+json.toJson(new TreeMap<>(pipeline.getShaderDefines().values()))+"\n"+json.toJson(new TreeSet<>(pipeline.getShaderDefines().flags())));
    }
    void clearSourceValidation(){verifiedSources.clear();}
    Program program(RenderPipeline pipeline,ShaderSource source,boolean allowPreloadedSource){
        String key=key(pipeline);JsonObject entry=programs.get(key);
        if(entry==null){
            // Naming the pipeline here is the difference between "some variant is missing" and a
            // rebuild target; the key alone is unreadable in a log.
            System.err.println("[MCFAO_SHADER] no bundle entry for "+pipeline.getLocation()+" vertex="+pipeline.getVertexShader()+" fragment="+pipeline.getFragmentShader());
            throw new UnsupportedOperationException("Rebuild required for shader variant: "+pipeline.getLocation()+" "+key);
        }
        try{
            if(!hash(Files.readAllBytes(directory.resolve(key+".metallib"))).equals(entry.get("metallibSHA256").getAsString()))throw new IllegalStateException("Precompiled Metal library fingerprint changed: "+key);
            if(source!=null){
                String vertex=source.get(pipeline.getVertexShader(),ShaderType.VERTEX);
                String fragment=source.get(pipeline.getFragmentShader(),ShaderType.FRAGMENT);
                // The splash draws before ShaderManager's initial reload. It can reuse only a
                // program already checked through GameRenderer's explicit vanilla preload.
                if(!(vertex==null&&fragment==null&&allowPreloadedSource&&verifiedSources.contains(key))){
                    // Only reached when a pipeline draws before its sources exist and the preload
                    // never verified this program - the two conditions are easy to confuse, so the
                    // line reports both facts next to the pipeline being drawn.
                    if(vertex==null)System.err.println("[MCFAO_SHADER] missing source "+pipeline.getLocation()+" vertex="+pipeline.getVertexShader()+" fragment="+pipeline.getFragmentShader()+" verified="+verifiedSources.contains(key)+" allow="+allowPreloadedSource);
                    verifyStage(pipeline,entry,"vertex",vertex);
                    verifyStage(pipeline,entry,"fragment",fragment);
                    verifiedSources.add(key);
                }
            }
        }catch(java.io.IOException error){throw new IllegalStateException("Cannot read precompiled shader: "+key,error);}
        List<Binding> bindings=new ArrayList<>();JsonArray inputs=new JsonArray();JsonObject stages=entry.getAsJsonObject("stages");
        for(int stage=0;stage<2;stage++)for(JsonElement item:stages.getAsJsonObject(stage==0?"vertex":"fragment").getAsJsonArray("resources")){
            JsonObject resource=item.getAsJsonObject();String kind=resource.get("kind").getAsString();
            if(stage==0&&kind.equals("input"))inputs.add(resource);
            if(!resource.has("metalIndex"))continue;
            long index=resource.get("metalIndex").getAsLong();if(index==0xffffffffL)continue;
            if(index>=30||!kind.equals("uniform")&&!kind.equals("texture"))throw new UnsupportedOperationException("Unsupported Metal shader binding: "+resource);
            bindings.add(new Binding(resource.get("name").getAsString(),stage,kind,(int)index,
                resource.has("metalSamplerIndex")?resource.get("metalSamplerIndex").getAsInt():-1,
                resource.has("bytes")?resource.get("bytes").getAsLong():0,
                resource.has("bufferTexture")&&resource.get("bufferTexture").getAsBoolean()));
        }
        return new Program(key,List.copyOf(bindings),inputs,entry);
    }
    private static void verifyStage(RenderPipeline pipeline,JsonObject entry,String stage,String text){
        if(text==null)throw new IllegalStateException("Shader source unavailable before preload: "+pipeline.getLocation()+" "+stage);
        if(!hash(GlslPreprocessor.injectDefines(text,pipeline.getShaderDefines())).equals(entry.get(stage+"SHA256").getAsString()))
            throw new UnsupportedOperationException("Shader resource changed; rebuild the Metal bundle: "+pipeline.getLocation()+" "+stage);
    }
}
