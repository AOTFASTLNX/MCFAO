package fabricaot.b0;

import net.fabricmc.api.ModInitializer;

public final class ParentEntrypoint implements ModInitializer {
    @Override public void onInitialize() { ProbeState.parentInitializations++; }
}
