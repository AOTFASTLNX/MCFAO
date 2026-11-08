package fabricaot.b0.bootstrap;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class CaptureAgent {
    public static void premain(String ignored, Instrumentation instrumentation) {
        Path output = Path.of(System.getProperty("b0.export")).toAbsolutePath().normalize();
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override public byte[] transform(ClassLoader loader, String name, Class<?> redefined,
                    ProtectionDomain domain, byte[] bytes) {
                if (loader == null || !loader.getClass().getName().contains("Knot")) return null;
                if (!(name.startsWith("fabricaot/b0/") || name.startsWith("net/minecraft/fabricaot_fixture/"))) return null;
                try {
                    Path file = output.resolve(name + ".class").normalize();
                    if (!file.startsWith(output)) throw new IllegalArgumentException("export escaped output");
                    Files.createDirectories(file.getParent());
                    Files.write(file, bytes);
                } catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
                return null;
            }
        }, false);
    }
}
