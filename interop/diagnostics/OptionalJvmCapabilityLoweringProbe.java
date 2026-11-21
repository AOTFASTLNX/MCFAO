package mcfao.build;

import java.nio.file.*;
import java.util.*;
import java.util.jar.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

public final class OptionalJvmCapabilityLoweringProbe {
    static ClassNode parse(byte[] data) {
        var n = new ClassNode(); new ClassReader(data).accept(n, 0); return n;
    }
    static byte[] bytes(ClassNode n) {
        var w = new ClassWriter(0); n.accept(w); return w.toByteArray();
    }
    static List<Map<String, Object>> lower(ClassNode n) {
        var outcomes = new ArrayList<Map<String, Object>>();
        OptionalJvmCapabilityLowering.lower(n, "test-input", new ArrayList<>(), outcomes);
        return outcomes;
    }
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        String name = OptionalJvmCapabilityLowering.IRIS + ".class";
        byte[] original;
        try (var jar = new JarFile(args[0])) { original = jar.getInputStream(jar.getJarEntry(name)).readAllBytes(); }
        ClassNode node = parse(original);
        var before = new HashMap<String, byte[]>();
        for (var m : node.methods) {
            var c = new ClassNode(); c.version = node.version; c.name = node.name; c.superName = node.superName;
            c.methods.add(m); before.put(m.name + m.desc, bytes(c));
        }
        var outcomes = lower(node);
        check(outcomes.stream().anyMatch(o -> o.get("status").equals("APPLIED")));
        byte[] fixed = bytes(node);
        lower(node); check(Arrays.equals(fixed, bytes(node)));
        for (var m : node.methods) {
            if (m.name.equals("<clinit>")) continue;
            var c = new ClassNode(); c.version = node.version; c.name = node.name; c.superName = node.superName;
            c.methods.add(m); check(Arrays.equals(before.get(m.name + m.desc), bytes(c)));
        }
        for (int variant = 0; variant < 4; variant++) {
            ClassNode changed = parse(original);
            MethodNode init = changed.methods.stream().filter(m -> m.name.equals("<clinit>")).findFirst().orElseThrow();
            if (variant == 0) for (var i : init.instructions) {
                if (i instanceof LdcInsnNode v && v.cst.equals("UseFMA")) v.cst = "OtherOption";
            }
            if (variant == 1) init.instructions.insert(new InsnNode(Opcodes.NOP));
            if (variant == 2) changed.name = "unrelated/Probe";
            if (variant == 3) for (var i : init.instructions) {
                if (i instanceof JumpInsnNode v && v.getOpcode() == Opcodes.IFNONNULL) v.setOpcode(Opcodes.IFNULL);
            }
            byte[] untouched = bytes(changed); lower(changed); check(Arrays.equals(untouched, bytes(changed)));
        }
        Path output = Path.of(args[1]); Files.createDirectories(output.resolve(name).getParent());
        Files.write(output.resolve(name), fixed);
        System.out.println("OPTIONAL_JVM_LOWERING_PASS unchanged algorithm methods=" + (node.methods.size() - 1));
    }
}
