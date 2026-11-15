package mcfao.build;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

final class RuntimeLowering implements Opcodes {
    private static final String LOADER = "net/fabricmc/loader/api/FabricLoader";
    private static final String HOOKS = "mcfao/aot/Entrypoints";
    private static final String MAPPING_RESOLVER = "net/fabricmc/loader/api/MappingResolver";
    // Pinned, audited value/parser closure: references only these types and JDK value utilities.
    static final Set<String> PURE_LOADER_TYPES = Set.of(
            "net/fabricmc/loader/api/Version", "net/fabricmc/loader/api/SemanticVersion",
            "net/fabricmc/loader/api/VersionParsingException",
            "net/fabricmc/loader/impl/util/version/VersionParser",
            "net/fabricmc/loader/impl/util/version/SemanticVersionImpl",
            "net/fabricmc/loader/impl/util/version/StringVersion",
            "net/fabricmc/loader/util/version/SemanticVersionImpl",
            "net/fabricmc/loader/util/version/VersionParsingException");

    /**
     * MappingResolver queries the closed world can answer. The runtime runs official names, so a
     * query that targets the official namespace never changes its input: the name argument comes
     * straight back. Methods targeting other namespaces keep their signature but return the input
     * too - the callers either degrade gracefully (a try/catch fallback) or were already stubbed.
     */
    private static final Map<String, String> MAPPING_HOOKS = Map.of(
            "mapFieldName", "mappingFieldName",
            "mapMethodName", "mappingMethodName",
            "mapClassName", "mappingClassName",
            "unmapClassName", "mappingUnmapClassName",
            "unmapFieldName", "mappingUnmapFieldName",
            "getNamespaces", "mappingNamespaces");
    private static final String EVENTS = "net/fabricmc/fabric/impl/base/event/EventFactoryImpl";
    private static final String EVENTS_SHA256 = "065be26b910ddcf78f27e48d2808eb7ecbacfbcdc38292459ca2c8f496ae7d79";
    // GlitchCore's event bus asks TypeResolver for the Consumer<T> type argument of a hidden
    // lambda class. Native Image has no generic signature/constant pool for such a class, so the
    // closed world must resolve T at build time instead. Both hashes are the original Mod JAR
    // class bytes; a different upstream version is refused rather than guessed at.
    static final String GLITCHCORE_MANAGER = "glitchcore/event/EventManager";
    static final String GLITCHCORE_MANAGER_SHA256 =
            "dafe0c0a36b71b9dd602e32294acb9105daa55e64e7c0f28a8776d13ba0580a3";
    static final String REGISTRY_HELPER = "glitchcore/util/RegistryHelper";
    static final String REGISTRY_HELPER_SHA256 =
            "d2e5f55de5042e7a84fab1e5e4a80f77ff6cdc8a36cdf6cac69f53db6e598b2c";
    static final String RESOLVED_LISTENER = "addListenerResolved";
    static final String LISTENER_DESC = "(Ljava/util/function/Consumer;)V";
    static final String RESOLVED_LISTENER_DESC =
            "(Ljava/util/function/Consumer;Ljava/lang/Class;)V";
    // ImmediatelyFast has no Fabric entrypoint: its MixinConfigPlugin.onLoad calls earlyInit(),
    // which loads the config and the runtime config. The plugin runs only inside Knot at build
    // time, so the image would otherwise reach RenderSystem.initRenderer with config == null.
    // Both audited hashes are the original Mod JAR class bytes.
    static final String IF_PLATFORM = "net/raphimc/immediatelyfast/fabric/PlatformCodeImpl";
    static final String IF_PLATFORM_SHA256 =
            "c8beac0023583d9d6adb29f0ff9c73a9cd1caa94063115430fd958cb624826b2";
    static final String IF_PLUGIN = "net/raphimc/immediatelyfast/injection/ImmediatelyFastMixinPlugin";
    static final String IF_PLUGIN_SHA256 =
            "10f0fa06be51064ab1e320d7a0633585d716532b2ef51d2646bfcc26b2ec3a92";
    static final String IF_MAIN = "net/raphimc/immediatelyfast/ImmediatelyFast";
    static final String IF_EARLY_INIT = "earlyInit";
    static final String IF_EARLY_INIT_DESC = "()V";
    static final String OPTIONAL_VERSION = "optionalModVersion";
    static final String OPTIONAL_VERSION_DESC = "(Ljava/lang/String;)Ljava/util/Optional;";
    // Jade's tooltip labels every entry with the owning Mod's display name; the lookup goes
    // through net.fabricmc.loader.api (FabricLoader -> ModContainer -> ModMetadata), none of
    // which exists in a closed image. Entrypoints.optionalModName answers from the same
    // build-time modNames table optionalModVersion uses, and an id outside the pack is
    // Optional.empty() - exactly what the Loader would answer and what Jade's own
    // .filter(Predicate.not(String::isEmpty)) then swallows.
    static final String OPTIONAL_MOD_NAME = "optionalModName";
    static final String OPTIONAL_MOD_NAME_DESC = "(Ljava/lang/String;)Ljava/util/Optional;";
    static final String JADE_CLIENT_PROXY = "snownee/jade/util/ClientProxy";
    // sha256 of snownee/jade/util/ClientProxy.class inside Jade-mc26.1-Fabric-26.1.0.jar.
    // A mismatch is fatal on purpose: the cut below assumes getModName's loader fallback is the
    // trailing block, so an upstream rewrite has to be re-audited instead of silently mangled.
    static final String JADE_CLIENT_PROXY_SHA256 =
            "1e4f14565ec804aa120c9e22e0f65457049f601761fa8d3136e97d6433d5acbb";
    // A Mod that locates its own JAR dereferences the answer one frame later, so the residue pass'
    // null turns into a NullPointerException inside the Mod's client initialiser. The closed image
    // has no Mod JARs, but the question has a usable answer: where that JAR would be. Both hashes
    // are the original Mod JAR class bytes; a different upstream build is refused, not guessed at.
    static final String XAERO_WORLDMAP = "xaero/map/WorldMapFabric";
    static final String XAERO_WORLDMAP_SHA256 =
            "14a179c3b70025519228ad4afd4db5512396126212adbf067dc510bf013aa958";
    static final String XAERO_PLATFORM_HELPER =
            "xaero/common/platform/services/FabricPlatformHelper";
    static final String XAERO_PLATFORM_HELPER_SHA256 =
            "d640dd03f99ccc4665759f7ece3aaaade499fad0ca85f0ef9f07179e54aaea94";
    static final String MOD_FILES = "mcfao/aot/ModFiles";
    static final String MOD_FILE_DESC =
            "(Ljava/nio/file/Path;Ljava/lang/String;)Ljava/nio/file/Path;";
    // The closed image ships one merged resource pack: every Mod's assets/ and data/ is in the
    // game jar, but no Mod jar exists from which Fabric could build a ModResourcePack. Vanilla's
    // builder only exposes "minecraft" and "realms", and MultiPackResourceManager builds its
    // namespace index from getNamespaces(), so every other namespace is unreachable even though
    // the files themselves are readable through resource:/assets/<namespace>/. Rewriting build()
    // is the single point both ClientPackSource and ServerPacksSource pass through.
    static final String VANILLA_PACK_BUILDER =
            "net/minecraft/server/packs/VanillaPackResourcesBuilder";
    static final String MOD_NAMESPACES = "mcfao/aot/ModNamespaces";
    static final String SET_COPY_DESC = "(Ljava/util/Collection;)Ljava/util/Set;";
    // Framework keeps each Mod's config declaration in its `fabric.mod.json` and reads it back
    // through `FabricLoader.getAllMods()`: the class name is a JSON string, the config instance is
    // a static field found by `getDeclaredFields` + a `@FrameworkConfig` annotation, and the
    // properties inside it are linked by another reflective field walk. A closed image has no Mod
    // jars and folds that loader query to an empty collection, so every config property stays
    // unlinked and `AbstractProperty.get` then throws "Config property is not linked yet" on the
    // first gameplay tick. The declarations are enumerated from the shipped bytecode instead and
    // the helper is rewritten into a table that hands back the same (annotation, instance) pairs.
    static final String FRAMEWORK_CONFIG = "com/mrcrayfish/framework/api/config/FrameworkConfig";
    static final String FRAMEWORK_CONFIG_DESC = "L" + FRAMEWORK_CONFIG + ";";
    static final String CONFIG_HELPER = "com/mrcrayfish/framework/platform/FabricConfigHelper";
    static final String CONFIG_DISCOVERY = "getAllFrameworkConfigs";
    static final String CONFIG_DISCOVERY_DESC = "()Ljava/util/List;";
    static final String CONFIG_TABLE = "mcfao/aot/FrameworkConfigs";
    static final String CONFIG_ANNOTATION = "mcfao/aot/FrameworkConfigAnnotation";
    static final String CONFIG_TYPE = "com/mrcrayfish/framework/api/config/ConfigType";
    private static final String CONFIG_ANNOTATION_DESC = "(Ljava/lang/String;Ljava/lang/String;Z"
            + "L" + CONFIG_TYPE + ";C)V";
    private static final String VANILLA_BUILD_DESC =
            "(Lnet/minecraft/server/packs/PackLocationInfo;)"
                    + "Lnet/minecraft/server/packs/VanillaPackResources;";
    // Minecraft Identifier namespaces are lower-case; a directory that does not match cannot be
    // addressed by a ResourceLocation and is deliberately not exposed.
    private static final Pattern RESOURCE_NAMESPACE =
            Pattern.compile("^(?:assets|data)/([a-z0-9_.-]+)/");
    // Loader-only code that carries no gameplay behaviour. A whole class is listed only when every
    // method in it serves diagnostics, and constructors stay excluded, so a Mod that reaches the
    // Loader from game code still fails the build instead of going quiet.
    private static final Set<String> DIAGNOSTIC_CLASSES = Set.of("net/minecraft/SystemReport");
    // A Mod that builds classes at run time becomes closed-world when the generated code is
    // replaced by an equivalent computed from the same inputs. Sodium's serializer registry is
    // the one such case here: it emitted a class per (source, target) vertex format pair and
    // loaded it with Lookup.defineClass. The replacement derives the same copy plan from the two
    // formats, so the generator and its value types have no caller and can be left out.
    private static final String SODIUM_REGISTRY =
            "net/caffeinemc/mods/sodium/client/render/vertex/serializers/VertexSerializerRegistryImpl";
    private static final String SODIUM_FACTORY =
            "net/caffeinemc/mods/sodium/client/render/vertex/serializers/generated/VertexSerializerFactory";
    static final Set<String> GENERATOR_CLASSES = Set.of(SODIUM_FACTORY,
            SODIUM_FACTORY + "$Bytecode", SODIUM_FACTORY + "$MemoryTransfer");
    private static final Set<String> CONSUMERS = Set.of("forEach", "ifPresent");
    // Optional.map/filter/flatMap return Optional, so deleting them leaves the stack unchanged.
    private static final Set<String> MAPPERS = Set.of("map", "filter", "flatMap");

