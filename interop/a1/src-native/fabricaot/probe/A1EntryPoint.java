package fabricaot.probe;

import org.graalvm.nativeimage.IsolateThread;
import org.graalvm.nativeimage.c.function.CEntryPoint;
import org.graalvm.nativeimage.c.type.CCharPointer;
import org.graalvm.nativeimage.c.type.CTypeConversion;

/** Narrow C entry for a future signed iOS harness; no UI or game emulation. */
public final class A1EntryPoint {
    @CEntryPoint(name = "fabricaot_a1_run")
    public static int run(IsolateThread thread, CCharPointer library, CCharPointer scratch) {
        try {
            A1Probe.main(new String[] {CTypeConversion.toJavaString(library), CTypeConversion.toJavaString(scratch)});
            return 0;
        } catch (Throwable failure) {
            failure.printStackTrace();
            return 1;
        }
    }
}
