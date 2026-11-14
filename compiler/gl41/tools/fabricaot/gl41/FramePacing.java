package fabricaot.gl41;

import java.util.concurrent.locks.LockSupport;

/** Fixed-deadline frame limiter for the GL41 renderer. */
public final class FramePacing {
    private static final long NANOS_PER_SECOND = 1_000_000_000L;
    private static final long NO_DEADLINE = Long.MIN_VALUE;
    /* The full-frame OSMesa readback cannot hold 120 FPS on device; cap the steady state
       at a rate the GL41 renderer can deliver without frame drops. Lower in-game choices
       are still honoured. */
    private static final int STABLE_FPS_CAP = 60;

    private static long nextDeadlineNs = NO_DEADLINE;
    private static int currentFps;
    private static int reportedCap;

    private FramePacing() {}

    /**
     * Waits for an absolute deadline and advances that deadline by one frame interval.
     * Unlike sleeping from the wake-up time, a late wake-up does not shift every later frame.
     */
    public static void limitDisplayFPS(int fps) {
        if (fps <= 0) return;
        if (fps > STABLE_FPS_CAP) {
            if (reportedCap != STABLE_FPS_CAP) {
                reportedCap = STABLE_FPS_CAP;
                System.err.println("[GL41] frame limiter caps " + fps + " fps at a stable "
                        + STABLE_FPS_CAP + " fps");
            }
            fps = STABLE_FPS_CAP;
        } else if (reportedCap != 0) {
            reportedCap = 0;
        }
        long intervalNs = NANOS_PER_SECOND / fps;
        long now = System.nanoTime();
        if (fps != currentFps || nextDeadlineNs == NO_DEADLINE) {
            currentFps = fps;
            nextDeadlineNs = now + intervalNs;
            System.err.println("[GL41] frame limiter=fixed-timeline fps=" + fps
                    + " intervalNs=" + intervalNs);
        }

        // A long stall must not produce a burst of catch-up frames.
        if (now - nextDeadlineNs > intervalNs) nextDeadlineNs = now;
        long waitNs = nextDeadlineNs - now;
        while (waitNs > 0) {
            if (Thread.interrupted()) {
                nextDeadlineNs = now + intervalNs;
                return;
            }
            if (waitNs > 1_000_000L) {
                LockSupport.parkNanos(waitNs - 500_000L);
            } else {
                Thread.onSpinWait();
            }
            now = System.nanoTime();
            waitNs = nextDeadlineNs - now;
        }

        nextDeadlineNs += intervalNs;
        if (nextDeadlineNs <= now) nextDeadlineNs = now + intervalNs;
    }
}
