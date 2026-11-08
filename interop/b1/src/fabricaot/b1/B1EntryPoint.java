package fabricaot.b1;

import org.graalvm.nativeimage.IsolateThread;
import org.graalvm.nativeimage.c.function.CEntryPoint;
import org.graalvm.nativeimage.c.type.CCharPointer;

public final class B1EntryPoint {
    // Keep the already verified native harness ABI; this image executes B1Probe.
    @CEntryPoint(name = "fabricaot_a1_run")
    public static int run(IsolateThread thread, CCharPointer unusedLibrary, CCharPointer unusedScratch) {
        try {
            B1Probe.main(new String[0]);
            return 0;
        } catch (Throwable failure) {
            failure.printStackTrace();
            return 1;
        }
    }
}
