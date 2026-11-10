import java.util.ArrayList;

/** First-party allocation fixture, never part of the iPhone App. */
public final class CensusFixture {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("interval")) {
            /* Slow growth so a scheduled snapshot lands before the run exits. */
            var kept = new ArrayList<byte[]>();
            for (int i = 0; i < 4; i++) {
                kept.add(new byte[4 * 1024 * 1024]);
                Thread.sleep(1000);
            }
            return;
        }
        var keep = new ArrayList<byte[]>();
        for (;;) keep.add(new byte[256 * 1024]);
    }
}
