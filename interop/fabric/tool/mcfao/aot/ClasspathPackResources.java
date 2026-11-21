package mcfao.aot;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/** Stream access to unique classpath entries stored in the individual Fabric pack layers. */
public final class ClasspathPackResources {
    public static final String INDEX = "mcfao/classpath-pack-resources.tsv";

    private ClasspathPackResources() {}

    public static InputStream open(Class<?> owner, String name) {
        if (name != null && (name.startsWith("/assets/") || name.startsWith("/data/"))
                && !owner.getModule().isNamed()
                && owner.getClassLoader() == ClasspathPackResources.class.getClassLoader()) {
            String path = Index.ENTRIES.get(name.substring(1));
            if (path != null) {
                InputStream stream = ClasspathPackResources.class.getResourceAsStream("/" + path);
                if (stream == null) throw new IllegalStateException("Missing indexed classpath resource " + path);
                return stream;
            }
        }
        return owner.getResourceAsStream(name);
    }

    private static final class Index {
        private static final Map<String, String> ENTRIES = read();

        private static Map<String, String> read() {
            InputStream stream = ClasspathPackResources.class.getResourceAsStream("/" + INDEX);
            if (stream == null) throw new IllegalStateException("Missing classpath pack index " + INDEX);
            try (var reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                var entries = new HashMap<String, String>();
                for (String line; (line = reader.readLine()) != null; ) {
                    int separator = line.indexOf('	');
                    if (separator <= 0 || separator == line.length() - 1) {
                        throw new IllegalStateException("Malformed classpath pack index");
                    }
                    if (entries.putIfAbsent(line.substring(0, separator), line.substring(separator + 1)) != null) {
                        throw new IllegalStateException("Duplicate classpath pack index entry");
                    }
                }
                return Map.copyOf(entries);
            } catch (IOException failure) {
                throw new IllegalStateException("Cannot read classpath pack index", failure);
            }
        }
    }
}
