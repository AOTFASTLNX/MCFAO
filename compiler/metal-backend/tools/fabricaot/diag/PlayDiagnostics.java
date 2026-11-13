package fabricaot.diag;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Build-time-injected, runtime-switchable diagnostics for the Configuration to Play transition.
 *
 * <p>This class is not a Mod and does not change any protocol state. The Metal injector prepends
 * the calls below to the real client methods and ships this one class in the transformed JAR.
 * Every hook is a no-op when diagnostics are disabled.
 *
 * <p>Enable with {@code -Dmcfao.diag.play=true} (the default) and disable with
 * {@code -Dmcfao.diag.play=false}. The optional {@code -Dmcfao.diag.stallSeconds=N} controls when
 * a full Java thread dump is written after a level-load state has stopped progressing.
 */
public final class PlayDiagnostics implements Runnable {
    private static final boolean ENABLED =
            !"false".equals(System.getProperty("mcfao.diag.play", "true"));
    private static final int STALL_SECONDS = integer("mcfao.diag.stallSeconds", 35);
    private static final int HEARTBEAT_MILLIS = integer("mcfao.diag.heartbeatMillis", 2000);
    private static final long START_NANOS = System.nanoTime();
    private static final PlayDiagnostics INSTANCE = new PlayDiagnostics();
    private static final Object LOCK = new Object();

    private static final AtomicLong SEQ = new AtomicLong();
    private static final AtomicLong TICKS = new AtomicLong();
    private static final AtomicLong CHUNK_PACKETS = new AtomicLong();
    private static final AtomicLong CHUNKS_DECODED = new AtomicLong();
    private static final AtomicLong BATCHES = new AtomicLong();
    private static final AtomicLong BATCH_CHUNKS = new AtomicLong();
    private static final AtomicLong CLIENT_POSITIONS = new AtomicLong();
    private static final AtomicLong SERVER_POSITIONS = new AtomicLong();
    private static final AtomicLong SECTION_CHECKS = new AtomicLong();
    private static final AtomicLong SECTION_VISIBLE = new AtomicLong();
    private static final AtomicLong SECTION_CALLS = new AtomicLong();
    private static final AtomicLong LAST_TICK_NANOS = new AtomicLong();
    private static final AtomicLong LAST_PACKET_NANOS = new AtomicLong();
    private static final AtomicLong LAST_SECTION_NANOS = new AtomicLong();

    private static volatile String trackerState = "none";
    private static volatile long trackerChangedNanos = System.nanoTime();
    private static volatile String sectionPosition = "?";
    private static volatile boolean sectionWasVisible;
    private static volatile boolean watchdogStarted;
    private static long lastTrackerLogNanos;
    private static long lastReadyLogNanos;
    private static long lastSectionLogNanos;
    private static long lastStallDumpNanos;
    private static boolean stallDumped;

    private PlayDiagnostics() {}

    private static int integer(String property, int fallback) {
        try {
            return Integer.parseInt(System.getProperty(property, Integer.toString(fallback)));
        } catch (NumberFormatException error) {
            return fallback;
        }
    }

    private static long now() {
        return System.nanoTime();
    }

    private static long since(AtomicLong value) {
        long then = value.get();
        return then == 0 ? -1 : (now() - then) / 1_000_000L;
    }

    private static String text(Object value) {
        if (value == null) return "null";
        String rendered = value.toString();
        return rendered.length() <= 320 ? rendered : rendered.substring(0, 320) + "…";
    }

    private static String error(Throwable value) {
        if (value == null) return "null";
        String rendered = value.toString();
        Throwable cause = value.getCause();
        if (cause != null && cause != value) rendered += " causedBy=" + cause;
        return rendered.length() <= 900 ? rendered : rendered.substring(0, 900) + "…";
    }

    private static void log(String event, String fields) {
        if (!ENABLED) return;
        String line = "[MCFAO_DIAG] event=" + event + " seq=" + SEQ.incrementAndGet()
                + " upMs=" + (now() - START_NANOS) / 1_000_000L
                + " wall=" + Instant.now()
                + " thread=" + Thread.currentThread().getName()
                + (fields.isEmpty() ? "" : " " + fields);
        synchronized (LOCK) {
            System.out.println(line);
            System.out.flush();
        }
    }

    // ---- hooks called by bytecode injected into the real client -------------------------------

    public static void tick() {
        if (!ENABLED) return;
        TICKS.incrementAndGet();
        LAST_TICK_NANOS.set(now());
        startWatchdog();
        maybeDumpStall();
    }

    public static void login(Object packet) {
        if (!ENABLED) return;
        trackerState = "login";
        trackerChangedNanos = now();
        log("configuration_to_play", "state=PLAY_LOGIN packet=" + text(packet));
    }

