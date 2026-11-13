package fabricaot.metal;

/** Render-thread-confined GPU read tracking for CPU-owned buffer storage. */
final class BufferHazardTracker {
    private long generation=1;
    static final class State { private long readGeneration; }
    void read(State state){state.readGeneration=generation;}
    boolean needsProtection(State state){return state.readGeneration==generation;}
    void renamed(State state){state.readGeneration=0;}
    void completed(){generation=Math.addExact(generation,1);}
}
