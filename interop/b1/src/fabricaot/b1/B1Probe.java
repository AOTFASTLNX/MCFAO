package fabricaot.b1;

import fabricaot.b0.ReplayMain;

/** Executes only the pre-transformed first-party B0 fixture. */
public final class B1Probe {
    public static void main(String[] args) throws Exception {
        ReplayMain.main(new String[0]);
        System.out.println("B1_SEMANTICS_PASS");
    }
}
