package mcfao.build;

import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.zip.ZipFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.BasicVerifier;

/**
 * Checks the closed-world replacement for Fabric's Mod resource packs.
 *
 * <p>Every Mod's assets/ and data/ is merged into the single game jar, but the image has no Mod
 * jars and therefore no ModResourcePackCreator. VanillaPackResources.getResource() resolves by
 * path and would happily read those files; MultiPackResourceManager, however, builds its index
 * from getNamespaces(), which the builder freezes from only "minecraft" (and "realms" on the
 * client). The lowering therefore rewrites the single build() funnel to widen that frozen set
 * with a generated build-time table.
 *
 * <p>The probe asserts three things: that the namespace scan accepts only addressable asset/data
 * directories, that the generated class really merges those namespaces with vanilla's, and that
 * the rewrite changes exactly the intended call and refuses a changed upstream shape.
 */
public final class ModNamespacesProbe implements Opcodes {
    private static final String BUILDER = RuntimeLowering.VANILLA_PACK_BUILDER;
    private static final String PACK = "net/minecraft/server/packs/VanillaPackResources";
    private static final String BUILD_DESC =
            "(Lnet/minecraft/server/packs/PackLocationInfo;)L" + PACK + ";";
    private static final String SET = "java/util/Set";
    private static final String COPY_DESC = "(Ljava/util/Collection;)Ljava/util/Set;";
    private static final String WITH_DESC = "(Ljava/util/Set;)Ljava/util/Set;";

    private ModNamespacesProbe() {}