    public static void chunk(int x, int z) {
        if (!ENABLED) return;
        long count = CHUNK_PACKETS.incrementAndGet();
        LAST_PACKET_NANOS.set(now());
        if (count <= 24 || count % 64 == 0) {
            log("chunk_received", "x=" + x + " z=" + z + " packets=" + count
                    + " decoded=" + CHUNKS_DECODED.get());
        }
    }

    public static void chunkDecode(int x, int z) {
        if (!ENABLED) return;
        long count = CHUNKS_DECODED.incrementAndGet();
        if (count <= 16 || count % 128 == 0) {
            log("chunk_decoded", "x=" + x + " z=" + z + " decoded=" + count);
        }
    }

    public static void batchStart() {
        if (!ENABLED) return;
        long count = BATCHES.incrementAndGet();
        if (count <= 8 || count % 32 == 0) {
            log("chunk_batch_start", "batches=" + count + " packets=" + CHUNK_PACKETS.get());
        }
    }

    public static void batch(int size) {
        if (!ENABLED) return;
        long total = BATCH_CHUNKS.addAndGet(Math.max(0, size));
        if (BATCHES.get() <= 8 || total <= 128 || total % 256 == 0) {
            log("chunk_batch_finished", "size=" + size + " chunks=" + total
                    + " batches=" + BATCHES.get() + " received=" + CHUNK_PACKETS.get());
        }
    }

    public static void radius(int value) {
        if (!ENABLED) return;
        log("chunk_radius", "radius=" + value);
    }

    public static void cacheCenter(int x, int z) {
        if (!ENABLED) return;
        log("chunk_cache_center", "x=" + x + " z=" + z);
    }

    public static void tracker(Object state) {
        if (!ENABLED) return;
        String rendered = state == null ? "none" : state.getClass().getSimpleName() + " " + text(state);
        long current = now();
        if (!rendered.equals(trackerState)) {
            trackerState = rendered;
            trackerChangedNanos = current;
            lastTrackerLogNanos = current;
            stallDumped = false;
            log("level_load_tracker", "state=" + rendered);
        } else if (current - lastTrackerLogNanos >= 2_000_000_000L) {
            lastTrackerLogNanos = current;
            log("level_load_tracker", "state=" + rendered + " unchangedMs="
                    + (current - trackerChangedNanos) / 1_000_000L);
        }
    }

    public static void ready(boolean value) {
        if (!ENABLED) return;
        long current = now();
        if (value) {
            log("level_load_ready", "ready=true waitingMs="
                    + (current - trackerChangedNanos) / 1_000_000L);
            lastReadyLogNanos = current;
        } else if (current - lastReadyLogNanos >= 2_000_000_000L) {
            lastReadyLogNanos = current;
            log("level_load_ready", "ready=false state=" + trackerState);
        }
    }

    public static void chunkReady(boolean value) {
        if (!ENABLED) return;
        long current = now();
        if (value) {
            log("player_chunk_ready", "ready=true state=" + trackerState);
            lastReadyLogNanos = current;
        } else if (current - lastReadyLogNanos >= 2_000_000_000L) {
            lastReadyLogNanos = current;
            log("player_chunk_ready", "ready=false state=" + trackerState);
        }
    }

    public static void sectionCheck(String position) {
        if (!ENABLED) return;
        sectionPosition = position;
        LAST_SECTION_NANOS.set(now());
        SECTION_CHECKS.incrementAndGet();
    }

    public static void sectionVisible(boolean value) {
        if (!ENABLED) return;
        if (value) SECTION_VISIBLE.incrementAndGet();
        long current = now();
        long calls = SECTION_CALLS.incrementAndGet();
        // The game asks about several sections per frame. Log a short initial sample, then at
        // most twice a second; per-change logging floods the run log during normal chunk meshing.
        if (calls > 8 && current - lastSectionLogNanos < 2_000_000_000L) {
            sectionWasVisible = value;
            return;
        }
        boolean changed = value != sectionWasVisible;
        sectionWasVisible = value;
        lastSectionLogNanos = current;
        log("section_visibility", "pos=" + sectionPosition + " visible=" + value
                + " changed=" + changed + " calls=" + calls
                + " checks=" + SECTION_CHECKS.get()
                + " visibleChecks=" + SECTION_VISIBLE.get());
    }

    public static void clientPosition(double x, double y, double z) {
        if (!ENABLED) return;
        long count = CLIENT_POSITIONS.incrementAndGet();
        if (count <= 5 || count % 40 == 0) {
            log("client_position_send", "x=" + round(x) + " y=" + round(y) + " z=" + round(z)
                    + " count=" + count);
        }
    }

    public static void serverPosition(String packet) {
        if (!ENABLED) return;
        long count = SERVER_POSITIONS.incrementAndGet();
        if (count <= 5 || count % 20 == 0) {
            log("server_position", "count=" + count + " packet=" + text(packet));
        }
    }

