package mcfao.aot;

import java.lang.management.ManagementFactory;
import static mcfao.aot.OptionalJvmCapabilities.BooleanCapability.*;

public final class OptionalJvmCapabilitiesProbe {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        check(OptionalJvmCapabilities.optionalBoolean(() -> "true") == ENABLED);
        check(OptionalJvmCapabilities.optionalBoolean(() -> "false") == DISABLED);
        check(OptionalJvmCapabilities.optionalBoolean(() -> null) == UNAVAILABLE);
        for (RuntimeException failure : new RuntimeException[] {new IllegalArgumentException(),
                new UnsupportedOperationException(), new SecurityException()}) {
            check(OptionalJvmCapabilities.optionalBoolean(() -> { throw failure; }) == UNAVAILABLE);
        }
        for (RuntimeException failure : new RuntimeException[] {new IllegalStateException(), new NullPointerException()}) {
            try {
                OptionalJvmCapabilities.optionalBoolean(() -> { throw failure; });
                throw new AssertionError("unexpected exception swallowed");
            } catch (RuntimeException actual) { check(actual == failure); }
        }
        Error failure = new ExceptionInInitializerError("real initializer failure");
        try {
            OptionalJvmCapabilities.optionalBoolean(() -> { throw failure; });
            throw new AssertionError("error swallowed");
        } catch (Error actual) { check(actual == failure); }
        check(ManagementFactory.getMemoryMXBean() != null);
        boolean original;
        try {
            var bean = ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class);
            original = bean != null && Boolean.parseBoolean(bean.getVMOption("UseFMA").getValue());
        } catch (IllegalArgumentException | UnsupportedOperationException | SecurityException unavailable) {
            original = false;
        }
        check(OptionalJvmCapabilities.isFmaEnabled() == original);
        System.out.println("OPTIONAL_JVM_CAPABILITIES_PASS " + OptionalJvmCapabilities.hotSpotBooleanOption("UseFMA"));
    }
}
