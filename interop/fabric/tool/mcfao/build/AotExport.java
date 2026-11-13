package mcfao.build;

import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.api.EnvType;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.launch.knot.Knot;
import net.fabricmc.loader.impl.metadata.DependencyOverrides;
import net.fabricmc.loader.impl.metadata.ModMetadataParser;
import net.fabricmc.loader.impl.metadata.VersionOverrides;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Label;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FrameNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.BasicVerifier;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import org.spongepowered.asm.mixin.injection.callback.Cancellable;
import org.spongepowered.asm.mixin.injection.callback.CancellationException;

public final class AotExport implements Opcodes {
    private static final Gson JSON = new GsonBuilder().setPrettyPrinting().create();
    private static final String HOOKS = "net/fabricmc/loader/impl/game/minecraft/Hooks";
    private static final String STATIC_HOOKS = "mcfao/aot/Entrypoints";
    private static final String METADATA = "META-INF/native-image/mcfao/fabric/";
    private static final String SERVICES = "META-INF/services/";
    private static final String VERSIONS = "META-INF/versions/";
    private static final String HOST_METADATA = "META-INF/native-image/";
    private static final int RUNTIME_FEATURE = 25;
    private static final String REGISTRY_CONTAINER_DESC =
            "Lcom/mrcrayfish/framework/api/registry/RegistryContainer;";
    private static final String REGISTRATION_HELPER =
            "com/mrcrayfish/framework/platform/FabricRegistrationHelper";
    private static final String FRAMEWORK_CONFIG = RuntimeLowering.FRAMEWORK_CONFIG;
    private static final String FRAMEWORK_CONFIG_DESC = RuntimeLowering.FRAMEWORK_CONFIG_DESC;
    private static final String CONFIG_HELPER = RuntimeLowering.CONFIG_HELPER;
    private static final String WRAP_OPERATION = "com/llamalad7/mixinextras/injector/wrapoperation/";

    /**
     * One line per dispatched entrypoint, printed <em>after</em> the callback returned. Presence
     * therefore means "this Mod's initialiser ran to completion": a throwing initialiser never
     * reaches the print and aborts start-up anyway. `tools/scan_mod_evidence.py` reads these
     * lines to move a Mod from `BUILD_PASS` to `LOAD_PASS` without a human watching the screen -
     * before this hook existed, only 7 of 114 Mods left any trace of their own code running.
     */
    private static void emitEntrypointDispatched(MethodVisitor code, Entry entry) {
        code.visitFieldInsn(GETSTATIC, "java/lang/System", "out", "Ljava/io/PrintStream;");
        code.visitLdcInsn("[MCFAO_ENTRYPOINT] mod=" + entry.mod() + " stage=" + entry.stage()
                + " class=" + entry.definition());
        code.visitMethodInsn(INVOKEVIRTUAL, "java/io/PrintStream", "println",
                "(Ljava/lang/String;)V", false);
    }

    private record Metadata(String path, String id, String version, boolean client,
            Map<String, ?> entrypoints, List<?> dependencies, List<String> jars,
            List<String> mixins, String classTweaker) {}
    private record Entry(String mod, String stage, String definition, String type, String method,
            String refOwner, String refName, boolean refStatic, boolean singleton) {}