    public static void main(String[] arguments) throws Exception {
        Set<String> discovered = RuntimeLowering.resourceNamespaces(List.of(
                "assets/minecraft/textures/block/stone.png",
                "data/minecraft/tags/block/planks.json",
                "assets/biomesoplenty/models/item/peach.json",
                "data/advancednetherite/recipe/upgrade.json",
                "assets/c/lang/en_us.json",
                "assets/.mcassetsroot",
                "data/.mcassetsroot",
                "assets/minecraft",                 // a file, not a namespace directory
                "assets/UPPERCASE/thing.png",        // not a legal Identifier namespace
                "assets/has space/thing.png",
                "pack.mcmeta",
                "META-INF/services/x",
                "resourcepacks/vanilla/assets/foo/x.png"));
        Set<String> expected = Set.of("minecraft", "biomesoplenty", "advancednetherite", "c");
        require(discovered.equals(expected), "Namespace scan: " + discovered);
        require(discovered instanceof TreeSet, "The scan must be deterministic (sorted)");

        byte[] generated = RuntimeLowering.modNamespacesClass(
                List.of("biomesoplenty", "c", "minecraft", "biomesoplenty", "advancednetherite"));
        ClassNode table = new ClassNode();
        new ClassReader(generated).accept(table, 0);
        require(table.name.equals(RuntimeLowering.MOD_NAMESPACES),
                "Generated class name: " + table.name);
        require(table.version == V25, "Generated class must target the pinned Java 25 runtime");
        require(table.methods.stream().anyMatch(method -> method.name.equals("withVanilla")
                        && method.desc.equals(WITH_DESC) && (method.access & ACC_PUBLIC) != 0
                        && (method.access & ACC_STATIC) != 0),
                "withVanilla(Set)Set must be a public static method");
        for (MethodNode method : table.methods) {
            new Analyzer<>(new BasicVerifier()).analyze(table.name, method);
        }

        Class<?> loaded = new ByteLoader().define("mcfao.aot.ModNamespaces", generated);
        @SuppressWarnings("unchecked")
        Set<String> merged = (Set<String>) loaded.getMethod("withVanilla", Set.class)
                .invoke(null, Set.of("minecraft", "realms"));
        require(merged.equals(Set.of("minecraft", "realms", "biomesoplenty",
                        "advancednetherite", "c")), "withVanilla: " + merged);
        require(merged.contains("minecraft") && merged.size() == 5,
                "Vanilla namespaces must be preserved, not replaced");
        // The table is immutable: a pack that mutates it must fail rather than silently widen.
        boolean immutable = false;
        try {
            merged.add("injected");
        } catch (UnsupportedOperationException expectedFailure) {
            immutable = true;
        }
        require(immutable, "withVanilla must return an immutable set like Set.copyOf did");

        List<String> adaptations = new ArrayList<>();
        ClassNode builder = builder();
        RuntimeLowering.lowerVanillaPackBuilder(builder, "probe-hash", adaptations);
        MethodNode build = method(builder, "build");
        List<MethodInsnNode> calls = new ArrayList<>();
        for (AbstractInsnNode instruction : build.instructions) {
            if (instruction instanceof MethodInsnNode call) calls.add(call);
        }
        MethodInsnNode freeze = calls.stream().filter(call -> call.name.equals("withVanilla"))
                .findFirst().orElseThrow(() -> new AssertionError("Set.copyOf was not rewritten"));
        require(freeze.owner.equals(RuntimeLowering.MOD_NAMESPACES), "Rewrite owner: " + freeze.owner);
        require(freeze.desc.equals(WITH_DESC), "Rewrite descriptor: " + freeze.desc);
        require(freeze.getOpcode() == INVOKESTATIC && !freeze.itf,
                "A class static call must not keep the interface Methodref flag");
        require(calls.stream().noneMatch(call -> call.name.equals("copyOf")),
                "The original namespace freeze must be gone");
        require(adaptations.size() == 1 && adaptations.get(0).startsWith(BUILDER + "#build "),
                "The rewrite must be reported: " + adaptations);
        // The stack still holds a Set when the call runs, and the rewritten class still verifies.
        new Analyzer<>(new BasicVerifier()).analyze(builder.name, build);
        byte[] rewritten = bytes(builder);
        new ClassReader(rewritten).accept(new ClassNode(), 0);

        // A changed upstream build() must fail loudly instead of shipping an orphan table.
        ClassNode extra = builder();
        MethodNode extraBuild = method(extra, "build");
        var insn = new org.objectweb.asm.tree.InsnList();
        insn.add(new VarInsnNode(ALOAD, 0));
        insn.add(new FieldInsnNode(GETFIELD, BUILDER, "namespaces", "Ljava/util/Set;"));
        insn.add(new MethodInsnNode(INVOKESTATIC, SET, "copyOf", COPY_DESC, true));
        insn.add(new InsnNode(POP));
        extraBuild.instructions.insert(insn);
        require(throwsOnRewrite(extra), "A second namespace freeze must be refused, not guessed at");
        ClassNode missing = builder();
        for (AbstractInsnNode node : method(missing, "build").instructions.toArray()) {
            if (node instanceof MethodInsnNode call && call.name.equals("copyOf")) {
                method(missing, "build").instructions.remove(call);
            }
        }
        require(throwsOnRewrite(missing), "A build() without a namespace freeze must be refused");
        ClassNode other = builder();
        other.name = "net/minecraft/server/packs/SomeOtherBuilder";
        RuntimeLowering.lowerVanillaPackBuilder(other, "probe-hash", adaptations);
        require(adaptations.size() == 1, "An unrelated class must be left alone");

        if (arguments.length > 0) realClient(Path.of(arguments[0]));
        System.out.println("MCFAO_MOD_NAMESPACES_PASS " + merged.size() + " namespaces");
    }

    /**
     * Applies the rewrite to the pinned vanilla client, not just a synthetic stand-in. A Mixin
     * could reshape build() between packs; finding out after a 30-minute native-image build is
     * exactly the failure mode this check exists to prevent.
     */
    private static void realClient(Path client) throws Exception {
        byte[] original;
        try (ZipFile zip = new ZipFile(client.toFile())) {
            var entry = zip.getEntry(BUILDER + ".class");
            require(entry != null, "VanillaPackResourcesBuilder missing from " + client);
            try (InputStream input = zip.getInputStream(entry)) {
                original = input.readAllBytes();
            }
        }
        ClassNode node = new ClassNode();
        new ClassReader(original).accept(node, 0);
        MethodNode build = node.methods.stream()
                .filter(candidate -> candidate.name.equals("build") && candidate.desc.equals(BUILD_DESC))
                .findFirst().orElseThrow(() -> new AssertionError("Real build(PackLocationInfo) missing"));
        require(freezes(build) == 1, "Expected one namespace freeze in the real build(): " + freezes(build));
        List<String> adaptations = new ArrayList<>();
        RuntimeLowering.lowerVanillaPackBuilder(node, "real-client", adaptations);
        require(freezes(build) == 0, "The original Set.copyOf must be gone");
        require(widened(build) == 1, "Exactly one withVanilla call: " + widened(build));
        require(adaptations.size() == 1, "The real rewrite must be reported: " + adaptations);
        new Analyzer<>(new BasicVerifier()).analyze(node.name, build);
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        new ClassReader(writer.toByteArray()).accept(new ClassNode(), 0);
        System.out.println("MCFAO_REAL_PACK_BUILDER_PASS");
    }

