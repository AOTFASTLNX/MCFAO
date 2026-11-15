package fabricaot.gl41;

import java.util.concurrent.locks.LockSupport;

/**
 * Fixed-deadline frame limiter for the GL41 renderer.
 *
 * <p>v14 pinned the deadline to whatever the game asked for (120 Hz after the options load).
 * On this device a frame costs roughly 9 ms of GPU time plus the game's own work, so an
 * 8.3 ms deadline is missed every single frame: the limiter never actually waits, the frame
 * rate floats with whatever the scene costs, and the result reads as an unstable 46-86 FPS.
 *
 * <p>This version keeps the absolute-deadline design but picks a target the device can
 * sustain, using a small ladder and two-counter hysteresis:
 *
 * <ul>
 *   <li>frames are consistently late (smoothed interval above the target) - step down;</li>
 *   <li>frames are comfortably early and the 95th percentile also fits - step up;</li>
 *   <li>otherwise stay put, so the rate does not oscillate between two rungs.</li>
 * </ul>
 *
 * <p>Steady state matters more than peak FPS here: 60 FPS with a tight interval looks much
 * smoother than 71 FPS that swings between 46 and 86.
 *
 * <p>Environment: {@code FAOT_PACING=fixed} restores the old behaviour (always target the
 * requested rate), which is useful for A/B comparison on device.
 */
public final class FramePacing {
    private static final long NS_PER_SECOND = 1_000_000_000L;
    private static final long NO_DEADLINE = Long.MIN_VALUE;
    /** Sustainable rates, descending. The limiter never exceeds the requested rate. */
    private static final int[] LADDER = {120, 90, 72, 60, 48, 30};
    /** How long the very first target is held before the ladder is allowed to move. */
    private static final long STARTUP_GRACE_NS = 2 * NS_PER_SECOND;
    /** Reporting and adaptation period. */
    private static final long REPORT_PERIOD_NS = 2 * NS_PER_SECOND;
    /** Consecutive reports needed before moving one rung. */
    private static final int STEPS_TO_MOVE = 2;
    /** Late threshold: smoothed interval above target * LATE_RATIO means step down. */
    private static final double LATE_RATIO = 1.15;
    /** Early threshold: smoothed interval below target * EARLY_RATIO means there is headroom. */
    private static final double EARLY_RATIO = 0.85;
    /** Ring of recent frame intervals used for the reported percentile. */
    private static final int SAMPLE_COUNT = 256;

    private static final boolean ADAPTIVE = !"fixed".equalsIgnoreCase(System.getenv("FAOT_PACING"));

    private static long nextDeadlineNs = NO_DEADLINE;
    private static long lastFrameNs = 0;
    private static long lastReportNs = 0;
    private static long startedNs = 0;
    private static int requestedFps = -1;
    private static int effectiveFps = -1;
    private static int stepsDown = 0;
    private static int stepsUp = 0;
    private static double emaMs = 0;
    private static final double[] samples = new double[SAMPLE_COUNT];
    private static int sampleCount = 0;
    private static int sampleCursor = 0;

    private FramePacing() {}

    /**
     * Waits for an absolute deadline and advances that deadline by one frame interval.
     * Unlike sleeping from the wake-up time, a late wake-up does not shift every later frame.
     *
     * @param fps the rate the game asked for (its frame limit); 0 or less disables pacing
     */
    public static void limitDisplayFPS(int fps) {
        long now = System.nanoTime();
        if (fps <= 0) {
            nextDeadlineNs = NO_DEADLINE;
            return;
        }

        if (fps != requestedFps) adoptRequest(fps, now);
        if (startedNs == 0) startedNs = now;

        observeInterval(now);

        long intervalNs = NS_PER_SECOND / effectiveFps;
        if (nextDeadlineNs == NO_DEADLINE) nextDeadlineNs = now + intervalNs;

        // A long stall must not produce a burst of catch-up frames: re-anchor instead.
        if (now - nextDeadlineNs > intervalNs) nextDeadlineNs = now;

        long waitNs = nextDeadlineNs - now;
        while (waitNs > 0) {
            if (Thread.interrupted()) {
                nextDeadlineNs = now + intervalNs;
                return;
            }
            /* parkNanos oversleeps by several milliseconds on iOS. Park the bulk of the wait
               and spin the last two milliseconds, so the deadline is met within microseconds
               instead of drifting by the scheduler's wake-up granularity. */
            if (waitNs > 3_000_000L) {
                LockSupport.parkNanos(waitNs - 2_000_000L);
            } else {
                Thread.onSpinWait();
            }
            long after = System.nanoTime();
            if (after - nextDeadlineNs > 50_000_000L) break; // clock jump guard
            waitNs = nextDeadlineNs - after;
        }

        nextDeadlineNs += intervalNs;
        if (nextDeadlineNs <= now) nextDeadlineNs = now + intervalNs;

        if (now - lastReportNs >= REPORT_PERIOD_NS) {
            lastReportNs = now;
            reportAndAdapt(now);
        }
    }

