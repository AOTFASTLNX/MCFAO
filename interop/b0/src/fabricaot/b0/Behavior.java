package fabricaot.b0;

import net.minecraft.fabricaot_fixture.Target;
import java.lang.reflect.Modifier;

public final class Behavior {
    public static void verify() throws Exception {
        if (Runtime.version().feature() != 25) throw new AssertionError("Java25 required");
        Target target = new Target();
        if (target.mixedResult() != 42) throw new AssertionError("real Mixin did not change result to 42");
        var field = Target.class.getField("widened");
        if (!Modifier.isPublic(field.getModifiers()) || field.getInt(target) != 7)
            throw new AssertionError("ClassTweaker access modification missing");
        if (ProbeState.parentInitializations != 1 || ProbeState.nestedInitializations != 1)
            throw new AssertionError("parent/nested entrypoints must run exactly once");
        System.out.println("B0_BEHAVIOR mixed=42 widened=7 parent=1 nested=1");
    }
}
