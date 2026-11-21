package mcfao.aot;

import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;
import java.util.function.Supplier;

/** Optional HotSpot optimizations; never changes the platform management API. */
public final class OptionalJvmCapabilities {
    public enum BooleanCapability { ENABLED, DISABLED, UNAVAILABLE }

    private OptionalJvmCapabilities() {}

    public static BooleanCapability hotSpotBooleanOption(String name) {
        return optionalBoolean(() -> {
            HotSpotDiagnosticMXBean bean =
                    ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
            return bean == null ? null : bean.getVMOption(name).getValue();
        });
    }

    public static boolean isFmaEnabled() {
        return hotSpotBooleanOption("UseFMA") == BooleanCapability.ENABLED;
    }

    // Also exercises absent beans and option-query failures without replacing ManagementFactory.
    static BooleanCapability optionalBoolean(Supplier<String> query) {
        try {
            String value = query.get();
            if (value == null) return BooleanCapability.UNAVAILABLE;
            return Boolean.parseBoolean(value) ? BooleanCapability.ENABLED : BooleanCapability.DISABLED;
        } catch (IllegalArgumentException | UnsupportedOperationException | SecurityException unavailable) {
            return BooleanCapability.UNAVAILABLE;
        }
    }
}
