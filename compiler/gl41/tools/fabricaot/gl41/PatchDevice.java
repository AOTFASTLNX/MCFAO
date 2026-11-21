package fabricaot.gl41;

import fabricaot.metal.InjectBackend;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.IOException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.jar.Manifest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.UnaryOperator;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

/** Build-time only: disable the 4.5 direct-state path absent from the 4.1 OSMesa export surface. */
public final class PatchDevice {
    static byte[] cleanManifest(byte[] bytes) throws IOException {
        Manifest original = new Manifest(new ByteArrayInputStream(bytes));
        Manifest clean = new Manifest();
        clean.getMainAttributes().putAll(original.getMainAttributes());
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        clean.write(out);
        return out.toByteArray();
    }
    private static final String TARGET = "com/mojang/blaze3d/opengl/GlDevice.class";
    private static final String FLAG = "USE_GL_ARB_direct_state_access";
    private static final String TRACKER = "net/minecraft/client/multiplayer/LevelLoadTracker.class";
    private static final String PLAYER_CHUNK = "net/minecraft/client/multiplayer/LevelLoadTracker$WaitingForPlayerChunk.class";
    private static final String MINECRAFT = "net/minecraft/client/Minecraft.class";
    private static final String LISTENER = "net/minecraft/client/multiplayer/ClientPacketListener.class";
    private static final String CHUNK_CACHE = "net/minecraft/client/multiplayer/ClientChunkCache.class";
    private static final String CONNECTION = "net/minecraft/network/Connection.class";
    private static final String DYNAMIC_UNIFORMS = "net/minecraft/client/renderer/DynamicUniforms.class";
    private static final String UNIFORM_STORAGE = "net/minecraft/client/renderer/DynamicUniformStorage";
    private static final String DIAGNOSTICS = "fabricaot/diag/PlayDiagnostics";
    private static final String FRAME_LIMITER = "net/minecraft/client/FramerateLimiter";
    private static final String FRAME_PACING = "fabricaot/gl41/FramePacing";
    static final String IRIS_ENTITY = "net/irisshaders/iris/pipeline/transform/transformer/EntityPatcher.class";
    private static final String IRIS_ENTITY_SHA256 =
            "d0072c583ba1ef21896198dc12966bbc90d8f52570152f37426285bb970addf3";

