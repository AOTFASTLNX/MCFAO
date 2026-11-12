package mcfao.build;

import java.util.List;
import java.util.Map;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;

/**
 * First-party JVM regression for the closed-world Fabric API closure.
 *
 * XaeroLib's three client entrypoints implement both ClientModInitializer and
 * DedicatedServerModInitializer. When the latter interface was absent from the shipped image,
 * Native Image did not fail the build: it made all three classes unlinkable and the client
 * entrypoint dispatch died with NoClassDefFoundError at Minecraft.<init>. This probe proves
 * that the exported API set is complete and that a dual initializer can be linked using only
 * those bytes, with no Fabric Loader jar visible to its defining class loader.
 */
public final class FabricApiClosureProbe implements Opcodes {
    public static void main(String[] args) throws Exception {
        Map<String, byte[]> types = AotExport.fabricApiTypes();
        for (String expected : List.of(
                "net/fabricmc/api/ClientModInitializer.class",
                "net/fabricmc/api/DedicatedServerModInitializer.class",
                "net/fabricmc/api/EnvType.class",
                "net/fabricmc/api/ModInitializer.class")) {
            if (!types.containsKey(expected)) {
                throw new AssertionError("Missing pinned Fabric API type " + expected);
            }
        }
        for (var entry : types.entrySet()) {
            String name = new ClassReader(entry.getValue()).getClassName();
            if (!entry.getKey().equals(name + ".class")) {
                throw new AssertionError("Entry " + entry.getKey() + " holds " + name);
            }
        }

        byte[] dualBytes = dualInitializer();
        var closedWorld = new ClassLoader(FabricApiClosureProbe.class.getClassLoader()) {
            @Override
            protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> found = findLoadedClass(name);
                    if (found == null) {
                        byte[] data = "probe.DualInitializer".equals(name)
                                ? dualBytes : types.get(name.replace('.', '/') + ".class");
                        if (data != null) found = defineClass(name, data, 0, data.length);
                        else found = super.loadClass(name, false);
                    }
                    if (resolve) resolveClass(found);
                    return found;
                }
            }
        };
        Class<?> dual = Class.forName("probe.DualInitializer", true, closedWorld);
        Class<?> clientApi = Class.forName("net.fabricmc.api.ClientModInitializer", false, closedWorld);
        Class<?> serverApi = Class.forName(
                "net.fabricmc.api.DedicatedServerModInitializer", false, closedWorld);
        if (!clientApi.isAssignableFrom(dual) || !serverApi.isAssignableFrom(dual)) {
            throw new AssertionError("Dual initializer lost one of its Fabric API interfaces");
        }
        if (clientApi.getClassLoader() != closedWorld || serverApi.getClassLoader() != closedWorld) {
            throw new AssertionError("Fabric API leaked in from the parent Loader jar");
        }
        System.out.println("MCFAO_FABRIC_API_CLOSURE_PASS types=" + types.size());
    }

    private static byte[] dualInitializer() {
        var writer = new ClassWriter(0);
        writer.visit(V1_8, ACC_PUBLIC | ACC_FINAL, "probe/DualInitializer", null, "java/lang/Object",
                new String[] {"net/fabricmc/api/ClientModInitializer",
                        "net/fabricmc/api/DedicatedServerModInitializer"});
        var constructor = writer.visitMethod(ACC_PUBLIC, "<init>", "()V", null, null);
        constructor.visitCode();
        constructor.visitVarInsn(ALOAD, 0);
        constructor.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        constructor.visitInsn(RETURN);
        constructor.visitMaxs(1, 1);
        constructor.visitEnd();
        for (String method : List.of("onInitializeClient", "onInitializeServer")) {
            var body = writer.visitMethod(ACC_PUBLIC, method, "()V", null, null);
            body.visitCode();
            body.visitInsn(RETURN);
            body.visitMaxs(0, 1);
            body.visitEnd();
        }
        writer.visitEnd();
        return writer.toByteArray();
    }
}
