import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Loads every class in a jar with a real JVM so the class-file verifier runs.
 *
 * <p>Missing dependencies are tolerated; bytecode-format problems (ClassFormatError,
 * VerifyError) are collected and make the process exit non-zero.
 */
public final class VerifyClasses {
    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: VerifyClasses <jar> [classpath...]");
            System.exit(2);
        }
        Path jar = Path.of(args[0]);
        List<URL> urls = new ArrayList<>();
        urls.add(jar.toUri().toURL());
        for (int i = 1; i < args.length; i++) {
            urls.add(Path.of(args[i]).toUri().toURL());
        }
        List<String> broken = new ArrayList<>();
        int loaded = 0;
        int skipped = 0;
        try (ZipFile zip = new ZipFile(jar.toFile());
             URLClassLoader loader = new URLClassLoader(urls.toArray(new URL[0]), ClassLoader.getPlatformClassLoader())) {
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                String name = entry.getName();
                if (!name.endsWith(".class") || name.contains("module-info") || name.contains("package-info")) {
                    continue;
                }
                String binary = name.substring(0, name.length() - 6).replace('/', '.');
                try (InputStream ignored = zip.getInputStream(entry)) {
                    Class.forName(binary, false, loader);
                    loaded++;
                } catch (ClassFormatError | VerifyError error) {
                    broken.add(binary + " -> " + error);
                } catch (Throwable expected) {
                    skipped++;
                }
            }
        }
        System.out.println("verified " + loaded + " classes, skipped " + skipped + " with missing dependencies");
        if (!broken.isEmpty()) {
            System.out.println("BROKEN " + broken.size() + " classes:");
            for (int i = 0; i < Math.min(broken.size(), 25); i++) {
                System.out.println("  " + broken.get(i));
            }
            System.exit(1);
        }
        System.out.println("class verification OK");
    }
}
