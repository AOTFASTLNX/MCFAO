package mcfao.diagnostics;

import mcfao.aot.OptionalJvmCapabilities;
import net.irisshaders.iris.shadows.frustum.advanced.AdvancedShadowCullingFrustum;
import org.joml.*;
import java.util.Random;

/** Executes the shipped Iris algorithm with a deterministic camera, without a renderer. */
public final class IrisShadowProbe extends AdvancedShadowCullingFrustum {
    IrisShadowProbe() {
        super(new Matrix4f().perspective((float)java.lang.Math.toRadians(70), 1.6f, 0.05f, 128),
                new Matrix4f(), new Vector3f(0.3f, 0.8f, 0.5f).normalize(), null);
    }
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("original")) {
            // A separate class owns main so initialization failure can be observed (see runner).
            throw new AssertionError("original initializer unexpectedly succeeded");
        }
        var capability = OptionalJvmCapabilities.hotSpotBooleanOption("UseFMA");
        var fma = AdvancedShadowCullingFrustum.class.getDeclaredField("FMA_SUPPORT"); fma.setAccessible(true);
        boolean enabled = fma.getBoolean(null);
        if (args.length > 0 && args[0].equals("unavailable")) {
            check(capability == OptionalJvmCapabilities.BooleanCapability.UNAVAILABLE); check(!enabled);
        }
        var probe = new IrisShadowProbe();
        var pf = AdvancedShadowCullingFrustum.class.getDeclaredField("planes"); pf.setAccessible(true);
        var cf = AdvancedShadowCullingFrustum.class.getDeclaredField("planeCount"); cf.setAccessible(true);
        float[][] planes = (float[][]) pf.get(probe); int count = cf.getInt(probe); check(count > 0);
        Random random = new Random(20261121);
        int visible = 0, outside = 0, edge = 0, ambiguous = 0;
        for (int sample = 0; sample < 20000; sample++) {
            float x = random.nextFloat() * 400 - 200, y = random.nextFloat() * 400 - 200;
            float z = random.nextFloat() * 400 - 200, radius = random.nextFloat() * 10 + 0.1f;
            float[] low = {x-radius, y-radius, z-radius}, high = {x+radius, y+radius, z+radius};
            int plain = 1, fused = 1; boolean near = false;
            for (int p = 0; p < count; p++) {
                float[] plane = planes[p]; float[] a = new float[3], b = new float[3];
                for (int axis = 0; axis < 3; axis++) {
                    a[axis] = plane[axis] < 0 ? low[axis] : high[axis];
                    b[axis] = plane[axis] < 0 ? high[axis] : low[axis];
                }
                float far = plane[0]*a[0] + (plane[1]*a[1] + plane[2]*a[2]);
                float farF = java.lang.Math.fma(plane[0], a[0], java.lang.Math.fma(plane[1], a[1], plane[2]*a[2]));
                float close = plane[0]*b[0] + (plane[1]*b[1] + (plane[2]*b[2] + plane[3]));
                float closeF = java.lang.Math.fma(plane[0], b[0], java.lang.Math.fma(plane[1], b[1], java.lang.Math.fma(plane[2], b[2], plane[3])));
                float scale = 1 + java.lang.Math.abs(plane[0]*a[0]) + java.lang.Math.abs(plane[1]*a[1])
                        + java.lang.Math.abs(plane[2]*a[2]) + java.lang.Math.abs(plane[3]);
                float tolerance = 8 * java.lang.Math.ulp(scale);
                check(java.lang.Math.abs(far - farF) <= tolerance);
                check(java.lang.Math.abs(close - closeF) <= tolerance);
                near |= java.lang.Math.abs(far + plane[3]) <= tolerance || java.lang.Math.abs(close) <= tolerance;
                if (plain != -3) plain = far < -plane[3] ? -3 : plain & (close >= 0 ? 1 : 0);
                if (fused != -3) fused = farF < -plane[3] ? -3 : fused & (closeF >= 0 ? 1 : 0);
            }
            plain = plain == -3 ? -3 : plain == 1 ? -2 : -1;
            fused = fused == -3 ? -3 : fused == 1 ? -2 : -1;
            int actual = probe.checkCornerVisibility(low[0],low[1],low[2],high[0],high[1],high[2]);
            check(actual == (enabled ? fused : plain));
            if (!near) check(plain == fused); else ambiguous++;
            if (actual == -3) outside++; else if (actual == -2) visible++; else edge++;
        }
        check(outside > 0 && visible > 0 && edge > 0);
        System.out.println("IRIS_SHADOW_PASS FMA=" + enabled + " capability=" + capability + " planes=" + count
                + " visible=" + visible + " outside=" + outside + " intersect=" + edge + " nearBoundary=" + ambiguous);
    }
}
