package fabricaot.b0;

import fabricaot.b0.nested.NestedEntrypoint;

/** Explicit closed entrypoint list for this fixture only, without initializing Loader/Mixin. */
public final class ReplayMain {
    public static void main(String[] args) throws Exception {
        new ParentEntrypoint().onInitialize();
        new NestedEntrypoint().onInitialize();
        Behavior.verify();
        System.out.println("B0_REPLAY_PASS");
    }
}
