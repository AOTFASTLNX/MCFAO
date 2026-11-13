import squeek.appleskin.shadowed.blue.endless.jankson.Jankson;

/** Runs against the user's locally transformed AppleSkin, never a bundled third-party jar. */
public final class AppleSkinConfigProbe {
    public static void main(String[] args) throws Exception {
        // Runtime input prevents Native Image from inferring this reflection registration.
        Class<?> type = Class.forName(args[0]);
        Object defaults = type.getDeclaredConstructor().newInstance();
        var enabled = type.getField("showFoodValuesInTooltip");
        var alpha = type.getField("maxHudOverlayFlashAlpha");
        if (!enabled.getBoolean(defaults) || Math.abs(alpha.getFloat(defaults) - 0.65f) > 0.001f) {
            throw new AssertionError("Constructor defaults changed");
        }
        enabled.setBoolean(defaults, false);
        alpha.setFloat(defaults, 0.25f);
        Jankson jankson = Jankson.builder().build();
        String saved = jankson.toJson(defaults).toJson(true, true);
        Object loaded = jankson.fromJson(saved, type);
        if (loaded == null || enabled.getBoolean(loaded)
                || Math.abs(alpha.getFloat(loaded) - 0.25f) > 0.001f) {
            throw new AssertionError("Configuration round trip lost user values: " + saved);
        }
        System.out.println("MCFAO_APPLESKIN_CONFIG_ROUNDTRIP_PASS");
    }
}
