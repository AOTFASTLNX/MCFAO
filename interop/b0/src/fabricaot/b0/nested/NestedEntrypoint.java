package fabricaot.b0.nested;

import fabricaot.b0.ProbeState;
import net.fabricmc.api.ModInitializer;
import java.nio.charset.StandardCharsets;

public final class NestedEntrypoint implements ModInitializer {
    @Override public void onInitialize() {
        try (var input = getClass().getResourceAsStream("/fabricaot-b0-nested.txt")) {
            if (input == null || !new String(input.readAllBytes(), StandardCharsets.UTF_8).equals("nested-resource-v1\n"))
                throw new AssertionError("nested resource missing or changed");
        } catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
        ProbeState.nestedInitializations++;
    }
}
