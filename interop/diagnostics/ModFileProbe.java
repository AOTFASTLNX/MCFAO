package mcfao.build;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;
import mcfao.aot.ModFiles;

/**
 * Checks the "where is my JAR" answer and the rewrite that installs it.
 *
 * <p>Both Xaero entry points dereference the result of the Loader container's origin, which the
 * closed image does not carry; the residue pass answered null and the mod died on the next line.
 * The rewrite must produce {@code ModFiles.modFile(GAME_DIR, id)} and nothing else, and it must
 * refuse a class it was not audited against.
 */
public final class ModFileProbe {
    private ModFileProbe() {}

    public static void main(String[] arguments) {
        Path expected = Path.of("/game/mods/xaeroworldmap.jar");
        require(expected.equals(ModFiles.modFile(Path.of("/game"), "xaeroworldmap")),
                "ModFiles must place the mod below <game>/mods: " + ModFiles.modFile(Path.of("/game"), "xaeroworldmap"));
        require(ModFiles.modFile(null, "xaeroworldmap").endsWith("mods/xaeroworldmap.jar"),
                "A missing launch directory must fall back to the working directory");

        List<String> adaptations = new ArrayList<>();
        ClassNode worldMap = holder(RuntimeLowering.XAERO_WORLDMAP,
                "fetchModFile", "()Ljava/nio/file/Path;");
        MethodNode fetch = method(worldMap, "fetchModFile");
        RuntimeLowering.lowerModFile(worldMap, RuntimeLowering.XAERO_WORLDMAP_SHA256, adaptations);
        assertBody(fetch, "xaeroworldmap", false);

        ClassNode helper = holder(RuntimeLowering.XAERO_PLATFORM_HELPER,
                "getModFile", "(Ljava/lang/String;)Ljava/nio/file/Path;");
        MethodNode modFile = method(helper, "getModFile");
        RuntimeLowering.lowerModFile(helper, RuntimeLowering.XAERO_PLATFORM_HELPER_SHA256, adaptations);
        assertBody(modFile, null, true);

        require(adaptations.size() == 2, "Both call sites must be reported: " + adaptations);

        boolean refused = false;
        try {
            RuntimeLowering.lowerModFile(holder(RuntimeLowering.XAERO_WORLDMAP,
                    "fetchModFile", "()Ljava/nio/file/Path;"), "0".repeat(64), adaptations);
        } catch (IllegalArgumentException expectedFailure) {
            refused = true;
        }
        require(refused, "An unaudited class must be refused, not guessed at");

        System.out.println("MCFAO_MOD_FILE_PASS " + adaptations);
    }

    private static void assertBody(MethodNode method, String literal, boolean fromArgument) {
        List<AbstractInsnNode> body = new ArrayList<>();
        for (AbstractInsnNode node : method.instructions) {
            body.add(node);
        }
        require(body.size() == 4, "Expected four instructions, got " + body.size());
        require(body.get(0) instanceof FieldInsnNode field
                        && field.getOpcode() == Opcodes.GETSTATIC
                        && field.name.equals("GAME_DIR"),
                "The launch directory must come from the hook, not a Loader container");
        if (fromArgument) {
            require(body.get(1) instanceof VarInsnNode load && load.getOpcode() == Opcodes.ALOAD
                    && load.var == 1, "The HUD helper must forward its Mod id argument");
        } else {
            require(body.get(1) instanceof LdcInsnNode literalNode && literal.equals(literalNode.cst),
                    "The world map must pass its own Mod id");
        }
        require(body.get(2) instanceof MethodInsnNode call
                        && call.owner.equals(RuntimeLowering.MOD_FILES)
                        && call.name.equals("modFile")
                        && call.getOpcode() == Opcodes.INVOKESTATIC,
                "The answer must come from ModFiles.modFile");
        require(body.get(3).getOpcode() == Opcodes.ARETURN, "The method must return the path");
    }

    private static ClassNode holder(String name, String method, String descriptor) {
        ClassNode node = new ClassNode();
        node.version = Opcodes.V17;
        node.name = name;
        node.superName = "java/lang/Object";
        MethodNode body = new MethodNode(Opcodes.ACC_PUBLIC, method, descriptor, null, null);
        body.maxStack = 1;
        body.maxLocals = descriptor.contains("String") ? 2 : 1;
        body.instructions.add(new InsnNode(Opcodes.ACONST_NULL));
        body.instructions.add(new InsnNode(Opcodes.ARETURN));
        node.methods.add(body);
        return node;
    }

    private static MethodNode method(ClassNode node, String name) {
        return node.methods.stream().filter(candidate -> candidate.name.equals(name))
                .findFirst().orElseThrow(AssertionError::new);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
