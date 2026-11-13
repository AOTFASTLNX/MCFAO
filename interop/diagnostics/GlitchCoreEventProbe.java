package mcfao.build;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * First-party JVM regression for the build-time GlitchCore event type lowering.
 *
 * <p>The stand-in EventManager deliberately throws from getEventClass, exactly as TypeResolver
 * does inside a Native Image. A real JVM definition of the rewritten classes therefore proves
 * the reflective path is gone, the frames/maxStack are legal, and both a hidden lambda listener
 * and a named Consumer listener are still registered under their true event types.
 */
public final class GlitchCoreEventProbe implements Opcodes {
    private static final String MANAGER = RuntimeLowering.GLITCHCORE_MANAGER;
    private static final String HELPER = RuntimeLowering.REGISTRY_HELPER;
    private static final String EVENT_A = "glitchcore/event/ProbeEventA";
    private static final String EVENT_B = "glitchcore/event/ProbeEventB";
    private static final String CONSUMER = "java/util/function/Consumer";
    private static final String LISTENER_DESC = RuntimeLowering.LISTENER_DESC;

    static final class Loader extends ClassLoader {
        final Map<String, byte[]> classes = new HashMap<>();

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] data = classes.get(name.replace('.', '/'));
            if (data == null) throw new ClassNotFoundException(name);
            return defineClass(name, data, 0, data.length);
        }
    }

    private static ClassNode clazz(String name, String signature, String... interfaces) {
        var node = new ClassNode();
        node.version = V17;
        node.access = ACC_PUBLIC | ACC_SUPER;
        node.name = name;
        node.superName = "java/lang/Object";
        node.signature = signature;
        node.interfaces.addAll(List.of(interfaces));
        var init = new MethodNode(ACC_PUBLIC, "<init>", "()V", null, null);
        init.instructions.add(new VarInsnNode(ALOAD, 0));
        init.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false));
        init.instructions.add(new InsnNode(RETURN));
        init.maxStack = 1;
        init.maxLocals = 1;
        node.methods.add(init);
        return node;
    }

    private static byte[] bytes(ClassNode node) {
        var writer = new ClassWriter(0);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static ClassNode manager() {
        var node = clazz(MANAGER, null);
        node.fields.add(new FieldNode(ACC_PUBLIC | ACC_STATIC, "LISTENERS", "Ljava/util/Map;", null, null));
        var clinit = new MethodNode(ACC_STATIC, "<clinit>", "()V", null, null);
        clinit.instructions.add(new TypeInsnNode(NEW, "java/util/HashMap"));
        clinit.instructions.add(new InsnNode(DUP));
        clinit.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/util/HashMap", "<init>", "()V", false));
        clinit.instructions.add(new FieldInsnNode(PUTSTATIC, MANAGER, "LISTENERS", "Ljava/util/Map;"));
        clinit.instructions.add(new InsnNode(RETURN));
        clinit.maxStack = 2;
        node.methods.add(clinit);
        var add = new MethodNode(ACC_PUBLIC | ACC_STATIC, "addListener", LISTENER_DESC, null, null);
        add.instructions.add(new VarInsnNode(ALOAD, 0));
        add.instructions.add(new MethodInsnNode(INVOKESTATIC, MANAGER, "getEventClass",
                "(Ljava/util/function/Consumer;)Ljava/lang/Class;", false));
        add.instructions.add(new VarInsnNode(ASTORE, 1));
        add.instructions.add(new FieldInsnNode(GETSTATIC, MANAGER, "LISTENERS", "Ljava/util/Map;"));
        add.instructions.add(new VarInsnNode(ALOAD, 1));
        add.instructions.add(new VarInsnNode(ALOAD, 0));
        add.instructions.add(new MethodInsnNode(INVOKEINTERFACE, "java/util/Map", "put",
                "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", true));
        add.instructions.add(new InsnNode(POP));
        add.instructions.add(new InsnNode(RETURN));
        add.maxStack = 3;
        add.maxLocals = 2;
        node.methods.add(add);
        var reflect = new MethodNode(ACC_PRIVATE | ACC_STATIC, "getEventClass",
                "(Ljava/util/function/Consumer;)Ljava/lang/Class;", null, null);
        reflect.instructions.add(new TypeInsnNode(NEW, "java/lang/IllegalStateException"));
        reflect.instructions.add(new InsnNode(DUP));
        reflect.instructions.add(new LdcInsnNode("reflection unavailable in a closed world"));
        reflect.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/lang/IllegalStateException",
                "<init>", "(Ljava/lang/String;)V", false));
        reflect.instructions.add(new InsnNode(ATHROW));
        reflect.maxStack = 3;
        reflect.maxLocals = 1;
        node.methods.add(reflect);
        var listeners = new MethodNode(ACC_PUBLIC | ACC_STATIC, "listeners", "()Ljava/util/Map;", null, null);
        listeners.instructions.add(new FieldInsnNode(GETSTATIC, MANAGER, "LISTENERS", "Ljava/util/Map;"));
        listeners.instructions.add(new InsnNode(ARETURN));
        listeners.maxStack = 1;
        node.methods.add(listeners);
        return node;
    }

    private static final Handle METAFACTORY = new Handle(H_INVOKESTATIC,
            "java/lang/invoke/LambdaMetafactory", "metafactory",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;"
                    + "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;"
                    + "Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;", false);

    private static ClassNode caller(boolean unsupportedShape) {
        var node = clazz("probe/Caller", null);
        var register = new MethodNode(ACC_PUBLIC | ACC_STATIC, "register", "()V", null, null);
        if (unsupportedShape) {
            register.instructions.add(new InsnNode(ACONST_NULL));
        } else {
            register.instructions.add(new InvokeDynamicInsnNode("accept",
                    "()Ljava/util/function/Consumer;", METAFACTORY,
                    Type.getType("(Ljava/lang/Object;)V"),
                    new Handle(H_INVOKESTATIC, "probe/Handlers", "onEvent", "(L" + EVENT_A + ";)V", false),
                    Type.getType("(L" + EVENT_A + ";)V")));
        }
        register.instructions.add(new MethodInsnNode(INVOKESTATIC, MANAGER, "addListener", LISTENER_DESC, false));
        register.instructions.add(new InsnNode(RETURN));
        register.maxStack = 1;
        node.methods.add(register);
        return node;
    }

    private static ClassNode handlers() {
        var node = clazz("probe/Handlers", null);
        var onEvent = new MethodNode(ACC_PUBLIC | ACC_STATIC, "onEvent", "(L" + EVENT_A + ";)V", null, null);
        onEvent.instructions.add(new InsnNode(RETURN));
        onEvent.maxLocals = 1;
        node.methods.add(onEvent);
        return node;
    }

    private static ClassNode helper() {
        var node = clazz(HELPER,
                "Ljava/lang/Object;Ljava/util/function/Consumer<L" + EVENT_B + ";>;", CONSUMER);
        var init = node.methods.get(0);
        init.instructions.remove(init.instructions.getLast());
        init.instructions.add(new VarInsnNode(ALOAD, 0));
        init.instructions.add(new MethodInsnNode(INVOKESTATIC, MANAGER, "addListener", LISTENER_DESC, false));
        init.instructions.add(new InsnNode(RETURN));
        init.maxStack = 1;
        var accept = new MethodNode(ACC_PUBLIC, "accept", "(Ljava/lang/Object;)V", null, null);
        accept.instructions.add(new InsnNode(RETURN));
        accept.maxLocals = 2;
        node.methods.add(accept);
        return node;
    }

    /** A javac-compiled synchronized body carries the same relative stack-map frames as upstream. */
    public static final class RealManager {
        public static final Map<Class<?>, java.util.function.Consumer<?>[]> LISTENERS = new HashMap<>();
        private static final Object lock = new Object();

        public static <T> void addListener(java.util.function.Consumer<T> consumer) {
            Class<?> eventClass = getEventClass(consumer);
            synchronized (lock) {
                java.util.function.Consumer<?>[] existing = LISTENERS.get(eventClass);
                if (existing != null) {
                    LISTENERS.put(eventClass, java.util.Arrays.copyOf(existing, existing.length + 1));
                } else {
                    LISTENERS.put(eventClass, new java.util.function.Consumer<?>[]{consumer});
                }
            }
        }

        private static Class<?> getEventClass(java.util.function.Consumer<?> consumer) {
            throw new IllegalStateException("reflection unavailable in a closed world");
        }

        public static Map<Class<?>, java.util.function.Consumer<?>[]> listeners() {
            return LISTENERS;
        }
    }

    private static final String REAL_MANAGER = "mcfao/build/GlitchCoreEventProbe$RealManager";

    private static ClassNode realManager() throws Exception {
        byte[] data;
        try (var in = GlitchCoreEventProbe.class.getResourceAsStream(
                "/" + REAL_MANAGER + ".class")) {
            if (in == null) throw new AssertionError("compiled RealManager missing");
            data = in.readAllBytes();
        }
        var node = new ClassNode();
        new org.objectweb.asm.ClassReader(data).accept(node, 0);
        node.name = MANAGER;
        node.innerClasses.clear();
        for (var method : node.methods) {
            for (var instruction : method.instructions) {
                if (instruction instanceof MethodInsnNode call && call.owner.equals(REAL_MANAGER)) {
                    call.owner = MANAGER;
                } else if (instruction instanceof FieldInsnNode field && field.owner.equals(REAL_MANAGER)) {
                    field.owner = MANAGER;
                }
            }
        }
        return node;
    }

    /** Mirrors AotExport.recomputedClassBytes for the generated two-parameter method. */
    private static byte[] recomputed(ClassNode node) {
        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        return writer.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        var adaptations = new ArrayList<String>();
        var managerNode = manager();
        RuntimeLowering.lowerGlitchCoreEvents(managerNode,
                RuntimeLowering.GLITCHCORE_MANAGER_SHA256, adaptations);
        if (managerNode.methods.stream().noneMatch(m -> m.name.equals(RuntimeLowering.RESOLVED_LISTENER)
                && m.desc.equals(RuntimeLowering.RESOLVED_LISTENER_DESC))) {
            throw new AssertionError("resolved listener method not generated");
        }
        var callerNode = caller(false);
        RuntimeLowering.lowerGlitchCoreEvents(callerNode, "caller", adaptations);
        var helperNode = helper();
        RuntimeLowering.lowerGlitchCoreEvents(helperNode,
                RuntimeLowering.REGISTRY_HELPER_SHA256, adaptations);
        if (!adaptations.toString().contains("event=" + EVENT_A)
                || !adaptations.toString().contains("event=" + EVENT_B)) {
            throw new AssertionError("event types missing from the build report: " + adaptations);
        }
        var loader = new Loader();
        loader.classes.put(MANAGER, bytes(managerNode));
        loader.classes.put("probe/Caller", bytes(callerNode));
        loader.classes.put(HELPER, bytes(helperNode));
        loader.classes.put("probe/Handlers", bytes(handlers()));
        loader.classes.put(EVENT_A, bytes(clazz(EVENT_A, null)));
        loader.classes.put(EVENT_B, bytes(clazz(EVENT_B, null)));

        var managerClass = loader.loadClass(MANAGER.replace('/', '.'));
        loader.loadClass("probe.Caller").getMethod("register").invoke(null);
        loader.loadClass(HELPER.replace('/', '.')).getConstructor().newInstance();
        @SuppressWarnings("unchecked")
        Map<Object, Object> registered = (Map<Object, Object>) managerClass.getMethod("listeners").invoke(null);
        Class<?> eventA = loader.loadClass(EVENT_A.replace('/', '.'));
        Class<?> eventB = loader.loadClass(EVENT_B.replace('/', '.'));
        if (registered.size() != 2 || !registered.containsKey(eventA) || !registered.containsKey(eventB)
                || registered.get(eventA) == null || registered.get(eventB) == null) {
            throw new AssertionError("listeners registered under the wrong event type: " + registered.keySet());
        }
        // A LambdaMetafactory call site must still create a usable Consumer, not just a Class key.
        var consumer = (java.util.function.Consumer<Object>) registered.get(eventA);
        consumer.accept(null);

        try {
            RuntimeLowering.lowerGlitchCoreEvents(manager(), "changed", new ArrayList<>());
            throw new AssertionError("Unaudited EventManager was accepted");
        } catch (IllegalArgumentException expected) { }
        try {
            RuntimeLowering.lowerGlitchCoreEvents(caller(true), "caller", new ArrayList<>());
            throw new AssertionError("Unrecognised consumer shape was accepted");
        } catch (IllegalArgumentException expected) { }

        // Relative stack-map frames copied from a one-parameter method do not fit the
        // two-parameter generated method. Define a javac-compiled framed body after the
        // production style recomputation: a VerifyError here is exactly the pack-63 failure.
        var framed = realManager();
        RuntimeLowering.lowerGlitchCoreEvents(framed,
                RuntimeLowering.GLITCHCORE_MANAGER_SHA256, new ArrayList<>());
        var framedLoader = new Loader();
        framedLoader.classes.put(MANAGER, recomputed(framed));
        framedLoader.classes.put(EVENT_A, bytes(clazz(EVENT_A, null)));
        var framedManager = framedLoader.loadClass(MANAGER.replace('/', '.'));
        var resolved = framedManager.getMethod(RuntimeLowering.RESOLVED_LISTENER,
                java.util.function.Consumer.class, Class.class);
        java.util.function.Consumer<Object> noop = ignored -> { };
        Class<?> framedEvent = framedLoader.loadClass(EVENT_A.replace('/', '.'));
        resolved.invoke(null, noop, framedEvent);
        @SuppressWarnings("unchecked")
        Map<Object, Object> framedRegistered = (Map<Object, Object>) framedManager
                .getMethod("listeners").invoke(null);
        if (!framedRegistered.containsKey(framedEvent)) {
            throw new AssertionError("framed registration lost: " + framedRegistered.keySet());
        }
        System.out.println("MCFAO_GLITCHCORE_EVENT_LOWERING_PASS");
    }
}
