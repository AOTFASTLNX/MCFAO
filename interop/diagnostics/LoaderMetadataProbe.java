package mcfao.build;

import java.util.ArrayList;
import java.util.List;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * Checks the rewrite that removes Jade's only Fabric-loader reference: the tooltip's mod-name
 * fallback must become one Entrypoints.optionalModName call, keep its I18n branch, and refuse
 * an unaudited Jade build.
 */
public final class LoaderMetadataProbe {
    private LoaderMetadataProbe() {}

    private static ClassNode clientProxy() {
        var node = new ClassNode();
        node.version = Opcodes.V25;
        node.access = Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER;
        node.name = RuntimeLowering.JADE_CLIENT_PROXY;
        node.superName = "java/lang/Object";
        var getModName = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                "getModName", "(Ljava/lang/String;Z)Ljava/util/Optional;", null, null);
        var body = getModName.instructions;
        // The translated branch: "modmenu.nameTranslation.<id>" through I18n, then Optional.of.
        body.add(new LdcInsnNode("modmenu.nameTranslation.%s"));
        body.add(new VarInsnNode(Opcodes.ALOAD, 0));
        body.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, "java/lang/String", "formatted",
                "([Ljava/lang/Object;)Ljava/lang/String;", false));
        body.add(new VarInsnNode(Opcodes.ASTORE, 2));
        body.add(new VarInsnNode(Opcodes.ALOAD, 2));
        body.add(new MethodInsnNode(Opcodes.INVOKESTATIC,
                "net/minecraft/client/resources/language/I18n", "exists",
                "(Ljava/lang/String;)Z", false));
        body.add(new VarInsnNode(Opcodes.ALOAD, 2));
        body.add(new MethodInsnNode(Opcodes.INVOKESTATIC,
                "net/minecraft/client/resources/language/I18n", "get",
                "(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;", false));
        body.add(new MethodInsnNode(Opcodes.INVOKESTATIC, "java/util/Optional", "of",
                "(Ljava/lang/Object;)Ljava/util/Optional;", false));
        body.add(new InsnNode(Opcodes.ARETURN));
        // The loader fallback that must be cut: getInstance -> getModContainer -> ... -> return.
        body.add(new MethodInsnNode(Opcodes.INVOKESTATIC,
                "net/fabricmc/loader/api/FabricLoader", "getInstance",
                "()Lnet/fabricmc/loader/api/FabricLoader;", false));
        body.add(new VarInsnNode(Opcodes.ALOAD, 1));
        body.add(new MethodInsnNode(Opcodes.INVOKEINTERFACE,
                "net/fabricmc/loader/api/FabricLoader", "getModContainer",
                "(Ljava/lang/String;)Ljava/util/Optional;", true));
        body.add(new TypeInsnNode(Opcodes.NEW, "java/lang/IllegalArgumentException"));
        body.add(new InsnNode(Opcodes.DUP));
        body.add(new LdcInsnNode("loader was reachable"));
        body.add(new MethodInsnNode(Opcodes.INVOKESPECIAL,
                "java/lang/IllegalArgumentException", "<init>", "(Ljava/lang/String;)V", false));
        body.add(new InsnNode(Opcodes.ATHROW));
        // Pinned so the check below can prove the rewrite leaves the surviving branch's
        // javac-computed frame sizes alone (their real value is 5/3).
        getModName.maxStack = 3;
        getModName.maxLocals = 3;
        node.methods.add(getModName);
        return node;
    }

    public static void main(String[] arguments) {
        var adaptations = new ArrayList<String>();
        var node = clientProxy();
        RuntimeLowering.lowerLoaderMetadata(node, RuntimeLowering.JADE_CLIENT_PROXY_SHA256,
                adaptations);

        var getModName = node.methods.stream()
                .filter(method -> method.name.equals("getModName")).findFirst().orElseThrow();
        boolean hasTable = false, hasLoader = false, hasI18n = false, endsWithReturn = false;
        boolean tableTakesTheId = false;
        for (AbstractInsnNode instruction : getModName.instructions) {
            if (instruction instanceof MethodInsnNode call) {
                if (call.owner.equals("mcfao/aot/Entrypoints")
                        && call.name.equals(RuntimeLowering.OPTIONAL_MOD_NAME)) {
                    hasTable = true;
                    // The id is local 0; local 1 is the boolean "modmenu name" flag. Loading 1
                    // here would push an int where the String parameter is declared.
                    tableTakesTheId = instruction.getPrevious() instanceof VarInsnNode load
                            && load.getOpcode() == Opcodes.ALOAD && load.var == 0
                            && call.desc.equals(RuntimeLowering.OPTIONAL_MOD_NAME_DESC);
                }
                if (call.owner.startsWith("net/fabricmc/loader")) hasLoader = true;
                if (call.owner.equals("net/minecraft/client/resources/language/I18n")) hasI18n = true;
            }
            if (instruction instanceof InsnNode simple && simple.getOpcode() == Opcodes.ARETURN
                    && instruction.getNext() == null) endsWithReturn = true;
        }
        require(!hasLoader, "the rewrite must remove every loader reference");
        require(hasTable, "the rewrite must end in the generated table");
        require(tableTakesTheId, "the generated table must be called with the Mod id (ALOAD 0)");
        require(hasI18n, "the I18n translation branch must survive");
        require(endsWithReturn, "the rewrite must end in a return");
        require(adaptations.size() == 1, "the rewrite must record one adaptation, got "
                + adaptations);
        require(getModName.maxStack == 3 && getModName.maxLocals == 3,
                "the rewrite must keep the javac frame sizes (the I18n branch still needs them), got "
                        + getModName.maxStack + "/" + getModName.maxLocals);
        require(getModName.localVariables == null,
                "the rewrite must drop local-variable ranges that end at the removed label");

        var unaudited = clientProxy();
        try {
            RuntimeLowering.lowerLoaderMetadata(unaudited, "deadbeef", new ArrayList<>());
            throw new AssertionError("an unaudited Jade build must be refused");
        } catch (IllegalArgumentException expected) {
            require(expected.getMessage().contains("Unaudited"), "refusal must explain itself");
        }
        System.out.println("MCFAO_LOADER_METADATA_PASS");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