    static byte[] fixIrisEntityAttribute(byte[] bytes) {
        String digest;
        try {
            digest = java.util.HexFormat.of().formatHex(
                    java.security.MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
        if (!digest.equals(IRIS_ENTITY_SHA256)) {
            throw new IllegalArgumentException("Unverified Iris EntityPatcher SHA-256: " + digest
                    + "; review the entity vertex format before applying the GL41 conversion");
        }
        ClassNode cls = new ClassNode();
        new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(IRIS_ENTITY.substring(0, IRIS_ENTITY.length() - 6))) {
            throw new IllegalArgumentException("Unexpected Iris entity patch class");
        }
        int inputs = 0, assignments = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("patchEntityId")) continue;
            for (AbstractInsnNode instruction : method.instructions) {
                if (!(instruction instanceof LdcInsnNode literal)) continue;
                if ("in ivec3 iris_Entity;".equals(literal.cst)) {
                    literal.cst = "in uvec3 iris_Entity;";
                    inputs++;
                } else if ("iris_entityInfo = iris_Entity;".equals(literal.cst)) {
                    // The USHORT4 stream supplies 0..65535, all exactly representable as int.
                    // Keep downstream signed varyings and all entity/item IDs unchanged.
                    literal.cst = "iris_entityInfo = ivec3(iris_Entity);";
                    assignments++;
                }
            }
        }
        if (inputs != 1 || assignments != 1) {
            throw new IllegalArgumentException("Expected one audited Iris entity input and assignment");
        }
        ClassWriter writer = new ClassWriter(0);
        cls.accept(writer);
        return writer.toByteArray();
    }

    // Every registered class patch must be applied and change its input bytes.
    private static final Map<String, UnaryOperator<byte[]>> CLASS_PATCHES = Map.of(
            TARGET, PatchDevice::transform,
            MINECRAFT, PatchDevice::instrumentClientTick,
            LISTENER, InjectBackend::avoidUnneededChatKeyWait,
            TRACKER, InjectBackend::instrumentLevelLoadTracker,
            PLAYER_CHUNK, InjectBackend::instrumentWaitingForPlayerChunk,
            CHUNK_CACHE, InjectBackend::instrumentChunkCache,
            CONNECTION, InjectBackend::instrumentConnection,
            DYNAMIC_UNIFORMS, PatchDevice::presizeUniformBuffers,
            InjectBackend.GLX, InjectBackend::useIosHardwareDiagnostics,
            InjectBackend.SYSTEM_REPORT, InjectBackend::useIosHardwareDiagnostics);

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

    static byte[] instrumentClientTick(byte[] bytes) {
        ClassNode cls = new ClassNode();
        new ClassReader(bytes).accept(cls, 0);
        int matches = 0, limiterCalls = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("runTick") || !method.desc.equals("(Z)V")) continue;
            method.instructions.insert(new MethodInsnNode(Opcodes.INVOKESTATIC, DIAGNOSTICS,
                    "tick", "()V", false));
            matches++;
        }
        if (matches != 1) throw new IllegalArgumentException("Expected one Minecraft.runTick, found " + matches);
        for (MethodNode method : cls.methods) {
            for (AbstractInsnNode instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call)) continue;
                if (call.getOpcode() != Opcodes.INVOKESTATIC || !call.owner.equals(FRAME_LIMITER)
                        || !call.name.equals("limitDisplayFPS") || !call.desc.equals("(I)V")) continue;
                method.instructions.set(call, new MethodInsnNode(Opcodes.INVOKESTATIC,
                        FRAME_PACING, "limitDisplayFPS", "(I)V", false));
                limiterCalls++;
            }
        }
        if (limiterCalls != 1) {
            throw new IllegalArgumentException("Expected one frame limiter call, found " + limiterCalls);
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        return writer.toByteArray();
    }

    static byte[] presizeUniformBuffers(byte[] bytes) {
        ClassNode cls = new ClassNode();
        new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals("net/minecraft/client/renderer/DynamicUniforms")) {
            throw new IllegalArgumentException("Unexpected dynamic uniform class: " + cls.name);
        }
        int matches = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("<init>") || !method.desc.equals("()V")) continue;
            for (AbstractInsnNode instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call)) continue;
                if (call.getOpcode() != Opcodes.INVOKESPECIAL || !call.owner.equals(UNIFORM_STORAGE)
                        || !call.name.equals("<init>") || !call.desc.equals("(Ljava/lang/String;II)V")) continue;
                AbstractInsnNode capacity = call.getPrevious();
                if (capacity == null || capacity.getOpcode() != Opcodes.ICONST_2) {
                    throw new IllegalArgumentException("Unexpected dynamic uniform initial capacity");
                }
                method.instructions.set(capacity, new LdcInsnNode(4096));
                matches++;
            }
        }
        if (matches != 2) {
            throw new IllegalArgumentException("Expected two dynamic uniform buffers, found " + matches);
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        return writer.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Set<String> pending = new TreeSet<>(CLASS_PATCHES.keySet());
        try (ZipInputStream source = new ZipInputStream(Files.newInputStream(input));
             ZipOutputStream destination = new ZipOutputStream(Files.newOutputStream(output))) {
            ZipEntry entry;
            while ((entry = source.getNextEntry()) != null) {
                byte[] data = source.readAllBytes();
                String name = entry.getName();
                var patch = CLASS_PATCHES.get(name);
                if (patch != null) {
                    byte[] patched = patch.apply(data);
                    if (Arrays.equals(data, patched)) {
                        throw new IllegalArgumentException("GL41 patch did not change " + name);
                    }
                    pending.remove(name);
                    data = patched;
                } else if (name.equals(IRIS_ENTITY)) {
                    data = fixIrisEntityAttribute(data);
                    System.out.println("GL41_IRIS_ENTITY_UNSIGNED_INPUT_APPLIED");
                } else if (name.equals("META-INF/MANIFEST.MF")) {
                    data = cleanManifest(data);
                }
                ZipEntry copy = new ZipEntry(name);
                copy.setTime(entry.getTime());
                destination.putNextEntry(copy);
                destination.write(data);
                destination.closeEntry();
            }
            if (!pending.isEmpty()) {
                throw new IllegalArgumentException("Missing GL41 patch targets: " + pending);
            }
            for (String helperName : List.of(DIAGNOSTICS, FRAME_PACING)) {
                ZipEntry helper = new ZipEntry(helperName + ".class");
                helper.setTime(0);
                destination.putNextEntry(helper);
                destination.write(Files.readAllBytes(Path.of(args[2]).resolve(helperName + ".class")));
                destination.closeEntry();
            }
        }
        System.out.println("GL41_DIRECT_STATE_DISABLED");
    }
}
