package mcfao.fixture;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import net.fabricmc.api.ClientModInitializer;

public final class GameMod implements ClientModInitializer {
    private static boolean initialized;

    @Override
    public void onInitializeClient() {
        try (var stream = GameMod.class.getResourceAsStream("/assets/mcfao_fixture/proof.txt")) {
            if (stream == null || !new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .equals("mcfao-world-resource-v1\n")) {
                throw new IllegalStateException("Mod resource missing or changed");
            }
        } catch (IOException error) {
            throw new IllegalStateException("Reading mod resource", error);
        }
        initialized = true;
        System.out.println("MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS");
    }

    public static void onWorldJoined() {
        if (!initialized) throw new IllegalStateException("World callback preceded mod initialization");
        System.out.println("MCFAO_F3_CLIENT_WORLD_JOIN_PASS");
    }
}
