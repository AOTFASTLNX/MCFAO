import com.google.gson.Gson;
import com.google.gson.JsonSyntaxException;
import com.google.gson.reflect.TypeToken;
import java.io.InputStream;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.EnumMap;
import java.util.HexFormat;
import java.util.List;
import mcfao.aot.ClasspathPackResources;

public final class ResourceMetadataProbe {
    enum Mode { LOW, HIGH }

    static class BaseSettings {
        int distance = 12;
    }

    static final class Settings extends BaseSettings {
        EnumMap<Mode, Integer> levels = new EnumMap<>(Mode.class);
    }

    static Settings load(Gson gson, String data) {
        return gson.fromJson(data, Settings.class);
    }

    static final class Track {
        private final String title;
        Track(String title) { this.title = title; }
    }

    private static final Type TRACKS = new TypeToken<List<Track>>() {}.getType();

    static List<Track> loadTracks(Gson gson, String data) {
        return gson.fromJson(data, TRACKS);
    }

    public static void main(String[] args) throws Exception {
        var parser = new Gson();
        var tracks = loadTracks(parser, "[{\"title\":\"Overworld\"}]");
        if (!"Overworld".equals(tracks.getFirst().title)
                || !"Overworld".equals(loadTracks(parser, parser.toJson(tracks, TRACKS)).getFirst().title)) {
            throw new AssertionError("Generic Gson DTO round trip");
        }
        var initial = load(parser, "{}");
        if (initial.distance != 12 || !initial.levels.isEmpty()) throw new AssertionError("defaults");
        Path config = Files.createTempFile("ncl-compat-", ".json");
        try {
            initial.distance = 29;
            initial.levels.put(Mode.HIGH, 8);
            Files.writeString(config, parser.toJson(initial));
            var actual = load(parser, Files.readString(config));
            if (actual.distance != 29 || actual.levels.get(Mode.HIGH) != 8) {
                throw new AssertionError("Gson round trip");
            }
            try {
                load(parser, "{bad");
                throw new AssertionError("Malformed configuration accepted");
            } catch (JsonSyntaxException expected) {
                // Same failure in the host reference and Native Image.
            }
        } finally {
            Files.delete(config);
        }
        for (int index = 0; index < args.length; index += 2) {
            try (InputStream input = ClasspathPackResources.open(ResourceMetadataProbe.class, "/" + args[index])) {
                if (input == null || !HexFormat.of().formatHex(
                        MessageDigest.getInstance("SHA-256").digest(input.readAllBytes())).equals(args[index + 1])) {
                    throw new AssertionError("Missing or changed resource " + args[index]);
                }
            }
        }
        System.out.println("RESOURCE_METADATA_RUNTIME_PASS");
    }
}
