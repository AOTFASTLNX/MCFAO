package mcfao.build;
import mcfao.aot.ModCatalog;
import java.nio.file.Files;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
public final class ModCatalogProbe implements Opcodes {
    private static final class Definer extends ClassLoader {
        Class<?> define(byte[] bytes) { return defineClass(null,bytes,0,bytes.length); }
    }
    public static void main(String[] args) throws Exception {
        var mod = ModCatalog.lookup(null, "fixture").orElseThrow();
        if (mod != ModCatalog.lookup(null, new String("fixture")).orElseThrow()) throw new AssertionError("identity");
        if (ModCatalog.lookup(null, "absent").isPresent()) throw new AssertionError("absent");
        if (!mod.getMetadata().getName().equals("Fixture") || !mod.getMetadata().getVersion().getFriendlyString().equals("1.2.3")) throw new AssertionError("metadata");
        if (!Files.readString(mod.findPath("resourcepacks/dark/pack.mcmeta").orElseThrow()).equals("fixture")) throw new AssertionError("builtin file");
        if (mod.findPath("absent").isPresent()) throw new AssertionError("missing path");
        try { mod.getPath("../outside"); throw new AssertionError("traversal"); } catch (IllegalArgumentException expected) {}
        if (ModCatalog.all().size()!=1 || ModCatalog.required("fixture")!=mod) throw new AssertionError("enumeration");
        var meta=mod.getMetadata();
        if (!meta.getCustomValue("flag").getAsBoolean() || meta.getCustomValue("missing")!=null) throw new AssertionError("custom");
        var array=meta.getCustomValue("object").getAsObject().get("array").getAsArray();
        if(array.size()!=3 || array.get(1).getType()!=net.fabricmc.loader.api.metadata.CustomValue.CvType.NULL) throw new AssertionError("nested custom");
        try { array.get(0).getAsString(); throw new AssertionError("wrong custom type"); } catch(ClassCastException expected) {}
        if(!meta.getContact().get("homepage").orElseThrow().equals("https://example.org") || !meta.getAuthors().iterator().next().getName().equals("Author")) throw new AssertionError("people/contact");
        var dep=meta.getDependencies().iterator().next();
        if(!dep.matches(net.fabricmc.loader.api.Version.parse("26.1.2")) || dep.matches(net.fabricmc.loader.api.Version.parse("1.21.1")) || dep.getVersionIntervals().isEmpty()) throw new AssertionError("dependency semantics");
        if(mod.getContainingMod().isPresent() || !mod.getContainedMods().isEmpty() || mod.getOrigin().getPaths().size()!=1) throw new AssertionError("origin");
        var node = new ClassNode(); node.name = "example/Mod";
        var method = new MethodNode(ACC_PUBLIC | ACC_STATIC, "query", "()V", null, null);
        node.methods.add(method);
        method.instructions.add(new MethodInsnNode(INVOKESTATIC,"net/fabricmc/loader/api/FabricLoader","getInstance","()Lnet/fabricmc/loader/api/FabricLoader;",false));
        method.instructions.add(new LdcInsnNode("fixture"));
        method.instructions.add(new MethodInsnNode(INVOKEINTERFACE,"net/fabricmc/loader/api/FabricLoader","getModContainer","(Ljava/lang/String;)Ljava/util/Optional;",true));
        method.instructions.add(new InsnNode(POP)); method.instructions.add(new InsnNode(RETURN));
        var adaptations = new ArrayList<String>(); var stubbed = new HashSet<String>();
        RuntimeLowering.lowerQueries(node, Set.of("fixture"), Map.of("fixture","1.2.3"), adaptations, stubbed, Set.of());
        if (!stubbed.isEmpty() || adaptations.stream().noneMatch(s -> s.contains("build snapshot"))) throw new AssertionError("lowering");
        if (method.instructions.size()!=5) throw new AssertionError("query instructions lost");
        var computed=new ClassNode();computed.version=V25;computed.access=ACC_PUBLIC;
        computed.name="probe/ComputedQuery";computed.superName="java/lang/Object";
        var query=new MethodNode(ACC_PUBLIC|ACC_STATIC,"query","(Ljava/util/Map;)Ljava/util/Optional;",null,null);
        computed.methods.add(query);
        query.instructions.add(new MethodInsnNode(INVOKESTATIC,"net/fabricmc/loader/api/FabricLoader","getInstance","()Lnet/fabricmc/loader/api/FabricLoader;",false));
        query.instructions.add(new VarInsnNode(ALOAD,0));query.instructions.add(new LdcInsnNode("id"));
        query.instructions.add(new MethodInsnNode(INVOKEINTERFACE,"java/util/Map","get","(Ljava/lang/Object;)Ljava/lang/Object;",true));
        query.instructions.add(new TypeInsnNode(CHECKCAST,"java/lang/String"));
        query.instructions.add(new MethodInsnNode(INVOKEINTERFACE,"net/fabricmc/loader/api/FabricLoader","getModContainer","(Ljava/lang/String;)Ljava/util/Optional;",true));
        query.instructions.add(new InsnNode(ARETURN));query.maxLocals=1;query.maxStack=3;
        var computedStubs=new HashSet<String>();
        RuntimeLowering.lowerQueries(computed,Set.of("fixture"),Map.of("fixture","1.2.3"),new ArrayList<>(),computedStubs,Set.of());
        if(!computedStubs.isEmpty())throw new AssertionError("computed query stubbed");
        var bytes=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS);computed.accept(bytes);
        var computedType=new Definer().define(bytes.toByteArray());
        var actual=(Optional<?>)computedType.getMethod("query",Map.class).invoke(null,Map.of("id","fixture"));
        if(actual.orElseThrow()!=mod)throw new AssertionError("computed query lost identity");
        var generator=AotExport.class.getDeclaredMethod("entrypointContainer");
        generator.setAccessible(true);
        var containerType=new Definer().define((byte[])generator.invoke(null));
        var container=containerType.getConstructor(int.class,String.class,String.class).newInstance(0,"fixture.Entry","fixture");
        if(containerType.getMethod("getProvider").invoke(container)!=mod) throw new AssertionError("provider identity");
        if(!RuntimeLowering.isValueCall(new MethodInsnNode(INVOKEINTERFACE,"net/fabricmc/loader/api/entrypoint/EntrypointContainer","getProvider","()Lnet/fabricmc/loader/api/ModContainer;",true))) throw new AssertionError("provider residue");
        System.out.println("MOD_CATALOG_PASS");
    }
}
