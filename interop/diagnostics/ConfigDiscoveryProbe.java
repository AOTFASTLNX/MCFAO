package mcfao.build;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.BasicVerifier;

/**
 * Contract for the {@code @FrameworkConfig} table.
 *
 * <p>{@code FabricConfigHelper.getAllFrameworkConfigs()} is the only place the framework learns
 * which configs exist, and it learns it from Mod metadata the image does not have. The export
 * replaces it with a generated table, so two things must hold: the generated classes must carry
 * exactly the declared ids/types/separators with the config instance loaded by {@code GETSTATIC},
 * and the shipped helper's method must call that table and nothing else.
 */
public final class ConfigDiscoveryProbe implements Opcodes {
    private static final String HELPER = "com/mrcrayfish/framework/platform/FabricConfigHelper";

    public static void main(String[] args) throws Exception {
        table();
        annotation();
        rewritten(java.nio.file.Path.of(args[0]));
        System.out.println("MCFAO_CONFIG_DISCOVERY_PASS");
    }

    private static void table() throws Exception {
        List<String[]> entries = new ArrayList<>();
        entries.add(new String[]{"probe/Owner", "CONFIG", "Lprobe/Owner;", "probe_id",
                "Probe Name", "true", "SERVER_SYNC", ";"});
        ClassNode node = parse(RuntimeLowering.frameworkConfigsClass(entries));
        require(node.name.equals(RuntimeLowering.CONFIG_TABLE), "The table must be generated");
        MethodNode init = method(node, "<clinit>");
        int created = 0;
        int instance = 0;
        boolean pair = false;
        String id = null;
        String name = null;
        String type = null;
        String separator = null;
        for (AbstractInsnNode instruction : init.instructions) {
            if (instruction instanceof org.objectweb.asm.tree.TypeInsnNode alloc
                    && alloc.getOpcode() == NEW
                    && alloc.desc.equals(RuntimeLowering.CONFIG_ANNOTATION)) created++;
            if (instruction instanceof FieldInsnNode field && field.getOpcode() == GETSTATIC) {
                if (field.owner.equals("probe/Owner") && field.name.equals("CONFIG")) instance++;
                if (field.owner.equals(RuntimeLowering.CONFIG_TYPE)) type = field.name;
            }
            if (instruction instanceof LdcInsnNode constant) {
                if ("probe_id".equals(constant.cst)) id = (String) constant.cst;
                if ("Probe Name".equals(constant.cst)) name = (String) constant.cst;
                if (Integer.valueOf((int) ';').equals(constant.cst)) separator = ";";
            }
            if (instruction instanceof MethodInsnNode call
                    && call.owner.equals("org/apache/commons/lang3/tuple/Pair") && call.name.equals("of")) {
                pair = true;
            }
        }
        require(created == 1, "Each entry must build one annotation instance");
        require(instance == 1, "Each entry must read the config field directly");
        require(pair, "The framework consumes Pair.of(annotation, instance)");
        require("probe_id".equals(id) && "Probe Name".equals(name), "The annotation values must ship");
        require("SERVER_SYNC".equals(type), "The declared config type must ship");
        require(separator != null, "The declared separator must ship");
        MethodNode all = method(node, "all");
        require(all.instructions.size() == 2, "all() must return the constant table");
        AbstractInsnNode first = all.instructions.getFirst();
        require(first instanceof FieldInsnNode constant && constant.name.equals("ALL"),
                "all() must read the generated constant");
        verify(node, all);
    }

    private static void annotation() {
        ClassNode node = parse(RuntimeLowering.frameworkConfigAnnotationClass());
        require(node.interfaces.contains(RuntimeLowering.FRAMEWORK_CONFIG),
                "The table hands the framework a real annotation instance");
        String[][] members = {{"id", "()Ljava/lang/String;"}, {"name", "()Ljava/lang/String;"},
                {"readOnly", "()Z"}, {"type", "()L" + RuntimeLowering.CONFIG_TYPE + ";"},
                {"separator", "()C"}, {"annotationType", "()Ljava/lang/Class;"}};
        for (String[] member : members) {
            require(node.methods.stream().anyMatch(candidate -> candidate.name.equals(member[0])
                    && candidate.desc.equals(member[1])), "Missing annotation member " + member[0]);
        }
    }

    private static void rewritten(java.nio.file.Path client) throws Exception {
        try (ZipFile jar = new ZipFile(client.toFile())) {
            ZipEntry entry = jar.getEntry(HELPER + ".class");
            require(entry != null, "The shipped jar must contain the config helper");
            ClassNode node = new ClassNode();
            try (InputStream data = jar.getInputStream(entry)) {
                new ClassReader(data.readAllBytes()).accept(node, 0);
            }
            List<String> adaptations = new ArrayList<>();
            RuntimeLowering.lowerConfigDiscovery(node, adaptations);
            require(adaptations.size() == 1, "The helper must be rewritten once");
            MethodNode discovery = method(node, RuntimeLowering.CONFIG_DISCOVERY);
            require(discovery.instructions.size() == 2, "The scan must collapse to a table lookup");
            require(discovery.instructions.getFirst() instanceof MethodInsnNode call
                    && call.owner.equals(RuntimeLowering.CONFIG_TABLE) && call.name.equals("all"),
                    "The scan must read the generated table");
            verify(node, discovery);
        }
    }

    private static MethodNode method(ClassNode node, String name) {
        return node.methods.stream().filter(candidate -> candidate.name.equals(name)).findFirst()
                .orElseThrow(() -> new IllegalStateException("Missing " + name + " in " + node.name));
    }

    private static ClassNode parse(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static void verify(ClassNode node, MethodNode method) throws Exception {
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        ClassNode reparsed = new ClassNode();
        new ClassReader(writer.toByteArray()).accept(reparsed, 0);
        new Analyzer<>(new BasicVerifier()).analyze(reparsed.name, method(reparsed, method.name));
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