    private static Metadata metadata(Path path) throws Exception {
        try (var zip = new ZipFile(path.toFile())) {
            try (var input = zip.getInputStream(zip.getEntry("fabric.mod.json"))) {
                var meta = ModMetadataParser.parseMetadata(input, path.toString(), List.of(),
                        new VersionOverrides(), new DependencyOverrides(Path.of("config")), false);
                var entries = new TreeMap<String, Object>();
                for (String key : meta.getEntrypointKeys()) {
                    entries.put(key, meta.getEntrypoints(key).stream()
                            .map(e -> Map.of("adapter", e.getAdapter(), "value", e.getValue())).toList());
                }
                return new Metadata(path.toString(), meta.getId(), meta.getVersion().getFriendlyString(),
                        meta.loadsInEnvironment(EnvType.CLIENT), entries,
                        meta.getDependencies().stream().map(Object::toString).toList(),
                        meta.getJars().stream().map(e -> e.getFile()).toList(),
                        List.copyOf(meta.getMixinConfigs(EnvType.CLIENT)), meta.getClassTweaker());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args[0].equals("resolve")) {
            var graph = FabricResolve.resolve(Path.of(args[2]), Path.of(args[3]), Path.of(args[4]));
            Files.writeString(Path.of(args[1]), JSON.toJson(graph));
            return;
        }
        if (args[0].equals("inspect")) {
            var result = new ArrayList<Metadata>();
            for (int i = 2; i < args.length; i++) result.add(metadata(Path.of(args[i])));
            Files.writeString(Path.of(args[1]), JSON.toJson(result));
            return;
        }
        Path client = Path.of(args[1]);
        Path output = Path.of(args[2]);
        Set<String> requested = new TreeSet<>(Files.readAllLines(Path.of(args[3])));
        // Optional: pre-compiled first-party classes that replace run-time generated code.
        Path runtimeClasses = args.length > 5 && !args[5].isBlank() ? Path.of(args[5]) : null;
        var runtimeExported = new TreeSet<String>();
        var knot = new Knot(EnvType.CLIENT);
        ClassLoader target = knot.init(new String[]{"--version", "26.1.2", "--gameDir", args[4]});
        if (knot.isDevelopment() || !"official".equals(knot.getMappingConfiguration().getRuntimeNamespace())) {
            throw new IllegalStateException("Expected Fabric production with the official runtime namespace");
        }
        if (!target.getClass().getName().equals("net.fabricmc.loader.impl.launch.knot.KnotClassLoader")) {
            throw new IllegalStateException("Unsupported Fabric target classloader " + target.getName());
        }
        // Pinned Loader 0.19.3. Read the same bytes Knot defines without loading or initializing
        // each Minecraft class, including classes unreachable in the JVM build host.
        Method getDelegate = target.getClass().getDeclaredMethod("getDelegate");
        getDelegate.setAccessible(true);
        Object delegate = getDelegate.invoke(target);
        Method transform = delegate.getClass().getDeclaredMethod(
                "getPostMixinClassByteArray", String.class, boolean.class);
        transform.setAccessible(true);
        var loader = FabricLoaderImpl.INSTANCE;
        // The pinned Indigo plugin's runtime query repeats its build-time metadata decision.
        // Keep the plugin itself out of the image; verify its bytes before folding a call.
        boolean indigoApplicable = loader.getModsInternal().stream().noneMatch(mod ->
                mod.getMetadata().containsCustomValue("fabric-renderer-api-v1:contains_renderer"));
        String indigoPluginHash;
        try (var plugin = target.getResourceAsStream(RuntimeLowering.INDIGO_PLUGIN + ".class")) {
            indigoPluginHash = plugin == null ? null : hash(plugin.readAllBytes());
        }
        var jadeFlags = new TreeMap<String, Boolean>();
        var jadeDisabledTooltips = new ArrayList<String>();
        for (var mod : loader.getModsInternal()) {
            var custom = mod.getMetadata().getCustomValue("jade");
            if (custom == null || custom.getType() != net.fabricmc.loader.api.metadata.CustomValue.CvType.OBJECT) continue;
            var object = custom.getAsObject();
            for (String field : List.of("accessibilityMod", "fastScroll", "smoothScroll", "disableItemModNameTooltip")) {
                var value = object.containsKey(field) ? object.get(field) : null;
                boolean enabled = value != null && value.getType()
                        == net.fabricmc.loader.api.metadata.CustomValue.CvType.BOOLEAN && value.getAsBoolean();
                if (field.equals("disableItemModNameTooltip")) {
                    if (enabled) jadeDisabledTooltips.add(mod.getMetadata().getId());
                } else jadeFlags.merge(field, enabled, (left, right) -> left || right);
            }
        }
        var loadedIds = new TreeSet<String>();
        var versions = new TreeMap<String, String>();
        var modNames = new TreeMap<String, String>();
        var modDependencies = new TreeMap<String, List<String>>();
        for (var mod : loader.getModsInternal()) {
            String id = mod.getMetadata().getId();
            loadedIds.add(id);
            loadedIds.addAll(mod.getMetadata().getProvides());
            versions.put(id, mod.getMetadata().getVersion().getFriendlyString());
            modNames.put(id, mod.getMetadata().getName());
            modDependencies.put(id, mod.getMetadata().getDependencies().stream()
                    .filter(dependency -> dependency.getKind()
                            == net.fabricmc.loader.api.metadata.ModDependency.Kind.DEPENDS)
                    .map(dependency -> dependency.getModId()).toList());
        }
        var entries = new ArrayList<Entry>();
        collect(entries, requested, loader, target, transform, delegate, "main", ModInitializer.class, "onInitialize");
        collect(entries, requested, loader, target, transform, delegate, "client", ClientModInitializer.class,
                "onInitializeClient");
        // Entrypoints are the one place where a stubbed body would silently disable a Mod instead
        // of reporting it, so the lowering pass refuses to touch them.
        var protectedMethods = new TreeSet<String>();
        for (Entry entry : entries) {
            if (entry.refOwner() != null) {
                protectedMethods.add(entry.refOwner().replace('.', '/') + "#" + entry.refName());
            } else {
                String owner = entry.definition().replace('.', '/');
                protectedMethods.add(owner + "#onInitialize");
                protectedMethods.add(owner + "#onInitializeClient");
            }
        }
        // Custom entrypoint stages are dispatched from a generated switch. The provider list is
        // read from metadata, so the image carries the same instances the reference Loader would
        // have handed to the consuming Mod.
        var stages = new TreeMap<String, List<String>>();
        var stageOwners = new TreeMap<String, List<String>>();
        var singletonStageProviders = new TreeSet<String>();
        var queriedStages = new TreeSet<String>();
        var unqueriedStages = new TreeMap<String, List<String>>();
        for (var mod : loader.getModsInternal()) {
            if (!requested.contains(mod.getMetadata().getId())) continue;
            for (String stage : mod.getMetadata().getEntrypointKeys()) {
                if (stage.equals("main") || stage.equals("client") || stage.equals("server")) continue;
                for (var provider : mod.getMetadata().getEntrypoints(stage)) {
                    String value = provider.getValue();
                    if (value.contains("::")) {
                        throw new IllegalArgumentException("Unsupported method-reference entrypoint "
                                + mod.getMetadata().getId() + "/" + stage + ": " + value);
                    }
                    stages.computeIfAbsent(stage, key -> new ArrayList<>()).add(value);
                    stageOwners.computeIfAbsent(stage, key -> new ArrayList<>()).add(mod.getMetadata().getId());
                }
            }
        }

        var resources = new TreeSet<String>();
        var modClasses = new TreeSet<String>();
        var serializationRoots = new TreeSet<String>();
        var names = new TreeSet<String>();
        var changes = new TreeMap<String, Object>();
        var selected = new ArrayList<Map<String, String>>();
        var adaptations = new ArrayList<String>();
        var pinnedFabricApi = new TreeSet<String>();
        var earlyInitializers = new TreeSet<String>();
        // Provider lists per ServiceLoader interface, merged across every mod because the
        // overlay is a single jar and two mods may register different providers for one type.
        var services = new TreeMap<String, TreeSet<String>>();
        var serviceProviders = new TreeSet<String>();
        var droppedEntries = new TreeSet<String>();
        var mixinClasses = new TreeSet<String>();
        // A Mixin config may name a plugin class. The plugin ran inside Knot while this export was
        // prepared - it decides which of the config's mixins apply - and no runtime path can reach
        // it: it implements the Mixin API, which a shipped image does not carry.
        var mixinPlugins = new TreeSet<String>();
        // Targets a shipped Mixin names. Most are game classes the merge already rewrote; the rest
        // live in library jars and are handled after every Mod has been read.
        var mixinTargets = new TreeSet<String>();
        // Static accessors keep their implementation in the interface body, written by Mixin when
        // the target class is transformed. These lists record which mixin classes came back
        // transformed and which the transformer still refused, so a silently-unapplied accessor
        // shows up in the report instead of as an `Untransformed @Accessor` crash.
        var mixinAccessorsApplied = new TreeSet<String>();
        var mixinAccessorsRefused = new TreeSet<String>();
        var libraryTransforms = new TreeSet<String>();
        var mixinTargetsAbsent = new TreeSet<String>();
        // A @ModifyArgs handler's call site is rewritten by Mixin into `new Args$N(arg...)`, where
        // Args$N is generated in memory by Mixin's ArgsClassGenerator and therefore does not exist
        // in a closed world. The generated shape only stores its arguments, so each observed
        // call site is reproduced here from its own constructor descriptor.
        var argumentHolders = new TreeMap<String, Map<String, String>>();
        var generatedArgumentHolders = new TreeSet<String>();
        // MixinExtras types named by merged code. Its sugar refs (LocalRefImpl and friends) are
        // written by its generator during transformation, so they exist only inside Knot; whatever
        // Knot can still resolve is shipped, and the rest is recorded.
        var extrasTypes = new TreeSet<String>();
        // Framework finds @RegistryContainer classes by scanning the classpath with the
        // reflections library, which is absent from a closed world - the container classes'
        // static final fields are recorded here instead, and the scan is rewritten into a
        // table that reads them directly.
        var registryContainers = new TreeMap<String, List<String[]>>();
        // Framework's config discovery starts from `FabricLoader.getAllMods()`, which the closed
        // world folds to an empty collection: no Mod jar means no `fabric.mod.json`, and the JSON
        // is where both the config class name and the `@FrameworkConfig` annotation live. The
        // declarations are recorded here instead, one row per annotated static field, so the
        // platform helper can return the same pairs without touching the Loader.
        var frameworkConfigs = new ArrayList<String[]>();
        // Mixin writes `Target$Anonymous$<hash>` helper classes in memory when a handler needs
        // one; the rewritten target names them, so they have to be fetched and shipped too.
        var syntheticClasses = new TreeSet<String>();
        var syntheticShipped = new TreeSet<String>();
        var syntheticAbsent = new TreeSet<String>();
        var extrasShipped = new TreeSet<String>();
        var extrasAbsent = new TreeSet<String>();
        var multiReleaseIgnored = new TreeSet<String>();
        var multiReleasePromoted = new TreeSet<String>();
        // Mods ship their own resource-pack layer. A single jar cannot express layering, so
        // contributions to vanilla tag and atlas files are merged while every other path keeps
        // the later-pack-wins rule the reference client applies.
        var pendingResources = new TreeMap<String, byte[]>();
        var mergedResources = new TreeSet<String>();
        // Every assets/ and data/ path that actually ships in the merged jar. The namespace
        // table is derived from these paths rather than from Mod metadata, so a Mod that ships
        // no resources cannot advertise a namespace and a filtered-out path cannot be exposed.
        var resourceEntryNames = new TreeSet<String>();
        var shippedNamespaces = new TreeSet<String>();
        // A Mod file that replaces a vanilla file is declared here: one jar cannot express the
        // pack layering the reference client uses, so the merge step verifies this list instead.
        var overriddenResources = new TreeSet<String>();
        // Collected instead of thrown on the spot: one run then lists every class the closure
        // cannot lower, so a Mod set can be triaged in a single pass.
        var failures = new ArrayList<String>();
        var stubbed = new TreeSet<String>();
        int hooks = 0;
        try (var base = new ZipFile(client.toFile());
             var jar = new ZipOutputStream(Files.newOutputStream(output.resolve("overlay.jar")))) {
            for (var original : base.stream().toList()) {
                String name = original.getName();
                if (name.startsWith("assets/") || name.startsWith("data/")) resourceEntryNames.add(name);
            }
            for (var original : base.stream().filter(e -> e.getName().endsWith(".class")).toList()) {
                String path = original.getName();
                byte[] before;
                try (var input = base.getInputStream(original)) {
                    before = input.readAllBytes();
                }
                byte[] after = transform(transform, delegate, path);
                // The crash report gets one change that does not depend on a Mixin touching it,
                // so it is handled even when the transformed bytes are identical.
                boolean report = path.equals("net/minecraft/CrashReport.class");
                // The built-in pack builder is not always touched by a Mixin, but its namespace
                // freeze must be rewritten even when the transformed bytes are unchanged.
                boolean packBuilder = path.equals(RuntimeLowering.VANILLA_PACK_BUILDER + ".class");
                // The pipeline registry is untouched by Mixins, but the Metal bundle guard must be
                // installed whether or not the class came back byte-identical.
                boolean pipelines = path.equals(RuntimeLowering.RENDER_PIPELINES + ".class");
                // The config helper is likewise untouched by Mixins: its Loader-facing scan is
                // replaced by the build-time table whenever the pack declared any config.
                boolean configHelper = path.equals(CONFIG_HELPER + ".class") && !frameworkConfigs.isEmpty();
                if (Arrays.equals(before, after) && !report && !packBuilder && !pipelines
                        && !configHelper) continue;
                ClassNode node = parse(after);
                if (packBuilder) {
                    RuntimeLowering.lowerVanillaPackBuilder(node, hash(before), adaptations);
                }
                if (pipelines) {
                    RuntimeLowering.lowerRenderPipelineRegister(node, hash(before), adaptations);
                }
                if (configHelper) {
                    RuntimeLowering.lowerConfigDiscovery(node, adaptations);
                }
                int rewritten = redirectHooks(node);
                hooks += rewritten;
                collectArgumentHolders(node, argumentHolders);
                collectExtrasReferences(node, extrasTypes);
                collectSyntheticClasses(node, syntheticClasses);
                try {
                    RuntimeLowering.lowerQueries(node, loadedIds, versions, adaptations, stubbed, protectedMethods);
                    RuntimeLowering.lowerGlitchCoreEvents(node, hash(before), adaptations);
                    RuntimeLowering.collectStageQueries(node, queriedStages);
                    RuntimeLowering.printBeforeReport(node, adaptations);
                } catch (RuntimeException problem) {
                    failures.add("client/" + path + ": " + problem.getMessage());
                    continue;
                }
                after = classBytes(node);
                verify(node, adaptations);
                put(jar, names, path, after);
                changes.put(path, Map.of("originalSHA256", hash(before), "transformedSHA256", hash(after),
                        "loaderHookCalls", rewritten));
            }
            if (hooks != 1) throw new IllegalStateException("Expected exactly one Fabric client hook, got " + hooks);
            // Framework finds @RegistryContainer classes by scanning the classpath with the
            // reflections library at run time; no classpath exists in a closed world, and the
            // library was excluded for its run-time class definition anyway. The containers are
            // enumerated here from the mod files instead, and the helper's scan below is
            // rewritten into a table that reads their fields directly. The sweep runs before the
            // export loop because the helper's class file may stream out before its containers'.
            for (var mod : loader.getModsInternal()) {
                if (!requested.contains(mod.getMetadata().getId())) continue;
                for (Path root : mod.getRootPaths()) {
                    try (var paths = Files.walk(root)) {
                        for (Path path : paths.filter(Files::isRegularFile)
                                .filter(p -> p.getFileName().toString().endsWith(".class")).toList()) {
                            byte[] data = Files.readAllBytes(path);
                            boolean container = indexOf(data,
                                    REGISTRY_CONTAINER_DESC.getBytes(StandardCharsets.UTF_8)) >= 0;
                            boolean config = indexOf(data,
                                    FRAMEWORK_CONFIG_DESC.getBytes(StandardCharsets.UTF_8)) >= 0;
                            if (!container && !config) continue;
                            try {
                                var scanned = parse(data);
                                if (container) collectRegistryContainers(scanned, registryContainers);
                                if (config) collectFrameworkConfigs(scanned, frameworkConfigs);
                            } catch (RuntimeException ignored) {
                                // Not a framework container; the main loop re-parses and reports
                                // anything genuinely broken.
                            }
                        }
                    }
                }
            }
            for (var mod : loader.getModsInternal()) {
                String id = mod.getMetadata().getId();
                if (!requested.contains(id)) continue;
                selected.add(Map.of("id", id, "version", mod.getMetadata().getVersion().getFriendlyString()));
                for (Path root : mod.getRootPaths()) {
                    var mixinPackages = new ArrayList<String>();
                    for (String config : mod.getMetadata().getMixinConfigs(EnvType.CLIENT)) {
                        try (var reader = Files.newBufferedReader(root.resolve(config))) {
                            JsonObject parsed = JSON.fromJson(reader, JsonObject.class);
                            String pkg = parsed.get("package").getAsString();
                            mixinPackages.add(pkg.replace('.', '/') + "/");
                            if (parsed.has("plugin")) {
                                mixinPlugins.add(parsed.get("plugin").getAsString().replace('.', '/'));
                            }
                        }
                    }
                    // Multi-release trees are resolved the way this runtime resolves them: the
                    // in-JVM reference loader (Knot over a union filesystem) does not read
                    // META-INF/versions, so a versioned copy is ignored when the base entry
                    // exists and only promoted when it would otherwise be missing.
                    var effective = new TreeMap<String, Path>();
                    var versioned = new TreeMap<String, TreeMap<Integer, Path>>();
                    boolean multiRelease = multiRelease(root);
                    try (var paths = Files.walk(root)) {
                        for (Path path : paths.filter(Files::isRegularFile).sorted().toList()) {
                            String name = root.relativize(path).toString();
                            if (!name.startsWith(VERSIONS)) {
                                effective.put(name, path);
                                continue;
                            }
                            String[] parts = name.split("/", 4);
                            if (!multiRelease || parts.length != 4 || parts[3].isEmpty()) continue;
                            if (parts[3].endsWith("module-info.class")) continue;
                            int version;
                            try {
                                version = Integer.parseInt(parts[2]);
                            } catch (NumberFormatException error) {
                                throw new IllegalArgumentException("Invalid multi-release path in " + id + ": " + name);
                            }
                            if (version > RUNTIME_FEATURE) continue;
                            versioned.computeIfAbsent(parts[3], key -> new TreeMap<>()).put(version, path);
                        }
                    }
                    for (var entry : versioned.entrySet()) {
                        String name = entry.getKey();
                        var highest = entry.getValue().lastEntry();
                        if (effective.containsKey(name)) {
                            multiReleaseIgnored.add(id + "!" + name + " (versions " + entry.getValue().keySet() + ")");
                            continue;
                        }
                        effective.put(name, highest.getValue());
                        multiReleasePromoted.add(id + "!" + name + "=version " + highest.getKey());
                    }
                    for (var entry : effective.entrySet()) {
                        Path path = entry.getValue();
                        String name = entry.getKey();
                        if (name.equals("module-info.class") || name.endsWith("/module-info.class")) {
                            droppedEntries.add(id + "!" + name);
                            continue;
                        }
                        if (name.startsWith(HOST_METADATA)) {
                            // Mod-shipped Native Image configuration would be applied to the
                            // whole image, including initialization policy for shared classes.
                            droppedEntries.add(id + "!" + name);
                            continue;
                        }
                        if (name.startsWith(SERVICES) && !name.endsWith("/")) {
                            collectService(services, serviceProviders, id, name.substring(SERVICES.length()),
                                    Files.readAllLines(path));
                            continue;
                        }
                        if (name.endsWith(".class")) {
                            if (name.endsWith("/package-info.class")) continue;
                            // A generator whose output a replacement computes from data has no
                            // caller once that member is rewritten, so it is left out rather than
                            // failing the build on the run-time class definition it performs.
                            if (RuntimeLowering.GENERATOR_CLASSES.contains(
                                    name.substring(0, name.length() - ".class".length()))) {
                                droppedEntries.add(id + "!" + name);
                                continue;
                            }
                            if (mixinPlugins.contains(name.substring(0, name.length() - ".class".length()))) {
                                droppedEntries.add(id + "!" + name + " (MixinConfigPlugin)");
                                byte[] plugin = Files.readAllBytes(path);
                                RuntimeLowering.collectMixinPluginEarlyInit(name, plugin, hash(plugin),
                                        earlyInitializers, adaptations);
                                continue;
                            }
                            boolean mixinPackage = mixinPackages.stream().anyMatch(name::startsWith);
                            if (mixinPackage) {
                                // A mixin is read from the jar instead of being transformed by
                                // Knot, which refuses to hand out a class a Mixin config owns.
                                //
                                // Every such class still ships, stripped of its Mixin annotations.
                                // A Mixin-derived member the merge copied into the target names the
                                // owner type - in a supertype list, a cast or a signature - and a
                                // class that references a type the image does not contain cannot be
                                // loaded at all. Native Image does not fail that build: it replaces
                                // every call into the unreachable class with a stub that throws
                                // NoSuchMethodError at run time, which is indistinguishable from an
                                // unrelated missing method minutes into start-up.
                                //
                                // The raw bytes are only the fallback: a static @Accessor keeps its
                                // implementation in the interface's own method body, written there
                                // by Mixin when the target is transformed. Shipping the raw stub
                                // body would make every call hit `Untransformed @Accessor`, so the
                                // transformer is asked first and its answer wins when it differs.
                                byte[] rawBytes = Files.readAllBytes(path);
                                ClassNode raw = parse(rawBytes);
                                if (!name.equals(raw.name + ".class")) {
                                    throw new IllegalArgumentException("Invalid class path in " + id + ": " + name);
                                }
                                // Read the declared targets before the annotation is stripped: a
                                // target outside the game jar is a library class, and Mixin would
                                // have merged into it in the reference client.
                                collectMixinTargets(raw, mixinTargets);
                                byte[] bytes = rawBytes;
                                try {
                                    byte[] transformed = transform(transform, delegate, name);
                                    if (!Arrays.equals(rawBytes, transformed)) {
                                        ClassNode node = parse(transformed);
                                        if (!name.equals(node.name + ".class")) {
                                            throw new IllegalStateException("transformed name mismatch");
                                        }
                                        RuntimeLowering.stripMixinMetadata(node);
                                        verify(node);
                                        bytes = classBytes(node);
                                        mixinAccessorsApplied.add(id + "!" + name);
                                    }
                                } catch (RuntimeException | ReflectiveOperationException | java.io.IOException problem) {
                                    mixinAccessorsRefused.add(id + "!" + name
                                            + " (" + problem.getMessage() + ")");
                                }
                                if (bytes == rawBytes) {
                                    RuntimeLowering.stripMixinMetadata(raw);
                                    verify(raw);
                                    bytes = classBytes(raw);
                                }
                                put(jar, names, name, bytes);
                                mixinClasses.add(raw.name);
                                modClasses.add(raw.name.replace('/', '.'));
                                continue;
                            }
                            if (base.getEntry(name) != null) throw new IllegalArgumentException("Mod shadows Minecraft: " + name);
                            int previousAdaptations = adaptations.size();
                            int previousStubs = stubbed.size();
                            try {
                                byte[] data = transform(transform, delegate, name);
                                ClassNode node = parse(data);
                                if (!name.equals(node.name + ".class")) {
                                    throw new IllegalArgumentException("Invalid class path in " + id + ": " + name);
                                }
                                String sourceHash = hash(Files.readAllBytes(path));
                                RuntimeLowering.lowerJadeMetadata(node, sourceHash,
                                        jadeFlags, jadeDisabledTooltips, adaptations);
                                RuntimeLowering.lowerModFile(node, sourceHash, adaptations);
                                RuntimeLowering.lowerLoaderMetadata(node, sourceHash, adaptations);
                                RuntimeLowering.lowerVersionLookup(node, sourceHash, adaptations);
                                RuntimeLowering.lowerSodiumMetadata(node, sourceHash, adaptations);
                                RuntimeLowering.lowerImmediatelyFastVersion(node, sourceHash, adaptations);
                                // Must precede lowerQueries: the Loader query fold would otherwise
                                // turn the scan into an empty iteration before the table replaces
                                // it, and an empty config list links no properties at all.
                                if (node.name.equals(CONFIG_HELPER) && !frameworkConfigs.isEmpty()) {
                                    RuntimeLowering.lowerConfigDiscovery(node, adaptations);
                                }
                                RuntimeLowering.lowerQueries(node, loadedIds, versions, adaptations, stubbed, protectedMethods);
                                RuntimeLowering.collectStageQueries(node, queriedStages);
                                RuntimeLowering.foldIndigoGate(node, indigoApplicable, indigoPluginHash, adaptations);
                                RuntimeLowering.lowerGlitchCoreEvents(node, sourceHash, adaptations);
                                RuntimeLowering.collectSerializationRoots(node, serializationRoots);
                                RuntimeLowering.replaceGeneratedSerializer(node, adaptations);
                                if (id.equals("fabric-api-base") && node.name.endsWith("/EventFactoryImpl")) {
                                    RuntimeLowering.removeUnusedEventProxy(id, hash(Files.readAllBytes(path)), node, adaptations);
                                }
                                validateModCode(id, node);
                                verify(node, adaptations);
                                collectArgumentHolders(node, argumentHolders);
                                collectExtrasReferences(node, extrasTypes);
                                collectRegistryContainers(node, registryContainers);
                                if (node.name.equals(REGISTRATION_HELPER) && !registryContainers.isEmpty()) {
                                    rewriteRegistrationScan(node, registryContainers, adaptations);
                                }
                                // The residue pass stubs methods without recording an adaptation,
                                // so the stub delta has to count too: otherwise a class whose only
                                // change is a stub ships with its original, Loader-calling body.
                                boolean rewritten = adaptations.size() != previousAdaptations
                                        || stubbed.size() != previousStubs;
                                // The generated addListenerResolved keeps the original body but
                                // has two parameters instead of one. Copied relative stack-map
                                // frames are measured from a one-parameter implicit frame, so the
                                // JVM rejects the exception-handler frame; only this class needs
                                // its frames recomputed from the rewritten control flow.
                                put(jar, names, name, rewritten
                                        ? (node.name.equals(RuntimeLowering.GLITCHCORE_MANAGER)
                                                ? recomputedClassBytes(node) : classBytes(node))
                                        : data);
                                modClasses.add(node.name.replace('/', '.'));
                            } catch (RuntimeException problem) {
                                failures.add(id + "/" + name + ": " + problem.getMessage());
                            }
                        } else if (!name.endsWith(".class")) {
                            // Only ship what closed-world code can actually reach: data files under
                            // `assets/`/`data/` (the runtime resource config embeds them) and root
                            // level declarative files (a bundled default config like
                            // `/forgeconfigapiport.toml`, mixin configs, the mod descriptor). Mods
                            // also carry junk - bundled resource packs (resourcepacks/,
                            // programmer_art/), license texts, .cache/ scratch data - and one build
                            // merged 2,173 such entries into the jar; the analysis heap jumped by
                            // gigabytes and the image never built, so the merge stays narrow.
                            // Nested Mod jars stay excluded: their classes are merged separately.
                            boolean dataTree = name.startsWith("assets/") || name.startsWith("data/");
                            if (!dataTree && (name.startsWith("META-INF/") || name.contains("/"))) continue;
                            if (!dataTree && !name.equals("pack.mcmeta") && !name.endsWith(".toml")
                                    && !name.endsWith(".json")) continue;
                            byte[] data = Files.readAllBytes(path);
                            var existing = pendingResources.get(name);
                            if (existing != null) {
                                data = mergeResource(name, existing, data, mergedResources);
                            }
                            pendingResources.put(name, data);
                        }
                    }
                }
            }
            if (selected.isEmpty()) throw new IllegalArgumentException("No client mods resolved by Fabric Loader");
            // A Mixin may target a library class instead of a game class: Fabric API's dimension
            // module makes datafixerupper's TaggedChoice implement an extension interface, and a
            // redirect it injects into V2832 then casts to that interface. Library jars are never
            // merged, so the cast failed with ClassCastException during data fixer initialisation.
            // The transformed copy ships in the overlay; the client jar precedes every library on
            // the image classpath, so it shadows the untouched original.
            for (String mixinTarget : mixinTargets) {
                String entry = mixinTarget + ".class";
                if (names.contains(entry)) continue;
                byte[] original;
                try (var in = AotExport.class.getResourceAsStream("/" + entry)) {
                    if (in == null) {
                        mixinTargetsAbsent.add(mixinTarget);
                        continue;
                    }
                    original = in.readAllBytes();
                }
                byte[] after;
                try {
                    after = transform(transform, delegate, entry);
                } catch (RuntimeException | ReflectiveOperationException problem) {
                    mixinTargetsAbsent.add(mixinTarget + " (" + problem.getMessage() + ")");
                    continue;
                }
                if (Arrays.equals(after, original)) continue;
                ClassNode node = parse(after);
                if (!mixinTarget.equals(node.name)) {
                    throw new IllegalArgumentException("Mixin target resolved elsewhere: " + entry);
                }
                verify(node);
                put(jar, names, entry, after);
                libraryTransforms.add(mixinTarget);
            }
            for (var holder : argumentHolders.entrySet()) {
                put(jar, names, holder.getKey() + ".class", argumentHolder(holder.getKey(), holder.getValue()));
                generatedArgumentHolders.add(holder.getKey() + " " + holder.getValue().keySet());
            }
            for (String extra : extrasTypes) {
                String entry = extra + ".class";
                if (names.contains(entry)) continue;
                byte[] resolved = refImplBytes(extra);
                if (resolved != null) {
                    // MixinExtras writes these impls in memory when sugar is applied; the shape the
                    // rewritten hosts use is fixed (<init>/init/dispose plus the LocalRef interface),
                    // so the class is reproduced here instead of being asked from Knot.
                    put(jar, names, entry, resolved);
                    extrasShipped.add(extra + " (generated)");
                    continue;
                }
                try {
                    byte[] bytes = transform(transform, delegate, entry);
                    ClassNode node = parse(bytes);
                    if (!extra.equals(node.name)) throw new IllegalStateException("resolved elsewhere");
                    verify(node);
                    put(jar, names, entry, bytes);
                    extrasShipped.add(extra);
                } catch (RuntimeException | ReflectiveOperationException | java.io.IOException problem) {
                    extrasAbsent.add(extra + " (" + problem.getMessage() + ")");
                }
            }
            // The holder's base class and the two exceptions its index checks throw. They come from
            // the pinned Mixin jar on the tool classpath and touch nothing else in that jar.
            for (String api : List.of("Args", "ArgumentCountException", "ArgumentIndexOutOfBoundsException")) {
                String path = ARGS_PACKAGE + api + ".class";
                try (var in = AotExport.class.getResourceAsStream("/" + path)) {
                    if (in == null) throw new IllegalStateException("Pinned Mixin class missing: " + path);
                    put(jar, names, path, in.readAllBytes());
                }
            }
            // Mods keep defensive catch/throw sites around Mixin's own exception (libgui's
            // IViewRootDefaultImpl is the shipped case). A merged class that names a type the
            // image lacks cannot be linked, so the exception and the two interface types its
            // constructor signature names ship from the pinned Mixin jar as well.
            for (String pinned : List.of("throwables/MixinException",
                    "extensibility/IActivityContext", "extensibility/IActivityContext$IActivity")) {
                String path = "org/spongepowered/asm/mixin/" + pinned + ".class";
                try (var in = AotExport.class.getResourceAsStream("/" + path)) {
                    if (in == null) throw new IllegalStateException("Pinned Mixin class missing: " + path);
                    put(jar, names, path, in.readAllBytes());
                }
            }
            for (String synthetic : syntheticClasses) {
                String entry = synthetic + ".class";
                if (names.contains(entry)) continue;
                try {
                    byte[] bytes = transform(transform, delegate, entry);
                    ClassNode node = parse(bytes);
                    if (!synthetic.equals(node.name)) throw new IllegalStateException("resolved elsewhere");
                    verify(node);
                    put(jar, names, entry, bytes);
                    syntheticShipped.add(synthetic);
                } catch (RuntimeException | ReflectiveOperationException | java.io.IOException problem) {
                    syntheticAbsent.add(synthetic + " (" + problem.getMessage() + ")");
                }
            }
            if (!failures.isEmpty()) {
                // Grouped by Mod so the driver can retry without the Mods that cannot join a
                // closed world, instead of failing the whole pack on the first bad class.
                var blocked = new TreeMap<String, List<String>>();
                for (String failure : failures) {
                    int separator = failure.indexOf('/');
                    String id = separator < 0 ? "client" : failure.substring(0, separator);
                    blocked.computeIfAbsent(id, key -> new ArrayList<>()).add(failure);
                }
                var report = new TreeMap<String, Object>();
                report.put("mods", blocked);
                Files.writeString(output.resolve("incompatible.json"), JSON.toJson(report));
                throw new IllegalArgumentException(failures.size() + " class(es) cannot be lowered in "
                        + blocked.size() + " Mod(s):\n  " + String.join("\n  ", failures));
            }
            for (var resource : pendingResources.entrySet()) {
                byte[] data = resource.getValue();
                var vanilla = base.getEntry(resource.getKey());
                if (vanilla != null) {
                    overriddenResources.add(resource.getKey());
                    try (var input = base.getInputStream(vanilla)) {
                        data = mergeResource(resource.getKey(), input.readAllBytes(), data, mergedResources);
                    }
                }
                put(jar, names, resource.getKey(), data);
                resources.add(resource.getKey());
            }
            // The closed image has no ModResourcePackCreator, so the built-in pack is the only
            // pack that can report namespaces. Rewriting its build() above makes it consult this
            // generated table, which is a build-time constant set of the paths actually shipped.
            if (!changes.containsKey(RuntimeLowering.VANILLA_PACK_BUILDER + ".class")) {
                throw new IllegalStateException("Vanilla pack builder was not rewritten;"
                        + " shipped resource namespaces would remain unreachable");
            }
            var shippedResources = new TreeSet<>(resourceEntryNames);
            shippedResources.addAll(pendingResources.keySet());
            shippedNamespaces.addAll(RuntimeLowering.resourceNamespaces(shippedResources));
            if (!shippedNamespaces.contains("minecraft")) {
                throw new IllegalStateException("Resource namespace scan lost the vanilla tree: "
                        + shippedNamespaces);
            }
            byte[] namespaceClass = RuntimeLowering.modNamespacesClass(shippedNamespaces);
            verify(parse(namespaceClass));
            put(jar, names, RuntimeLowering.MOD_NAMESPACES + ".class", namespaceClass);
            adaptations.add(RuntimeLowering.MOD_NAMESPACES + " exposes "
                    + shippedNamespaces.size() + " shipped resource namespaces");
            for (Class<?> api : List.of(ModInitializer.class, ClientModInitializer.class, EnvType.class,
                    CallbackInfo.class, CallbackInfoReturnable.class, Cancellable.class,
                    CancellationException.class)) {
                String name = api.getName().replace('.', '/') + ".class";
                try (var resource = api.getResourceAsStream("/" + name)) {
                    put(jar, names, name, resource.readAllBytes());
                }
            }
            // A shipped Mod class that implements a Fabric API interface cannot be linked unless
            // that interface is in the image too. Native Image does not fail the build for this:
            // it silently turns every reference into a run-time NoClassDefFoundError. XaeroLib's
            // three client entrypoints also implement DedicatedServerModInitializer, which the
            // hand-kept allow-list above omitted, so all three were unlinkable. Ship the whole
            // inert net/fabricmc/api package from the pinned Loader jar instead of guessing which
            // declarations the pack happens to name.
            for (var api : fabricApiTypes().entrySet()) {
                if (names.contains(api.getKey())) continue;
                put(jar, names, api.getKey(), api.getValue());
                pinnedFabricApi.add(api.getKey());
            }
            // The generated dispatch list hands out objects through the Loader's own container
            // interface, so that interface and the type it reports have to exist in the image.
            // Both are inert declarations: no Loader instance, no discovery, no class loading.
            for (String name : List.of("net/fabricmc/loader/api/entrypoint/EntrypointContainer",
                    "net/fabricmc/loader/api/ModContainer")) {
                try (var resource = target.getResourceAsStream(name + ".class")) {
                    if (resource == null) throw new IllegalStateException("Pinned Loader API class missing: " + name);
                    put(jar, names, name + ".class", resource.readAllBytes());
                }
            }
            for (String name : new TreeSet<>(RuntimeLowering.PURE_LOADER_TYPES)) {
                try (var resource = target.getResourceAsStream(name + ".class")) {
                    if (resource == null) throw new IllegalStateException("Pinned version value type missing: " + name);
                    put(jar, names, name + ".class", resource.readAllBytes());
                }
            }
            put(jar, names, STATIC_HOOKS + "$Container.class", entrypointContainer());
            // Only stages with a surviving lowered query can be reached by this runtime ABI.
            // Metadata also declares optional integrations whose provider classes may not exist.
            for (String stage : new ArrayList<>(stages.keySet())) {
                if (!queriedStages.contains(stage)) unqueriedStages.put(stage, stages.remove(stage));
            }
            for (var providers : stages.values()) {
                for (String value : providers) {
                    try (var resource = target.getResourceAsStream(value.replace('.', '/') + ".class")) {
                        if (resource == null) throw new IllegalArgumentException("Missing live stage provider " + value);
                        var providerNode = parse(resource.readAllBytes());
                        boolean singleton = providerNode.fields.stream().anyMatch(field -> field.name.equals("INSTANCE")
                                && field.desc.equals("L" + providerNode.name + ";")
                                && (field.access & (ACC_PUBLIC | ACC_STATIC)) == (ACC_PUBLIC | ACC_STATIC));
                        if (singleton) singletonStageProviders.add(value);
                        else if (providerNode.methods.stream().noneMatch(method -> method.name.equals("<init>")
                                && method.desc.equals("()V") && (method.access & ACC_PUBLIC) != 0)) {
                            throw new IllegalArgumentException("Stage provider has no public constructor or singleton: " + value);
                        }
                    }
                }
            }
            // The hooks class is generated, not copied, so a generation bug would otherwise only
            // surface as a VerifyError inside the image - Native Image silently drops the class
            // and every call into it becomes a NoSuchMethodError minutes into start-up.
            var hooksNode = parse(staticHooks(entries, loadedIds, stages, modDependencies,
                    singletonStageProviders, versions, modNames, stageOwners, earlyInitializers));
            verify(hooksNode);
            put(jar, names, STATIC_HOOKS + ".class", classBytes(hooksNode));
            // The generated config table is only meaningful together with the annotation
            // instances it hands to the framework; both are built from the same scan and are
            // verified here for the same reason as the hooks class.
            if (!frameworkConfigs.isEmpty()) {
                put(jar, names, RuntimeLowering.CONFIG_ANNOTATION + ".class",
                        RuntimeLowering.frameworkConfigAnnotationClass());
                var configTable = parse(RuntimeLowering.frameworkConfigsClass(frameworkConfigs));
                verify(configTable);
                put(jar, names, RuntimeLowering.CONFIG_TABLE + ".class", classBytes(configTable));
                // A static initializer that reads Mod fields must not run inside the image
                // builder: it would initialize the Mod's config classes before the game exists.
                modClasses.add(RuntimeLowering.CONFIG_TABLE.replace('/', '.'));
                modClasses.add(RuntimeLowering.CONFIG_ANNOTATION.replace('/', '.'));
                var roots = new TreeSet<String>();
                for (String[] entry : frameworkConfigs) roots.add(entry[0]);
                put(jar, names, METADATA + "framework-config-roots.json", utf8(JSON.toJson(roots)));
            }
            // First-party replacements for run-time generated code. They are compiled ahead of the
            // export against the same Mod jars, because the Mod APIs they implement are not part of
            // the vanilla reference classpath the tool itself is built from.
            if (runtimeClasses != null) {
                try (var tree = Files.walk(runtimeClasses)) {
                    for (var path : tree.filter(item -> item.toString().endsWith(".class")).toList()) {
                        String name = runtimeClasses.relativize(path).toString().replace('\\', '/');
                        put(jar, names, name, Files.readAllBytes(path));
                        runtimeExported.add(name);
                    }
                }
            }
            for (String type : List.of("Operation", "WrapOperationRuntime", "IncorrectArgumentCountException")) {
                String name = WRAP_OPERATION + type + ".class";
                // The extras closure above may already have resolved the same class from Knot.
                if (names.contains(name)) continue;
                try (var resource = target.getResourceAsStream(name)) {
                    if (resource == null) throw new IllegalStateException("Pinned MixinExtras runtime class missing: " + name);
                    put(jar, names, name, resource.readAllBytes());
                }
            }
            modClasses.add(STATIC_HOOKS.replace('/', '.'));
            for (var service : services.entrySet()) {
                String name = SERVICES + service.getKey();
                if (base.getEntry(name) != null) {
                    throw new IllegalArgumentException("Service registration shadows Minecraft: " + name);
                }
                put(jar, names, name, utf8(String.join("\n", service.getValue()) + "\n"));
                resources.add(name);
            }
            var reflection = new ArrayList<Map<String, Object>>();
            for (String provider : serviceProviders) {
                reflection.add(Map.of("type", provider,
                        "methods", List.of(Map.of("name", "<init>", "parameterTypes", List.of()))));
            }
            var metadata = new TreeMap<String, Object>();
            metadata.put("resources", resources.stream().map(name -> Map.of("glob", name)).toList());
            if (!reflection.isEmpty()) metadata.put("reflection", reflection);
            put(jar, names, METADATA + "native-image.properties",
                    utf8("Args = --initialize-at-run-time=" + String.join(",", modClasses) + "\n"));
            put(jar, names, METADATA + "reachability-metadata.json", utf8(JSON.toJson(metadata)));
            serializationRoots.removeIf(name -> !modClasses.contains(name.replace('/', '.')));
            put(jar, names, METADATA + "serialization-roots.json", utf8(JSON.toJson(serializationRoots)));
        }
        var report = new TreeMap<String, Object>();
        report.put("loader", FabricLoaderImpl.VERSION);
        report.put("namespace", "official");
        report.put("resolvedMods", selected);
        report.put("entrypoints", entries);
        report.put("gameTransforms", changes);
        report.put("resources", resources);
        report.put("resourceNamespaces", shippedNamespaces);
        report.put("runtimeInitializedClasses", modClasses);
        report.put("serializationRoots", serializationRoots);
        report.put("staticAdaptations", adaptations);
        report.put("frameworkConfigs", frameworkConfigs.stream()
                .map(entry -> entry[0] + "#" + entry[1]).toList());
        report.put("stubbedMethods", stubbed);
        report.put("entrypointStages", stages);
        report.put("singletonStageProviders", singletonStageProviders);
        report.put("queriedEntrypointStages", queriedStages);
        report.put("unqueriedEntrypointStages", unqueriedStages);
        report.put("entrypointStageOwners", stageOwners);
        report.put("services", services);
        report.put("serviceProviders", serviceProviders);
        report.put("multiReleaseIgnored", multiReleaseIgnored);
        report.put("multiReleasePromoted", multiReleasePromoted);
        report.put("droppedEntries", droppedEntries);
        report.put("runtimeClasses", runtimeExported);
        report.put("pinnedFabricApi", pinnedFabricApi);
        report.put("earlyInitializers", earlyInitializers);
        report.put("mixinClasses", mixinClasses);
        report.put("mixinAccessorsApplied", mixinAccessorsApplied);
        report.put("mixinAccessorsRefused", mixinAccessorsRefused);
        report.put("syntheticShipped", syntheticShipped);
        report.put("syntheticAbsent", syntheticAbsent);
        report.put("mixinPlugins", mixinPlugins);
        report.put("libraryTransforms", libraryTransforms);
        report.put("argumentHolders", generatedArgumentHolders);
        report.put("extrasShipped", extrasShipped);
        report.put("extrasAbsent", extrasAbsent);
        report.put("mixinTargetsAbsent", mixinTargetsAbsent);
        report.put("mergedResources", mergedResources);
        report.put("overriddenResources", overriddenResources);
        Files.writeString(output.resolve("transform.json"), JSON.toJson(report));
        System.out.println("MCFAO_FABRIC_EXPORT_PASS");
    }

    private static <T> void collect(List<Entry> entries, Set<String> requested, FabricLoaderImpl loader,
            ClassLoader target, Method transformMethod, Object delegate, String stage, Class<T> type,
            String method) throws Exception {
        for (var container : loader.getEntrypointContainers(stage, type)) {
            String id = container.getProvider().getMetadata().getId();
            if (!requested.contains(id)) {
                // Excluded while pruning an incompatible Mod; its entrypoint is not dispatched.
                continue;
            }
            String definition = container.getDefinition();
            int separator = definition.indexOf("::");
            if (separator < 0) {
                // Non-initializing verification. Fabric's class-form default adapter uses a no-arg
                // constructor; a Kotlin adapter returns the `object` singleton instead, which has
                // no accessible constructor of its own.
                Class<?> entry = Class.forName(definition, false, target);
                if (!type.isAssignableFrom(entry) || java.lang.reflect.Modifier.isAbstract(entry.getModifiers())
                        || !java.lang.reflect.Modifier.isPublic(entry.getModifiers())) {
                    throw new IllegalArgumentException("Unsupported " + id + " entrypoint " + definition);
                }
                boolean singleton = hasSingletonInstance(entry);
                if (!singleton) entry.getConstructor();
                entries.add(new Entry(id, stage, definition, type.getName().replace('.', '/'), method,
                        null, null, false, singleton));
                continue;
            }
            // Method-reference form: resolve the target at build time so the closed-world client
            // needs no MethodHandle. Fabric accepts any no-argument void method as the creator.
            String owner = definition.substring(0, separator);
            String refName = definition.substring(separator + 2);
            ClassNode node = parse(transform(transformMethod, delegate, owner.replace('.', '/') + ".class"));
            MethodNode found = null;
            for (MethodNode candidate : node.methods) {
                if (candidate.name.equals(refName) && candidate.desc.equals("()V")) {
                    found = candidate;
                    break;
                }
            }
            if (found == null) {
                throw new IllegalArgumentException(
                        "Entrypoint method reference needs a no-argument void method: " + definition);
            }
            boolean isStatic = (found.access & ACC_STATIC) != 0;
            Class<?> entry = Class.forName(owner, false, target);
            if (!isStatic) {
                if (!java.lang.reflect.Modifier.isPublic(entry.getModifiers())
                        || java.lang.reflect.Modifier.isAbstract(entry.getModifiers())) {
                    throw new IllegalArgumentException("Unsupported " + id + " entrypoint " + definition);
                }
                entry.getConstructor();
            }
            entries.add(new Entry(id, stage, definition, type.getName().replace('.', '/'), method,
                    owner, refName, isStatic, false));
        }
    }

    /**
     * A Kotlin `object` initializer exposes its single instance as a static INSTANCE field and
     * keeps its constructor private. Emitting the field read keeps the hook free of reflection.
     */
    private static boolean hasSingletonInstance(Class<?> type) {
        try {
            var field = type.getDeclaredField("INSTANCE");
            return java.lang.reflect.Modifier.isStatic(field.getModifiers()) && field.getType() == type;
        } catch (NoSuchFieldException absent) {
            return false;
        }
    }

    private static void collectMixinTargets(ClassNode node, Set<String> targets) {
        // Mixin declares its annotation with CLASS retention, so it is usually invisible here; a
        // few Mods keep it visible. Both lists have to be read.
        var annotations = new ArrayList<org.objectweb.asm.tree.AnnotationNode>();
        if (node.visibleAnnotations != null) annotations.addAll(node.visibleAnnotations);
        if (node.invisibleAnnotations != null) annotations.addAll(node.invisibleAnnotations);
        for (var annotation : annotations) {
            if (!"Lorg/spongepowered/asm/mixin/Mixin;".equals(annotation.desc) || annotation.values == null) continue;
            for (int index = 0; index + 1 < annotation.values.size(); index += 2) {
                Object value = annotation.values.get(index + 1);
                if ("value".equals(annotation.values.get(index))) {
                    if (!(value instanceof List<?> classes)) continue;
                    for (Object element : classes) {
                        if (element instanceof org.objectweb.asm.Type type) targets.add(type.getInternalName());
                    }
                } else if ("targets".equals(annotation.values.get(index)) && value instanceof List<?> names) {
                    for (Object element : names) {
                        if (element instanceof String text) targets.add(text.replace('.', '/'));
                    }
                }
            }
        }
    }

    /** Records every MixinExtras type a merged class names, so the library closure can be shipped. */
    private static void collectExtrasReferences(ClassNode node, Set<String> types) {
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                String owner = null;
                if (instruction instanceof MethodInsnNode call) owner = call.owner;
                else if (instruction instanceof org.objectweb.asm.tree.FieldInsnNode field) owner = field.owner;
                else if (instruction instanceof org.objectweb.asm.tree.TypeInsnNode type) owner = type.desc;
                if (owner != null && owner.startsWith("com/llamalad7/mixinextras/")) types.add(owner);
            }
        }
    }

    /**
     * Records the static final fields of a class the framework annotates as a registry container.
     * These are exactly the members the original reflections scan would hand to the helper, so
     * they can replace the scan with plain {@code GETSTATIC} reads.
     */
    private static void collectRegistryContainers(ClassNode node, Map<String, List<String[]>> containers) {
        var annotations = new ArrayList<org.objectweb.asm.tree.AnnotationNode>();
        if (node.visibleAnnotations != null) annotations.addAll(node.visibleAnnotations);
        if (node.invisibleAnnotations != null) annotations.addAll(node.invisibleAnnotations);
        boolean marked = annotations.stream().anyMatch(a -> REGISTRY_CONTAINER_DESC.equals(a.desc));
        if (!marked) return;
        var fields = new ArrayList<String[]>();
        for (var field : node.fields) {
            if ((field.access & Opcodes.ACC_STATIC) == 0 || (field.access & Opcodes.ACC_FINAL) == 0) continue;
            if (field.desc.length() == 1) continue; // primitives can never satisfy an object query
            // Native Image resolves field accesses with access checks: a GETSTATIC from another
            // class onto a private field fails resolution and becomes a run-time NoSuchFieldError.
            // Containers that keep values private expose a getter instead - find it now, while
            // the class body is still here to inspect.
            String getter = "";
            if ((field.access & Opcodes.ACC_PUBLIC) == 0) {
                for (var candidate : node.methods) {
                    if ((candidate.access & Opcodes.ACC_PUBLIC) == 0
                            || (candidate.access & Opcodes.ACC_STATIC) == 0
                            || candidate.instructions == null
                            || !candidate.desc.equals("()" + field.desc)) continue;
                    boolean reads = false;
                    for (var insn : candidate.instructions.toArray()) {
                        if (insn instanceof FieldInsnNode f && f.getOpcode() == Opcodes.GETSTATIC
                                && f.owner.equals(node.name) && f.name.equals(field.name)
                                && f.desc.equals(field.desc)) {
                            reads = true;
                            break;
                        }
                    }
                    if (reads) {
                        getter = candidate.name;
                        break;
                    }
                }
            }
            fields.add(new String[]{field.name, field.desc, String.valueOf(field.access), getter});
        }
        containers.put(node.name, fields);
    }

    /**
     * Records every static field carrying {@code @FrameworkConfig}.
     *
     * <p>The annotation is the whole declaration: its {@code id}/{@code name} name the config
     * file, {@code type} decides client/server/sync behaviour and {@code separator} picks the
     * path syntax. They are read here, from the annotation attached to the shipped field, because
     * nothing at run time can re-read {@code fabric.mod.json} to find the class in the first place.
     * A field the generated table cannot read without reflection is skipped and reported rather
     * than shipped as a broken entry.
     */
    private static void collectFrameworkConfigs(ClassNode node, List<String[]> configs) {
        for (var field : node.fields) {
            if ((field.access & Opcodes.ACC_STATIC) == 0 || field.visibleAnnotations == null) continue;
            for (var annotation : field.visibleAnnotations) {
                if (!FRAMEWORK_CONFIG_DESC.equals(annotation.desc)) continue;
                Object id = annotationValue(annotation, "id", "");
                Object name = annotationValue(annotation, "name", "");
                if (!(id instanceof String identifier) || identifier.isEmpty()
                        || !(name instanceof String label) || label.isEmpty()) {
                    throw new IllegalArgumentException("@" + FRAMEWORK_CONFIG
                            + " without id/name on " + node.name + "#" + field.name);
                }
                Object type = annotationValue(annotation, "type", null);
                String typeName = type instanceof String[] constant && constant.length == 2
                        ? constant[1] : "UNIVERSAL";
                Object separator = annotationValue(annotation, "separator", null);
                char separatorChar = separator instanceof Integer code ? (char) code.intValue() : '.';
                boolean readOnly = Boolean.TRUE.equals(annotationValue(annotation, "readOnly", null));
                configs.add(new String[]{node.name, field.name, field.desc, identifier, label,
                        Boolean.toString(readOnly), typeName, Character.toString(separatorChar)});
            }
        }
    }

    private static Object annotationValue(org.objectweb.asm.tree.AnnotationNode annotation,
            String name, Object fallback) {
        if (annotation.values == null) return fallback;
        for (int index = 0; index + 1 < annotation.values.size(); index += 2) {
            if (name.equals(annotation.values.get(index))) return annotation.values.get(index + 1);
        }
        return fallback;
    }

    /**
     * Replaces the helper's reflections-backed scan with the recorded container fields. The
     * generated body keeps the original contract - declared type assignable to the query, value
     * of a public-shaped static final field - without any run-time classpath, reflection or
     * library code. Frames are written by hand: every branch target resumes with an empty stack
     * over the same three locals.
     */
    private static void rewriteRegistrationScan(ClassNode node, Map<String, List<String[]>> containers,
            List<String> adaptations) {
        var method = node.methods.stream().filter(m -> "getRegistryObjects".equals(m.name)
                && "(Ljava/lang/Class;)Ljava/util/List;".equals(m.desc)).findFirst().orElse(null);
        if (method == null) throw new IllegalStateException("Registration scan method missing in " + node.name);
        var body = new InsnList();
        // The original scan resolved every container through `ReflectionUtils.getClass`, and
        // `Class.forName(..., initialize=true)` initialized it in passing. Constructing the
        // entries inside a container's static initializer registers them with `Registration`,
        // which the caller reads right after this method - containers whose fields the current
        // query never touches would otherwise stay unloaded and their entries unregistered.
        for (String container : containers.keySet()) {
            body.add(new LdcInsnNode(container.replace('/', '.')));
            body.add(new InsnNode(ICONST_1));
            body.add(new MethodInsnNode(INVOKESTATIC, "java/lang/ClassLoader", "getSystemClassLoader",
                    "()Ljava/lang/ClassLoader;", false));
            body.add(new MethodInsnNode(INVOKESTATIC, "java/lang/Class", "forName",
                    "(Ljava/lang/String;ZLjava/lang/ClassLoader;)Ljava/lang/Class;", false));
            body.add(new InsnNode(POP));
        }
        body.add(new TypeInsnNode(NEW, "java/util/ArrayList"));
        body.add(new InsnNode(DUP));
        body.add(new MethodInsnNode(INVOKESPECIAL, "java/util/ArrayList", "<init>", "()V", false));
        body.add(new VarInsnNode(ASTORE, 2));
        int fields = 0;
        int skipped = 0;
        for (var container : containers.entrySet()) {
            for (var field : container.getValue()) {
                boolean isPublic = (Integer.parseInt(field[2]) & Opcodes.ACC_PUBLIC) != 0;
                String getter = field[3];
                if (!isPublic && getter.isEmpty()) {
                    // Inaccessible and no getter: the value cannot be loaded from outside, and
                    // a stubbed access would blow up only when the scan reaches this branch.
                    skipped++;
                    continue;
                }
                var next = new org.objectweb.asm.tree.LabelNode();
                body.add(new VarInsnNode(ALOAD, 1));
                // The query asks for values assignable to the requested type, which is the FIELD's
                // declared type - `type.isAssignableFrom(fieldType)` - not the container class.
                // Comparing against the container made every test false and the scan returned an
                // empty list, so no entry ever reached `Registration` and nothing was created.
                body.add(new LdcInsnNode(org.objectweb.asm.Type.getType(field[1])));
                body.add(new MethodInsnNode(INVOKEVIRTUAL, "java/lang/Class", "isAssignableFrom",
                        "(Ljava/lang/Class;)Z", false));
                body.add(new JumpInsnNode(IFEQ, next));
                body.add(new VarInsnNode(ALOAD, 2));
                if (isPublic) {
                    body.add(new FieldInsnNode(GETSTATIC, container.getKey(), field[0], field[1]));
                } else {
                    body.add(new MethodInsnNode(INVOKESTATIC, container.getKey(), getter,
                            "()" + field[1], false));
                }
                body.add(new MethodInsnNode(INVOKEINTERFACE, "java/util/List", "add",
                        "(Ljava/lang/Object;)Z", true));
                body.add(new InsnNode(POP));
                body.add(next);
                body.add(new FrameNode(Opcodes.F_FULL, 3,
                        new Object[]{node.name, "java/lang/Class", "java/util/ArrayList"}, 0, new Object[]{}));
                fields++;
            }
        }
        body.add(new VarInsnNode(ALOAD, 2));
        body.add(new InsnNode(ARETURN));
        method.instructions = body;
        method.tryCatchBlocks = null;
        method.localVariables = null;
        method.maxStack = 3;
        method.maxLocals = 3;
        adaptations.add(node.name + "#getRegistryObjects scan=build-time field table over "
                + containers.size() + " container(s), " + fields + " field(s)"
                + (skipped == 0 ? "" : ", " + skipped + " inaccessible skipped"));
    }

    private static int indexOf(byte[] haystack, byte[] needle) {
        outer:
        for (int i = 0; i + needle.length <= haystack.length; i++) {
            for (int j = 0; j < needle.length; j++) {
                if (haystack[i + j] != needle[j]) continue outer;
            }
            return i;
        }
        return -1;
    }

    /** Records the anonymous helper classes Mixin generates for a rewritten target. */
    private static void collectSyntheticClasses(ClassNode node, Set<String> types) {
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                String owner = null;
                if (instruction instanceof MethodInsnNode call) owner = call.owner;
                else if (instruction instanceof org.objectweb.asm.tree.FieldInsnNode field) owner = field.owner;
                else if (instruction instanceof org.objectweb.asm.tree.TypeInsnNode type) owner = type.desc;
                if (owner != null && ANONYMOUS_HELPER.matcher(owner).matches()) types.add(owner);
            }
        }
    }

    // Mixin's InnerClassGenerator renames a merged inner class to
    // `target$innerSuffix$<uuid-v3-hex>` (32 lowercase hex, no dashes) and only materialises
    // the bytes when something asks for that exact name - anon helpers keep the older
    // `target$Anonymous$<hex>` shape. Both must be shipped with the transformed target or the
    // first construct of the merged inner class dies with NoClassDefFoundError at run time.
    private static final java.util.regex.Pattern ANONYMOUS_HELPER =
            java.util.regex.Pattern.compile(".+\\$(?:Anonymous\\$[0-9a-f]+|[0-9a-f]{32})");

    private static final String REF_IMPL_PREFIX = "com/llamalad7/mixinextras/sugar/impl/ref/generated/Local";
    private static final String REF_PACKAGE = "com/llamalad7/mixinextras/sugar/ref/Local";

    /**
     * Reproduces the ref impls MixinExtras writes in memory when sugar is applied. Every host that
     * names one uses the same fixed shape: a no-arg constructor, `init` to seed the value,
     * `dispose` to read it back, plus the `get`/`set` pair of the `LocalRef` interface.
     */
    private static byte[] refImplBytes(String internalName) {
        if (!internalName.startsWith(REF_IMPL_PREFIX) || !internalName.endsWith("RefImpl")) return null;
        String kind = internalName.substring(REF_IMPL_PREFIX.length(), internalName.length() - "RefImpl".length());
        String descriptor = switch (kind) {
            case "" -> "Ljava/lang/Object;";
            case "Boolean" -> "Z";
            case "Int" -> "I";
            case "Long" -> "J";
            case "Double" -> "D";
            default -> null;
        };
        if (descriptor == null) return null;
        String interfaze = REF_PACKAGE + (kind.isEmpty() ? "Ref" : kind + "Ref");
        var type = org.objectweb.asm.Type.getType(descriptor);
        int load = type.getOpcode(ILOAD);
        int store = type.getOpcode(IRETURN);
        // COMPUTE_MAXS matters: `init(J)` needs three local slots, and a hand-written maxs of zero
        // trips the verifier with "Arguments can't fit into locals".
        var writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        writer.visit(V25, ACC_PUBLIC | ACC_SUPER, internalName, null, "java/lang/Object", new String[]{interfaze});
        writer.visitField(ACC_PRIVATE, "value", descriptor, null, null).visitEnd();

        var constructor = writer.visitMethod(ACC_PUBLIC, "<init>", "()V", null, null);
        constructor.visitCode();
        constructor.visitVarInsn(ALOAD, 0);
        constructor.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        constructor.visitInsn(RETURN);
        constructor.visitMaxs(1, 1);
        constructor.visitEnd();

        var init = writer.visitMethod(ACC_PUBLIC, "init", "(" + descriptor + ")V", null, null);
        init.visitCode();
        init.visitVarInsn(ALOAD, 0);
        init.visitVarInsn(load, 1);
        init.visitFieldInsn(PUTFIELD, internalName, "value", descriptor);
        init.visitInsn(RETURN);
        init.visitMaxs(0, 0);
        init.visitEnd();

        var get = writer.visitMethod(ACC_PUBLIC, "get", "()" + descriptor, null, null);
        get.visitCode();
        get.visitVarInsn(ALOAD, 0);
        get.visitFieldInsn(GETFIELD, internalName, "value", descriptor);
        get.visitInsn(store);
        get.visitMaxs(0, 0);
        get.visitEnd();

        var set = writer.visitMethod(ACC_PUBLIC, "set", "(" + descriptor + ")V", null, null);
        set.visitCode();
        set.visitVarInsn(ALOAD, 0);
        set.visitVarInsn(load, 1);
        set.visitFieldInsn(PUTFIELD, internalName, "value", descriptor);
        set.visitInsn(RETURN);
        set.visitMaxs(0, 0);
        set.visitEnd();

        var dispose = writer.visitMethod(ACC_PUBLIC, "dispose", "()" + descriptor, null, null);
        dispose.visitCode();
        dispose.visitVarInsn(ALOAD, 0);
        dispose.visitFieldInsn(GETFIELD, internalName, "value", descriptor);
        dispose.visitVarInsn(ALOAD, 0);
        switch (descriptor) {
            case "Ljava/lang/Object;" -> dispose.visitInsn(ACONST_NULL);
            case "Z" -> dispose.visitInsn(ICONST_0);
            case "I" -> dispose.visitInsn(ICONST_0);
            case "J" -> dispose.visitInsn(LCONST_0);
            case "D" -> dispose.visitInsn(DCONST_0);
        }
        dispose.visitFieldInsn(PUTFIELD, internalName, "value", descriptor);
        dispose.visitInsn(store);
        dispose.visitMaxs(0, 0);
        dispose.visitEnd();

        writer.visitEnd();
        return writer.toByteArray();
    }

    private static final String ARGS_PACKAGE = "org/spongepowered/asm/mixin/injection/invoke/arg/";
    private static final String ARGS_SYNTHETIC = "org/spongepowered/asm/synthetic/args/";
    private static final String ARGS_BASE = ARGS_PACKAGE + "Args";

    /**
     * Records the shape every generated `Args$N` has to have, read from the sites that use it.
     *
     * Mixin generates one such class per rewritten call site, in memory, when `@ModifyArgs` is
     * applied. A closed world has no generator, so the members the rewritten code actually calls
     * are collected here - the `of` factory and the `$i` accessors - and reproduced exactly.
     */
    private static void collectArgumentHolders(ClassNode node, Map<String, Map<String, String>> holders) {
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call) || !call.owner.startsWith(ARGS_SYNTHETIC)) continue;
                String name = call.name;
                boolean factory = "of".equals(name) && INVOKESTATIC == call.getOpcode();
                boolean accessor = name.startsWith("$") && name.length() > 1 && name.chars().skip(1).allMatch(Character::isDigit);
                if (!factory && !accessor) continue;
                if (!call.owner.substring(ARGS_SYNTHETIC.length()).matches("Args\\$\\d+")) continue;
                holders.computeIfAbsent(call.owner, key -> new TreeMap<>()).put(name, call.desc);
            }
        }
    }

    /**
     * Export the pinned Mixin generator's actual output while its registry is alive on the build
     * host. This preserves typed getters, checked set/setAll and upstream exception semantics.
     */
    private static byte[] argumentHolder(String internalName, Map<String, String> members) throws Exception {
        var transformer = (org.spongepowered.asm.mixin.transformer.IMixinTransformer)
                org.spongepowered.asm.mixin.MixinEnvironment.getCurrentEnvironment().getActiveTransformer();
        var extensions = (org.spongepowered.asm.mixin.transformer.ext.Extensions) transformer.getExtensions();
        var generator = extensions.getGenerator(
                org.spongepowered.asm.mixin.injection.invoke.arg.ArgsClassGenerator.class);
        var node = new ClassNode();
        if (!generator.generate(internalName.replace('/', '.'), node) || !node.name.equals(internalName)) {
            throw new IllegalArgumentException("Missing build-time Mixin Args class: " + internalName);
        }
        for (var member : members.entrySet()) {
            if (node.methods.stream().noneMatch(method -> method.name.equals(member.getKey())
                    && method.desc.equals(member.getValue()))) {
                throw new IllegalArgumentException("Mixin Args member mismatch: " + internalName + "." + member);
            }
        }
        return generatedClassBytes(node);
    }

    static byte[] generatedClassBytes(ClassNode node) throws Exception {
        var writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        byte[] bytes = writer.toByteArray();
        verify(parse(bytes));
        return bytes;
    }

    private static byte[] transform(Method method, Object delegate, String name) throws Exception {
        byte[] bytes = (byte[]) method.invoke(delegate, name.substring(0, name.length() - 6).replace('/', '.'), false);
        if (bytes == null) throw new IllegalArgumentException("Knot could not resolve class " + name);
        return bytes;
    }

    private static ClassNode parse(byte[] data) {
        var node = new ClassNode();
        new ClassReader(data).accept(node, 0);
        return node;
    }

    private static byte[] classBytes(ClassNode node) {
        var writer = new ClassWriter(0);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static byte[] recomputedClassBytes(ClassNode node) {
        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static void verify(ClassNode node) throws Exception {
        verify(node, null);
    }

    /**
     * Dataflow-checks every method. {@link BasicVerifier} collapses all reference types into one
     * value, which cannot see a rewrite that left a String where a method expects an Optional;
     * methods this exporter rewrote therefore get the exact {@link SimpleVerifier}, falling back
     * to the basic check when the hierarchy needs a type the tool classpath cannot load.
     */
    private static void verify(ClassNode node, List<String> adaptations) throws Exception {
        for (var method : node.methods) {
            boolean rewritten = adaptations != null && adaptations.stream()
                    .anyMatch(a -> a.startsWith(node.name + "#" + method.name + " "));
            if (rewritten) {
                try {
                    new Analyzer<>(new org.objectweb.asm.tree.analysis.SimpleVerifier()).analyze(node.name, method);
                    continue;
                } catch (org.objectweb.asm.tree.analysis.AnalyzerException exact) {
                    if (unresolvableType(exact)) {
                        // An optional dependency only the runtime would provide; the basic check
                        // is all that is meaningful here.
                    } else {
                        throw new IllegalArgumentException("Bytecode verification failed: "
                                + node.name + "." + method.name, exact);
                    }
                }
            }
            try {
                new Analyzer<>(new BasicVerifier()).analyze(node.name, method);
            } catch (Exception error) {
                throw new IllegalArgumentException("Bytecode verification failed: " + node.name + "." + method.name, error);
            }
        }
    }

    private static boolean unresolvableType(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof TypeNotPresentException || t instanceof ClassNotFoundException
                    || t instanceof NoClassDefFoundError) return true;
        }
        return false;
    }

    private static int redirectHooks(ClassNode node) {
        int startup = 0;
        for (var method : node.methods) {
            for (var instruction : method.instructions) {
                if (instruction instanceof MethodInsnNode call && call.owner.equals(HOOKS)) {
                    if (call.name.equals("startClient") && call.desc.equals("(Ljava/io/File;Ljava/lang/Object;)V")) {
                        startup++;
                    } else if (!(call.name.equals("insertBranding") && call.desc.equals("(Ljava/lang/String;)Ljava/lang/String;"))) {
                        throw new IllegalArgumentException("Unsupported Fabric hook: " + call.name + call.desc);
                    }
                    call.owner = STATIC_HOOKS;
                }
            }
        }
        return startup;
    }

    private static void validateModCode(String mod, ClassNode node) {
        String name = node.name;
        // JVMS 4.2.2: a class name segment only forbids these characters. Kotlin's inline
        // reification produces names such as `VanillaAccessorsKt$(itemType)$1`, which are legal
        // and appear in shipped mods.
        if (name.isEmpty() || name.contains("//") || name.contains(";") || name.contains("[")
                || name.contains("<") || name.contains(">") || name.contains(".")
                || name.startsWith("/") || name.endsWith("/")) {
            throw new IllegalArgumentException("Unsupported Java class name: " + name);
        }
        for (var method : node.methods) {
            if ((method.access & ACC_NATIVE) != 0) {
                throw new IllegalArgumentException("Unsupported JNI native method: " + mod + " " + name + "." + method.name);
            }
            for (var instruction : method.instructions) {
                if (!(instruction instanceof MethodInsnNode call)) continue;
                boolean definesClasses = call.name.startsWith("defineClass") || call.name.startsWith("defineHiddenClass")
                        || call.owner.equals("java/net/URLClassLoader")
                        || call.owner.equals("java/lang/reflect/Proxy");
                boolean usesRuntimeLoader = (call.owner.startsWith("net/fabricmc/loader/")
                        && !RuntimeLowering.isValueCall(call))
                        || call.owner.startsWith("org/spongepowered/asm/mixin/transformer/");
                boolean loadsNative = (call.owner.equals("java/lang/System") || call.owner.equals("java/lang/Runtime"))
                        && (call.name.equals("load") || call.name.equals("loadLibrary"));
                if (definesClasses || usesRuntimeLoader || loadsNative) {
                    throw new IllegalArgumentException("Unsupported runtime class/native loading: " + mod + " "
                            + name + "." + method.name + " -> " + call.owner + "." + call.name);
                }
            }
        }
    }

    /**
     * Orders the entrypoints of one stage so a Mod initialises only after the Mods it depends
     * on. Ties break alphabetically for a deterministic dispatch; an unresolvable graph (a cycle
     * or missing metadata) falls back to the declaration order rather than dropping entrypoints.
     */
    private static List<Entry> orderedByDependencies(List<Entry> entries, Map<String, List<String>> dependencies) {
        var queued = new LinkedHashMap<String, List<Entry>>();
        for (Entry entry : entries) queued.computeIfAbsent(entry.mod(), key -> new ArrayList<>()).add(entry);
        var waiting = new LinkedHashMap<String, Set<String>>();
        for (String mod : queued.keySet()) {
            var pending = new LinkedHashSet<String>();
            for (String dependency : dependencies.getOrDefault(mod, List.of())) {
                if (queued.containsKey(dependency) && !dependency.equals(mod)) pending.add(dependency);
            }
            waiting.put(mod, pending);
        }
        var ordered = new ArrayList<Entry>();
        var done = new TreeSet<String>();
        var frontier = new TreeSet<String>();
        for (String mod : queued.keySet()) if (waiting.get(mod).isEmpty()) frontier.add(mod);
        while (!frontier.isEmpty()) {
            String mod = frontier.pollFirst();
            done.add(mod);
            ordered.addAll(queued.get(mod));
            for (String other : queued.keySet()) {
                if (done.contains(other)) continue;
                var pending = waiting.get(other);
                if (pending.remove(mod) && pending.isEmpty()) frontier.add(other);
            }
        }
        if (ordered.size() != entries.size()) {
            System.out.println("[AotExport] dependency order unresolved, keeping declaration order ("
                    + ordered.size() + "/" + entries.size() + " resolved, pending: "
                    + waiting.entrySet().stream().filter(e -> !e.getValue().isEmpty()).map(Map.Entry::getKey).toList() + ")");
            return entries;
        }
        return ordered;
    }

    private static byte[] staticHooks(List<Entry> entries, Set<String> loadedIds,
            Map<String, List<String>> stages, Map<String, List<String>> dependencies,
            Set<String> singletonStageProviders, Map<String, String> versions,
            Map<String, String> modNames, Map<String, List<String>> stageOwners,
            Set<String> earlyInitializers) {
        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES);
        writer.visit(V25, ACC_PUBLIC | ACC_FINAL, STATIC_HOOKS, null, "java/lang/Object", null);
        // The Loader's launch directory, captured from the hook argument it already receives.
        // PUBLIC: the lowering folds `FabricLoader.getGameDir()` in Mod classes into a direct
        // GETSTATIC of this field. Native Image resolves field accesses with access checks, and
        // a private field named from another class fails resolution into a run-time
        // NoSuchFieldError - so the field has to stay readable from everywhere.
        writer.visitField(ACC_PUBLIC | ACC_STATIC, "GAME_DIR", "Ljava/nio/file/Path;", null, null).visitEnd();
        var start = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "startClient", "(Ljava/io/File;Ljava/lang/Object;)V", null, null);
        start.visitCode();
        start.visitVarInsn(ALOAD, 0);
        var noDirectory = new Label();
        start.visitJumpInsn(IFNULL, noDirectory);
        start.visitVarInsn(ALOAD, 0);
        start.visitMethodInsn(INVOKEVIRTUAL, "java/io/File", "toPath", "()Ljava/nio/file/Path;", false);
        start.visitFieldInsn(PUTSTATIC, STATIC_HOOKS, "GAME_DIR", "Ljava/nio/file/Path;");
        start.visitLabel(noDirectory);
        // MixinConfigPlugin.onLoad runs inside Knot while the Mixin set is applied, which in the
        // closed world happens at build time. A plugin whose onLoad initializes Mod state has to
        // be replayed here, before any entrypoint can observe that state. The set is populated
        // only by audited plugins (see RuntimeLowering.collectMixinPluginEarlyInit).
        for (String initializer : earlyInitializers) {
            int separator = initializer.indexOf('#');
            start.visitMethodInsn(INVOKESTATIC, initializer.substring(0, separator),
                    initializer.substring(separator + 1), "()V", false);
        }
        // The dispatch list must mirror Fabric's dependency-ordered invocation: a Mod that reads
        // another Mod's registry content has to initialise after its dependencies, or every entry
        // is still uncreated - observed as `Entry has not been created yet` minutes into start-up.
        List<Entry> dispatchOrder = new ArrayList<>(orderedByDependencies(entries.stream()
                .filter(entry -> entry.stage().equals("main")).toList(), dependencies));
        dispatchOrder.addAll(orderedByDependencies(entries.stream()
                .filter(entry -> entry.stage().equals("client")).toList(), dependencies));
        System.out.println("[AotExport] entrypoint dispatch: " + dispatchOrder.size() + " entries, first mods "
                + dispatchOrder.stream().limit(10).map(Entry::mod).toList());
        for (Entry entry : dispatchOrder) {
            if (entry.refOwner() != null) {
                String refOwner = entry.refOwner().replace('.', '/');
                if (entry.refStatic()) {
                    start.visitMethodInsn(INVOKESTATIC, refOwner, entry.refName(), "()V", false);
                } else {
                    start.visitTypeInsn(NEW, refOwner);
                    start.visitInsn(DUP);
                    start.visitMethodInsn(INVOKESPECIAL, refOwner, "<init>", "()V", false);
                    start.visitMethodInsn(INVOKEVIRTUAL, refOwner, entry.refName(), "()V", false);
                }
                emitEntrypointDispatched(start, entry);
                continue;
            }
            String owner = entry.definition().replace('.', '/');
            if (entry.singleton()) {
                start.visitFieldInsn(GETSTATIC, owner, "INSTANCE", "L" + owner + ";");
            } else {
                start.visitTypeInsn(NEW, owner);
                start.visitInsn(DUP);
                start.visitMethodInsn(INVOKESPECIAL, owner, "<init>", "()V", false);
            }
            start.visitMethodInsn(INVOKEINTERFACE, entry.type(), entry.method(), "()V", true);
            emitEntrypointDispatched(start, entry);
        }
        start.visitInsn(RETURN);
        start.visitMaxs(0, 0);
        start.visitEnd();
        // RuntimeLowering routes non-literal isModLoaded queries here. A membership test keeps
        // the answer identical to the build-time Loader without touching it at runtime.
        var query = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "isModLoaded",
                "(Ljava/lang/String;)Z", null, null);
        query.visitCode();
        for (String id : loadedIds) {
            query.visitLdcInsn(id);
            query.visitVarInsn(ALOAD, 0);
            query.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals", "(Ljava/lang/Object;)Z", false);
            var next = new Label();
            query.visitJumpInsn(IFEQ, next);
            query.visitInsn(ICONST_1);
            query.visitInsn(IRETURN);
            query.visitLabel(next);
        }
        query.visitInsn(ICONST_0);
        query.visitInsn(IRETURN);
        query.visitMaxs(0, 0);
        query.visitEnd();
        var version = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "modVersion",
                "(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;", null, null);
        version.visitCode();
        for (var entry : versions.entrySet()) {
            var next = new Label();
            version.visitLdcInsn(entry.getKey());
            version.visitVarInsn(ALOAD, 0);
            version.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals", "(Ljava/lang/Object;)Z", false);
            version.visitJumpInsn(IFEQ, next);
            version.visitLdcInsn(entry.getValue());
            version.visitMethodInsn(INVOKESTATIC, "net/fabricmc/loader/api/Version", "parse",
                    "(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;", true);
            version.visitInsn(ARETURN);
            version.visitLabel(next);
        }
        version.visitTypeInsn(NEW, "java/lang/IllegalArgumentException");
        version.visitInsn(DUP);
        version.visitLdcInsn("Unknown mod version in build snapshot: ");
        version.visitVarInsn(ALOAD, 0);
        version.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "concat", "(Ljava/lang/String;)Ljava/lang/String;", false);
        version.visitMethodInsn(INVOKESPECIAL, "java/lang/IllegalArgumentException", "<init>", "(Ljava/lang/String;)V", false);
        version.visitInsn(ATHROW);
        version.visitMaxs(0, 0);
        version.visitEnd();
        // Optional form for Mod code that asks "is this Mod present, and what version?".
        // A snapshot miss is Optional.empty(), not an exception: that is the Loader's answer for
        // an absent Mod and callers use it to skip optional integrations.
        var optional = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, RuntimeLowering.OPTIONAL_VERSION,
                RuntimeLowering.OPTIONAL_VERSION_DESC, null, null);
        optional.visitCode();
        for (var entry : versions.entrySet()) {
            var next = new Label();
            optional.visitLdcInsn(entry.getKey());
            optional.visitVarInsn(ALOAD, 0);
            optional.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals",
                    "(Ljava/lang/Object;)Z", false);
            optional.visitJumpInsn(IFEQ, next);
            optional.visitLdcInsn(entry.getValue());
            optional.visitMethodInsn(INVOKESTATIC, "java/util/Optional", "of",
                    "(Ljava/lang/Object;)Ljava/util/Optional;", false);
            optional.visitInsn(ARETURN);
            optional.visitLabel(next);
        }
        optional.visitMethodInsn(INVOKESTATIC, "java/util/Optional", "empty",
                "()Ljava/util/Optional;", false);
        optional.visitInsn(ARETURN);
        optional.visitMaxs(0, 0);
        optional.visitEnd();
        // Display name by Mod id, Optional form. Jade's tooltip labels vanilla blocks with the
        // id it got from the block's namespace; a namespace that is not a Mod in this pack must
        // answer Optional.empty() (the Loader's answer) rather than throw, because Jade filters
        // empties and keeps its own fallback label.
        var optionalName = writer.visitMethod(ACC_PUBLIC | ACC_STATIC,
                RuntimeLowering.OPTIONAL_MOD_NAME, RuntimeLowering.OPTIONAL_MOD_NAME_DESC,
                null, null);
        optionalName.visitCode();
        for (var entry : modNames.entrySet()) {
            var next = new Label();
            optionalName.visitLdcInsn(entry.getKey());
            optionalName.visitVarInsn(ALOAD, 0);
            optionalName.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals",
                    "(Ljava/lang/Object;)Z", false);
            optionalName.visitJumpInsn(IFEQ, next);
            optionalName.visitLdcInsn(entry.getValue());
            optionalName.visitMethodInsn(INVOKESTATIC, "java/util/Optional", "of",
                    "(Ljava/lang/Object;)Ljava/util/Optional;", false);
            optionalName.visitInsn(ARETURN);
            optionalName.visitLabel(next);
        }
        optionalName.visitMethodInsn(INVOKESTATIC, "java/util/Optional", "empty",
                "()Ljava/util/Optional;", false);
        optionalName.visitInsn(ARETURN);
        optionalName.visitMaxs(0, 0);
        optionalName.visitEnd();
        var modName = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "modName",
                "(Ljava/lang/String;)Ljava/lang/String;", null, null);
        modName.visitCode();
        for (var entry : modNames.entrySet()) {
            var next = new Label();
            modName.visitLdcInsn(entry.getKey());
            modName.visitVarInsn(ALOAD, 0);
            modName.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals", "(Ljava/lang/Object;)Z", false);
            modName.visitJumpInsn(IFEQ, next);
            modName.visitLdcInsn(entry.getValue());
            modName.visitInsn(ARETURN);
            modName.visitLabel(next);
        }
        modName.visitTypeInsn(NEW, "java/lang/IllegalArgumentException");
        modName.visitInsn(DUP);
        modName.visitLdcInsn("Unknown mod name in build snapshot: ");
        modName.visitVarInsn(ALOAD, 0);
        modName.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "concat", "(Ljava/lang/String;)Ljava/lang/String;", false);
        modName.visitMethodInsn(INVOKESPECIAL, "java/lang/IllegalArgumentException", "<init>", "(Ljava/lang/String;)V", false);
        modName.visitInsn(ATHROW);
        modName.visitMaxs(0, 0);
        modName.visitEnd();
        var providerId = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "providerModId",
                "(Ljava/lang/Object;)Ljava/lang/String;", null, null);
        providerId.visitCode();
        providerId.visitVarInsn(ALOAD, 0);
        providerId.visitTypeInsn(CHECKCAST, STATIC_HOOKS + "$Container");
        providerId.visitMethodInsn(INVOKEVIRTUAL, STATIC_HOOKS + "$Container", "getModId", "()Ljava/lang/String;", false);
        providerId.visitInsn(ARETURN);
        providerId.visitMaxs(0, 0);
        providerId.visitEnd();
        // getConfigDir() has no Loader state behind it beyond the launch directory. The directory
        // is only known once the client hook runs, but Mods ask for it earlier: ETF reads its
        // config while Minecraft's data fixers initialise, before startClient. The working
        // directory is the same launch directory in every launcher this runtime supports, so it
        // stands in until the hook reports the authoritative one.
        var config = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "configDir",
                "()Ljava/nio/file/Path;", null, null);
        config.visitCode();
        config.visitFieldInsn(GETSTATIC, STATIC_HOOKS, "GAME_DIR", "Ljava/nio/file/Path;");
        config.visitVarInsn(ASTORE, 0);
        config.visitVarInsn(ALOAD, 0);
        var known = new Label();
        config.visitJumpInsn(IFNONNULL, known);
        config.visitLdcInsn("user.dir");
        config.visitMethodInsn(INVOKESTATIC, "java/lang/System", "getProperty",
                "(Ljava/lang/String;)Ljava/lang/String;", false);
        config.visitVarInsn(ASTORE, 1);
        config.visitTypeInsn(NEW, "java/io/File");
        config.visitInsn(DUP);
        config.visitVarInsn(ALOAD, 1);
        config.visitMethodInsn(INVOKESPECIAL, "java/io/File", "<init>", "(Ljava/lang/String;)V", false);
        config.visitMethodInsn(INVOKEVIRTUAL, "java/io/File", "toPath", "()Ljava/nio/file/Path;", false);
        config.visitVarInsn(ASTORE, 0);
        config.visitVarInsn(ALOAD, 0);
        config.visitFieldInsn(PUTSTATIC, STATIC_HOOKS, "GAME_DIR", "Ljava/nio/file/Path;");
        config.visitLabel(known);
        config.visitVarInsn(ALOAD, 0);
        config.visitLdcInsn("config");
        config.visitMethodInsn(INVOKEINTERFACE, "java/nio/file/Path", "resolve",
                "(Ljava/lang/String;)Ljava/nio/file/Path;", true);
        config.visitInsn(ARETURN);
        config.visitMaxs(0, 0);
        config.visitEnd();

        // MappingResolver identity hooks. The runtime runs official names, so every resolver
        // query returns the name it was given; callers that ask for a different namespace only
        // ever hit this through a graceful-degradation path.
        var mapping = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "mappingFieldName",
                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", null, null);
        mapping.visitCode();
        mapping.visitVarInsn(ALOAD, 2);
        mapping.visitInsn(ARETURN);
        mapping.visitMaxs(1, 4);
        mapping.visitEnd();
        var mappingMethod = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "mappingMethodName",
                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", null, null);
        mappingMethod.visitCode();
        mappingMethod.visitVarInsn(ALOAD, 2);
        mappingMethod.visitInsn(ARETURN);
        mappingMethod.visitMaxs(1, 4);
        mappingMethod.visitEnd();
        for (String name : List.of("mappingClassName", "mappingUnmapClassName", "mappingUnmapFieldName")) {
            var unmap = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, name,
                    "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", null, null);
            unmap.visitCode();
            unmap.visitVarInsn(ALOAD, 1);
            unmap.visitInsn(ARETURN);
            unmap.visitMaxs(1, 2);
            unmap.visitEnd();
        }
        var namespaces = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "mappingNamespaces",
                "()Ljava/util/Collection;", null, null);
        namespaces.visitCode();
        namespaces.visitLdcInsn("official");
        namespaces.visitLdcInsn("intermediary");
        namespaces.visitMethodInsn(INVOKESTATIC, "java/util/List", "of",
                "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/List;", true);
        namespaces.visitInsn(ARETURN);
        namespaces.visitMaxs(2, 0);
        namespaces.visitEnd();
        var brand = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "insertBranding", "(Ljava/lang/String;)Ljava/lang/String;", null, null);
        brand.visitCode();
        var fabric = new Label();
        brand.visitVarInsn(ALOAD, 0);
        brand.visitJumpInsn(IFNULL, fabric);
        brand.visitVarInsn(ALOAD, 0);
        brand.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "isEmpty", "()Z", false);
        brand.visitJumpInsn(IFNE, fabric);
        brand.visitLdcInsn("vanilla");
        brand.visitVarInsn(ALOAD, 0);
        brand.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals", "(Ljava/lang/Object;)Z", false);
        brand.visitJumpInsn(IFNE, fabric);
        brand.visitVarInsn(ALOAD, 0);
        brand.visitLdcInsn(",fabric");
        brand.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "concat", "(Ljava/lang/String;)Ljava/lang/String;", false);
        brand.visitInsn(ARETURN);
        brand.visitLabel(fabric);
        brand.visitLdcInsn("fabric");
        brand.visitInsn(ARETURN);
        brand.visitMaxs(0, 0);
        brand.visitEnd();
        // Custom entrypoint stages, resolved from the build-time provider table. The receiver is
        // accepted so a lowered call site keeps its stack shape and is ignored.
        var stage = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "stage",
                "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Class;)Ljava/util/List;", null, null);
        stage.visitCode();
        var providerClasses = new ArrayList<String>();
        for (var dispatch : stages.entrySet()) {
            int ownerIndex = 0;
            var next = new Label();
            stage.visitVarInsn(ALOAD, 1);
            stage.visitLdcInsn(dispatch.getKey());
            stage.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "equals", "(Ljava/lang/Object;)Z", false);
            stage.visitJumpInsn(IFEQ, next);
            stage.visitTypeInsn(NEW, "java/util/ArrayList");
            stage.visitInsn(DUP);
            stage.visitMethodInsn(INVOKESPECIAL, "java/util/ArrayList", "<init>", "()V", false);
            for (String provider : dispatch.getValue()) {
                stage.visitInsn(DUP);
                stage.visitTypeInsn(NEW, STATIC_HOOKS + "$Container");
                stage.visitInsn(DUP);
                stage.visitLdcInsn(providerClasses.size());
                providerClasses.add(provider);
                stage.visitLdcInsn(provider);
                stage.visitLdcInsn(stageOwners.get(dispatch.getKey()).get(ownerIndex++));
                stage.visitMethodInsn(INVOKESPECIAL, STATIC_HOOKS + "$Container", "<init>",
                        "(ILjava/lang/String;Ljava/lang/String;)V", false);
                stage.visitMethodInsn(INVOKEVIRTUAL, "java/util/ArrayList", "add", "(Ljava/lang/Object;)Z", false);
                stage.visitInsn(POP);
            }
            stage.visitInsn(ARETURN);
            stage.visitLabel(next);
        }
        stage.visitMethodInsn(INVOKESTATIC, "java/util/List", "of", "()Ljava/util/List;", true);
        stage.visitInsn(ARETURN);
        stage.visitMaxs(0, 0);
        stage.visitEnd();
        var provider = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "provider", "(I)Ljava/lang/Object;", null, null);
        provider.visitCode();
        for (int index = 0; index < providerClasses.size(); index++) {
            var next = new Label();
            provider.visitVarInsn(ILOAD, 0);
            provider.visitLdcInsn(index);
            provider.visitJumpInsn(IF_ICMPNE, next);
            String owner = providerClasses.get(index);
            if (singletonStageProviders.contains(owner)) {
                provider.visitFieldInsn(GETSTATIC, owner.replace('.', '/'), "INSTANCE", "L" + owner.replace('.', '/') + ";");
            } else {
                String factory = lazyStageProvider(writer, owner.replace('.', '/'), index);
                provider.visitMethodInsn(INVOKESTATIC, STATIC_HOOKS, factory, "()Ljava/lang/Object;", false);
            }
            provider.visitInsn(ARETURN);
            provider.visitLabel(next);
        }
        provider.visitTypeInsn(NEW, "java/lang/IllegalArgumentException");
        provider.visitInsn(DUP);
        provider.visitLdcInsn("Unknown static provider index");
        provider.visitMethodInsn(INVOKESPECIAL, "java/lang/IllegalArgumentException", "<init>", "(Ljava/lang/String;)V", false);
        provider.visitInsn(ATHROW);
        provider.visitMaxs(0, 0);
        provider.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static String lazyStageProvider(ClassWriter writer, String provider, int index) {
        String name = "stageProvider$" + index;
        writer.visitField(ACC_PRIVATE | ACC_STATIC, name, "Ljava/lang/Object;", null, null).visitEnd();
        var factory = writer.visitMethod(ACC_PRIVATE | ACC_STATIC | ACC_SYNCHRONIZED, name,
                "()Ljava/lang/Object;", null, null);
        factory.visitCode();
        factory.visitFieldInsn(GETSTATIC, STATIC_HOOKS, name, "Ljava/lang/Object;");
        factory.visitInsn(DUP);
        var create = new Label();
        factory.visitJumpInsn(IFNULL, create);
        factory.visitInsn(ARETURN);
        factory.visitLabel(create);
        factory.visitInsn(POP);
        factory.visitTypeInsn(NEW, provider);
        factory.visitInsn(DUP);
        factory.visitMethodInsn(INVOKESPECIAL, provider, "<init>", "()V", false);
        factory.visitInsn(DUP);
        factory.visitFieldInsn(PUTSTATIC, STATIC_HOOKS, name, "Ljava/lang/Object;");
        factory.visitInsn(ARETURN);
        factory.visitMaxs(0, 0);
        factory.visitEnd();
        return name;
    }

    /** The container the generated stage dispatch hands out; it only answers what consumers ask. */
    private static byte[] entrypointContainer() {
        String name = STATIC_HOOKS + "$Container";
        String iface = "net/fabricmc/loader/api/entrypoint/EntrypointContainer";
        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES);
        writer.visit(V25, ACC_PUBLIC | ACC_FINAL | ACC_SUPER, name, null, "java/lang/Object", new String[]{iface});
        writer.visitField(ACC_PRIVATE | ACC_FINAL, "providerIndex", "I", null, null).visitEnd();
        writer.visitField(ACC_PRIVATE | ACC_FINAL, "definition", "Ljava/lang/String;", null, null).visitEnd();
        writer.visitField(ACC_PRIVATE | ACC_FINAL, "modId", "Ljava/lang/String;", null, null).visitEnd();
        var init = writer.visitMethod(ACC_PUBLIC, "<init>", "(ILjava/lang/String;Ljava/lang/String;)V", null, null);
        init.visitCode();
        init.visitVarInsn(ALOAD, 0);
        init.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        init.visitVarInsn(ALOAD, 0);
        init.visitVarInsn(ILOAD, 1);
        init.visitFieldInsn(PUTFIELD, name, "providerIndex", "I");
        init.visitVarInsn(ALOAD, 0);
        init.visitVarInsn(ALOAD, 2);
        init.visitFieldInsn(PUTFIELD, name, "definition", "Ljava/lang/String;");
        init.visitVarInsn(ALOAD, 0);
        init.visitVarInsn(ALOAD, 3);
        init.visitFieldInsn(PUTFIELD, name, "modId", "Ljava/lang/String;");
        init.visitInsn(RETURN);
        init.visitMaxs(0, 0);
        init.visitEnd();
        var entry = writer.visitMethod(ACC_PUBLIC, "getEntrypoint", "()Ljava/lang/Object;", null, null);
        entry.visitCode();
        entry.visitVarInsn(ALOAD, 0);
        entry.visitFieldInsn(GETFIELD, name, "providerIndex", "I");
        entry.visitMethodInsn(INVOKESTATIC, STATIC_HOOKS, "provider", "(I)Ljava/lang/Object;", false);
        entry.visitInsn(ARETURN);
        entry.visitMaxs(0, 0);
        entry.visitEnd();
        // No ModContainer exists at runtime. Callers that only read the definition string, which
        // is how Mod-provided entrypoint stages report themselves, are unaffected.
        var provider = writer.visitMethod(ACC_PUBLIC, "getProvider",
                "()Lnet/fabricmc/loader/api/ModContainer;", null, null);
        provider.visitCode();
        provider.visitInsn(ACONST_NULL);
        provider.visitInsn(ARETURN);
        provider.visitMaxs(0, 0);
        provider.visitEnd();
        var definition = writer.visitMethod(ACC_PUBLIC, "getDefinition", "()Ljava/lang/String;", null, null);
        definition.visitCode();
        definition.visitVarInsn(ALOAD, 0);
        definition.visitFieldInsn(GETFIELD, name, "definition", "Ljava/lang/String;");
        definition.visitInsn(ARETURN);
        definition.visitMaxs(0, 0);
        definition.visitEnd();
        var modId = writer.visitMethod(ACC_PUBLIC, "getModId", "()Ljava/lang/String;", null, null);
        modId.visitCode();
        modId.visitVarInsn(ALOAD, 0);
        modId.visitFieldInsn(GETFIELD, name, "modId", "Ljava/lang/String;");
        modId.visitInsn(ARETURN);
        modId.visitMaxs(0, 0);
        modId.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static byte[] mergeResource(String name, byte[] existing, byte[] incoming,
            Set<String> merged) {
        boolean tags = name.startsWith("data/") && name.contains("/tags/");
        boolean atlases = name.startsWith("assets/") && name.contains("/atlases/");
        if (!tags && !atlases) {
            merged.add(name + ": later pack wins");
            return incoming;
        }
        JsonObject left;
        JsonObject right;
        try {
            left = JSON.fromJson(new String(existing, java.nio.charset.StandardCharsets.UTF_8), JsonObject.class);
            right = JSON.fromJson(new String(incoming, java.nio.charset.StandardCharsets.UTF_8), JsonObject.class);
        } catch (RuntimeException malformed) {
            throw new IllegalArgumentException("Cannot merge resource " + name + ": " + malformed.getMessage());
        }
        if (left == null || right == null) throw new IllegalArgumentException("Cannot merge resource " + name);
        String field = tags ? "values" : "sources";
        // A pack that marks the file as a replacement does not inherit earlier entries.
        boolean replace = tags && right.has("replace") && right.get("replace").getAsBoolean();
        var combined = new JsonArray();
        var seen = new java.util.HashSet<String>();
        if (!replace) copyEntries(left, field, combined, seen);
        int before = combined.size();
        copyEntries(right, field, combined, seen);
        var result = left.deepCopy();
        for (var entry : right.entrySet()) result.add(entry.getKey(), entry.getValue());
        result.add(field, combined);
        merged.add(name + (replace ? ": replaced" : ": merged " + (combined.size() - before)));
        return utf8(JSON.toJson(result));
    }

    private static void copyEntries(JsonObject source, String field, JsonArray target, Set<String> seen) {
        if (!source.has(field) || !source.get(field).isJsonArray()) return;
        for (var element : source.getAsJsonArray(field)) {
            if (seen.add(element.toString())) target.add(element);
        }
    }

    private static boolean multiRelease(Path root) throws IOException {
        Path manifest = root.resolve("META-INF/MANIFEST.MF");
        if (!Files.isRegularFile(manifest)) return false;
        for (String line : Files.readAllLines(manifest)) {
            String trimmed = line.trim();
            int colon = trimmed.indexOf(':');
            if (colon > 0 && trimmed.substring(0, colon).equalsIgnoreCase("Multi-Release")) {
                return trimmed.substring(colon + 1).trim().equalsIgnoreCase("true");
            }
        }
        return false;
    }

    /**
     * Merge one ServiceLoader registration. Annotation processors are javac-only and are
     * deliberately not carried into the image; every other provider is kept and later
     * registered for reflective construction.
     */
    private static void collectService(TreeMap<String, TreeSet<String>> services, TreeSet<String> providers,
            String id, String service, List<String> lines) {
        if (service.equals("javax.annotation.processing.Processor")) return;
        var target = services.computeIfAbsent(service, key -> new TreeSet<>());
        for (String line : lines) {
            String provider = line.strip();
            int comment = provider.indexOf('#');
            if (comment >= 0) provider = provider.substring(0, comment).strip();
            if (provider.isEmpty()) continue;
            if (!provider.matches("[A-Za-z_$][\\w$]*(?:\\.[A-Za-z_$][\\w$]*)+")) {
                throw new IllegalArgumentException("Invalid service provider in " + id + " for " + service
                        + ": " + provider);
            }
            target.add(provider);
            providers.add(provider);
        }
    }

    private static byte[] utf8(String text) {
        return text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    private static String hash(byte[] data) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    /**
     * Every inert class in the pinned Fabric Loader's {@code net/fabricmc/api} package, keyed by
     * jar entry name. A Mod class that implements one of these interfaces is unlinkable without
     * it, and Native Image reports that only as a run-time NoClassDefFoundError at the entrypoint
     * dispatch. Deriving the set from the Loader jar keeps it complete when a Mod names an API
     * type no hand-maintained allow-list anticipated.
     */
    static Map<String, byte[]> fabricApiTypes() {
        var location = ClientModInitializer.class.getProtectionDomain().getCodeSource().getLocation();
        var result = new TreeMap<String, byte[]>();
        try {
            Path root = Path.of(location.toURI());
            if (Files.isDirectory(root)) {
                try (var tree = Files.walk(root.resolve("net/fabricmc/api"))) {
                    for (Path file : tree.filter(path -> path.toString().endsWith(".class")).toList()) {
                        result.put(root.relativize(file).toString().replace('\\', '/'),
                                Files.readAllBytes(file));
                    }
                }
            } else {
                try (var loader = new ZipFile(root.toFile())) {
                    for (var entry : loader.stream().filter(item -> item.getName()
                            .startsWith("net/fabricmc/api/") && item.getName().endsWith(".class")).toList()) {
                        try (var input = loader.getInputStream(entry)) {
                            result.put(entry.getName(), input.readAllBytes());
                        }
                    }
                }
            }
        } catch (Exception problem) {
            throw new IllegalStateException("Cannot read pinned Fabric API from " + location, problem);
        }
        if (result.isEmpty()) throw new IllegalStateException("Pinned Fabric API is empty: " + location);
        return result;
    }

    private static void put(ZipOutputStream jar, Set<String> names, String name, byte[] data) throws IOException {
        if (!names.add(name)) throw new IllegalArgumentException("Duplicate class or resource: " + name);
        var entry = new ZipEntry(name);
        entry.setTime(315532800000L);
        jar.putNextEntry(entry);
        jar.write(data);
        jar.closeEntry();
    }
}
