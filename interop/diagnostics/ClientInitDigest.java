import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;

/**
 * First-party semantic digest for the split client build.
 *
 * <p>It boots Minecraft's own registries on a normal JVM and prints a deterministic digest of
 * "static field of {@code Blocks} -> registry id of the block it holds". Running this against the
 * original client jar and against a split jar must produce byte-identical output: that is the only
 * cheap evidence that rewriting {@code Blocks.<clinit>} into a chain of parts preserved the
 * initialisation order and the values it publishes.
 *
 * <p>Reflection is used on purpose so the harness does not depend on an exact API surface of the
 * target version; only public registry lookups are touched. It does not start a game, open a window
 * or touch assets, and it is not a Gate C result.
 */
public final class ClientInitDigest {

    private static long fnv(long hash, String text) {
        for (int i = 0; i < text.length(); i++) {
            hash ^= text.charAt(i) & 0xff;
            hash *= 1099511628211L;
        }
        return hash;
    }

    public static void main(String[] args) throws Exception {
        // Vanilla refuses to bootstrap until the version is known; the launcher normally does this.
        try {
            Class.forName("net.minecraft.SharedConstants").getMethod("tryDetectVersion").invoke(null);
        } catch (NoSuchMethodException missing) {
            Class.forName("net.minecraft.SharedConstants").getMethod("setVersion", String.class)
                    .invoke(null, "26.1.2");
        }
        Class<?> bootstrap = Class.forName("net.minecraft.server.Bootstrap");
        Method bootStrap = bootstrap.getMethod("bootStrap");
        bootStrap.invoke(null);

        Object registry = Class.forName("net.minecraft.core.registries.BuiltInRegistries")
                .getField("BLOCK").get(null);
        // Look the accessor up on the interface: built-in registries are package-private implementations
        // whose inherited methods are not reported by getClass().getMethods().
        Class<?> registryInterface = Class.forName("net.minecraft.core.Registry");
        Method getKey = null;
        for (Method method : registryInterface.getMethods()) {
            // Mojang renamed ResourceLocation to Identifier in this version; accept either name by shape.
            if (method.getName().equals("getKey") && method.getParameterCount() == 1) {
                getKey = method;
                break;
            }
        }
        if (getKey == null) {
            throw new IllegalStateException("registry getKey(1) not found");
        }

        Class<?> blocks = Class.forName("net.minecraft.world.level.block.Blocks");
        List<String> lines = new ArrayList<>();
        for (Field field : blocks.getDeclaredFields()) {
            if (!Modifier.isStatic(field.getModifiers())) {
                continue;
            }
            if (!field.getType().getName().endsWith(".Block")) {
                continue;
            }
            field.setAccessible(true);
            Object value = field.get(null);
            Object key = value == null ? null : getKey.invoke(registry, value);
            lines.add(field.getName() + "=" + key);
        }
        lines.sort(String::compareTo);

        long hash = 1469598103934665603L;
        for (String line : lines) {
            hash = fnv(hash, line);
        }
        System.out.println("blockFields=" + lines.size());
        System.out.println("registryEntries=" + ((java.util.Collection<?>) registryInterface
                .getMethod("keySet").invoke(registry)).size());
        System.out.println("digest=" + Long.toUnsignedString(hash, 16));
        for (int i = 0; i < Math.min(5, lines.size()); i++) {
            System.out.println("sample=" + lines.get(i));
        }
    }
}