    private static void adoptRequest(int fps, long now) {
        requestedFps = fps;
        if (!ADAPTIVE) {
            effectiveFps = fps;
        } else if (effectiveFps <= 0 || effectiveFps > fps) {
            /* Start from the sustainable rung closest to the request instead of the highest
               one: beginning at 120 would spend the first seconds late on every frame. */
            effectiveFps = Math.min(fps, 60);
        }
        nextDeadlineNs = now + NS_PER_SECOND / effectiveFps;
        lastFrameNs = 0;
        emaMs = 0;
        stepsUp = stepsDown = 0;
        System.err.println("[GL41] pacing target=" + effectiveFps + " requested=" + fps
                + " mode=" + (ADAPTIVE ? "adaptive" : "fixed"));
    }

    private static void observeInterval(long now) {
        if (lastFrameNs != 0) {
            double dtMs = (now - lastFrameNs) / 1_000_000.0;
            if (dtMs > 0.2 && dtMs < 250.0) {
                emaMs = emaMs == 0 ? dtMs : emaMs * 0.9 + dtMs * 0.1;
                samples[sampleCursor] = dtMs;
                sampleCursor = (sampleCursor + 1) % SAMPLE_COUNT;
                if (sampleCount < SAMPLE_COUNT) sampleCount++;
            }
        }
        lastFrameNs = now;
    }

    private static void reportAndAdapt(long now) {
        double targetMs = 1000.0 / effectiveFps;
        double p95 = percentile(0.95);
        double max = maximum();
        System.err.println("[GL41] pacing fps=" + effectiveFps + " requested=" + requestedFps
                + " ema=" + fmt(emaMs) + "ms p95=" + fmt(p95) + "ms max=" + fmt(max)
                + "ms steps=" + stepsDown + "down/" + stepsUp + "up");

        if (!ADAPTIVE || now - startedNs < STARTUP_GRACE_NS) return;

        if (emaMs > targetMs * LATE_RATIO) {
            stepsDown++;
            stepsUp = 0;
        } else if (emaMs < targetMs * EARLY_RATIO && p95 <= targetMs) {
            stepsUp++;
            stepsDown = 0;
        } else {
            stepsDown = 0;
            stepsUp = 0;
        }

        if (stepsDown >= STEPS_TO_MOVE) {
            int lower = lowerRung();
            if (lower < 0) {
                stepsDown = 0;
                return;
            }
            System.err.println("[GL41] pacing step down " + effectiveFps + " -> " + lower
                    + " (ema " + fmt(emaMs) + "ms > " + fmt(targetMs * LATE_RATIO) + "ms)");
            applyRung(lower, now);
        } else if (stepsUp >= STEPS_TO_MOVE) {
            int higher = higherRung();
            if (higher < 0) {
                stepsUp = 0;
                return;
            }
            System.err.println("[GL41] pacing step up " + effectiveFps + " -> " + higher
                    + " (ema " + fmt(emaMs) + "ms, p95 " + fmt(p95) + "ms)");
            applyRung(higher, now);
        }
    }

    private static void applyRung(int fps, long now) {
        effectiveFps = fps;
        nextDeadlineNs = now + NS_PER_SECOND / fps;
        stepsUp = stepsDown = 0;
        sampleCount = 0;
        sampleCursor = 0;
        emaMs = 0;
    }

    private static int lowerRung() {
        for (int i = LADDER.length - 1; i >= 0; i--) {
            if (LADDER[i] < effectiveFps && LADDER[i] <= requestedFps) return LADDER[i];
        }
        return -1;
    }

    private static int higherRung() {
        for (int i = 0; i < LADDER.length; i++) {
            if (LADDER[i] > effectiveFps && LADDER[i] <= requestedFps) return LADDER[i];
        }
        return -1;
    }

    private static double percentile(double fraction) {
        if (sampleCount == 0) return emaMs;
        double[] copy = new double[sampleCount];
        System.arraycopy(samples, 0, copy, 0, sampleCount);
        java.util.Arrays.sort(copy);
        int index = (int) Math.round(fraction * (sampleCount - 1));
        if (index < 0) index = 0;
        if (index >= copy.length) index = copy.length - 1;
        return copy[index];
    }

    private static double maximum() {
        if (sampleCount == 0) return emaMs;
        double max = 0;
        for (int i = 0; i < sampleCount; i++) {
            if (samples[i] > max) max = samples[i];
        }
        return max;
    }

    private static String fmt(double value) {
        return String.format(java.util.Locale.ROOT, "%.1f", value);
    }
}