    public static void connectionFailure(Throwable failure) {
        if (!ENABLED) return;
        log("connection_exception", "error=" + error(failure));
        StackTraceElement[] frames = failure == null ? null : failure.getStackTrace();
        if (frames == null) return;
        for (int index = 0; index < Math.min(frames.length, 8); index++) {
            log("connection_exception_frame", "index=" + index + " at=" + frames[index]);
        }
    }

    public static void channelInactive() {
        if (!ENABLED) return;
        log("channel_inactive", "tracker=" + trackerState + " ticks=" + TICKS.get()
                + " chunks=" + CHUNK_PACKETS.get() + " decoded=" + CHUNKS_DECODED.get());
    }

    // ---- watchdog ----------------------------------------------------------------------------

    private static void startWatchdog() {
        if (watchdogStarted) return;
        synchronized (LOCK) {
            if (watchdogStarted) return;
            watchdogStarted = true;
        }
        Thread thread = new Thread(INSTANCE, "MCFAO Diag");
        thread.setDaemon(true);
        thread.start();
        log("diagnostics_start", "enabled=true stallSeconds=" + STALL_SECONDS
                + " heartbeatMillis=" + HEARTBEAT_MILLIS);
    }

    @Override
    public void run() {
        while (true) {
            try {
                Thread.sleep(HEARTBEAT_MILLIS);
            } catch (InterruptedException interrupted) {
                return;
            }
            long current = now();
            log("heartbeat", "ticks=" + TICKS.get() + " tickAgeMs=" + since(LAST_TICK_NANOS)
                    + " chunkPackets=" + CHUNK_PACKETS.get()
                    + " chunkDecoded=" + CHUNKS_DECODED.get()
                    + " packetAgeMs=" + since(LAST_PACKET_NANOS)
                    + " batches=" + BATCHES.get() + " batchChunks=" + BATCH_CHUNKS.get()
                    + " tracker=" + trackerState
                    + " trackerAgeMs=" + (current - trackerChangedNanos) / 1_000_000L
                    + " section=" + sectionPosition
                    + " sectionVisible=" + sectionWasVisible
                    + " sectionAgeMs=" + since(LAST_SECTION_NANOS)
                    + " clientPositions=" + CLIENT_POSITIONS.get()
                    + " serverPositions=" + SERVER_POSITIONS.get());
            maybeDumpStall();
        }
    }

    private static void maybeDumpStall() {
        if (!ENABLED || !trackerState.contains("WaitingFor")) {
            stallDumped = false;
            lastStallDumpNanos = 0;
            return;
        }
        long current = now();
        long waitingMs = (current - trackerChangedNanos) / 1_000_000L;
        if (waitingMs < STALL_SECONDS * 1000L) return;
        if (stallDumped && current - lastStallDumpNanos < 30_000_000_000L) return;
        stallDumped = true;
        lastStallDumpNanos = current;
        log("stall_detected", "state=" + trackerState + " waitingMs=" + waitingMs
                + " tickAgeMs=" + since(LAST_TICK_NANOS)
                + " packetAgeMs=" + since(LAST_PACKET_NANOS)
                + " chunks=" + CHUNK_PACKETS.get() + " decoded=" + CHUNKS_DECODED.get()
                + " section=" + sectionPosition + " visible=" + sectionWasVisible);
        dumpThreads();
    }

    private static void dumpThreads() {
        Map<Thread, StackTraceElement[]> traces;
        try {
            traces = Thread.getAllStackTraces();
        } catch (Throwable unsupported) {
            log("thread_dump_unavailable", "error=" + error(unsupported));
            return;
        }
        for (Map.Entry<Thread, StackTraceElement[]> entry : traces.entrySet()) {
            Thread thread = entry.getKey();
            String name = thread.getName();
            if (!interesting(name)) continue;
            log("thread", "name=" + name + " state=" + thread.getState()
                    + " daemon=" + thread.isDaemon());
            StackTraceElement[] frames = entry.getValue();
            for (int index = 0; index < Math.min(frames.length, 28); index++) {
                log("thread_frame", "name=" + name + " index=" + index + " at=" + frames[index]);
            }
        }
    }

    private static boolean interesting(String name) {
        return name.equals("Render thread") || name.equals("main") || name.equals("Server thread")
                || name.equals("MCFAO Diag") || name.startsWith("Netty")
                || name.startsWith("Worker-Main") || name.startsWith("Download")
                || name.startsWith("IO-Worker") || name.startsWith("Yggdrasil");
    }

    private static String round(double value) {
        long thousandths = Math.round(value * 1000.0);
        long whole = thousandths / 1000;
        long fraction = Math.abs(thousandths % 1000);
        return whole + "." + (fraction < 100 ? (fraction < 10 ? "00" : "0") : "") + fraction;
    }
}
