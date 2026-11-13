package mcfao.aot;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import net.fabricmc.loader.api.*;
import net.fabricmc.loader.api.metadata.*;

/** Build-time identity snapshot; no discovery, executable JARs, or runtime class loading. */
public final class ModCatalog {
    private ModCatalog() {}
    private static final class State {
        static final Map<String, ModContainer> MODS = read();
    }
    private static Map<String, ModContainer> read() {
        try (var in = ModCatalog.class.getResourceAsStream("/mcfao/mod-catalog.json")) {
            if (in == null) throw new IllegalStateException("Missing AOT Mod catalog");
            var json = JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject();
            var result = new LinkedHashMap<String, ModContainer>();
            for (var entry : json.entrySet()) result.put(entry.getKey(), new Container(entry.getValue().getAsJsonObject()));
            return Collections.unmodifiableMap(result);
        } catch (IOException error) { throw new UncheckedIOException(error); }
    }
    public static Optional<ModContainer> lookup(Object ignored, String id) {
        return Optional.ofNullable(State.MODS.get(Objects.requireNonNull(id)));
    }
    public static ModContainer required(String id) {
        return lookup(null, id).orElseThrow(() -> new IllegalStateException("Missing AOT Mod provider: " + id));
    }
    public static Collection<ModContainer> all() { return State.MODS.values(); }
    private static List<String> strings(JsonObject json, String key) {
        var result = new ArrayList<String>();
        if (json.has(key)) for (var item : json.getAsJsonArray(key)) result.add(item.getAsString());
        return List.copyOf(result);
    }
    private static ContactInformation contact(JsonObject json) {
        var values = new TreeMap<String,String>();
        if (json != null) json.entrySet().forEach(e -> values.put(e.getKey(),e.getValue().getAsString()));
        var frozen = Collections.unmodifiableMap(values);
        return new ContactInformation() {
            public Optional<String> get(String key) { return Optional.ofNullable(frozen.get(key)); }
            public Map<String,String> asMap() { return frozen; }
        };
    }
    private static UnsupportedOperationException unsupported(String field) {
        return new UnsupportedOperationException("AOT Mod catalog does not yet snapshot " + field);
    }
    private static final class Container implements ModContainer {
        private final JsonObject json;
        private final ModMetadata metadata;
        private Path root;
        Container(JsonObject json) { this.json = json; this.metadata = new Metadata(json); }
        public ModMetadata getMetadata() { return metadata; }
        public synchronized List<Path> getRootPaths() {
            if (root == null) {
                Path directory = null;
                try {
                    directory = Files.createTempDirectory("mcfao-mod-" + metadata.getId() + "-");
                    for (var entry : json.getAsJsonArray("files")) {
                        String relative = entry.getAsString();
                        Path file = directory.resolve(relative).normalize();
                        if (!file.startsWith(directory) || relative.contains("\\") || Path.of(relative).isAbsolute())
                            throw new IllegalArgumentException("Unsafe Mod resource: " + relative);
                        try (var in = ModCatalog.class.getResourceAsStream("/mcfao/mod-files/" + metadata.getId() + "/" + relative)) {
                            if (in == null) throw new FileNotFoundException(relative);
                            Files.createDirectories(file.getParent());
                            Files.copy(in, file);
                        }
                    }
                    root = directory; // Publish only a complete tree.
                } catch (IOException error) { throw new UncheckedIOException(error); }
            }
            return List.of(root);
        }
        public Path getRootPath() { return getRootPaths().getFirst(); }
        public Path getRoot() { return getRootPath(); }
        public Path getPath(String name) {
            Path base = getRootPath();
            Path path = base.resolve(name).normalize();
            if (!path.startsWith(base)) throw new IllegalArgumentException("Path outside Mod root: " + name);
            return path;
        }
        public Optional<Path> findPath(String name) {
            Path path = getPath(name); return Files.exists(path) ? Optional.of(path) : Optional.empty();
        }
        public ModOrigin getOrigin() {
            return new ModOrigin() {
                public Kind getKind() { return Kind.valueOf(json.get("originKind").getAsString()); }
                public List<Path> getPaths() {
                    if (getKind()!=Kind.PATH) throw new UnsupportedOperationException("Origin is not PATH");
                    return getRootPaths();
                }
                public String getParentModId() {
                    if (getKind()!=Kind.NESTED) throw new UnsupportedOperationException("Origin is not NESTED");
                    return json.get("originParent").getAsString();
                }
                public String getParentSubLocation() {
                    if (getKind()!=Kind.NESTED) throw new UnsupportedOperationException("Origin is not NESTED");
                    return json.get("originLocation").getAsString();
                }
            };
        }
        public Optional<ModContainer> getContainingMod() {
            String parent = json.get("parent").getAsString();
            return parent.isEmpty() ? Optional.empty() : Optional.of(required(parent));
        }
        public Collection<ModContainer> getContainedMods() {
            return strings(json,"children").stream().map(ModCatalog::required).toList();
        }
    }
    private static final class Metadata implements ModMetadata {
        private final JsonObject json;
        Metadata(JsonObject json) { this.json = json; }
        private String text(String key) { return json.get(key).getAsString(); }
        public String getType() { return text("type"); }
        public String getId() { return text("id"); }
        public String getName() { return text("name"); }
        public String getDescription() { return text("description"); }
        public Version getVersion() {
            try { return Version.parse(text("version")); }
            catch (VersionParsingException error) { throw new IllegalStateException(error); }
        }
        public ModEnvironment getEnvironment() { return ModEnvironment.valueOf(text("environment")); }
        public Collection<String> getProvides() { return strings(json,"provides"); }
        public Collection<ModDependency> getDependencies() {
            var result = new ArrayList<ModDependency>();
            for (var item:json.getAsJsonArray("dependencies")) result.add(new Dependency(item.getAsJsonObject()));
            return List.copyOf(result);
        }
        private Collection<Person> people(String key) {
            var result = new ArrayList<Person>();
            for (var item:json.getAsJsonArray(key)) {
                var person = item.getAsJsonObject();
                result.add(new Person() {
                    public String getName() { return person.get("name").getAsString(); }
                    public ContactInformation getContact() { return contact(person.getAsJsonObject("contact")); }
                });
            }
            return List.copyOf(result);
        }
        public Collection<Person> getAuthors() { return people("authors"); }
        public Collection<Person> getContributors() { return people("contributors"); }
        public ContactInformation getContact() { return contact(json.getAsJsonObject("contact")); }
        public Collection<String> getLicense() { return strings(json,"license"); }
        public Optional<String> getIconPath(int size) {
            if (size < 0) size = 0;
            String selected = null; int selectedSize = -1;
            for (var entry:json.getAsJsonObject("icons").entrySet()) {
                int point = Integer.parseInt(entry.getKey());
                if (point<=size && point>selectedSize) { selected=entry.getValue().getAsString(); selectedSize=point; }
            }
            return Optional.ofNullable(selected);
        }
        public boolean containsCustomValue(String key) { return json.getAsJsonObject("custom").has(key); }
        public CustomValue getCustomValue(String key) {
            var element=json.getAsJsonObject("custom").get(key); return element==null ? null : value(element);
        }
        public Map<String, CustomValue> getCustomValues() {
            var result=new LinkedHashMap<String,CustomValue>();
            json.getAsJsonObject("custom").entrySet().forEach(e->result.put(e.getKey(),value(e.getValue())));
            return Collections.unmodifiableMap(result);
        }
        public boolean containsCustomElement(String key) { return containsCustomValue(key); }
    }
    private static final class Dependency implements ModDependency {
        private final JsonObject json;
        Dependency(JsonObject json) { this.json=json; }
        public Kind getKind() { return Kind.valueOf(json.get("kind").getAsString()); }
        public String getModId() { return json.get("id").getAsString(); }
        public Collection<net.fabricmc.loader.api.metadata.version.VersionPredicate> getVersionRequirements() {
            try { return List.copyOf(net.fabricmc.loader.api.metadata.version.VersionPredicate.parse(strings(json,"requirements"))); }
            catch(VersionParsingException error) { throw new IllegalStateException(error); }
        }
        public boolean matches(Version version) { return getVersionRequirements().stream().anyMatch(p->p.test(version)); }
        public List<net.fabricmc.loader.api.metadata.version.VersionInterval> getVersionIntervals() {
            List<net.fabricmc.loader.api.metadata.version.VersionInterval> result=List.of();
            for(var predicate:getVersionRequirements())
                result=net.fabricmc.loader.api.metadata.version.VersionInterval.or(result,predicate.getInterval());
            return List.copyOf(result);
        }
    }
    private static CustomValue value(JsonElement json) {
        if(json.isJsonObject()) return new ObjectValue(json);
        if(json.isJsonArray()) return new ArrayValue(json);
        return new Value(json);
    }
    private static class Value implements CustomValue {
        final JsonElement json;
        Value(JsonElement json) { this.json=json; }
        public CvType getType() {
            if(json.isJsonNull()) return CvType.NULL;
            if(json.isJsonObject()) return CvType.OBJECT;
            if(json.isJsonArray()) return CvType.ARRAY;
            var p=json.getAsJsonPrimitive();
            return p.isBoolean()?CvType.BOOLEAN:p.isNumber()?CvType.NUMBER:CvType.STRING;
        }
        private void require(CvType type) { if(getType()!=type) throw new ClassCastException("Expected "+type+", got "+getType()); }
        public CvObject getAsObject() { require(CvType.OBJECT); return (CvObject)this; }
        public CvArray getAsArray() { require(CvType.ARRAY); return (CvArray)this; }
        public String getAsString() { require(CvType.STRING); return json.getAsString(); }
        public Number getAsNumber() { require(CvType.NUMBER); return json.getAsNumber(); }
        public boolean getAsBoolean() { require(CvType.BOOLEAN); return json.getAsBoolean(); }
    }
    private static final class ObjectValue extends Value implements CustomValue.CvObject {
        ObjectValue(JsonElement json) { super(json); }
        public int size() { return json.getAsJsonObject().size(); }
        public boolean containsKey(String key) { return json.getAsJsonObject().has(key); }
        public CustomValue get(String key) { var x=json.getAsJsonObject().get(key);return x==null?null:value(x); }
        public Iterator<Map.Entry<String,CustomValue>> iterator() {
            var map=new LinkedHashMap<String,CustomValue>();
            json.getAsJsonObject().entrySet().forEach(e->map.put(e.getKey(),value(e.getValue())));
            return Collections.unmodifiableMap(map).entrySet().iterator();
        }
    }
    private static final class ArrayValue extends Value implements CustomValue.CvArray {
        ArrayValue(JsonElement json) { super(json); }
        public int size() { return json.getAsJsonArray().size(); }
        public CustomValue get(int index) { return value(json.getAsJsonArray().get(index)); }
        public Iterator<CustomValue> iterator() {
            var list=new ArrayList<CustomValue>();for(var e:json.getAsJsonArray())list.add(value(e));
            return Collections.unmodifiableList(list).iterator();
        }
    }
}
