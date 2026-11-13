package fabricaot.metal;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.pipeline.RenderPipeline;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * The set of render pipelines the shipped Metal bundle can actually compile.
 *
 * <p>The bundle is translated from vanilla shader sources at build time, so a Mod pipeline that
 * brings its own shaders has no precompiled program. Vanilla's {@code ShaderManager.apply}
 * precompiles <em>every</em> static pipeline during a resource reload and treats a single failure
 * as a fatal reload error - a Mod pipeline it cannot compile would therefore take the whole client
 * down before the first world frame. Registration is the one funnel every pipeline passes through,
 * so a pipeline outside the bundle is refused there: the Mod keeps its object, and the failure
 * surfaces at that pipeline's own draw call instead of breaking shared reload state.
 */
public final class BundledPipelines {
    private static Set<String> keys;
    private static boolean attempted;
    private static final Set<String> reported = new HashSet<>();

    private BundledPipelines() {
    }

    /** Guard installed in front of {@code RenderPipelines.register}. */
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static RenderPipeline register(Map byLocation, RenderPipeline pipeline) {
        if (supports(pipeline)) {
            byLocation.put(pipeline.getLocation(), pipeline);
        } else if (reported.add(pipeline.getLocation().toString())) {
            System.err.println("[MCFAO_SHADER] dropped pipeline " + pipeline.getLocation()
                    + " vertex=" + pipeline.getVertexShader() + " fragment=" + pipeline.getFragmentShader()
                    + " (no precompiled Metal program)");
        }
        return pipeline;
    }

    static synchronized boolean supports(RenderPipeline pipeline) {
        Set<String> known = known();
        return known == null || known.contains(ShaderIndex.key(pipeline));
    }

    private static Set<String> known() {
        if (attempted) {
            return keys;
        }
        attempted = true;
        String directory = System.getProperty("org.lwjgl.librarypath");
        if (directory == null) {
            // Registration also runs before the graphics directory is announced; refusing
            // everything in that window would drop vanilla's own pipelines.
            return null;
        }
        Path index = Path.of(directory).resolve("fabricaot-shaders").resolve("index.json");
        try {
            JsonObject root = JsonParser.parseString(Files.readString(index)).getAsJsonObject();
            Set<String> loaded = new HashSet<>();
            for (JsonElement item : root.getAsJsonArray("programs")) {
                loaded.add(item.getAsJsonObject().get("key").getAsString());
            }
            keys = Set.copyOf(loaded);
            return keys;
        } catch (Exception error) {
            System.err.println("[MCFAO_SHADER] pipeline bundle unreadable, keeping every registration: " + index);
            return null;
        }
    }
}
