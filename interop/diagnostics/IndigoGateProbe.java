package mcfao.build;

import java.util.ArrayList;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

/** First-party JVM bytecode regression; the removed plugin is absent from this classpath. */
public final class IndigoGateProbe implements Opcodes {
    public static class JadeBase {
        public boolean accessibilityMod = true;
        public boolean fastScroll;
        public boolean smoothScroll;
        public java.util.List<String> disableItemModNameTooltip = java.util.List.of();
    }

    private static Class<?> define(ClassNode node) {
        var writer = new ClassWriter(0);
        node.accept(writer);
        byte[] bytes = writer.toByteArray();
        return new ClassLoader() {
            Class<?> define() { return defineClass(null, bytes, 0, bytes.length); }
        }.define();
    }

    private static void verifyJadeAndConstructorFallback() throws Exception {
        var jade = new ClassNode();
        jade.version = V17;
        jade.access = ACC_PUBLIC;
        jade.name = RuntimeLowering.JADE_METADATA;
        jade.superName = "mcfao/build/IndigoGateProbe$JadeBase";
        jade.methods.add(new MethodNode(ACC_PUBLIC, "<init>", "()V", null, null));
        RuntimeLowering.lowerJadeMetadata(jade, RuntimeLowering.JADE_METADATA_SHA256,
                java.util.Map.of("smoothScroll", true), java.util.List.of("demo"), new ArrayList<>());
        JadeBase data = (JadeBase) define(jade).getConstructor().newInstance();
        if (!data.accessibilityMod || data.fastScroll || !data.smoothScroll
                || !data.disableItemModNameTooltip.equals(java.util.List.of("demo"))) {
            throw new AssertionError("Jade metadata or superclass state lost");
        }
        try {
            RuntimeLowering.lowerJadeMetadata(jade, "changed", java.util.Map.of(), java.util.List.of(), new ArrayList<>());
            throw new AssertionError("Changed Jade constructor accepted");
        } catch (IllegalArgumentException expected) { }
        var fallback = new ClassNode();
        fallback.version = V17;
        fallback.access = ACC_PUBLIC;
        fallback.name = "probe/UnsupportedConstructor";
        fallback.superName = "java/lang/Object";
        for (String methodName : java.util.List.of("<init>", "list")) {
            boolean constructor = methodName.equals("<init>");
            var method = new MethodNode(ACC_PUBLIC | (constructor ? 0 : ACC_STATIC), methodName,
                    constructor ? "()V" : "()Ljava/util/List;", null, null);
            method.instructions.add(new InsnNode(ACONST_NULL));
            method.instructions.add(new MethodInsnNode(INVOKEINTERFACE, "net/fabricmc/loader/api/ModContainer",
                    "getMetadata", "()Lnet/fabricmc/loader/api/metadata/ModMetadata;", true));
            method.maxLocals = constructor ? 1 : 0;
            method.maxStack = 3;
            fallback.methods.add(method);
        }
        RuntimeLowering.lowerQueries(fallback, java.util.Set.of(), java.util.Map.of(),
                new ArrayList<>(), new java.util.TreeSet<>(), java.util.Set.of());
        var type = define(fallback);
        if (!type.getMethod("list").invoke(null).equals(java.util.List.of())) {
            throw new AssertionError("Empty interface factory failed");
        }
        try {
            type.getConstructor().newInstance();
            throw new AssertionError("Unsupported constructor returned normally");
        } catch (java.lang.reflect.InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalStateException)) throw expected;
        }
    }

    private static ClassNode sample(String methodName) {
        var node = new ClassNode();
        node.version = V17;
        node.access = ACC_PUBLIC;
        node.name = "probe/IndigoGate";
        node.superName = "java/lang/Object";
        var method = new MethodNode(ACC_PUBLIC | ACC_STATIC, "enabled", "()Z", null, null);
        method.instructions.add(new MethodInsnNode(INVOKESTATIC, RuntimeLowering.INDIGO_PLUGIN,
                methodName, "()Z", false));
        method.instructions.add(new InsnNode(IRETURN));
        method.maxStack = 1;
        node.methods.add(method);
        return node;
    }

    public static void main(String[] args) throws Exception {
        verifyJadeAndConstructorFallback();
        for (boolean enabled : new boolean[]{false, true}) {
            var node = sample("shouldApplyIndigo");
            var report = new ArrayList<String>();
            RuntimeLowering.foldIndigoGate(node, enabled, RuntimeLowering.INDIGO_PLUGIN_SHA256, report);
            var writer = new ClassWriter(0);
            node.accept(writer);
            byte[] bytes = writer.toByteArray();
            Class<?> type = new ClassLoader() {
                Class<?> define() { return defineClass(null, bytes, 0, bytes.length); }
            }.define();
            if (!type.getMethod("enabled").invoke(null).equals(enabled) || report.size() != 1) {
                throw new AssertionError("Renderer metadata decision changed");
            }
        }
        try {
            RuntimeLowering.foldIndigoGate(sample("shouldApplyIndigo"), true, "changed", new ArrayList<>());
            throw new AssertionError("Changed plugin was accepted");
        } catch (IllegalArgumentException expected) { }
        var other = sample("unrelated");
        RuntimeLowering.foldIndigoGate(other, true, "changed", new ArrayList<>());
        if (!(other.methods.getFirst().instructions.getFirst() instanceof MethodInsnNode)) {
            throw new AssertionError("Unrelated plugin method changed");
        }
        var serialized = new ClassNode();
        var method = new MethodNode(ACC_PUBLIC | ACC_STATIC, "read", "()V", null, null);
        serialized.methods.add(method);
        method.instructions.add(new org.objectweb.asm.tree.LdcInsnNode(
                org.objectweb.asm.Type.getObjectType("mod/config/Settings")));
        method.instructions.add(new org.objectweb.asm.tree.LabelNode());
        method.instructions.add(new MethodInsnNode(INVOKEVIRTUAL, "com/google/gson/Gson",
                "fromJson", "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;", false));
        method.instructions.add(new InsnNode(ACONST_NULL)); // A runtime class is not a static root.
        method.instructions.add(new MethodInsnNode(INVOKEVIRTUAL, "com/google/gson/Gson",
                "fromJson", "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;", false));
        method.instructions.add(new org.objectweb.asm.tree.LdcInsnNode(
                org.objectweb.asm.Type.getObjectType("mod/config/Json5")));
        method.instructions.add(new MethodInsnNode(INVOKEVIRTUAL, "mod/shadowed/blue/endless/jankson/Jankson",
                "fromJsonCarefully", "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;", false));
        var roots = new java.util.TreeSet<String>();
        RuntimeLowering.collectSerializationRoots(serialized, roots);
        if (!roots.equals(java.util.Set.of("mod/config/Settings", "mod/config/Json5"))) {
            throw new AssertionError("Wrong serialization roots: " + roots);
        }
        method.instructions.add(new org.objectweb.asm.tree.LdcInsnNode("jade"));
        method.instructions.add(new org.objectweb.asm.tree.LdcInsnNode(org.objectweb.asm.Type.getType(Object.class)));
        method.instructions.add(new MethodInsnNode(INVOKESTATIC, "mcfao/aot/Entrypoints", "stage",
                "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Class;)Ljava/util/List;", false));
        var stages = new java.util.TreeSet<String>();
        RuntimeLowering.collectStageQueries(serialized, stages);
        if (!stages.equals(java.util.Set.of("jade"))) throw new AssertionError("Wrong live stages " + stages);
        System.out.println("MCFAO_INDIGO_GATE_LOWERING_PASS");
    }
}
