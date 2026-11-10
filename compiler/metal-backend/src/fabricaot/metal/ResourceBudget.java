package fabricaot.metal;

/** Bounds the total logical size of live resources, separately from the per-buffer limit. */
final class ResourceBudget {
    static final long MIB = 1024L * 1024;
    static final String PROPERTY = "fabricaot.metal.resourceBudgetMiB";
    static final int DEFAULT_MIB = 256;
    static final int MAX_MIB = 1024;
    private final long limit;
    private long used;

    ResourceBudget(String configured) {
        int mib = configured == null ? DEFAULT_MIB : Integer.parseInt(configured);
        if (mib < DEFAULT_MIB || mib > MAX_MIB)
            throw new IllegalArgumentException(PROPERTY + " must be between " + DEFAULT_MIB + " and " + MAX_MIB);
        limit = mib * MIB;
    }

    long limitMiB() { return limit / MIB; }

    void reserve(long bytes) {
        if (bytes <= 0) throw new IllegalArgumentException("Metal resource size must be positive");
        if (bytes > limit - used)
            throw new OutOfMemoryError("Metal resource budget " + limitMiB() + " MiB: "
                + bytes + " bytes requested with " + used + " bytes live");
        used += bytes;
    }

    void release(long bytes) {
        if (bytes <= 0 || bytes > used) throw new IllegalStateException("Invalid Metal resource release");
        used -= bytes;
    }
}
