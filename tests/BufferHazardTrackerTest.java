package fabricaot.metal;

/** Exercises the production state machine without Metal or Minecraft dependencies. */
public final class BufferHazardTrackerTest {
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    public static void main(String[] args){
        BufferHazardTracker tracker=new BufferHazardTracker();
        BufferHazardTracker.State a=new BufferHazardTracker.State(),b=new BufferHazardTracker.State();
        check(!tracker.needsProtection(a),"new storage must be CPU writable");
        tracker.read(a);
        check(tracker.needsProtection(a),"queued GPU reader must protect storage");
        check(!tracker.needsProtection(b),"another buffer must remain writable");
        tracker.renamed(a);
        check(!tracker.needsProtection(a),"renamed storage must be writable");
        tracker.read(a);tracker.read(b);tracker.completed();
        check(!tracker.needsProtection(a)&&!tracker.needsProtection(b),"completion clears prior reads");
        tracker.read(b);
        check(!tracker.needsProtection(a)&&tracker.needsProtection(b),"only subsequent reads need protection");
        tracker.completed();tracker.read(a);tracker.completed();tracker.read(b);
        check(!tracker.needsProtection(a)&&tracker.needsProtection(b),"read generations must not leak");
        System.out.println("BUFFER_HAZARD_TRACKER_PASS");
    }
}
