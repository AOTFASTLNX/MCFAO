package mcfao.build;

import java.util.LinkedHashSet;
import java.util.Set;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

/**
 * Checks that the JSON read scan sees a Mod's own {@code fromJson} wrapper.
 *
 * <p>In a real pack the call is {@code JsonUtil.fromJson(text, DynamicFPSConfig.class)} and the
 * helper forwards the {@code Class} to Gson, so no Gson call site ever holds the literal. Keying
 * on the call name plus a trailing {@code Class} parameter is what keeps those config classes
 * reflectable; this probe pins that behaviour, and pins the cases that must stay out of it.
 */
public final class SerializationRootProbe {
    private static final Set<String> ROOTS = new LinkedHashSet<>();

    private SerializationRootProbe() {}

    public static void main(String[] arguments) {
        expectCall("com/google/gson/Gson", "fromJson",
                   "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;",
                   "probe/Direct");
        expectCall("probe/JsonUtil", "fromJson",
                   "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;",
                   "probe/Wrapped");
        expectCall("probe/JsonUtil", "fromJsonCarefully",
                   "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;",
                   "probe/JanksonStyle");
        // A helper with the same shape but a different name is not a JSON read.
        rejectCall("probe/Registry", "lookup", "(Ljava/lang/String;Ljava/lang/Class;)V");
        // A fromJson that does not receive the type as a Class takes nothing from a literal.
        rejectCall("probe/JsonUtil", "fromJson", "(Ljava/lang/String;Ljava/lang/Object;)V");
        if (!ROOTS.equals(Set.of("probe/Direct", "probe/Wrapped", "probe/JanksonStyle"))) {
            throw new AssertionError("Unexpected serialization roots: " + ROOTS);
        }
        System.out.println("MCFAO_SERIALIZATION_ROOT_PASS roots=" + ROOTS);
    }

    private static void expectCall(String owner, String name, String descriptor, String root) {
        ClassNode node = holder(owner, name, descriptor, root);
        RuntimeLowering.collectSerializationRoots(node, ROOTS);
        if (!ROOTS.contains(root)) {
            throw new AssertionError("Missing serialization root: " + root
                    + " from " + owner + "." + name + descriptor);
        }
    }

    private static void rejectCall(String owner, String name, String descriptor) {
        ClassNode node = holder(owner, name, descriptor, "probe/Rejected");
        Set<String> before = new LinkedHashSet<>(ROOTS);
        RuntimeLowering.collectSerializationRoots(node, ROOTS);
        if (!before.equals(ROOTS)) {
            throw new AssertionError(owner + "." + name + descriptor
                    + " must not register a serialization root: " + ROOTS);
        }
    }

    private static ClassNode holder(String owner, String name, String descriptor, String root) {
        ClassNode node = new ClassNode();
        node.version = Opcodes.V17;
        node.name = "probe/Holder";
        node.superName = "java/lang/Object";
        MethodNode method = new MethodNode(Opcodes.ACC_STATIC, "read", "()V", null, null);
        method.instructions.add(new LdcInsnNode(Type.getObjectType(root)));
        method.instructions.add(new MethodInsnNode(Opcodes.INVOKESTATIC, owner, name,
                descriptor, false));
        method.instructions.add(new InsnNode(Opcodes.RETURN));
        node.methods.add(method);
        return node;
    }
}
