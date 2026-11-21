package mcfao.build;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.tree.ClassNode;

public final class ResourceLookupProbe {
    public static InputStream root() {
        String prefix = "/compat";
        return ResourceLookupProbe.class.getResourceAsStream(prefix + "-root.fsh");
    }

    public static InputStream relative() {
        Class<?> owner = ResourceLookupProbe.class;
        String path = "defaults".concat(".json");
        return owner.getResourceAsStream(path);
    }

    public static java.util.List<java.net.URL> enumerate() throws Exception {
        ClassLoader loader = ResourceLookupProbe.class.getClassLoader();
        return Collections.list(loader.getResources("compat-root.fsh"));
    }

    public static InputStream unresolved(boolean branch, String dynamic) {
        String path = branch ? "/compat-root.fsh" : dynamic;
        return ResourceLookupProbe.class.getResourceAsStream(path);
    }

    public static void main(String[] args) throws Exception {
        var node = new ClassNode();
        try (var in = ResourceLookupProbe.class.getResourceAsStream("ResourceLookupProbe.class")) {
            new ClassReader(in).accept(node, 0);
        }
        Map<String, ResourceLookup.Site> sites = ResourceLookup.scan(node).stream()
                .filter(site -> !site.method().startsWith("main("))
                .collect(Collectors.toMap(site -> site.method().split("\\(", 2)[0], Function.identity()));
        if (!"compat-root.fsh".equals(sites.get("root").path())
                || !"mcfao/build/defaults.json".equals(sites.get("relative").path())
                || !"compat-root.fsh".equals(sites.get("enumerate").path())
                || sites.get("unresolved").path() != null) {
            throw new AssertionError("Unexpected resource dataflow: " + sites);
        }
        System.out.println("RESOURCE_LOOKUP_PASS");
        if (args.length == 0) return;
        var fixture = new ClassNode();
        try (var in = ResourceLookupProbe.class.getResourceAsStream("PackStreamFixture.class")) {
            new ClassReader(in).accept(fixture, 0);
        }
        if (ResourceLookup.lowerPackStreams(fixture) != 1 || ResourceLookup.lowerPackStreams(fixture) != 0) {
            throw new AssertionError("Expected one idempotent stream redirection");
        }
        var writer = new ClassWriter(0);
        fixture.accept(writer);
        Files.write(Path.of(args[0]), writer.toByteArray());
    }
}

final class PackStreamFixture {
    public static void main(String[] args) throws Exception {
        for (int i = 0; i < args.length; i += 2) {
            try (var stream = PackStreamFixture.class.getResourceAsStream(args[i])) {
                String actual = stream == null ? "MISSING" : new String(stream.readAllBytes(), StandardCharsets.UTF_8);
                if (!args[i + 1].equals(actual)) throw new AssertionError(args[i] + ": " + actual);
            }
        }
        System.out.println("PACK_STREAM_PASS");
    }
}
