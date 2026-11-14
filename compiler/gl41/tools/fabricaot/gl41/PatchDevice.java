package fabricaot.gl41;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

/** Build-time only: disable the 4.5 direct-state path absent from the 4.1 OSMesa export surface. */
public final class PatchDevice {
    private static final String TARGET = "com/mojang/blaze3d/opengl/GlDevice.class";
    private static final String FLAG = "USE_GL_ARB_direct_state_access";

    static byte[] transform(byte[] bytes) {
        ClassNode cls = new ClassNode();
        new ClassReader(bytes).accept(cls, 0);
        int matches = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("<clinit>")) continue;
            for (AbstractInsnNode instruction : method.instructions.toArray()) {
                if (instruction.getOpcode() != Opcodes.PUTSTATIC) continue;
                if (!((FieldInsnNode) instruction).name.equals(FLAG)) continue;
                AbstractInsnNode previous = instruction.getPrevious();
                if (previous == null || previous.getOpcode() != Opcodes.ICONST_1) {
                    throw new IllegalArgumentException("Unexpected " + FLAG + " initialiser");
                }
                method.instructions.set(previous, new InsnNode(Opcodes.ICONST_0));
                matches++;
            }
        }
        if (matches != 1) throw new IllegalArgumentException("Expected one " + FLAG + ", found " + matches);
        ClassWriter writer = new ClassWriter(0);
        cls.accept(writer);
        return writer.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);
        List<String> changed = new ArrayList<>();
        try (ZipInputStream source = new ZipInputStream(Files.newInputStream(input));
             ZipOutputStream destination = new ZipOutputStream(Files.newOutputStream(output))) {
            ZipEntry entry;
            while ((entry = source.getNextEntry()) != null) {
                byte[] data = source.readAllBytes();
                if (entry.getName().equals(TARGET)) {
                    byte[] patched = transform(data);
                    if (!Arrays.equals(data, patched)) changed.add(entry.getName());
                    data = patched;
                }
                ZipEntry copy = new ZipEntry(entry.getName());
                copy.setTime(entry.getTime());
                destination.putNextEntry(copy);
                destination.write(data);
                destination.closeEntry();
            }
        }
        if (!changed.equals(List.of(TARGET))) {
            throw new IllegalArgumentException("Unexpected changed entries: " + changed);
        }
        System.out.println("GL41_DIRECT_STATE_DISABLED");
    }
}
