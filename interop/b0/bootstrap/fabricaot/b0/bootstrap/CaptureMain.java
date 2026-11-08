package fabricaot.b0.bootstrap;

import net.fabricmc.api.EnvType;
import net.fabricmc.loader.impl.launch.knot.Knot;

public final class CaptureMain {
    public static void main(String[] args) throws Exception {
        Knot knot = new Knot(EnvType.CLIENT);
        ClassLoader target = knot.init(args);
        if (!knot.getMappingConfiguration().getRuntimeNamespace().equals("official"))
            throw new AssertionError("fixture requires official namespace");
        // Deliberately stop before MinecraftGameProvider.launch: no game main/render initialization.
        target.loadClass("fabricaot.b0.ReferenceMain").getMethod("main", String[].class)
            .invoke(null, (Object)new String[0]);
    }
}
