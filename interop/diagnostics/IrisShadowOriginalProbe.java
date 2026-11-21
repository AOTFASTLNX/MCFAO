package mcfao.diagnostics;

public final class IrisShadowOriginalProbe {
    public static void main(String[] args) throws Exception {
        try {
            IrisShadowProbe.main(new String[]{"original"});
            throw new AssertionError("expected original initializer failure");
        } catch (ExceptionInInitializerError failure) {
            Throwable cause = failure.getCause();
            if (!(cause instanceof IllegalArgumentException)
                    || !cause.getMessage().contains("HotSpotDiagnosticMXBean")) throw failure;
            System.out.println("IRIS_ORIGINAL_FAILURE_REPRODUCED " + cause);
        }
    }
}
