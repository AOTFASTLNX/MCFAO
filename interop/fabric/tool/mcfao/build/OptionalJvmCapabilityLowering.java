package mcfao.build;

import static org.objectweb.asm.Opcodes.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.*;

/** Only opt-in, structurally verified optional probes may use the safe runtime API. */
final class OptionalJvmCapabilityLowering {
    static final String IRIS = "net/irisshaders/iris/shadows/frustum/advanced/AdvancedShadowCullingFrustum";
    static final String HELPER = "mcfao/aot/OptionalJvmCapabilities";
    private static final String BEAN = "com/sun/management/HotSpotDiagnosticMXBean";
    private static final String OPTION = "com/sun/management/VMOption";
    private static final String FACTORY_DESC = "(Ljava/lang/Class;)Ljava/lang/management/PlatformManagedObject;";

    private OptionalJvmCapabilityLowering() {}

    static void lower(ClassNode node, String sourceHash, List<String> adaptations,
            List<Map<String, Object>> outcomes) {
        if (!node.name.equals(IRIS)) return;
        var rule = new AdaptationRuleEngine.Rule() {
            public String id() { return "jvm.optional.hotspot-fma.v1"; }
            public int version() { return 1; }
            public AdaptationRuleEngine.Mode mode() { return AdaptationRuleEngine.Mode.VERIFIED; }
            public String mechanism() { return "Optional HotSpot UseFMA query with unavailable fallback"; }
            public String scope() { return "Iris 1.10.9 verified FMA-only initializer"; }
            public String evidence() { return "tests/test_optional_jvm_capabilities.py; input class SHA-256 " + sourceHash; }
            public String target(ClassNode n) { return n.name + "#<clinit>()V"; }
            public boolean matches(ClassNode n) { return n.name.equals(IRIS); }
            public boolean alreadyApplied(ClassNode n) {
                return initializer(n) != null && signature(initializer(n)).equals(signature(safeInitializer()));
            }
            public String preconditionFailure(ClassNode n) {
                if (n.fields.stream().noneMatch(f -> f.name.equals("FMA_SUPPORT") && f.desc.equals("Z")
                        && (f.access & (ACC_STATIC | ACC_FINAL)) == (ACC_STATIC | ACC_FINAL))) {
                    return "missing static final boolean FMA_SUPPORT";
                }
                MethodNode init = initializer(n);
                return init != null && init.tryCatchBlocks.isEmpty()
                        && signature(init).equals(signature(originalInitializer()))
                        ? null : "FMA probe control flow differs from audited Iris 1.10.9; left unchanged";
            }
            public int apply(ClassNode n) {
                MethodNode init = initializer(n);
                init.instructions = safeInitializer().instructions;
                init.tryCatchBlocks.clear();
                if (init.localVariables != null) init.localVariables.clear();
                init.visibleLocalVariableAnnotations = null;
                init.invisibleLocalVariableAnnotations = null;
                init.maxStack = 1;
                init.maxLocals = 0;
                adaptations.add(n.name + "#<clinit> jvm.optional.hotspot-fma.v1 source=" + sourceHash
                        + "; FMA unavailable selects existing non-FMA culling");
                return 1;
            }
            public String verificationFailure(ClassNode n) {
                return alreadyApplied(n) ? null : "safe FMA initializer postcondition failed";
            }
        };
        outcomes.addAll(AdaptationRuleEngine.run(node, List.of(rule)));
    }

    private static MethodNode initializer(ClassNode n) {
        return n.methods.stream().filter(m -> m.name.equals("<clinit>") && m.desc.equals("()V"))
                .findFirst().orElse(null);
    }

    private static MethodNode safeInitializer() {
        var m = new MethodNode(ACC_STATIC, "<clinit>", "()V", null, null);
        m.visitMethodInsn(INVOKESTATIC, HELPER, "isFmaEnabled", "()Z", false);
        m.visitFieldInsn(PUTSTATIC, IRIS, "FMA_SUPPORT", "Z");
        m.visitInsn(RETURN);
        return m;
    }

    private static MethodNode originalInitializer() {
        var m = new MethodNode(ACC_STATIC, "<clinit>", "()V", null, null);
        var query = new org.objectweb.asm.Label();
        var end = new org.objectweb.asm.Label();
        m.visitLdcInsn(Type.getObjectType(BEAN));
        m.visitMethodInsn(INVOKESTATIC, "java/lang/management/ManagementFactory", "getPlatformMXBean", FACTORY_DESC, false);
        m.visitTypeInsn(CHECKCAST, BEAN);
        m.visitVarInsn(ASTORE, 0);
        m.visitVarInsn(ALOAD, 0);
        m.visitJumpInsn(IFNONNULL, query);
        m.visitInsn(ICONST_0);
        m.visitFieldInsn(PUTSTATIC, IRIS, "FMA_SUPPORT", "Z");
        m.visitJumpInsn(GOTO, end);
        m.visitLabel(query);
        m.visitVarInsn(ALOAD, 0);
        m.visitLdcInsn("UseFMA");
        m.visitMethodInsn(INVOKEINTERFACE, BEAN, "getVMOption", "(Ljava/lang/String;)L" + OPTION + ";", true);
        m.visitVarInsn(ASTORE, 1);
        m.visitVarInsn(ALOAD, 1);
        m.visitMethodInsn(INVOKEVIRTUAL, OPTION, "getValue", "()Ljava/lang/String;", false);
        m.visitMethodInsn(INVOKESTATIC, "java/lang/Boolean", "parseBoolean", "(Ljava/lang/String;)Z", false);
        m.visitFieldInsn(PUTSTATIC, IRIS, "FMA_SUPPORT", "Z");
        m.visitLabel(end);
        m.visitInsn(RETURN);
        return m;
    }

    // Ignore debug/frame nodes, but compare every instruction, operand and branch destination.
    static List<String> signature(MethodNode m) {
        var real = new ArrayList<AbstractInsnNode>();
        for (var i : m.instructions) if (i.getOpcode() >= 0) real.add(i);
        var result = new ArrayList<String>();
        for (var i : real) {
            String operand = "";
            if (i instanceof LdcInsnNode v) operand = v.cst.getClass().getName() + ":" + v.cst;
            else if (i instanceof VarInsnNode v) operand = "" + v.var;
            else if (i instanceof TypeInsnNode v) operand = v.desc;
            else if (i instanceof FieldInsnNode v) operand = v.owner + "." + v.name + v.desc;
            else if (i instanceof MethodInsnNode v) operand = v.owner + "." + v.name + v.desc + ":" + v.itf;
            else if (i instanceof JumpInsnNode v) {
                AbstractInsnNode next = v.label;
                while (next != null && next.getOpcode() < 0) next = next.getNext();
                operand = "" + real.indexOf(next);
            } else if (!(i instanceof InsnNode)) operand = "unmatched:" + i.getClass().getName();
            result.add(i.getOpcode() + ":" + operand);
        }
        return result;
    }
}
