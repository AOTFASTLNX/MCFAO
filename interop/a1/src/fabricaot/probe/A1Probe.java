package fabricaot.probe;

import java.io.InputStream;
import java.lang.ref.WeakReference;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/** First-party semantic probe; contains no Minecraft, Fabric, or JavaFX code. */
public final class A1Probe {
    private static final ScopedValue<String> SCOPE = ScopedValue.newInstance();
    private static native int add(int a, int b);
    private static native String echo(String text);

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        System.out.println("PASS " + label);
    }

    private static WeakReference<byte[]> garbage() {
        return new WeakReference<>(new byte[1024 * 1024]);
    }

    public static void main(String[] args) throws Exception {
        check(Runtime.version().feature() == 25, "exact-java-25");
        if (args.length != 2) throw new IllegalArgumentException("native-library absolute-path, scratch-directory required");
        System.out.println("runtime=" + System.getProperty("java.runtime.version"));
        System.out.println("os=" + System.getProperty("os.name") + "/" + System.getProperty("os.arch"));
        AtomicInteger sum = new AtomicInteger();
        var threads = new ArrayList<Thread>();
        Runnable worker = () -> ScopedValue.where(SCOPE, "java25").run(() -> {
            if (!SCOPE.get().equals("java25")) throw new AssertionError("ScopedValue");
            sum.incrementAndGet();
        });
        for (int i = 0; i < 4; i++) {
            threads.add(Thread.ofPlatform().start(worker));
            threads.add(Thread.ofVirtual().start(worker));
        }
        for (Thread thread : threads) {
            thread.join(5000);
            check(!thread.isAlive(), "thread-joined");
        }
        check(sum.get() == 8 && !SCOPE.isBound(), "threads-and-java25-scoped-values");
        WeakReference<byte[]> weak = garbage();
        for (int i = 0; i < 40 && weak.get() != null; i++) {
            System.gc();
            Thread.sleep(10);
        }
        check(weak.get() == null, "gc-reclaims-unreachable-array");
        try (InputStream resource = A1Probe.class.getResourceAsStream("/fabricaot/probe/probe.txt")) {
            check(resource != null && new String(resource.readAllBytes(), StandardCharsets.UTF_8)
                    .equals("fabricaot-a1-resource-v1\n"), "embedded-resource");
        }
        Path nativeLibrary = Path.of(args[0]);
        check(nativeLibrary.isAbsolute(), "explicit-native-library-path");
        // This library is compiled beforehand, never generated at run time.
        // An iOS harness must embed and codesign it with the app before install.
        System.load(nativeLibrary.toString());
        check(add(20, 22) == 42, "jni-integer-call");
        check("资源-Java25".equals(echo("资源-Java25")), "jni-unicode-roundtrip");
        Path scratch = Path.of(args[1]);
        Files.createDirectories(scratch);
        Path temporary = scratch.resolve("probe.tmp");
        Path saved = scratch.resolve("probe.txt");
        Files.writeString(temporary, "a1-persistence-v1\n");
        Files.move(temporary, saved, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        check(Files.readString(saved).equals("a1-persistence-v1\n"), "file-write-atomic-move-read");
        System.out.println("A1_SEMANTICS_PASS");
    }
}
