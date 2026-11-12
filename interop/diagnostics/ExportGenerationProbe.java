package mcfao.build;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodNode;

public final class ExportGenerationProbe {
    public static int singletonCreations;
    public static final class SingletonProvider {
        public static final SingletonProvider INSTANCE = new SingletonProvider();
        private SingletonProvider() { singletonCreations++; }
    }

    public static final class PlainProvider {
        public static int creations;
        public PlainProvider() { creations++; }
    }
    public static class ConfigInfo {
        public final String name;
        public final String version;
        public ConfigInfo(String name, String version) { this.name = name; this.version = version; }
    }

    public static void main(String[] args) throws Exception {
        var hooks = AotExport.class.getDeclaredMethod("staticHooks", List.class, Set.class,
                Map.class, Map.class, Set.class, Map.class, Map.class, Map.class, Set.class);
        hooks.setAccessible(true);
        String singleton = SingletonProvider.class.getName();
        String plain = PlainProvider.class.getName();
        byte[] code = (byte[]) hooks.invoke(null, List.of(), Set.of(),
                Map.of("proof", List.of(singleton, plain)), Map.of(), Set.of(singleton),
                Map.of("minecraft", "26.1.2", "demo", "2.1.0+proof"),
                Map.of("minecraft", "Minecraft", "demo", "Demo 原生"),
                Map.of("proof", List.of("demo", "demo")), Set.of());
        var container = AotExport.class.getDeclaredMethod("entrypointContainer");
        container.setAccessible(true);
        byte[] wrapper = (byte[]) container.invoke(null);
        var wide = new ClassNode();
        wide.version = Opcodes.V25;
        wide.access = Opcodes.ACC_PUBLIC;
        wide.name = "probe/WideStack";
        wide.superName = "java/lang/Object";
        var value = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "value", "()J", null, null);
        value.instructions.add(new InsnNode(Opcodes.LCONST_1));
        value.instructions.add(new InsnNode(Opcodes.LCONST_1));
        value.instructions.add(new InsnNode(Opcodes.LADD));
        value.instructions.add(new InsnNode(Opcodes.LRETURN));
        value.maxStack = 1; // The generator's estimate is intentionally insufficient for wide slots.
        wide.methods.add(value);
        byte[] wideCode = AotExport.generatedClassBytes(wide);
        var lookup = new ClassNode();
        lookup.version = Opcodes.V25;
        lookup.access = Opcodes.ACC_PUBLIC;
        lookup.name = "eu/ha3/mc/quick/update/TargettedVersion";
        lookup.superName = "java/lang/Object";
        lookup.methods.add(new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "getVersion",
                "(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;", null, null));
        RuntimeLowering.lowerVersionLookup(lookup,
                "354dc01c8aff54e3b4543f1d441fcbbbefa32ee15ccc5041aad895a44196aa1b", new java.util.ArrayList<>());
        var parse = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "parse",
                "(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;", null, null);
        parse.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 0));
        parse.instructions.add(new org.objectweb.asm.tree.MethodInsnNode(Opcodes.INVOKESTATIC,
                "net/fabricmc/loader/api/Version", "parse", parse.desc, true));
        parse.instructions.add(new InsnNode(Opcodes.ARETURN));
        parse.maxStack = parse.maxLocals = 1;
        lookup.methods.add(parse);
        RuntimeLowering.lowerQueries(lookup, Set.of(), Map.of(), new java.util.ArrayList<>(),
                new java.util.TreeSet<>(), Set.of());
        byte[] lookupCode = AotExport.generatedClassBytes(lookup);
        var sodium = new ClassNode();
        sodium.version = Opcodes.V25;
        sodium.access = Opcodes.ACC_PUBLIC;
        sodium.name = "net/caffeinemc/mods/sodium/fabric/config/ConfigLoaderFabric";
        sodium.superName = "java/lang/Object";
        String infoName = "net/caffeinemc/mods/sodium/client/config/ConfigManager$ModMetadata";
        sodium.methods.add(new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "getModMetadata",
                "(Ljava/lang/String;)L" + infoName + ";", null, null));
        RuntimeLowering.lowerSodiumMetadata(sodium,
                "13cb0cc07040be08158ab8cd53992f519d1430bcd40574bd651c93362efa2cfd", new java.util.ArrayList<>());
        RuntimeLowering.lowerQueries(sodium, Set.of(), Map.of(), new java.util.ArrayList<>(),
                new java.util.TreeSet<>(), Set.of());
        byte[] sodiumCode = AotExport.generatedClassBytes(sodium);
        var info = new ClassNode();
        info.version = Opcodes.V25;
        info.access = Opcodes.ACC_PUBLIC;
        info.name = infoName;
        info.superName = "mcfao/build/ExportGenerationProbe$ConfigInfo";
        var init = new MethodNode(Opcodes.ACC_PUBLIC, "<init>", "(Ljava/lang/String;Ljava/lang/String;)V", null, null);
        init.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 0));
        init.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 1));
        init.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 2));
        init.instructions.add(new org.objectweb.asm.tree.MethodInsnNode(Opcodes.INVOKESPECIAL,
                info.superName, "<init>", init.desc, false));
        init.instructions.add(new InsnNode(Opcodes.RETURN));
        init.maxLocals = 3;
        info.methods.add(init);
        byte[] infoCode = AotExport.generatedClassBytes(info);
        var identity = new ClassNode();
        identity.version = Opcodes.V25;
        identity.access = Opcodes.ACC_PUBLIC;
        identity.name = "probe/ProviderIdentity";
        identity.superName = "java/lang/Object";
        var id = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "id",
                "(Ljava/lang/Object;)Ljava/lang/String;", null, null);
        id.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 0));
        id.instructions.add(new org.objectweb.asm.tree.TypeInsnNode(Opcodes.CHECKCAST,
                "net/fabricmc/loader/api/entrypoint/EntrypointContainer"));
        for (String[] call : new String[][]{
                {"net/fabricmc/loader/api/entrypoint/EntrypointContainer", "getProvider", "()Lnet/fabricmc/loader/api/ModContainer;"},
                {"net/fabricmc/loader/api/ModContainer", "getMetadata", "()Lnet/fabricmc/loader/api/metadata/ModMetadata;"},
                {"net/fabricmc/loader/api/metadata/ModMetadata", "getId", "()Ljava/lang/String;"}}) {
            id.instructions.add(new org.objectweb.asm.tree.MethodInsnNode(Opcodes.INVOKEINTERFACE,
                    call[0], call[1], call[2], true));
        }
        id.instructions.add(new InsnNode(Opcodes.ARETURN));
        id.maxLocals = id.maxStack = 1;
        identity.methods.add(id);
        var entryValue = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "entry",
                "(Ljava/lang/Object;)Ljava/lang/Object;", null, null);
        entryValue.instructions.add(new org.objectweb.asm.tree.VarInsnNode(Opcodes.ALOAD, 0));
        entryValue.instructions.add(new org.objectweb.asm.tree.TypeInsnNode(Opcodes.CHECKCAST,
                "net/fabricmc/loader/api/entrypoint/EntrypointContainer"));
        entryValue.instructions.add(new org.objectweb.asm.tree.MethodInsnNode(Opcodes.INVOKEINTERFACE,
                "net/fabricmc/loader/api/entrypoint/EntrypointContainer", "getEntrypoint", "()Ljava/lang/Object;", true));
        entryValue.instructions.add(new InsnNode(Opcodes.ARETURN));
        entryValue.maxLocals = entryValue.maxStack = 1;
        identity.methods.add(entryValue);
        RuntimeLowering.lowerQueries(identity, Set.of(), Map.of(), new java.util.ArrayList<>(),
                new java.util.TreeSet<>(), Set.of());
        byte[] identityCode = AotExport.generatedClassBytes(identity);
        var loader = new ClassLoader() {
            protected Class<?> findClass(String name) throws ClassNotFoundException {
                byte[] bytes = switch (name) {
                    case "mcfao.aot.Entrypoints" -> code;
                    case "mcfao.aot.Entrypoints$Container" -> wrapper;
                    case "probe.WideStack" -> wideCode;
                    case "eu.ha3.mc.quick.update.TargettedVersion" -> lookupCode;
                    case "net.caffeinemc.mods.sodium.fabric.config.ConfigLoaderFabric" -> sodiumCode;
                    case "net.caffeinemc.mods.sodium.client.config.ConfigManager$ModMetadata" -> infoCode;
                    case "probe.ProviderIdentity" -> identityCode;
                    default -> throw new ClassNotFoundException(name);
                };
                return defineClass(name, bytes, 0, bytes.length);
            }
        };
        var type = Class.forName("mcfao.aot.Entrypoints", true, loader);
        if (PlainProvider.creations != 0) throw new AssertionError("Provider initialized eagerly");
        var stage = type.getMethod("stage", Object.class, String.class, Class.class);
        var first = (List<?>) stage.invoke(null, null, "proof", Object.class);
        var second = (List<?>) stage.invoke(null, null, "proof", Object.class);
        if (PlainProvider.creations != 0 || singletonCreations != 0) {
            throw new AssertionError("Container query initialized a provider");
        }
        Object one = ((net.fabricmc.loader.api.entrypoint.EntrypointContainer<?>) first.get(0)).getEntrypoint();
        Object plainOne = ((net.fabricmc.loader.api.entrypoint.EntrypointContainer<?>) first.get(1)).getEntrypoint();
        Object plainTwo = ((net.fabricmc.loader.api.entrypoint.EntrypointContainer<?>) second.get(1)).getEntrypoint();
        if (one != SingletonProvider.INSTANCE || plainOne != plainTwo || PlainProvider.creations != 1) {
            throw new AssertionError("Entrypoint identity changed");
        }
        var owner = Class.forName("probe.ProviderIdentity", true, loader).getMethod("id", Object.class)
                .invoke(null, first.get(0));
        if (!owner.equals("demo")) throw new AssertionError("Entrypoint owner id lost");
        if (Class.forName("probe.ProviderIdentity", true, loader).getMethod("entry", Object.class)
                .invoke(null, first.get(0)) != one) throw new AssertionError("Entrypoint accessor was stubbed");
        var metadata = (ConfigInfo) Class.forName("net.caffeinemc.mods.sodium.fabric.config.ConfigLoaderFabric", true, loader)
                .getMethod("getModMetadata", String.class).invoke(null, "demo");
        if (!metadata.name.equals("Demo 原生") || !metadata.version.equals("2.1.0+proof")) {
            throw new AssertionError("Sodium config name/version lost");
        }
        if (!Class.forName("probe.WideStack", true, loader).getMethod("value").invoke(null).equals(2L)) {
            throw new AssertionError("Wide argument stack sizing changed");
        }
        var versionLookup = Class.forName("eu.ha3.mc.quick.update.TargettedVersion", true, loader);
        var version = (net.fabricmc.loader.api.Version) versionLookup.getMethod("getVersion", String.class)
                .invoke(null, "demo");
        if (!version.getFriendlyString().equals("2.1.0+proof")
                || version.compareTo(net.fabricmc.loader.api.Version.parse("2.0.9")) <= 0) {
            throw new AssertionError("Build snapshot version changed");
        }
        if (versionLookup.getMethod("parse", String.class).invoke(null, "plain-snapshot") == null) {
            throw new AssertionError("Pure version parsing was stubbed");
        }
        try {
            versionLookup.getMethod("getVersion", String.class).invoke(null, "missing");
            throw new AssertionError("Missing Mod acquired a version");
        } catch (java.lang.reflect.InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalArgumentException)) throw expected;
        }
        System.out.println("MCFAO_STAGE_SINGLETON_CACHE_PASS");
    }
}
