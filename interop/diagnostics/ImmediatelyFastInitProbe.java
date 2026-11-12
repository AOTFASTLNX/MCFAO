package mcfao.build;

import java.io.File;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * First-party JVM regression for ImmediatelyFast's build-time-only Mixin plugin side effect.
 *
 * The plugin's onLoad() calls ImmediatelyFast.earlyInit() inside Knot while Mixins are applied.
 * The plugin is not shipped, so the image reached RenderSystem.initRenderer with config == null.
 * This probe proves that (a) the plugin is audited and its earlyInit is replayed by the generated
 * client dispatch, and (b) the version lookup behind earlyInit reports the real build snapshot
 * instead of the residue stub's Optional.empty().
 */
public final class ImmediatelyFastInitProbe implements Opcodes {
    public static boolean earlyInitCalled;

    public static void mark() {
        earlyInitCalled = true;
    }

    public static void main(String[] args) throws Exception {
        var found = new TreeSet<String>();
        var adaptations = new ArrayList<String>();
        RuntimeLowering.collectMixinPluginEarlyInit(
                RuntimeLowering.IF_PLUGIN + ".class", pluginClass(true),
                RuntimeLowering.IF_PLUGIN_SHA256, found, adaptations);
        expect(found.equals(Set.of(RuntimeLowering.IF_MAIN + "#earlyInit")),
                "audited plugin did not yield the earlyInit replay");
        expect(adaptations.stream().anyMatch(text -> text.contains("earlyInit")),
                "plugin audit was not recorded");
        RuntimeLowering.collectMixinPluginEarlyInit("mod/UnrelatedPlugin.class",
                pluginClass(true), "not-the-plugin-hash", found, adaptations);
        expect(found.size() == 1, "an unrelated plugin changed the replay set");
        expectRejected(() -> RuntimeLowering.collectMixinPluginEarlyInit(
                RuntimeLowering.IF_PLUGIN + ".class", pluginClass(false),
                RuntimeLowering.IF_PLUGIN_SHA256, new TreeSet<>(), new ArrayList<>()),
                "onLoad without earlyInit");
        expectRejected(() -> RuntimeLowering.collectMixinPluginEarlyInit(
                RuntimeLowering.IF_PLUGIN + ".class", pluginClass(true),
                "deadbeef", new TreeSet<>(), new ArrayList<>()),
                "unaudited plugin fingerprint");

        byte[] hooksCode = generatedHooks(found);
        var hooks = new ClassNode();
        new ClassReader(hooksCode).accept(hooks, 0);
        var start = hooks.methods.stream().filter(m -> m.name.equals("startClient")).findFirst().orElseThrow();
        boolean replayed = false;
        for (var instruction : start.instructions) {
            if (instruction instanceof MethodInsnNode call && call.owner.equals(RuntimeLowering.IF_MAIN)
                    && call.name.equals("earlyInit") && call.desc.equals("()V")) replayed = true;
        }
        expect(replayed, "generated startClient does not replay earlyInit");
        expect(hooks.methods.stream().anyMatch(m -> m.name.equals(RuntimeLowering.OPTIONAL_VERSION)
                && m.desc.equals(RuntimeLowering.OPTIONAL_VERSION_DESC)),
                "generated hooks lack optionalModVersion");

        Map<String, byte[]> definitions = Map.of(
                "mcfao.aot.Entrypoints", hooksCode,
                RuntimeLowering.IF_PLATFORM.replace('/', '.'), loweredPlatform(),
                RuntimeLowering.IF_MAIN.replace('/', '.'), mainClass());
        var loader = new ClassLoader(ImmediatelyFastInitProbe.class.getClassLoader()) {
            @Override
            protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> loaded = findLoadedClass(name);
                    if (loaded == null) {
                        byte[] data = definitions.get(name);
                        loaded = data != null ? defineClass(name, data, 0, data.length)
                                : super.loadClass(name, false);
                    }
                    if (resolve) resolveClass(loaded);
                    return loaded;
                }
            }
        };
        Class<?> entrypoints = Class.forName("mcfao.aot.Entrypoints", true, loader);
        Method optional = entrypoints.getMethod(RuntimeLowering.OPTIONAL_VERSION, String.class);
        expect(Optional.of("1.15.2+26.1.2").equals(optional.invoke(null, "immediatelyfast")),
                "present Mod must report its build snapshot version");
        expect(Optional.empty().equals(optional.invoke(null, "iris")),
                "absent Mod must report Optional.empty");
        Class<?> platform = Class.forName(
                RuntimeLowering.IF_PLATFORM.replace('/', '.'), true, loader);
        Method version = platform.getMethod("getModVersion", String.class);
        expect(Optional.of("1.15.2+26.1.2").equals(version.invoke(null, "immediatelyfast")),
                "lowered getModVersion lost the real version");
        expect(Optional.empty().equals(version.invoke(null, "iris")),
                "residue stub replaced the optional lookup");
        entrypoints.getMethod("startClient", File.class, Object.class).invoke(null, null, null);
        expect(earlyInitCalled, "startClient did not execute earlyInit");
        System.out.println("MCFAO_IMMEDIATELYFAST_EARLY_INIT_PASS");
    }

    private static byte[] generatedHooks(Set<String> earlyInitializers) throws Exception {
        Method hooks = AotExport.class.getDeclaredMethod("staticHooks", List.class, Set.class,
                Map.class, Map.class, Set.class, Map.class, Map.class, Map.class, Set.class);
        hooks.setAccessible(true);
        return (byte[]) hooks.invoke(null, List.of(), Set.of("immediatelyfast"), Map.of(), Map.of(),
                Set.of(), Map.of("immediatelyfast", "1.15.2+26.1.2", "minecraft", "26.1.2"),
                Map.of(), Map.of(), earlyInitializers);
    }

    /** A PlatformCodeImpl whose original Loader chain would have been stubbed to Optional.empty. */
    private static byte[] loweredPlatform() throws Exception {
        var node = new ClassNode();
        node.version = V25;
        node.access = ACC_PUBLIC;
        node.name = RuntimeLowering.IF_PLATFORM;
        node.superName = "java/lang/Object";
        var method = new MethodNode(ACC_PUBLIC | ACC_STATIC, "getModVersion",
                RuntimeLowering.OPTIONAL_VERSION_DESC, null, null);
        method.instructions.add(new MethodInsnNode(INVOKESTATIC,
                "net/fabricmc/loader/api/FabricLoader", "getInstance",
                "()Lnet/fabricmc/loader/api/FabricLoader;", true));
        method.instructions.add(new VarInsnNode(ALOAD, 0));
        method.instructions.add(new MethodInsnNode(INVOKEINTERFACE,
                "net/fabricmc/loader/api/FabricLoader", "getModContainer",
                "(Ljava/lang/String;)Ljava/util/Optional;", true));
        method.instructions.add(new InsnNode(ARETURN));
        method.maxStack = 2;
        method.maxLocals = 1;
        node.methods.add(method);
        var adaptations = new ArrayList<String>();
        RuntimeLowering.lowerImmediatelyFastVersion(node, RuntimeLowering.IF_PLATFORM_SHA256, adaptations);
        RuntimeLowering.lowerQueries(node, Set.of(), Map.of(), new ArrayList<>(),
                new TreeSet<>(), Set.of());
        expect(adaptations.stream().anyMatch(text -> text.contains("build snapshot")),
                "version lookup was not folded");
        return AotExport.generatedClassBytes(node);
    }

    private static byte[] pluginClass(boolean withEarlyInit) {
        var writer = new ClassWriter(0);
        writer.visit(V1_8, ACC_PUBLIC, RuntimeLowering.IF_PLUGIN, null, "java/lang/Object", null);
        var onLoad = writer.visitMethod(ACC_PUBLIC, "onLoad", "(Ljava/lang/String;)V", null, null);
        onLoad.visitCode();
        if (withEarlyInit) {
            onLoad.visitMethodInsn(INVOKESTATIC, RuntimeLowering.IF_MAIN, "earlyInit", "()V", false);
        }
        onLoad.visitInsn(RETURN);
        onLoad.visitMaxs(0, 2);
        onLoad.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static byte[] mainClass() {
        var writer = new ClassWriter(0);
        writer.visit(V1_8, ACC_PUBLIC, RuntimeLowering.IF_MAIN, null, "java/lang/Object", null);
        var init = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "earlyInit", "()V", null, null);
        init.visitCode();
        init.visitMethodInsn(INVOKESTATIC, "mcfao/build/ImmediatelyFastInitProbe", "mark", "()V", false);
        init.visitInsn(RETURN);
        init.visitMaxs(0, 0);
        init.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static void expectRejected(Runnable action, String label) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected rejection: " + label);
    }

    private static void expect(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
