package mcfao.build;

import com.mojang.blaze3d.pipeline.RenderPipeline;
import com.mojang.blaze3d.vertex.DefaultVertexFormat;
import com.mojang.blaze3d.vertex.VertexFormat;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import net.minecraft.resources.Identifier;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.BasicVerifier;

/**
 * Contract for the Metal pipeline-bundle gate.
 *
 * <p>{@code ShaderManager.apply} precompiles every registered static pipeline and treats one
 * failure as a fatal reload error, so a Mod pipeline the bundle cannot compile would take the
 * client down before the first world frame. The gate lives in {@code RenderPipelines.register};
 * this probe checks the rewrite on a synthetic class and on the real shipped registry, and
 * exercises the bundle decision against an index it writes itself.
 */
public final class PipelineGateProbe implements Opcodes {
    private static final String RENDER_PIPELINES = "net/minecraft/client/renderer/RenderPipelines";
    private static final String DESCRIPTOR =
            "(Lcom/mojang/blaze3d/pipeline/RenderPipeline;)Lcom/mojang/blaze3d/pipeline/RenderPipeline;";

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("rewrite")) {
            synthetic();
            real(Path.of(args[1]));
            System.out.println("MCFAO_PIPELINE_GATE_PASS");
            return;
        }
        if (args.length == 3 && args[0].equals("bundle")) {
            bundle(Path.of(args[1]), args[2].equals("open"));
            System.out.println("MCFAO_PIPELINE_BUNDLE_PASS " + args[2]);
            return;
        }
        throw new IllegalArgumentException("usage: rewrite <client.jar> | bundle <dir> known|open");
    }

    private static void synthetic() throws Exception {
        ClassNode node = minimal();
        List<String> adaptations = new ArrayList<>();
        RuntimeLowering.lowerRenderPipelineRegister(node, "synthetic", adaptations);
        require(adaptations.size() == 1, "The rewrite must record exactly one adaptation");
        MethodNode register = method(node);
        require(register.instructions.size() == 4, "The guard body must replace the original body");
        AbstractInsnNode first = register.instructions.getFirst();
        require(first instanceof FieldInsnNode field && field.name.equals("PIPELINES_BY_LOCATION"),
                "The guard must read the registry itself");
        MethodInsnNode call = (MethodInsnNode) register.instructions.get(2);
        require(call.owner.equals(RuntimeLowering.BUNDLED_PIPELINES) && call.name.equals("register"),
                "The guard must delegate to the bundle decision");
        require(verify(node), "The rewritten synthetic method must verify");
        boolean refused = false;
        try {
            ClassNode without = minimal();
            without.methods.clear();
            RuntimeLowering.lowerRenderPipelineRegister(without, "synthetic", new ArrayList<>());
        } catch (RuntimeException expected) {
            refused = true;
        }
        require(refused, "A registry without register() must fail the build");
    }

    private static void real(Path client) throws Exception {
        try (ZipFile jar = new ZipFile(client.toFile())) {
            ZipEntry entry = jar.getEntry(RENDER_PIPELINES + ".class");
            require(entry != null, "The shipped jar must contain the registry");
            ClassNode node = new ClassNode();
            try (InputStream data = jar.getInputStream(entry)) {
                new ClassReader(data.readAllBytes()).accept(node, 0);
            }
            List<String> adaptations = new ArrayList<>();
            RuntimeLowering.lowerRenderPipelineRegister(node, "client", adaptations);
            require(adaptations.size() == 1, "The shipped registry must be rewritten once");
            require(verify(node), "The rewritten shipped method must verify");
        }
        System.out.println("MCFAO_REAL_PIPELINE_GATE_PASS");
    }

    private static void bundle(Path directory, boolean open) throws Exception {
        System.setProperty("org.lwjgl.librarypath", directory.toString());
        RenderPipeline known = pipeline("probe_known");
        RenderPipeline other = pipeline("probe_other");
        if (!open) {
            Path shaders = directory.resolve("fabricaot-shaders");
            Files.createDirectories(shaders);
            String key = (String) shaderIndexKey().invoke(null, known);
            Files.writeString(shaders.resolve("index.json"),
                    "{\"schema\":1,\"programs\":[{\"key\":\"" + key + "\",\"status\":\"TRANSLATED\"}]}\n",
                    StandardCharsets.UTF_8);
        }
        Method supports = Class.forName("fabricaot.metal.BundledPipelines")
                .getDeclaredMethod("supports", RenderPipeline.class);
        supports.setAccessible(true);
        boolean knownSupported = (boolean) supports.invoke(null, known);
        boolean otherSupported = (boolean) supports.invoke(null, other);
        require(knownSupported, open ? "An unreadable bundle must fail open" : "A bundled program must pass");
        require(otherSupported == open, "A program outside the bundle must be refused");
    }

    private static Method shaderIndexKey() throws Exception {
        Class<?> index = Class.forName("fabricaot.metal.ShaderIndex");
        Method key = index.getDeclaredMethod("key", RenderPipeline.class);
        key.setAccessible(true);
        return key;
    }

    private static RenderPipeline pipeline(String location) {
        return RenderPipeline.builder()
                .withLocation(Identifier.fromNamespaceAndPath("mcfao", location))
                .withVertexShader(Identifier.fromNamespaceAndPath("mcfao", location + "_v"))
                .withFragmentShader(Identifier.fromNamespaceAndPath("mcfao", location + "_f"))
                .withVertexFormat(DefaultVertexFormat.POSITION, VertexFormat.Mode.TRIANGLES)
                .build();
    }

    private static MethodNode method(ClassNode node) {
        return node.methods.stream().filter(candidate -> candidate.name.equals("register"))
                .findFirst().orElseThrow();
    }

    private static boolean verify(ClassNode node) throws Exception {
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        ClassNode reparsed = new ClassNode();
        new ClassReader(writer.toByteArray()).accept(reparsed, 0);
        new Analyzer<>(new BasicVerifier()).analyze(reparsed.name, method(reparsed));
        return true;
    }

    private static ClassNode minimal() {
        ClassNode node = new ClassNode();
        node.version = V21;
        node.access = ACC_PUBLIC | ACC_SUPER;
        node.name = RENDER_PIPELINES;
        node.superName = "java/lang/Object";
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_STATIC | ACC_FINAL,
                "PIPELINES_BY_LOCATION", "Ljava/util/Map;", null, null));
        MethodNode register = new MethodNode(ACC_PUBLIC | ACC_STATIC, "register", DESCRIPTOR, null, null);
        var body = register.instructions;
        body.add(new VarInsnNode(ALOAD, 0));
        body.add(new InsnNode(ARETURN));
        register.maxStack = 1;
        register.maxLocals = 1;
        node.methods.add(register);
        return node;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
