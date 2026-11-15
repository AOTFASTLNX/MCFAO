package fabricaot.probe;

import com.google.gson.JsonParser;
import com.mojang.authlib.minecraft.client.MinecraftClient;
import com.mojang.authlib.minecraft.client.ObjectMapper;
import com.mojang.authlib.yggdrasil.ServicesKeySet;
import com.mojang.authlib.yggdrasil.ServicesKeyType;
import com.mojang.authlib.yggdrasil.YggdrasilServicesKeyInfo;
import com.mojang.authlib.yggdrasil.request.JoinMinecraftServerRequest;
import com.mojang.authlib.yggdrasil.response.*;

import java.net.Proxy;
import java.net.URI;
import java.net.URL;
import java.nio.ByteBuffer;
import java.security.KeyPairGenerator;
import java.util.Base64;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** First-party, synthetic authlib regression. No network, account, or game bootstrap. */
public final class AuthlibJsonProbe {
    private static final UUID ID = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final String PROFILE = "{\"id\":\"00000000000000000000000000000001\","
            + "\"properties\":[{\"name\":\"textures\",\"value\":\"fixture\"}],"
            + "\"profileActions\":[{\"action\":\"FORCED_NAME_CHANGE\"}]}";

    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void joined() {
        HasJoinedMinecraftServerResponse result = ObjectMapper.create().readValue(
                PROFILE, HasJoinedMinecraftServerResponse.class);
        check(ID.equals(result.id()), "joined UUID");
        check(result.properties().size() == 1, "joined properties");
        check(result.profileActions().size() == 1, "joined profile actions");
        check(result.profileActions().iterator().next().type().name().equals("FORCED_NAME_CHANGE"),
                "joined action type");
        System.out.println("AUTHLIB_JOINED_RESPONSE_PASS");
    }

    private static void request() {
        // Only synthetic values are used; neither this payload nor credentials are logged.
        String json = ObjectMapper.create().writeValueAsString(
                new JoinMinecraftServerRequest("fixture-token", ID, "fixture-server"));
        var object = JsonParser.parseString(json).getAsJsonObject();
        check(object.get("accessToken").getAsString().equals("fixture-token"), "join token field");
        check(object.get("selectedProfile").getAsString().equals(
                "00000000000000000000000000000001"), "join profile field");
        check(object.get("serverId").getAsString().equals("fixture-server"), "join server field");
        System.out.println("AUTHLIB_JOIN_REQUEST_PASS");
    }

    private static void responses() {
        ObjectMapper mapper = ObjectMapper.create();
        var profile = mapper.readValue(PROFILE.replace("\"id\":", "\"name\":\"Fixture\",\"id\":"),
                MinecraftProfilePropertiesResponse.class);
        check(ID.equals(profile.id()) && profile.name().equals("Fixture"), "profile response");
        var key = mapper.readValue("{\"keyPair\":{\"privateKey\":\"fixture-private\","
                + "\"publicKey\":\"fixture-public\"},\"publicKeySignatureV2\":\"AQID\","
                + "\"expiresAt\":\"2030-01-01T00:00:00Z\","
                + "\"refreshedAfter\":\"2026-01-01T00:00:00Z\"}", KeyPairResponse.class);
        check(key.keyPair().publicKey().equals("fixture-public"), "nested key pair");
        check(key.publicKeySignature().equals(ByteBuffer.wrap(new byte[]{1, 2, 3})), "key signature");
        check(key.expiresAt().equals("2030-01-01T00:00:00Z"), "key expiration");
        var attrs = mapper.readValue("{\"privileges\":{\"multiplayerServer\":{\"enabled\":true}},"
                + "\"profanityFilterPreferences\":{\"enabled\":false},"
                + "\"banStatus\":{\"bannedScopes\":{\"MULTIPLAYER\":{"
                + "\"banId\":\"00000000000000000000000000000001\","
                + "\"expires\":\"2030-01-01T00:00:00Z\",\"reason\":\"fixture\","
                + "\"reasonMessage\":\"fixture\"}}}}", UserAttributesResponse.class);
        check(attrs.privileges().getMultiplayerServer(), "multiplayer privilege");
        check(!attrs.profanityFilterPreferences().enabled(), "profanity preference");
        check(ID.equals(attrs.banStatus().bannedScopes().get("MULTIPLAYER").banId()), "ban UUID");
        System.out.println("AUTHLIB_ACCOUNT_RESPONSES_PASS");
    }

    private static void keys() throws Exception {
        // Generate a disposable PUBLIC key so the real authlib parses a nonempty key set.
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(1024);
        String publicKey = Base64.getEncoder().encodeToString(generator.generateKeyPair().getPublic().getEncoded());
        String entry = "[{\"publicKey\":\"" + publicKey + "\"}]";
        String payload = "{\"profilePropertyKeys\":" + entry + ",\"playerCertificateKeys\":" + entry + "}";
        AtomicReference<Throwable> failure = new AtomicReference<>();
        MinecraftClient stub = new MinecraftClient(null, Proxy.NO_PROXY) {
            @Override public <T> T get(URL ignored, Class<T> type) {
                try {
                    return ObjectMapper.create().readValue(payload, type);
                } catch (RuntimeException | Error error) {
                    failure.set(error);
                    throw error;
                }
            }
        };
        // The override above handles all requests in memory, before any connection is opened.
        ServicesKeySet keySet = YggdrasilServicesKeyInfo.get(
                URI.create("https://fabricaot.invalid/publickeys").toURL(), stub);
        CompletableFuture<Void> done = new CompletableFuture<>();
        Thread render = new Thread(() -> {
            try {
                check(keySet.keys(ServicesKeyType.PROFILE_PROPERTY).size() == 1, "profile service key");
                check(keySet.keys(ServicesKeyType.PROFILE_KEY).size() == 1, "player service key");
                done.complete(null);
            } catch (Throwable error) {
                done.completeExceptionally(error);
            }
        }, "Render thread");
        render.setDaemon(true);
        render.start();
        try {
            done.get(3, TimeUnit.SECONDS);
        } catch (java.util.concurrent.TimeoutException timeout) {
            Throwable error = failure.get();
            System.err.println("AUTHLIB_SERVICE_KEYS_STALLED fetchFailure="
                    + (error == null ? "none" : error.getClass().getName()));
            if (error != null) error.printStackTrace();
            for (StackTraceElement frame : render.getStackTrace()) System.err.println("  at " + frame);
            throw timeout;
        }
        System.out.println("AUTHLIB_SERVICE_KEYS_PASS");
    }

    public static void main(String[] args) throws Exception {
        switch (args[0]) {
            case "joined" -> joined();
            case "request" -> request();
            case "responses" -> responses();
            case "keys" -> keys();
            default -> throw new IllegalArgumentException("Unknown probe mode");
        }
    }
}