    private RuntimeLowering() {}

    static boolean isValueCall(MethodInsnNode call) {
        return call.owner.equals("net/fabricmc/loader/api/ModContainer")
                || call.owner.startsWith("net/fabricmc/loader/api/metadata/")
                || PURE_LOADER_TYPES.contains(call.owner) || (call.owner.equals(
                "net/fabricmc/loader/api/entrypoint/EntrypointContainer") && Set.of(
                "getEntrypoint()Ljava/lang/Object;", "getDefinition()Ljava/lang/String;",
                "getProvider()Lnet/fabricmc/loader/api/ModContainer;")
                .contains(call.name + call.desc));
    }

    /**
     * Answers "where is my JAR" for the Mods that ask the Loader for it.
     *
     * <p>Both call sites were stubbed by the residue pass because the Loader container's origin is
     * not part of the image, and both dereference the result immediately: Xaero's world map reads
     * {@code getFileName()} while the minimap's HUD keeps the path for its update check. The
     * replacement is the nominal location {@link mcfao.aot.ModFiles} derives from the launch
     * directory, so the answer has the shape the caller expects and reading it fails honestly.
     */
    static void lowerModFile(ClassNode node, String sourceHash, List<String> adaptations) {
        if (node.name.equals(XAERO_WORLDMAP)) {
            if (!sourceHash.equals(XAERO_WORLDMAP_SHA256)) {
                throw new IllegalArgumentException("Unaudited Xaero world map file lookup: " + sourceHash);
            }
            MethodNode method = method(node, "fetchModFile", "()Ljava/nio/file/Path;");
            replaceWithModFile(method, new LdcInsnNode("xaeroworldmap"));
            adaptations.add(node.name + "#fetchModFile() = ModFiles.modFile(\"xaeroworldmap\")");
        } else if (node.name.equals(XAERO_PLATFORM_HELPER)) {
            if (!sourceHash.equals(XAERO_PLATFORM_HELPER_SHA256)) {
                throw new IllegalArgumentException("Unaudited Xaero platform helper file lookup: " + sourceHash);
            }
            MethodNode method = method(node, "getModFile", "(Ljava/lang/String;)Ljava/nio/file/Path;");
            replaceWithModFile(method, new VarInsnNode(ALOAD, 1));
            adaptations.add(node.name + "#getModFile(String) = ModFiles.modFile(id)");
        }
    }

    private static MethodNode method(ClassNode node, String name, String descriptor) {
        return node.methods.stream()
                .filter(candidate -> candidate.name.equals(name) && candidate.desc.equals(descriptor))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Missing " + node.name + "#" + name + descriptor));
    }

    /**
     * Jade's {@code ClientProxy.getModName} keeps its I18n translation branch (vanilla code,
     * works as-is) and replaces the whole Fabric-loader fallback with one table call. The
     * fallback is cut from the {@code FabricLoader.getInstance()} call to the method end so a
     * different trailing chain still lowers instead of leaving loader references behind.
     */
    static void lowerLoaderMetadata(ClassNode node, String sourceHash, List<String> adaptations) {
        if (!node.name.equals(JADE_CLIENT_PROXY)) return;
        if (!sourceHash.equals(JADE_CLIENT_PROXY_SHA256)) {
            throw new IllegalArgumentException("Unaudited Jade loader metadata lookup: " + sourceHash);
        }
        MethodNode getModName = method(node, "getModName", "(Ljava/lang/String;Z)Ljava/util/Optional;");
        AbstractInsnNode cutFrom = null;
        for (AbstractInsnNode instruction : getModName.instructions) {
            if (instruction instanceof MethodInsnNode call && call.getOpcode() == INVOKESTATIC
                    && call.owner.equals("net/fabricmc/loader/api/FabricLoader")
                    && call.name.equals("getInstance")) {
                cutFrom = instruction;
                break;
            }
        }
        if (cutFrom == null) {
            throw new IllegalStateException("getModName no longer queries the loader; audit the "
                    + "Jade update and re-pin " + JADE_CLIENT_PROXY_SHA256);
        }
        boolean removed = false;
        while (cutFrom != null) {
            var next = cutFrom.getNext();
            getModName.instructions.remove(cutFrom);
            cutFrom = next;
            removed = true;
        }
        if (!removed) throw new IllegalStateException("getModName fallback was not removed");
        // getModName(String id, boolean modMenu): the id is local 0, the flag is local 1. The
        // table lookup takes the id, so this must load 0 - ALOAD 1 would push the boolean and
        // fail verification instead of returning a name.
        getModName.instructions.add(new VarInsnNode(ALOAD, 0));
        getModName.instructions.add(new MethodInsnNode(INVOKESTATIC, HOOKS, OPTIONAL_MOD_NAME,
                OPTIONAL_MOD_NAME_DESC, false));
        getModName.instructions.add(new InsnNode(ARETURN));
        // maxStack/maxLocals are deliberately left alone: the surviving I18n branch needs the
        // javac value (5), and the class ships through ClassWriter(0), which trusts it. The
        // local-variable table is dropped because its ranges end at a label this cut removed.
        getModName.localVariables = null;
        adaptations.add(node.name + "#getModName(String,boolean) fallback = "
                + HOOKS + "." + OPTIONAL_MOD_NAME);
    }

    private static void replaceWithModFile(MethodNode method, org.objectweb.asm.tree.AbstractInsnNode id) {
        method.instructions.clear();
        method.tryCatchBlocks.clear();
        method.localVariables = null;
        var body = method.instructions;
        body.add(new FieldInsnNode(GETSTATIC, HOOKS, "GAME_DIR", "Ljava/nio/file/Path;"));
        body.add(id);
        body.add(new MethodInsnNode(INVOKESTATIC, MOD_FILES, "modFile", MOD_FILE_DESC, false));
        body.add(new InsnNode(ARETURN));
        method.maxStack = 2;
    }

    /**
     * Namespaces that actually ship under {@code assets/} and {@code data/} in the merged jar.
     *
     * <p>Fabric normally discovers these from each Mod JAR's root, but a closed image has no Mod
     * JARs: all resources live in the single game jar. Only directories can be namespaces - a
     * marker such as {@code assets/.mcassetsroot} is not one - and the identifier grammar is
     * enforced so a stray path cannot widen the pack with an unaddressable name.
     */
    static Set<String> resourceNamespaces(Collection<String> entries) {
        var namespaces = new TreeSet<String>();
        for (String entry : entries) {
            var matcher = RESOURCE_NAMESPACE.matcher(entry);
            if (matcher.find()) namespaces.add(matcher.group(1));
        }
        return namespaces;
    }

