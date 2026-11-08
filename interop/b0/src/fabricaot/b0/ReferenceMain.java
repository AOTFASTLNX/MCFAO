package fabricaot.b0;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.loader.api.FabricLoader;

public final class ReferenceMain {
    public static void main(String[] args) throws Exception {
        FabricLoader loader = FabricLoader.getInstance();
        if (!loader.isModLoaded("fabricaot_b0_nested")) throw new AssertionError("nested JAR not discovered");
        var entrypoints = loader.getEntrypoints("main", ModInitializer.class);
        if (entrypoints.size() != 2) throw new AssertionError("unexpected main entrypoints: " + entrypoints.size());
        for (ModInitializer initializer : entrypoints) initializer.onInitialize();
        Behavior.verify();
        System.out.println("B0_REFERENCE_PASS");
    }
}
