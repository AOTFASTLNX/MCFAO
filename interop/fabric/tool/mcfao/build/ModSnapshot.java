package mcfao.build;

import java.util.*;
import net.fabricmc.loader.api.ModContainer;
import net.fabricmc.loader.api.metadata.*;

/** Serialize only public metadata values; never serialize Loader objects or host paths. */
public final class ModSnapshot {
    private ModSnapshot() {}
    public static String json(Map<String, ?> catalog) {
        return new com.google.gson.GsonBuilder().serializeNulls().setPrettyPrinting().create().toJson(catalog);
    }
    public static Map<String, Object> capture(ModContainer mod, Collection<String> files) {
        var m = mod.getMetadata();
        var out = new TreeMap<String, Object>();
        out.put("id", m.getId()); out.put("type", m.getType());
        out.put("name", m.getName()); out.put("description", m.getDescription());
        out.put("version", m.getVersion().getFriendlyString());
        out.put("environment", m.getEnvironment().name()); out.put("provides", m.getProvides());
        out.put("license", m.getLicense()); out.put("contact", m.getContact().asMap());
        out.put("authors", people(m.getAuthors())); out.put("contributors", people(m.getContributors()));
        var custom = new TreeMap<String,Object>();
        m.getCustomValues().forEach((key,value) -> custom.put(key, custom(value)));
        out.put("custom", custom);
        var deps = new ArrayList<Object>();
        for (var d : m.getDependencies()) deps.add(Map.of("id", d.getModId(), "kind", d.getKind().name(),
                "requirements", d.getVersionRequirements().stream().map(Object::toString).toList()));
        out.put("dependencies", deps);
        // Descriptor icon sizes are the only possible selection boundaries. Query the actual
        // Loader at both sides; repeated filenames must not hide an intermediate transition.
        var points = new TreeSet<Integer>(List.of(0, Integer.MAX_VALUE));
        mod.findPath("fabric.mod.json").ifPresent(path -> {
            try (var reader = java.nio.file.Files.newBufferedReader(path)) {
                var descriptor = com.google.gson.JsonParser.parseReader(reader).getAsJsonObject();
                var icon = descriptor.get("icon");
                if (icon != null && icon.isJsonObject()) for (String key : icon.getAsJsonObject().keySet()) {
                    int size = Integer.parseInt(key);
                    if (size < 0) throw new IllegalArgumentException("Negative icon size");
                    points.add(size); if (size < Integer.MAX_VALUE) points.add(size + 1);
                }
            } catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
        });
        var icons = new TreeMap<String,String>();
        String previous = null;
        for (int size : points) {
            String value = m.getIconPath(size).orElse(null);
            if (!Objects.equals(previous, value)) {
                if (value == null) throw new IllegalStateException("Disappearing icon metadata");
                icons.put(Integer.toString(size), value); previous=value;
            }
        }
        out.put("icons", icons);
        out.put("parent", mod.getContainingMod().map(p -> p.getMetadata().getId()).orElse(""));
        out.put("children", mod.getContainedMods().stream().map(p -> p.getMetadata().getId()).sorted().toList());
        var origin = mod.getOrigin();
        out.put("originKind", origin.getKind().name());
        if (origin.getKind() == ModOrigin.Kind.NESTED) {
            out.put("originParent", origin.getParentModId()); out.put("originLocation", origin.getParentSubLocation());
        }
        out.put("files", files);
        return out;
    }
    private static List<Object> people(Collection<Person> people) {
        return people.stream().map(p -> (Object)Map.of("name", p.getName(), "contact", p.getContact().asMap())).toList();
    }
    private static Object custom(CustomValue v) {
        return switch(v.getType()) {
            case NULL -> com.google.gson.JsonNull.INSTANCE;
            case STRING -> v.getAsString();
            case NUMBER -> v.getAsNumber();
            case BOOLEAN -> v.getAsBoolean();
            case ARRAY -> { var a = new ArrayList<Object>(); for (var x:v.getAsArray()) a.add(custom(x)); yield a; }
            case OBJECT -> { var o = new TreeMap<String,Object>(); for (var x:v.getAsObject()) o.put(x.getKey(),custom(x.getValue())); yield o; }
        };
    }
}