    /**
     * Generates {@code mcfao.aot.ModNamespaces}. The table is an image-build-time constant, so
     * it needs no run-time reflection, class loading or resource lookup - all three are exactly
     * what the closed world cannot supply.
     */
    static byte[] modNamespacesClass(Collection<String> namespaces) {
        var sorted = new ArrayList<>(new TreeSet<>(namespaces));
        var node = new ClassNode();
        node.version = V25;
        node.access = ACC_PUBLIC | ACC_FINAL | ACC_SUPER;
        node.name = MOD_NAMESPACES;
        node.superName = "java/lang/Object";
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_STATIC | ACC_FINAL, "NAMESPACES",
                "Ljava/util/Set;", "Ljava/util/Set<Ljava/lang/String;>;", null));

        var init = new MethodNode(ACC_STATIC, "<clinit>", "()V", null, null);
        init.instructions.add(new LdcInsnNode(sorted.size()));
        init.instructions.add(new TypeInsnNode(ANEWARRAY, "java/lang/String"));
        for (int index = 0; index < sorted.size(); index++) {
            init.instructions.add(new InsnNode(DUP));
            init.instructions.add(new LdcInsnNode(index));
            init.instructions.add(new LdcInsnNode(sorted.get(index)));
            init.instructions.add(new InsnNode(AASTORE));
        }
        init.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/Set", "of",
                "([Ljava/lang/Object;)Ljava/util/Set;", true));
        init.instructions.add(new FieldInsnNode(PUTSTATIC, MOD_NAMESPACES, "NAMESPACES",
                "Ljava/util/Set;"));
        init.instructions.add(new InsnNode(RETURN));
        node.methods.add(init);

        var with = new MethodNode(ACC_PUBLIC | ACC_STATIC, "withVanilla",
                "(Ljava/util/Set;)Ljava/util/Set;",
                "(Ljava/util/Set<Ljava/lang/String;>;)Ljava/util/Set<Ljava/lang/String;>;", null);
        with.instructions.add(new TypeInsnNode(NEW, "java/util/HashSet"));
        with.instructions.add(new InsnNode(DUP));
        with.instructions.add(new VarInsnNode(ALOAD, 0));
        with.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/util/HashSet", "<init>",
                "(Ljava/util/Collection;)V", false));
        with.instructions.add(new VarInsnNode(ASTORE, 1));
        with.instructions.add(new VarInsnNode(ALOAD, 1));
        with.instructions.add(new FieldInsnNode(GETSTATIC, MOD_NAMESPACES, "NAMESPACES",
                "Ljava/util/Set;"));
        with.instructions.add(new MethodInsnNode(INVOKEVIRTUAL, "java/util/HashSet", "addAll",
                "(Ljava/util/Collection;)Z", false));
        with.instructions.add(new InsnNode(POP));
        with.instructions.add(new VarInsnNode(ALOAD, 1));
        with.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/Set", "copyOf",
                SET_COPY_DESC, true));
        with.instructions.add(new InsnNode(ARETURN));
        node.methods.add(with);

        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        return writer.toByteArray();
    }

    /**
     * Rewrites the single funnel through which both {@code ClientPackSource} and
     * {@code ServerPacksSource} construct their built-in pack: {@code Set.copyOf(namespaces)}
     * becomes {@code ModNamespaces.withVanilla(namespaces)}.
     *
     * <p>The rest of {@code VanillaPackResources} already reads resources by path, so widening
     * this one set makes {@code MultiPackResourceManager} build an index entry for every shipped
     * namespace and lets both {@code getResource} and {@code listResources} reach the files. This
     * replaces the whole {@code ModResourcePackCreator} layer rather than specialising any Mod.
     */
    static void lowerVanillaPackBuilder(ClassNode node, String sourceHash, List<String> adaptations) {
        lowerVanillaPackBuilder(node, sourceHash, adaptations, new ArrayList<>());
    }

    static void lowerVanillaPackBuilder(ClassNode node, String sourceHash, List<String> adaptations,
            List<Map<String, Object>> ruleOutcomes) {
        var rule = new AdaptationRuleEngine.Rule() {
            private MethodNode build(ClassNode target) {
                return method(target, "build", VANILLA_BUILD_DESC);
            }

            @Override public String id() { return "fabric.resource.merged-namespace-index.v1"; }
            @Override public String mechanism() {
                return "Vanilla built-in pack namespace index over merged Mod resources";
            }
            @Override public String target(ClassNode target) {
                return target.name + "#build" + VANILLA_BUILD_DESC;
            }
            @Override public boolean matches(ClassNode target) {
                return target.name.equals(VANILLA_PACK_BUILDER);
            }
            @Override public boolean alreadyApplied(ClassNode target) {
                MethodNode method = build(target);
                int rewritten = 0;
                int original = 0;
                for (AbstractInsnNode instruction : method.instructions) {
                    if (!(instruction instanceof MethodInsnNode call)) continue;
                    if (call.getOpcode() == INVOKESTATIC && call.owner.equals(MOD_NAMESPACES)
                            && call.name.equals("withVanilla")
                            && call.desc.equals("(Ljava/util/Set;)Ljava/util/Set;")) rewritten++;
                    if (call.getOpcode() == INVOKESTATIC && call.owner.equals("java/util/Set")
                            && call.name.equals("copyOf") && call.desc.equals(SET_COPY_DESC)) original++;
                }
                return rewritten == 1 && original == 0;
            }
            @Override public String preconditionFailure(ClassNode target) {
                MethodNode method = build(target);
                int candidates = 0;
                for (AbstractInsnNode instruction : method.instructions) {
                    if (!(instruction instanceof MethodInsnNode call)
                            || call.getOpcode() != INVOKESTATIC
                            || !call.owner.equals("java/util/Set") || !call.name.equals("copyOf")
                            || !call.desc.equals(SET_COPY_DESC)) continue;
                    AbstractInsnNode previous = previousReal(call);
                    if (!(previous instanceof FieldInsnNode field)
                            || field.getOpcode() != GETFIELD
                            || !field.owner.equals(VANILLA_PACK_BUILDER)
                            || !field.name.equals("namespaces")) {
                        return "Set.copyOf is not fed by this.namespaces";
                    }
                    candidates++;
                }
                return candidates == 1 ? null
                        : "expected one structural namespace freeze, found " + candidates
                                + " (source SHA-256 " + sourceHash + ")";
            }
            @Override public int apply(ClassNode target) {
                int changed = 0;
                for (AbstractInsnNode instruction : build(target).instructions) {
                    if (!(instruction instanceof MethodInsnNode call)
                            || call.getOpcode() != INVOKESTATIC
                            || !call.owner.equals("java/util/Set") || !call.name.equals("copyOf")
                            || !call.desc.equals(SET_COPY_DESC)) continue;
                    call.owner = MOD_NAMESPACES;
                    call.name = "withVanilla";
                    call.desc = "(Ljava/util/Set;)Ljava/util/Set;";
                    call.itf = false;
                    changed++;
                }
                adaptations.add(target.name + "#build = ModNamespaces.withVanilla(namespaces)");
                return changed;
            }
            @Override public String verificationFailure(ClassNode target) {
                MethodNode method = build(target);
                int rewritten = 0;
                int original = 0;
                for (AbstractInsnNode instruction : method.instructions) {
                    if (!(instruction instanceof MethodInsnNode call)) continue;
                    if (call.getOpcode() == INVOKESTATIC && call.owner.equals(MOD_NAMESPACES)
                            && call.name.equals("withVanilla")
                            && call.desc.equals("(Ljava/util/Set;)Ljava/util/Set;") && !call.itf) {
                        rewritten++;
                    }
                    if (call.getOpcode() == INVOKESTATIC && call.owner.equals("java/util/Set")
                            && call.name.equals("copyOf") && call.desc.equals(SET_COPY_DESC)) original++;
                }
                return rewritten == 1 && original == 0 ? null
                        : "expected one static ModNamespaces.withVanilla call and no original freeze; found "
                                + rewritten + " rewritten and " + original + " original";
            }
        };
        ruleOutcomes.addAll(AdaptationRuleEngine.run(node, List.of(rule)));
    }

    /**
     * Generates the {@code @FrameworkConfig} annotation instance handed to the framework.
     *
     * <p>The annotation is an interface with five constant members, so an ordinary implementing
     * class is indistinguishable from the one the JVM would synthesise from class-file metadata -
     * and unlike a synthesised instance it needs no annotation encoding, which a closed image
     * cannot produce for a field it did not read reflectively.
     */
    static byte[] frameworkConfigAnnotationClass() {
        var node = new ClassNode();
        node.version = V25;
        node.access = ACC_PUBLIC | ACC_FINAL | ACC_SUPER;
        node.name = CONFIG_ANNOTATION;
        node.superName = "java/lang/Object";
        node.interfaces.add(FRAMEWORK_CONFIG);
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_FINAL, "id", "Ljava/lang/String;", null, null));
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_FINAL, "name", "Ljava/lang/String;", null, null));
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_FINAL, "readOnly", "Z", null, null));
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_FINAL, "type", "L" + CONFIG_TYPE + ";", null, null));
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_FINAL, "separator", "C", null, null));

        var init = new MethodNode(ACC_PUBLIC, "<init>", CONFIG_ANNOTATION_DESC, null, null);
        init.instructions.add(new VarInsnNode(ALOAD, 0));
        init.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false));
        String[][] copies = {{"id", "Ljava/lang/String;", "1", "ALOAD"},
                {"name", "Ljava/lang/String;", "2", "ALOAD"},
                {"readOnly", "Z", "3", "ILOAD"},
                {"type", "L" + CONFIG_TYPE + ";", "4", "ALOAD"},
                {"separator", "C", "5", "ILOAD"}};
        for (String[] copy : copies) {
            init.instructions.add(new VarInsnNode(ALOAD, 0));
            init.instructions.add(new VarInsnNode(copy[3].equals("ALOAD") ? ALOAD : ILOAD,
                    Integer.parseInt(copy[2])));
            init.instructions.add(new FieldInsnNode(PUTFIELD, CONFIG_ANNOTATION, copy[0], copy[1]));
        }
        init.instructions.add(new InsnNode(RETURN));
        node.methods.add(init);

        String[][] members = {{"id", "Ljava/lang/String;"}, {"name", "Ljava/lang/String;"},
                {"readOnly", "Z"}, {"type", "L" + CONFIG_TYPE + ";"}, {"separator", "C"}};
        for (String[] member : members) {
            var accessor = new MethodNode(ACC_PUBLIC, member[0], "()" + member[1], null, null);
            accessor.instructions.add(new VarInsnNode(ALOAD, 0));
            accessor.instructions.add(new FieldInsnNode(GETFIELD, CONFIG_ANNOTATION, member[0], member[1]));
            accessor.instructions.add(new InsnNode(member[1].charAt(0) == 'L' ? ARETURN : IRETURN));
            node.methods.add(accessor);
        }
        var type = new MethodNode(ACC_PUBLIC, "annotationType", "()Ljava/lang/Class;", null, null);
        type.instructions.add(new LdcInsnNode(Type.getObjectType(FRAMEWORK_CONFIG)));
        type.instructions.add(new InsnNode(ARETURN));
        node.methods.add(type);

        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        return writer.toByteArray();
    }

    /**
     * Generates {@code mcfao.aot.FrameworkConfigs}, the build-time replacement for
     * {@code FabricConfigHelper.getAllFrameworkConfigs()}.
     *
     * <p>Each entry is a {@code Pair.of(<@FrameworkConfig annotation>, <static config field>)} -
     * exactly what the reflective scan produced per shipping Mod, with the annotation values read
     * from the field's own class-file annotation and the instance loaded by {@code GETSTATIC}.
     * Constructing the pairs in a static initializer keeps the ordering the framework relies on
     * (a Mod's configs in declaration order) and avoids any reflection on the way.
     */
    static byte[] frameworkConfigsClass(List<String[]> entries) {
        var node = new ClassNode();
        node.version = V25;
        node.access = ACC_PUBLIC | ACC_FINAL | ACC_SUPER;
        node.name = CONFIG_TABLE;
        node.superName = "java/lang/Object";
        node.fields.add(new FieldNode(ACC_PRIVATE | ACC_STATIC | ACC_FINAL, "ALL",
                "Ljava/util/List;", "Ljava/util/List<Lorg/apache/commons/lang3/tuple/Pair;>;", null));

        var init = new MethodNode(ACC_STATIC, "<clinit>", "()V", null, null);
        var code = init.instructions;
        code.add(new TypeInsnNode(NEW, "java/util/ArrayList"));
        code.add(new InsnNode(DUP));
        code.add(new MethodInsnNode(INVOKESPECIAL, "java/util/ArrayList", "<init>", "()V", false));
        code.add(new VarInsnNode(ASTORE, 0));
        for (String[] entry : entries) {
            // owner, field, descriptor, id, name, readOnly, type, separator
            code.add(new VarInsnNode(ALOAD, 0));
            code.add(new TypeInsnNode(NEW, CONFIG_ANNOTATION));
            code.add(new InsnNode(DUP));
            code.add(new LdcInsnNode(entry[3]));
            code.add(new LdcInsnNode(entry[4]));
            code.add(new InsnNode(Boolean.parseBoolean(entry[5]) ? ICONST_1 : ICONST_0));
            code.add(new FieldInsnNode(GETSTATIC, CONFIG_TYPE, entry[6], "L" + CONFIG_TYPE + ";"));
            code.add(new LdcInsnNode((int) entry[7].charAt(0)));
            code.add(new MethodInsnNode(INVOKESPECIAL, CONFIG_ANNOTATION, "<init>",
                    CONFIG_ANNOTATION_DESC, false));
            code.add(new FieldInsnNode(GETSTATIC, entry[0], entry[1], entry[2]));
            code.add(new MethodInsnNode(INVOKESTATIC, "org/apache/commons/lang3/tuple/Pair", "of",
                    "(Ljava/lang/Object;Ljava/lang/Object;)Lorg/apache/commons/lang3/tuple/Pair;", false));
            code.add(new MethodInsnNode(INVOKEVIRTUAL, "java/util/ArrayList", "add",
                    "(Ljava/lang/Object;)Z", false));
            code.add(new InsnNode(POP));
        }
        code.add(new VarInsnNode(ALOAD, 0));
        code.add(new MethodInsnNode(INVOKESTATIC, "java/util/List", "copyOf",
                "(Ljava/util/Collection;)Ljava/util/List;", true));
        code.add(new FieldInsnNode(PUTSTATIC, CONFIG_TABLE, "ALL", "Ljava/util/List;"));
        code.add(new InsnNode(RETURN));
        init.maxStack = 6;
        init.maxLocals = 1;
        node.methods.add(init);

        var all = new MethodNode(ACC_PUBLIC | ACC_STATIC, "all", CONFIG_DISCOVERY_DESC, null, null);
        all.instructions.add(new FieldInsnNode(GETSTATIC, CONFIG_TABLE, "ALL", "Ljava/util/List;"));
        all.instructions.add(new InsnNode(ARETURN));
        all.maxStack = 1;
        node.methods.add(all);

        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        return writer.toByteArray();
    }

    /**
     * Replaces {@code FabricConfigHelper.getAllFrameworkConfigs()} with the generated table.
     *
     * <p>The original body asks the Loader for every Mod, reads each {@code fabric.mod.json}
     * custom value, loads the named class and walks its annotated fields. Without Mod jars the
     * first step yields nothing, so the whole chain - including the two lambdas that do the
     * reflection - is dead once the table exists. Replacing just this method keeps the framework's
     * own {@code ConfigScanData} linking untouched, which is what actually marks the properties as
     * linked.
     */
    static void lowerConfigDiscovery(ClassNode node, List<String> adaptations) {
        if (!node.name.equals(CONFIG_HELPER)) return;
        MethodNode discovery = method(node, CONFIG_DISCOVERY, CONFIG_DISCOVERY_DESC);
        discovery.instructions.clear();
        discovery.tryCatchBlocks.clear();
        discovery.localVariables = null;
        discovery.instructions.add(new MethodInsnNode(INVOKESTATIC, CONFIG_TABLE, "all",
                CONFIG_DISCOVERY_DESC, false));
        discovery.instructions.add(new InsnNode(ARETURN));
        discovery.maxStack = 1;
        discovery.maxLocals = 1;
        adaptations.add(node.name + "#" + CONFIG_DISCOVERY + " = FrameworkConfigs.all()");
    }


    // The Metal bundle is translated from vanilla shader sources, so a Mod pipeline with its own
    // shaders has no precompiled program. ShaderManager.apply precompiles every registered static
    // pipeline during a resource reload and aborts the reload on the first failure, which would
    // take the client down before the first world frame. Registration is the single funnel, so the
    // guard lives there: the bundle decides what joins the static registry, and an unsupported
    // pipeline fails at its own draw call instead of breaking shared reload state.
    static final String RENDER_PIPELINES = "net/minecraft/client/renderer/RenderPipelines";
    static final String BUNDLED_PIPELINES = "fabricaot/metal/BundledPipelines";
    static final String RENDER_PIPELINE = "Lcom/mojang/blaze3d/pipeline/RenderPipeline;";
    static final String REGISTER_DESC = "(" + RENDER_PIPELINE + ")" + RENDER_PIPELINE;
    static final String BUNDLED_REGISTER_DESC =
            "(Ljava/util/Map;" + RENDER_PIPELINE + ")" + RENDER_PIPELINE;

    static void lowerRenderPipelineRegister(ClassNode node, String sourceHash, List<String> adaptations) {
        if (!node.name.equals(RENDER_PIPELINES)) return;
        MethodNode register = method(node, "register", REGISTER_DESC);
        register.instructions.clear();
        register.tryCatchBlocks.clear();
        register.localVariables = null;
        var body = register.instructions;
        body.add(new FieldInsnNode(GETSTATIC, RENDER_PIPELINES, "PIPELINES_BY_LOCATION",
                "Ljava/util/Map;"));
        body.add(new VarInsnNode(ALOAD, 0));
        body.add(new MethodInsnNode(INVOKESTATIC, BUNDLED_PIPELINES, "register",
                BUNDLED_REGISTER_DESC, false));
        body.add(new InsnNode(ARETURN));
        register.maxStack = 2;
        register.maxLocals = 1;
        adaptations.add(node.name + "#register = BundledPipelines.register(byLocation, pipeline)");
    }

    static void lowerSodiumMetadata(ClassNode node, String sourceHash, List<String> adaptations) {
        if (!node.name.equals("net/caffeinemc/mods/sodium/fabric/config/ConfigLoaderFabric")) return;
        if (!sourceHash.equals("13cb0cc07040be08158ab8cd53992f519d1430bcd40574bd651c93362efa2cfd")) {
            throw new IllegalArgumentException("Unaudited Sodium metadata lookup: " + sourceHash);
        }
        var method = node.methods.stream().filter(m -> m.name.equals("getModMetadata")
                && m.desc.equals("(Ljava/lang/String;)Lnet/caffeinemc/mods/sodium/client/config/ConfigManager$ModMetadata;"))
                .findFirst().orElseThrow();
        method.instructions.clear();
        method.tryCatchBlocks.clear();
        method.localVariables = null;
        String result = org.objectweb.asm.Type.getReturnType(method.desc).getInternalName();
        var body = method.instructions;
        body.add(new org.objectweb.asm.tree.TypeInsnNode(NEW, result));
        body.add(new InsnNode(DUP));
        body.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
        body.add(new MethodInsnNode(INVOKESTATIC, HOOKS, "modName", "(Ljava/lang/String;)Ljava/lang/String;", false));
        body.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
        body.add(new MethodInsnNode(INVOKESTATIC, HOOKS, "modVersion",
                "(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;", false));
        body.add(new MethodInsnNode(INVOKEINTERFACE, "net/fabricmc/loader/api/Version",
                "getFriendlyString", "()Ljava/lang/String;", true));
        body.add(new MethodInsnNode(INVOKESPECIAL, result, "<init>", "(Ljava/lang/String;Ljava/lang/String;)V", false));
        body.add(new InsnNode(ARETURN));
        method.maxStack = 4;
        method.maxLocals = 1;
        adaptations.add(node.name + "#getModMetadata name/version=build snapshot");
    }

    static void lowerVersionLookup(ClassNode node, String sourceHash, List<String> adaptations) {
        if (!node.name.equals("eu/ha3/mc/quick/update/TargettedVersion")) return;
        if (!sourceHash.equals("354dc01c8aff54e3b4543f1d441fcbbbefa32ee15ccc5041aad895a44196aa1b")) {
            throw new IllegalArgumentException("Unaudited TargettedVersion lookup: " + sourceHash);
        }
        var method = node.methods.stream().filter(m -> m.name.equals("getVersion")
                && m.desc.equals("(Ljava/lang/String;)Lnet/fabricmc/loader/api/Version;"))
                .findFirst().orElseThrow();
        method.instructions.clear();
        method.tryCatchBlocks.clear();
        method.localVariables = null;
        method.instructions.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
        method.instructions.add(new MethodInsnNode(INVOKESTATIC, HOOKS, "modVersion", method.desc, false));
        method.instructions.add(new InsnNode(ARETURN));
        method.maxStack = 1;
        method.maxLocals = 1;
        adaptations.add(node.name + "#getVersion version lookup=build snapshot");
    }

    /**
     * PlatformCodeImpl.getModVersion(id) is `getModContainer(id).map(version)`. The residue
     * lowering cannot resolve a computed id, so it folds the whole chain into Optional.empty -
     * but earlyInit() then calls orElseThrow() to read ImmediatelyFast's own version. Route the
     * query to the generated build snapshot instead: present Mods report their real version,
     * absent ones still report Optional.empty, exactly as the Loader would.
     */
    static void lowerImmediatelyFastVersion(ClassNode node, String sourceHash,
            List<String> adaptations) {
        if (!node.name.equals(IF_PLATFORM)) return;
        if (!sourceHash.equals(IF_PLATFORM_SHA256)) {
            throw new IllegalArgumentException("Unaudited ImmediatelyFast version lookup: " + sourceHash);
        }
        var method = node.methods.stream().filter(m -> m.name.equals("getModVersion")
                && m.desc.equals(OPTIONAL_VERSION_DESC)).findFirst().orElseThrow();
        method.instructions.clear();
        method.tryCatchBlocks.clear();
        method.localVariables = null;
        method.instructions.add(new VarInsnNode(ALOAD, 0));
        method.instructions.add(new MethodInsnNode(INVOKESTATIC, HOOKS, OPTIONAL_VERSION,
                OPTIONAL_VERSION_DESC, false));
        method.instructions.add(new InsnNode(ARETURN));
        method.maxStack = 1;
        method.maxLocals = 1;
        adaptations.add(node.name + "#getModVersion optional version=build snapshot");
    }

    /**
     * A MixinConfigPlugin is dropped from the image, but its onLoad side effects are not
     * optional. Only the audited ImmediatelyFast plugin is accepted: its onLoad must contain
     * exactly one call to ImmediatelyFast.earlyInit() and nothing else that initializes state.
     * The caller replays that call at the start of the generated client entrypoint dispatch,
     * which is the closed-world equivalent of Fabric's pre-entrypoint Mixin application.
     */
    static void collectMixinPluginEarlyInit(String entry, byte[] data, String sourceHash,
            Set<String> earlyInitializers, List<String> adaptations) {
        if (!entry.equals(IF_PLUGIN + ".class")) return;
        if (!sourceHash.equals(IF_PLUGIN_SHA256)) {
            throw new IllegalArgumentException("Unaudited ImmediatelyFast mixin plugin: " + sourceHash);
        }
        var node = new ClassNode();
        new ClassReader(data).accept(node, 0);
        var onLoad = node.methods.stream().filter(m -> m.name.equals("onLoad")
                && m.desc.equals("(Ljava/lang/String;)V")).findFirst().orElseThrow();
        int calls = 0;
        for (var instruction : onLoad.instructions) {
            if (instruction instanceof MethodInsnNode call && call.getOpcode() == INVOKESTATIC
                    && call.owner.equals(IF_MAIN) && call.name.equals(IF_EARLY_INIT)
                    && call.desc.equals(IF_EARLY_INIT_DESC)) calls++;
        }
        if (calls != 1) {
            throw new IllegalArgumentException("ImmediatelyFast mixin plugin onLoad changed: "
                    + calls + " earlyInit calls");
        }
        earlyInitializers.add(IF_MAIN + "#" + IF_EARLY_INIT);
        adaptations.add(IF_PLUGIN + "#onLoad earlyInit=replayed at client entrypoint dispatch");
    }

    static void collectStageQueries(ClassNode node, Set<String> stages) {
        for (var method : node.methods) {
            for (var instruction : method.instructions) {
                if (!(instruction instanceof MethodInsnNode call) || !call.owner.equals(HOOKS)
                        || !call.name.equals("stage")) continue;
                var lastArgument = previousReal(call);
                if (lastArgument == null) continue;
                var key = previousReal(lastArgument);
                if (key instanceof LdcInsnNode literal && literal.cst instanceof String stage) stages.add(stage);
                else throw new IllegalArgumentException("Non-static entrypoint stage in " + node.name);
            }
        }
    }

    /**
     * Records the types a Mod hands to a JSON reader, which a closed image must keep reflectable.
     *
     * <p>The last argument is the only thing that matters: a {@code Class} literal right before a
     * {@code fromJson} call names the type Gson instantiates by reflection. Gson and Jankson are
     * matched by owner, but Mods routinely wrap them in a helper with the same name and signature
     * ({@code JsonUtil.fromJson(String, Class)}) that forwards the {@code Class} straight through;
     * the literal is then only visible at the wrapper's call site, so the name and the trailing
     * {@code Class} parameter are what the scan keys on. A {@code fromJson} that takes anything
     * else, or a helper with a different name, is not a JSON read and is ignored.
     */
    static void collectSerializationRoots(ClassNode node, Set<String> roots) {
        for (var method : node.methods) {
            for (var instruction : method.instructions) {
                if (!(instruction instanceof MethodInsnNode call)
                        || !(call.name.equals("fromJson") || call.name.equals("fromJsonCarefully"))) continue;
                var arguments = org.objectweb.asm.Type.getArgumentTypes(call.desc);
                if (arguments.length == 0 || !arguments[arguments.length - 1].getDescriptor()
                        .equals("Ljava/lang/Class;")) continue;
                if (previousReal(call) instanceof LdcInsnNode literal
                        && literal.cst instanceof org.objectweb.asm.Type type
                        && type.getSort() == org.objectweb.asm.Type.OBJECT) {
                    roots.add(type.getInternalName());
                }
            }
        }
    }

    static final String INDIGO_PLUGIN =
            "net/fabricmc/fabric/impl/client/indigo/IndigoMixinConfigPlugin";
    static final String INDIGO_PLUGIN_SHA256 =
            "934ac8f2002a53fcf5a095d44cfd1ce97625ff362058b2556b5d4f59941f0d47";
    static final String JADE_METADATA = "snownee/jade/util/FabricJadeMetadata";
    static final String JADE_METADATA_SHA256 =
            "0893768a286b48ac48e75ab7b8d7ecf2da3321d8743fbba0366abd0c42aa2184";

    static void lowerJadeMetadata(ClassNode node, String sourceHash, Map<String, Boolean> flags,
            List<String> disabledTooltips, List<String> adaptations) {
        if (!node.name.equals(JADE_METADATA)) return;
        if (!JADE_METADATA_SHA256.equals(sourceHash)) {
            throw new IllegalArgumentException("Unaudited Jade metadata constructor: " + sourceHash);
        }
        var constructor = node.methods.stream().filter(m -> m.name.equals("<init>") && m.desc.equals("()V"))
                .findFirst().orElseThrow();
        constructor.instructions.clear();
        constructor.tryCatchBlocks.clear();
        constructor.localVariables = null;
        var body = constructor.instructions;
        body.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
        body.add(new MethodInsnNode(INVOKESPECIAL, node.superName, "<init>", "()V", false));
        for (String field : List.of("accessibilityMod", "fastScroll", "smoothScroll")) {
            body.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
            body.add(new InsnNode(DUP));
            body.add(new FieldInsnNode(GETFIELD, node.name, field, "Z"));
            body.add(new InsnNode(flags.getOrDefault(field, false) ? ICONST_1 : ICONST_0));
            body.add(new InsnNode(IOR));
            body.add(new FieldInsnNode(PUTFIELD, node.name, field, "Z"));
        }
        body.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
        body.add(new LdcInsnNode(disabledTooltips.size()));
        body.add(new org.objectweb.asm.tree.TypeInsnNode(ANEWARRAY, "java/lang/String"));
        for (int i = 0; i < disabledTooltips.size(); i++) {
            body.add(new InsnNode(DUP));
            body.add(new LdcInsnNode(i));
            body.add(new LdcInsnNode(disabledTooltips.get(i)));
            body.add(new InsnNode(AASTORE));
        }
        body.add(new MethodInsnNode(INVOKESTATIC, "java/util/List", "of",
                "([Ljava/lang/Object;)Ljava/util/List;", true));
        body.add(new FieldInsnNode(PUTFIELD, node.name, "disableItemModNameTooltip", "Ljava/util/List;"));
        body.add(new InsnNode(RETURN));
        constructor.maxStack = 6;
        constructor.maxLocals = 1;
        adaptations.add(node.name + "#<init> Jade metadata=" + flags + ", disabledTooltips=" + disabledTooltips);
    }

    static void foldIndigoGate(ClassNode node, boolean applicable, String pluginHash,
            List<String> adaptations) {
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call)
                        || call.getOpcode() != INVOKESTATIC || !call.owner.equals(INDIGO_PLUGIN)
                        || !call.name.equals("shouldApplyIndigo") || !call.desc.equals("()Z")) continue;
                if (!INDIGO_PLUGIN_SHA256.equals(pluginHash)) {
                    throw new IllegalArgumentException("Unaudited Indigo plugin query: " + pluginHash);
                }
                method.instructions.set(call, new InsnNode(applicable ? ICONST_1 : ICONST_0));
                adaptations.add(node.name + "#" + method.name
                        + " shouldApplyIndigo=" + applicable + " (resolved renderer metadata)");
            }
        }
    }

    /**
     * Drops the Mixin annotations from a class that is shipped verbatim. The merge already copied
     * the generated members into the target, so the class only has to exist for the references
     * other code makes to it; keeping the annotations would drag the Mixin annotation types into a
     * runtime that has no Mixin.
     */
    static void stripMixinMetadata(ClassNode node) {
        // Mixin makes a non-public mixin public when it merges it into a target, because a target
        // that implements (or extends) it has to be able to reach it from another package. A copy
        // shipped verbatim keeps the source flags, and then every class the merge gave that
        // interface fails to load with IllegalAccessError - a core game class in the worst case.
        // The shipped copy only has to be resolvable, so its own access is widened once here.
        node.access = (node.access | ACC_PUBLIC) & ~(ACC_PRIVATE | ACC_PROTECTED);
        node.visibleAnnotations = null;
        node.invisibleAnnotations = null;
        for (var field : node.fields) {
            field.visibleAnnotations = null;
            field.invisibleAnnotations = null;
        }
        for (var method : node.methods) {
            method.visibleAnnotations = null;
            method.invisibleAnnotations = null;
        }
    }

    private static boolean hasAnnotation(List<AnnotationNode> visible, List<AnnotationNode> invisible,
            Set<String> descriptors) {
        return (visible != null && visible.stream().anyMatch(a -> descriptors.contains(a.desc)))
                || (invisible != null && invisible.stream().anyMatch(a -> descriptors.contains(a.desc)));
    }


    static void lowerQueries(ClassNode node, Set<String> loadedIds, java.util.Map<String, String> versions,
            List<String> adaptations, Set<String> stubbed, Set<String> protectedMethods) {
        var deadLambdas = new java.util.TreeSet<String>();
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode provider) || !provider.owner.equals(
                        "net/fabricmc/loader/api/entrypoint/EntrypointContainer")
                        || !provider.name.equals("getProvider")) continue;
                var metadata = nextReal(provider);
                var id = metadata == null ? null : nextReal(metadata);
                if (metadata instanceof MethodInsnNode meta && meta.owner.equals("net/fabricmc/loader/api/ModContainer")
                        && meta.name.equals("getMetadata") && id instanceof MethodInsnNode value
                        && value.owner.equals("net/fabricmc/loader/api/metadata/ModMetadata") && value.name.equals("getId")) {
                    method.instructions.set(provider, new MethodInsnNode(INVOKESTATIC, HOOKS, "providerModId",
                            "(Ljava/lang/Object;)Ljava/lang/String;", false));
                    method.instructions.remove(metadata);
                    method.instructions.remove(id);
                    adaptations.add(node.name + "#" + method.name + " entrypoint provider id=build snapshot");
                }
            }
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode instance)
                        || !instance.owner.equals(LOADER) || !instance.name.equals("getInstance")
                        || !instance.desc.equals("()L" + LOADER + ";") || instance.getOpcode() != INVOKESTATIC) continue;
                var next = nextReal(instance);
                String location = node.name + "#" + method.name + " ";
                java.util.List<org.objectweb.asm.tree.AbstractInsnNode> chain = null;
                if (next instanceof LdcInsnNode doc && doc.cst instanceof String owner
                        && versions.containsKey(owner)) {
                    chain = versionChain(method.instructions, instance);
                }
                if (chain != null) {
                    // The pinned Mod set makes the reported version a build-time constant, so the
                    // whole container lookup collapses to the string the initializer asks for.
                    String id = (String) ((LdcInsnNode) next).cst;
                    method.instructions.set(instance, new LdcInsnNode(versions.get(id)));
                    for (var removed : chain) method.instructions.remove(removed);
                    adaptations.add(location + "getModContainer(" + id + ").version=" + versions.get(id));
                } else if (isQuery(next, "isDevelopmentEnvironment", "()Z")) {
                    method.instructions.set(instance, new InsnNode(ICONST_0));
                    method.instructions.remove(next);
                    adaptations.add(location + "isDevelopmentEnvironment=false");
                } else if (isQuery(next, "getEnvironmentType", "()Lnet/fabricmc/api/EnvType;")) {
                    method.instructions.set(instance, new FieldInsnNode(GETSTATIC, "net/fabricmc/api/EnvType",
                            "CLIENT", "Lnet/fabricmc/api/EnvType;"));
                    method.instructions.remove(next);
                    adaptations.add(location + "getEnvironmentType=CLIENT");
                } else if (isQuery(nextReal(next), "getModContainer", "(Ljava/lang/String;)Ljava/util/Optional;")) {
                    var lookup = nextReal(next);
                    method.instructions.set(instance, new InsnNode(ACONST_NULL));
                    method.instructions.set(lookup, new MethodInsnNode(INVOKESTATIC,
                            "mcfao/aot/ModCatalog", "lookup",
                            "(Ljava/lang/Object;Ljava/lang/String;)Ljava/util/Optional;", false));
                    adaptations.add(location + "getModContainer(query)=build snapshot");
                } else if (isQuery(next, "getGameDir", "()Ljava/nio/file/Path;")) {
                    // The hook receives the same launch directory the Loader would report.
                    method.instructions.set(instance, new FieldInsnNode(GETSTATIC, HOOKS,
                            "GAME_DIR", "Ljava/nio/file/Path;"));
                    method.instructions.remove(next);
                    adaptations.add(location + "getGameDir=launch directory");
                } else if (isQuery(next, "getConfigDir", "()Ljava/nio/file/Path;")) {
                    method.instructions.set(instance, new MethodInsnNode(INVOKESTATIC, HOOKS,
                            "configDir", "()Ljava/nio/file/Path;", false));
                    method.instructions.remove(next);
                    adaptations.add(location + "getConfigDir=launch directory/config");
                } else if (isQuery(next, "getAllMods", "()Ljava/util/Collection;")) {
                    method.instructions.set(instance, new MethodInsnNode(INVOKESTATIC,
                            "mcfao/aot/ModCatalog", "all", "()Ljava/util/Collection;", false));
                    method.instructions.remove(next);
                    adaptations.add(location + "getAllMods=build snapshot");
                } else if (next instanceof LdcInsnNode constant && constant.cst instanceof String stage
                        && (isQuery(nextReal(nextReal(next)),
                                "getEntrypointContainers", "(Ljava/lang/String;Ljava/lang/Class;)Ljava/util/List;")
                            || isQuery(nextReal(nextReal(next)),
                                "getEntrypoints", "(Ljava/lang/String;Ljava/lang/Class;)Ljava/util/List;"))) {
                    // A custom stage is dispatched from a generated switch over the build-time
                    // provider list. The receiver is replaced by a null the hook ignores, so no
                    // Loader instance and no Loader type reaches the image.
                    var classLiteral = nextReal(next);
                    var call = nextReal(classLiteral);
                    var receiver = new InsnNode(ACONST_NULL);
                    method.instructions.set(instance, receiver);
                    method.instructions.set(call, new MethodInsnNode(INVOKESTATIC, HOOKS,
                            ((MethodInsnNode) call).name.equals("getEntrypoints") ? "stageValues" : "stage",
                            "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Class;)Ljava/util/List;", false));
                    adaptations.add(location + "entrypoints(" + stage + ")=generated dispatch");
                } else if (next instanceof LdcInsnNode constant && constant.cst instanceof String id
                        && isQuery(nextReal(next), "isModLoaded", "(Ljava/lang/String;)Z")) {
                    boolean loaded = loadedIds.contains(id);
                    method.instructions.set(instance, new InsnNode(loaded ? ICONST_1 : ICONST_0));
                    method.instructions.remove(nextReal(next));
                    method.instructions.remove(next);
                    adaptations.add(location + "isModLoaded(" + id + ")=" + loaded);
                }
            }
            // Locate the receiver from stack provenance rather than adjacent instructions:
            // IDs may come from fields, method calls, or multi-instruction expressions.
            boolean hasContainerQuery = method.instructions.iterator().hasNext() &&
                    java.util.Arrays.stream(method.instructions.toArray()).anyMatch(insn ->
                        insn instanceof MethodInsnNode call && isQuery(call, "getModContainer",
                                "(Ljava/lang/String;)Ljava/util/Optional;"));
            if (hasContainerQuery) {
                try {
                    var analyzer = new org.objectweb.asm.tree.analysis.Analyzer<>(
                            new org.objectweb.asm.tree.analysis.SourceInterpreter());
                    var frames = analyzer.analyzeAndComputeMaxs(node.name, method);
                    var instructions = method.instructions.toArray();
                    for (int index = 0; index < instructions.length; index++) {
                        if (!(instructions[index] instanceof MethodInsnNode call)
                                || !isQuery(call, "getModContainer", "(Ljava/lang/String;)Ljava/util/Optional;")) continue;
                        var frame = frames[index];
                        if (frame == null || frame.getStackSize() < 2) continue;
                        var sources = frame.getStack(frame.getStackSize()-2).insns;
                        if (sources.isEmpty() || !sources.stream().allMatch(source ->
                                source instanceof MethodInsnNode factory && factory.owner.equals(LOADER)
                                && factory.name.equals("getInstance") && factory.getOpcode()==INVOKESTATIC)) continue;
                        for (var source : sources) if (method.instructions.indexOf(source)>=0)
                            method.instructions.set(source, new InsnNode(ACONST_NULL));
                        method.instructions.set(call, new MethodInsnNode(INVOKESTATIC,
                                "mcfao/aot/ModCatalog", "lookup",
                                "(Ljava/lang/Object;Ljava/lang/String;)Ljava/util/Optional;", false));
                        adaptations.add(node.name + "#" + method.name + " getModContainer(expression)=build snapshot");
                    }
                } catch (org.objectweb.asm.tree.analysis.AnalyzerException error) {
                    throw new IllegalArgumentException("Cannot analyze Loader query in " + node.name + "#" + method.name, error);
                }
            }
            // A query whose id is not a literal cannot be folded. Route it to the generated
            // membership test so the image never reaches the build-time Loader instance.
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call) || !call.owner.equals(LOADER)
                        || !call.name.equals("isModLoaded") || !call.desc.equals("(Ljava/lang/String;)Z")
                        || call.getOpcode() != INVOKEINTERFACE) continue;
                var argument = previousReal(call);
                var receiver = argument == null ? null : previousReal(argument);
                if (!(receiver instanceof MethodInsnNode source) || !source.owner.equals(LOADER)
                        || !source.name.equals("getInstance") || source.getOpcode() != INVOKESTATIC) continue;
                method.instructions.set(call, new MethodInsnNode(INVOKESTATIC, HOOKS,
                        "isModLoaded", "(Ljava/lang/String;)Z", false));
                method.instructions.remove(source);
                adaptations.add(node.name + "#" + method.name + " isModLoaded(query)=generated membership test");
            }
            // MappingResolver: the whole `getInstance().getMappingResolver().mapXxx(...)` chain is
            // routed to a generated identity hook, so no Loader type reaches the image and the
            // caller keeps the name it would have resolved in an official-name runtime. The
            // arguments sit between the resolver and the call, so the walk back crosses them.
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode query) || !query.owner.equals(MAPPING_RESOLVER)
                        || query.getOpcode() != INVOKEINTERFACE) continue;
                String hook = MAPPING_HOOKS.get(query.name);
                if (hook == null) continue;
                int arguments = org.objectweb.asm.Type.getArgumentTypes(query.desc).length;
                org.objectweb.asm.tree.AbstractInsnNode cursor = query;
                // `arguments` steps land on the last pushed argument; one more reaches the
                // resolver call the chain uses as its receiver.
                for (int index = 0; index <= arguments && cursor != null; index++) cursor = previousReal(cursor);
                if (!(cursor instanceof MethodInsnNode resolverCall)
                        || !resolverCall.owner.equals(LOADER)
                        || !resolverCall.name.equals("getMappingResolver")) continue;
                var instance = previousReal(resolverCall);
                if (!(instance instanceof MethodInsnNode instanceCall)
                        || !instanceCall.owner.equals(LOADER)
                        || !instanceCall.name.equals("getInstance")
                        || instanceCall.getOpcode() != INVOKESTATIC) continue;
                method.instructions.set(query, new MethodInsnNode(INVOKESTATIC, HOOKS, hook,
                        query.desc, false));
                method.instructions.remove(resolverCall);
                method.instructions.remove(instanceCall);
                adaptations.add(node.name + "#" + method.name + " MappingResolver." + query.name + "=identity");
            }
        }
        // Lambdas whose only caller was an emptied entrypoint stage become unreachable before
        // the residue check runs, so no Loader type reaches the image through them.
        for (var method : node.methods) {
            if (deadLambdas.contains(method.name + method.desc)) stub(method);
        }
        // A query that survived both passes belongs to code the closed world cannot answer:
        // ModContainer metadata, entrypoint definitions, Loader update checks. The method keeps
        // its signature and answers with the type's empty value, which is what a build-time-only
        // helper would return anyway. Entrypoints are excluded: silently emptying one would
        // disable a Mod instead of reporting it.
        // A Mixin that patches a diagnostic class lands in the same class the report walks, and
        // its body reaches into the patching Mod. The report must still be able to describe a
        // failure even when that Mod is absent from the image, so injected members are emptied
        // unconditionally rather than only when they happen to call the Loader.
        if (DIAGNOSTIC_CLASSES.contains(node.name)) {
            for (var method : node.methods) {
                if (method.name.startsWith("<") || !method.name.startsWith("handler$")) continue;
                stub(method);
                adaptations.add(node.name + "#" + method.name
                        + " stubbed: Mixin-patched diagnostic class");
            }
        }
        for (var method : node.methods) {
            var offender = firstLoaderCall(method);
            if (offender == null) continue;
            String where = node.name + "#" + method.name;
            if (protectedMethods.contains(node.name + "#" + method.name)) {
                throw new IllegalArgumentException("Entrypoint cannot be lowered " + where
                        + " -> " + offender.owner + "." + offender.name + offender.desc);
            }
            if (DIAGNOSTIC_CLASSES.contains(node.name) && !method.name.startsWith("<")) {
                // Fabric's own client patch lists loaded mods in the crash report. The image has
                // no Loader and no mod containers, and the report is diagnostic only, so each
                // member of the report class, including the Mixin-generated lambdas behind it,
                // becomes a no-op instead of dragging the Loader into the closure.
                stub(method);
                adaptations.add(where + " stubbed: " + offender.owner + "." + offender.name
                        + " reports mod metadata only");
                continue;
            }
            stub(method);
            stubbed.add(where + " -> " + offender.owner + "." + offender.name);
        }
    }

    /**
     * Adjacent real instruction. Mixin-injected code carries line numbers, labels and frames
     * between the operations themselves, so {@code getNext()} often lands on a pseudo node.
     */
    private static org.objectweb.asm.tree.AbstractInsnNode nextReal(
            org.objectweb.asm.tree.AbstractInsnNode node) {
        var next = node.getNext();
        while (next != null && next.getOpcode() < 0) next = next.getNext();
        return next;
    }

    private static org.objectweb.asm.tree.AbstractInsnNode previousReal(
            org.objectweb.asm.tree.AbstractInsnNode node) {
        var previous = node.getPrevious();
        while (previous != null && previous.getOpcode() < 0) previous = previous.getPrevious();
        return previous;
    }

    /**
     * Removes the callbacks that consumed a value which is now a constant empty collection, and
     * marks their lambda bodies as dead so the residue check never sees the Loader types inside
     * them. A mapping callback is deleted outright because an empty Optional maps to itself.
     */
    private static void dropConsumers(org.objectweb.asm.tree.InsnList instructions,
            org.objectweb.asm.tree.AbstractInsnNode value, String owner, Set<String> dead) {
        while (true) {
            var consumer = nextReal(value);
            var call = consumer == null ? null : nextReal(consumer);
            if (!(consumer instanceof InvokeDynamicInsnNode factory)
                    || !(call instanceof MethodInsnNode iteration)) return;
            if (!CONSUMERS.contains(iteration.name) && !MAPPERS.contains(iteration.name)) return;
            for (var argument : factory.bsmArgs) {
                if (argument instanceof Handle handle && handle.getOwner().equals(owner)) {
                    dead.add(handle.getName() + handle.getDesc());
                }
            }
            instructions.remove(consumer);
            if (CONSUMERS.contains(iteration.name)) instructions.set(call, new InsnNode(POP));
            else instructions.remove(call);
        }
    }

    private static MethodInsnNode firstLoaderCall(org.objectweb.asm.tree.MethodNode method) {
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.owner.startsWith("net/fabricmc/loader/")
                    && !isValueCall(call)) {
                return call;
            }
        }
        return null;
    }

    private static void stub(org.objectweb.asm.tree.MethodNode method) {
        method.instructions.clear();
        method.tryCatchBlocks.clear();
        method.localVariables = null;
        if (method.name.equals("<init>")) {
            // A constructor cannot RETURN before invoking its parent. An unsupported path must
            // fail explicitly, including when the constructor is reached after image analysis.
            method.instructions.add(new org.objectweb.asm.tree.TypeInsnNode(NEW, "java/lang/IllegalStateException"));
            method.instructions.add(new InsnNode(DUP));
            method.instructions.add(new LdcInsnNode("Unsupported closed-world constructor: " + method.desc));
            method.instructions.add(new MethodInsnNode(INVOKESPECIAL, "java/lang/IllegalStateException",
                    "<init>", "(Ljava/lang/String;)V", false));
            method.instructions.add(new InsnNode(ATHROW));
            method.maxStack = Math.max(method.maxStack, 3);
            return;
        }
        String result = method.desc.substring(method.desc.indexOf(')') + 1);
        switch (result) {
            case "V" -> method.instructions.add(new InsnNode(RETURN));
            case "Z", "B", "C", "S", "I" -> {
                method.instructions.add(new InsnNode(ICONST_0));
                method.instructions.add(new InsnNode(IRETURN));
            }
            case "J" -> {
                method.instructions.add(new InsnNode(LCONST_0));
                method.instructions.add(new InsnNode(LRETURN));
            }
            case "F" -> {
                method.instructions.add(new InsnNode(FCONST_0));
                method.instructions.add(new InsnNode(FRETURN));
            }
            case "D" -> {
                method.instructions.add(new InsnNode(DCONST_0));
                method.instructions.add(new InsnNode(DRETURN));
            }
            // An empty container keeps a caller that walks the answer working: a Mod that asks
            // for its own metadata list gets nothing to iterate instead of a null to dereference.
            case "Ljava/util/List;", "Ljava/util/Collection;", "Ljava/lang/Iterable;" -> {
                method.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/List",
                        "of", "()Ljava/util/List;", true));
                method.instructions.add(new InsnNode(ARETURN));
            }
            case "Ljava/util/Set;" -> {
                method.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/Set",
                        "of", "()Ljava/util/Set;", true));
                method.instructions.add(new InsnNode(ARETURN));
            }
            case "Ljava/util/Map;" -> {
                method.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/Map",
                        "of", "()Ljava/util/Map;", true));
                method.instructions.add(new InsnNode(ARETURN));
            }
            case "Ljava/util/Optional;" -> {
                method.instructions.add(new MethodInsnNode(INVOKESTATIC, "java/util/Optional",
                        "empty", "()Ljava/util/Optional;", false));
                method.instructions.add(new InsnNode(ARETURN));
            }
            case "Ljava/lang/String;" -> {
                method.instructions.add(new LdcInsnNode(""));
                method.instructions.add(new InsnNode(ARETURN));
            }
            default -> {
                method.instructions.add(new InsnNode(ACONST_NULL));
                method.instructions.add(new InsnNode(ARETURN));
            }
        }
    }

    /**
     * Matches {@code .getModContainer(id).orElseThrow(...).getMetadata().getVersion()
     * .getFriendlyString()} starting at the {@code getInstance} call, and returns the instructions
     * that the constant replaces. Anything shorter stays on the ordinary Optional path.
     */
    private static java.util.List<org.objectweb.asm.tree.AbstractInsnNode> versionChain(
            org.objectweb.asm.tree.InsnList instructions, org.objectweb.asm.tree.AbstractInsnNode instance) {
        var chain = new java.util.ArrayList<org.objectweb.asm.tree.AbstractInsnNode>();
        var cursor = nextReal(instance);
        if (!(cursor instanceof LdcInsnNode)) return null;
        chain.add(cursor);
        cursor = nextReal(cursor);
        if (!isQuery(cursor, "getModContainer", "(Ljava/lang/String;)Ljava/util/Optional;")) return null;
        chain.add(cursor);
        cursor = nextReal(cursor);
        if (cursor instanceof InvokeDynamicInsnNode) {
            chain.add(cursor);
            cursor = nextReal(cursor);
        }
        if (!(cursor instanceof MethodInsnNode optional) || !optional.owner.equals("java/util/Optional")
                || !(optional.name.equals("orElseThrow") || optional.name.equals("get"))) return null;
        chain.add(cursor);
        cursor = nextReal(cursor);
        if (cursor != null && cursor.getOpcode() == CHECKCAST) {
            chain.add(cursor);
            cursor = nextReal(cursor);
        }
        // A compiler may park the container in a local slot and read it back a few lines later.
        // That is still one straight-line read of the same value, so the slot is consumed here
        // and must not be read anywhere else in the method.
        int slot = -1;
        if (cursor instanceof org.objectweb.asm.tree.VarInsnNode store && store.getOpcode() == ASTORE) {
            slot = store.var;
            chain.add(store);
            cursor = nextReal(store);
            if (!(cursor instanceof org.objectweb.asm.tree.VarInsnNode load) || load.getOpcode() != ALOAD
                    || load.var != slot) return null;
            chain.add(cursor);
            cursor = nextReal(cursor);
            if (countReads(instructions, slot) != 1) return null;
        }
        for (String[] step : new String[][]{{"net/fabricmc/loader/api/ModContainer", "getMetadata"},
                {"net/fabricmc/loader/api/metadata/ModMetadata", "getVersion"},
                {"net/fabricmc/loader/api/Version", "getFriendlyString"}}) {
            if (!(cursor instanceof MethodInsnNode call) || !call.owner.equals(step[0])
                    || !call.name.equals(step[1])) return null;
            chain.add(cursor);
            cursor = nextReal(cursor);
        }
        return chain;
    }

    private static int countReads(org.objectweb.asm.tree.InsnList instructions, int slot) {
        int reads = 0;
        for (var node : instructions) {
            if (node instanceof org.objectweb.asm.tree.VarInsnNode var && var.var == slot
                    && var.getOpcode() >= ILOAD && var.getOpcode() <= ALOAD) {
                reads++;
            }
        }
        return reads;
    }

    private static boolean isQuery(org.objectweb.asm.tree.AbstractInsnNode instruction, String name, String descriptor) {
        return instruction instanceof MethodInsnNode call && call.owner.equals(LOADER)
                && call.name.equals(name) && call.desc.equals(descriptor) && call.getOpcode() == INVOKEINTERFACE;
    }

    /**
     * Replaces Sodium's run-time class generation with the layout-driven equivalent.
     *
     * <p>The registry answered {@code createSerializer(from, to)} by emitting and defining a class
     * per format pair. Both formats are available at run time, so the replacement builds the same
     * copy plan from their layouts; the factory and its value types then have no caller and are
     * dropped from the export instead of failing the build.
     */
    static void replaceGeneratedSerializer(ClassNode node, List<String> adaptations) {
        if (!node.name.equals(SODIUM_REGISTRY)) return;
        String descriptor = "(Lcom/mojang/blaze3d/vertex/VertexFormat;"
                + "Lcom/mojang/blaze3d/vertex/VertexFormat;)"
                + "Lnet/caffeinemc/mods/sodium/api/vertex/serializer/VertexSerializer;";
        for (var method : node.methods) {
            if (!method.name.equals("createSerializer") || !method.desc.equals(descriptor)) continue;
            method.instructions.clear();
            method.tryCatchBlocks.clear();
            method.localVariables = null;
            method.instructions.add(new org.objectweb.asm.tree.TypeInsnNode(NEW,
                    "mcfao/aot/GenericVertexSerializer"));
            method.instructions.add(new InsnNode(DUP));
            method.instructions.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
            method.instructions.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 1));
            method.instructions.add(new MethodInsnNode(INVOKESPECIAL,
                    "mcfao/aot/GenericVertexSerializer", "<init>",
                    "(Lcom/mojang/blaze3d/vertex/VertexFormat;Lcom/mojang/blaze3d/vertex/VertexFormat;)V",
                    false));
            method.instructions.add(new InsnNode(ARETURN));
            method.maxStack = 4;
            method.maxLocals = 2;
            adaptations.add(node.name + "#createSerializer() = layout-driven copy plan,"
                    + " no generated class");
            return;
        }
        throw new IllegalArgumentException("Sodium serializer registry no longer has the expected"
                + " createSerializer method: " + node.name);
    }

    /**
     * Prints a failure's own stack before the crash report is assembled.
     *
     * <p>Every fatal path funnels through {@code CrashReport.forThrowable}. Assembling the report
     * touches the system report and the client, which on this target means oshi, a Mixin-patched
     * world and code the closed image may not contain. When assembly fails it throws a second
     * error and the first one is never printed, so the only visible symptom is a report-path
     * failure that hides the real cause. Printing first costs one stack trace on a path that only
     * runs when the game is already failing.
     */
    static void printBeforeReport(ClassNode node, List<String> adaptations) {
        if (!node.name.equals("net/minecraft/CrashReport")) return;
        String descriptor = "(Ljava/lang/Throwable;Ljava/lang/String;)Lnet/minecraft/CrashReport;";
        for (var method : node.methods) {
            if (!method.name.equals("forThrowable") || !method.desc.equals(descriptor)) continue;
            var list = new org.objectweb.asm.tree.InsnList();
            list.add(new org.objectweb.asm.tree.VarInsnNode(ALOAD, 0));
            list.add(new MethodInsnNode(INVOKEVIRTUAL, "java/lang/Throwable", "printStackTrace", "()V", false));
            method.instructions.insert(list);
            method.maxStack = Math.max(method.maxStack, 1);
            adaptations.add(node.name + "#forThrowable prints the original stack before building"
                    + " the report");
            return;
        }
    }

    /**
     * Replaces GlitchCore's run-time event-type reflection with a build-time Class literal.
     *
     * <p>{@code EventManager.addListener(Consumer)} asks typetools' TypeResolver for the
     * {@code Consumer<T>} type argument of the consumer's class. The four BiomesOPlenty listeners
     * are hidden lambda classes and one more is a named Consumer; neither keeps a usable generic
     * signature inside a Native Image, so the bus throws "Failed to resolve consumer event type"
     * before any listener is registered. The lambda bootstrap already names the event in its
     * instantiated method type, and a named Consumer declares it in its class Signature.
     *
     * <p>A new {@code addListenerResolved(Consumer, Class)} keeps the original registration body
     * byte for byte - the original stored the resolved Class in local slot 1, which is exactly
     * where the new second parameter lives - and every call site pushes its Class literal. No
     * listener, event or registration ordering is skipped or stubbed.
     */
    static void lowerGlitchCoreEvents(ClassNode node, String sourceHash,
            List<String> adaptations) {
        if (node.name.equals(GLITCHCORE_MANAGER)) {
            if (!Set.of(GLITCHCORE_MANAGER_SHA256,
                    "e7fdef73b3935532e931fc48c452c7e1b5406bc6c7673dbf204c837fd08e1dc9").contains(sourceHash)) {
                throw new IllegalArgumentException("Unaudited GlitchCore EventManager: " + sourceHash);
            }
            MethodNode original = node.methods.stream()
                    .filter(method -> method.name.equals("addListener")
                            && method.desc.equals(LISTENER_DESC))
                    .findFirst().orElseThrow(() -> new IllegalArgumentException(
                            "GlitchCore EventManager has no addListener(Consumer)"));
            var resolved = new MethodNode(ACC_PUBLIC | ACC_STATIC, RESOLVED_LISTENER,
                    RESOLVED_LISTENER_DESC, null, null);
            original.accept(resolved);
            var load = real(resolved.instructions.getFirst());
            var lookup = load == null ? null : real(load.getNext());
            var store = lookup == null ? null : real(lookup.getNext());
            if (!(load instanceof VarInsnNode first) || first.getOpcode() != ALOAD || first.var != 0
                    || !(lookup instanceof MethodInsnNode getter)
                    || !getter.name.equals("getEventClass") || !getter.owner.equals(GLITCHCORE_MANAGER)
                    || !(store instanceof VarInsnNode third) || third.getOpcode() != ASTORE
                    || third.var != 1) {
                throw new IllegalArgumentException("Unexpected GlitchCore addListener prologue");
            }
            resolved.instructions.remove(load);
            resolved.instructions.remove(lookup);
            resolved.instructions.remove(store);
            // Debug local variable tables can name the removed generic TT; they carry no runtime
            // meaning. Frames, try/catch ranges and maxs stay valid: slot 1 remains a Class.
            resolved.localVariables.clear();
            resolved.signature = null;
            node.methods.add(resolved);
            adaptations.add(node.name + "#" + RESOLVED_LISTENER
                    + " event Class supplied by build-time call sites");
            return;
        }
        for (var method : node.methods) {
            int originalMaxStack = method.maxStack;
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode call) || call.getOpcode() != INVOKESTATIC
                        || !call.owner.equals(GLITCHCORE_MANAGER) || !call.name.equals("addListener")
                        || !call.desc.equals(LISTENER_DESC)) continue;
                var producer = previousReal(call);
                String event = null;
                if (producer instanceof InvokeDynamicInsnNode lambda) {
                    event = lambdaEventType(lambda);
                } else if (producer instanceof VarInsnNode load && load.getOpcode() == ALOAD
                        && load.var == 0 && (method.access & ACC_STATIC) == 0
                        && node.name.equals(REGISTRY_HELPER)) {
                    if (!REGISTRY_HELPER_SHA256.equals(sourceHash)) {
                        throw new IllegalArgumentException("Unaudited GlitchCore RegistryHelper: " + sourceHash);
                    }
                    event = namedConsumerEventType(node);
                }
                if (event == null) throw new IllegalArgumentException(
                        "Unresolved GlitchCore listener in " + node.name + "#" + method.name
                                + " (consumer from " + (producer == null ? "nothing" : producer.getClass().getSimpleName())
                                + ")");
                method.instructions.insertBefore(call, new LdcInsnNode(Type.getObjectType(event)));
                call.name = RESOLVED_LISTENER;
                call.desc = RESOLVED_LISTENER_DESC;
                // The literal Class sits on the stack beside the consumer. One extra slot is
                // enough for every site in this method; without it a straight-line listener
                // registrar (maxStack 1) fails verification inside the image.
                method.maxStack = Math.max(method.maxStack, originalMaxStack + 1);
                adaptations.add(node.name + "#" + method.name + " GlitchCore event=" + event);
            }
        }
    }

    private static org.objectweb.asm.tree.AbstractInsnNode real(
            org.objectweb.asm.tree.AbstractInsnNode node) {
        var current = node;
        while (current != null && current.getOpcode() < 0) current = current.getNext();
        return current;
    }

    /** The instantiated SAM type of a LambdaMetafactory call is exactly {@code (TEvent;)V}. */
    private static String lambdaEventType(InvokeDynamicInsnNode lambda) {
        if (lambda.bsm == null || !lambda.bsm.getOwner().equals("java/lang/invoke/LambdaMetafactory")
                || !lambda.bsm.getName().equals("metafactory") || lambda.bsmArgs.length < 3
                || !(lambda.bsmArgs[2] instanceof Type instantiated)
                || !Type.getReturnType(lambda.desc).equals(Type.getType("Ljava/util/function/Consumer;"))) {
            return null;
        }
        var arguments = instantiated.getArgumentTypes();
        if (arguments.length != 1 || arguments[0].getSort() != Type.OBJECT
                || instantiated.getReturnType().getSort() != Type.VOID) return null;
        String event = arguments[0].getInternalName();
        return glitchCoreEvent(event) ? event : null;
    }

    /** A named Consumer declares its event in the class Signature, not in a hidden lambda. */
    private static String namedConsumerEventType(ClassNode node) {
        String signature = node.signature;
        if (signature == null) return null;
        String marker = "Ljava/util/function/Consumer<L";
        int start = signature.indexOf(marker);
        if (start < 0) return null;
        int end = signature.indexOf(';', start + marker.length());
        if (end < 0) return null;
        String event = signature.substring(start + marker.length(), end);
        return glitchCoreEvent(event) && event.indexOf('<') < 0 ? event : null;
    }

    private static boolean glitchCoreEvent(String internalName) {
        if (!internalName.startsWith("glitchcore/event/")) return false;
        // RegisterColorsEvent.Block is a nested event class, not a generated lambda name.
        return internalName.indexOf('$') < 0
                || internalName.startsWith("glitchcore/event/client/RegisterColorsEvent$");
    }

    static void removeUnusedEventProxy(String mod, String sourceHash, ClassNode node, List<String> adaptations) {
        if (!mod.equals("fabric-api-base") || !node.name.equals(EVENTS) || !sourceHash.equals(EVENTS_SHA256)) return;
        // This exact upstream class has no references to the private proxy helper.
        // Retain createArrayBacked and its normal invoker factory unchanged.
        int count = node.methods.size();
        node.methods.removeIf(method -> (method.access & ACC_PRIVATE) != 0
                && (method.name.equals("buildEmptyInvoker") || method.name.equals("lambda$buildEmptyInvoker$0")));
        if (count - node.methods.size() != 2) throw new IllegalStateException("Unexpected Fabric API event factory");
        adaptations.add(node.name + " removed two unused private dynamic-proxy methods");
    }
}