    private static int freezes(MethodNode method) {
        int count = 0;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.owner.equals(SET)
                    && call.name.equals("copyOf") && call.desc.equals(COPY_DESC)) count++;
        }
        return count;
    }

    private static int widened(MethodNode method) {
        int count = 0;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call
                    && call.owner.equals(RuntimeLowering.MOD_NAMESPACES)
                    && call.name.equals("withVanilla") && call.desc.equals(WITH_DESC)) count++;
        }
        return count;
    }

    private static boolean throwsOnRewrite(ClassNode node) {
        try {
            RuntimeLowering.lowerVanillaPackBuilder(node, "probe-hash", new ArrayList<>());
        } catch (IllegalArgumentException expectedFailure) {
            return true;
        }
        return false;
    }

    /** Mirrors the real VanillaPackResourcesBuilder.build() instruction sequence. */
    private static ClassNode builder() {
        ClassNode node = new ClassNode();
        node.version = V25;
        node.name = BUILDER;
        node.superName = "java/lang/Object";
        node.fields.add(new org.objectweb.asm.tree.FieldNode(ACC_PRIVATE, "namespaces",
                "Ljava/util/Set;", null, null));
        node.fields.add(new org.objectweb.asm.tree.FieldNode(ACC_PRIVATE, "metadata",
                "Lnet/minecraft/server/packs/resources/ResourceMetadata;", null, null));
        MethodNode build = new MethodNode(ACC_PUBLIC, "build", BUILD_DESC, null, null);
        build.instructions.add(new TypeInsnNode(NEW, PACK));
        build.instructions.add(new InsnNode(DUP));
        build.instructions.add(new VarInsnNode(ALOAD, 1));
        build.instructions.add(new VarInsnNode(ALOAD, 0));
        build.instructions.add(new FieldInsnNode(GETFIELD, BUILDER, "metadata",
                "Lnet/minecraft/server/packs/resources/ResourceMetadata;"));
        build.instructions.add(new VarInsnNode(ALOAD, 0));
        build.instructions.add(new FieldInsnNode(GETFIELD, BUILDER, "namespaces", "Ljava/util/Set;"));
        build.instructions.add(new MethodInsnNode(INVOKESTATIC, SET, "copyOf", COPY_DESC, true));
        build.instructions.add(new MethodInsnNode(INVOKESPECIAL, PACK, "<init>",
                "(Lnet/minecraft/server/packs/PackLocationInfo;"
                        + "Lnet/minecraft/server/packs/resources/ResourceMetadata;"
                        + "Ljava/util/Set;)V", false));
        build.instructions.add(new InsnNode(ARETURN));
        build.maxStack = 6;
        build.maxLocals = 2;
        node.methods.add(build);
        return node;
    }

    private static byte[] bytes(ClassNode node) {
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static MethodNode method(ClassNode node, String name) {
        return node.methods.stream().filter(candidate -> candidate.name.equals(name))
                .findFirst().orElseThrow(AssertionError::new);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    /** Defines the generated table under its real binary name without touching the classpath. */
    private static final class ByteLoader extends ClassLoader {
        ByteLoader() { super(ModNamespacesProbe.class.getClassLoader()); }

        Class<?> define(String name, byte[] data) {
            return defineClass(name, data, 0, data.length);
        }
    }
}
