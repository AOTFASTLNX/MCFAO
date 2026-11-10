import java.util.ArrayList;

/** First-party allocation fixture, never part of the iPhone App. */
public final class CensusFixture {
    public static void main(String[] args) {
        var keep = new ArrayList<byte[]>();
        for (;;) keep.add(new byte[256 * 1024]);
    }
}
