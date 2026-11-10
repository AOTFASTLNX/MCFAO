package mcfao.build;

import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
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
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Label;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
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
    private static final String WRAP_OPERATION = "com/llamalad7/mixinextras/injector/wrapoperation/";

    private record Metadata(String path, String id, String version, boolean client,
            Map<String, ?> entrypoints, List<?> dependencies, List<String> jars,
            List<String> mixins, String classTweaker) {}
    private record Entry(String mod, String stage, String definition, String type, String method,
            String refOwner, String refName, boolean refStatic) {}

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
        var loadedIds = new TreeSet<String>();
        for (var mod : loader.getModsInternal()) {
            loadedIds.add(mod.getMetadata().getId());
            loadedIds.addAll(mod.getMetadata().getProvides());
        }
        var entries = new ArrayList<Entry>();
        collect(entries, requested, loader, target, transform, delegate, "main", ModInitializer.class, "onInitialize");
        collect(entries, requested, loader, target, transform, delegate, "client", ClientModInitializer.class,
                "onInitializeClient");

        var resources = new TreeSet<String>();
        var modClasses = new TreeSet<String>();
        var names = new TreeSet<String>();
        var changes = new TreeMap<String, Object>();
        var selected = new ArrayList<Map<String, String>>();
        var adaptations = new ArrayList<String>();
        var accessorInterfaces = new TreeSet<String>();
        int hooks = 0;
        try (var base = new ZipFile(client.toFile());
             var jar = new ZipOutputStream(Files.newOutputStream(output.resolve("overlay.jar")))) {
            for (var original : base.stream().filter(e -> e.getName().endsWith(".class")).toList()) {
                String path = original.getName();
                byte[] before;
                try (var input = base.getInputStream(original)) {
                    before = input.readAllBytes();
                }
                byte[] after = transform(transform, delegate, path);
                if (Arrays.equals(before, after)) continue;
                ClassNode node = parse(after);
                int rewritten = redirectHooks(node);
                hooks += rewritten;
                RuntimeLowering.lowerQueries(node, loadedIds, adaptations);
                after = classBytes(node);
                verify(node);
                put(jar, names, path, after);
                changes.put(path, Map.of("originalSHA256", hash(before), "transformedSHA256", hash(after),
                        "loaderHookCalls", rewritten));
            }
            if (hooks != 1) throw new IllegalStateException("Expected exactly one Fabric client hook, got " + hooks);
            for (var mod : loader.getModsInternal()) {
                String id = mod.getMetadata().getId();
                if (!requested.contains(id)) continue;
                selected.add(Map.of("id", id, "version", mod.getMetadata().getVersion().getFriendlyString()));
                for (Path root : mod.getRootPaths()) {
                    var mixinPackages = new ArrayList<String>();
                    for (String config : mod.getMetadata().getMixinConfigs(EnvType.CLIENT)) {
                        try (var reader = Files.newBufferedReader(root.resolve(config))) {
                            String pkg = JSON.fromJson(reader, JsonObject.class).get("package").getAsString();
                            mixinPackages.add(pkg.replace('.', '/') + "/");
                        }
                    }
                    try (var paths = Files.walk(root)) {
                        for (Path path : paths.filter(Files::isRegularFile).sorted().toList()) {
                            String name = root.relativize(path).toString();
                            if (name.endsWith(".class")) {
                                if (name.endsWith("/package-info.class")) continue;
                                boolean mixinPackage = mixinPackages.stream().anyMatch(name::startsWith);
                                if (mixinPackage && !RuntimeLowering.isAccessorInterface(parse(Files.readAllBytes(path)))) {
                                    continue;
                                }
                                if (base.getEntry(name) != null) throw new IllegalArgumentException("Mod shadows Minecraft: " + name);
                                byte[] data = transform(transform, delegate, name);
                                ClassNode node = parse(data);
                                if (!name.equals(node.name + ".class")) {
                                    throw new IllegalArgumentException("Invalid class path in " + id + ": " + name);
                                }
                                int previousAdaptations = adaptations.size();
                                RuntimeLowering.lowerQueries(node, loadedIds, adaptations);
                                if (id.equals("fabric-api-base") && node.name.endsWith("/EventFactoryImpl")) {
                                    RuntimeLowering.removeUnusedEventProxy(id, hash(Files.readAllBytes(path)), node, adaptations);
                                }
                                validateModCode(id, node);
                                verify(node);
                                put(jar, names, name, adaptations.size() == previousAdaptations ? data : classBytes(node));
                                if (mixinPackage) accessorInterfaces.add(node.name);
                                modClasses.add(node.name.replace('/', '.'));
                            } else if (name.startsWith("assets/") || name.startsWith("data/")) {
                                if (base.getEntry(name) != null) throw new IllegalArgumentException("Mod resource collides with Minecraft: " + name);
                                put(jar, names, name, Files.readAllBytes(path));
                                resources.add(name);
                            }
                        }
                    }
                }
            }
            if (selected.isEmpty()) throw new IllegalArgumentException("No client mods resolved by Fabric Loader");
            for (Class<?> api : List.of(ModInitializer.class, ClientModInitializer.class, EnvType.class,
                    CallbackInfo.class, CallbackInfoReturnable.class, Cancellable.class,
                    CancellationException.class)) {
                String name = api.getName().replace('.', '/') + ".class";
                try (var resource = api.getResourceAsStream("/" + name)) {
                    put(jar, names, name, resource.readAllBytes());
                }
            }
            for (String type : List.of("Operation", "WrapOperationRuntime", "IncorrectArgumentCountException")) {
                String name = WRAP_OPERATION + type + ".class";
                try (var resource = target.getResourceAsStream(name)) {
                    if (resource == null) throw new IllegalStateException("Pinned MixinExtras runtime class missing: " + name);
                    put(jar, names, name, resource.readAllBytes());
                }
            }
            put(jar, names, STATIC_HOOKS + ".class", staticHooks(entries));
            modClasses.add(STATIC_HOOKS.replace('/', '.'));
            put(jar, names, METADATA + "native-image.properties",
                    utf8("Args = --initialize-at-run-time=" + String.join(",", modClasses) + "\n"));
            put(jar, names, METADATA + "reachability-metadata.json", utf8(JSON.toJson(
                    Map.of("resources", resources.stream().map(name -> Map.of("glob", name)).toList()))));
        }
        Files.writeString(output.resolve("transform.json"), JSON.toJson(Map.of(
                "loader", FabricLoaderImpl.VERSION, "namespace", "official", "resolvedMods", selected,
                "entrypoints", entries, "gameTransforms", changes, "resources", resources,
                "runtimeInitializedClasses", modClasses, "staticAdaptations", adaptations,
                "accessorInterfaces", accessorInterfaces)));
        System.out.println("MCFAO_FABRIC_EXPORT_PASS");
    }

    private static <T> void collect(List<Entry> entries, Set<String> requested, FabricLoaderImpl loader,
            ClassLoader target, Method transformMethod, Object delegate, String stage, Class<T> type,
            String method) throws Exception {
        for (var container : loader.getEntrypointContainers(stage, type)) {
            String id = container.getProvider().getMetadata().getId();
            if (!requested.contains(id)) {
                throw new IllegalArgumentException("Unaccounted Fabric entrypoint: " + id + "/" + stage);
            }
            String definition = container.getDefinition();
            int separator = definition.indexOf("::");
            if (separator < 0) {
                // Non-initializing verification. Fabric's class-form default adapter uses a no-arg constructor.
                Class<?> entry = Class.forName(definition, false, target);
                if (!type.isAssignableFrom(entry) || java.lang.reflect.Modifier.isAbstract(entry.getModifiers())
                        || !java.lang.reflect.Modifier.isPublic(entry.getModifiers())) {
                    throw new IllegalArgumentException("Unsupported " + id + " entrypoint " + definition);
                }
                entry.getConstructor();
                entries.add(new Entry(id, stage, definition, type.getName().replace('.', '/'), method,
                        null, null, false));
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
                    owner, refName, isStatic));
        }
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

    private static void verify(ClassNode node) throws Exception {
        for (var method : node.methods) {
            try {
                new Analyzer<>(new BasicVerifier()).analyze(node.name, method);
            } catch (Exception error) {
                throw new IllegalArgumentException("Bytecode verification failed: " + node.name + "." + method.name, error);
            }
        }
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
        if (!name.matches("[A-Za-z_$][A-Za-z0-9_$]*(/[A-Za-z_$][A-Za-z0-9_$]*)*")) {
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
                boolean usesRuntimeLoader = call.owner.startsWith("net/fabricmc/loader/")
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

    private static byte[] staticHooks(List<Entry> entries) {
        var writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES);
        writer.visit(V25, ACC_PUBLIC | ACC_FINAL, STATIC_HOOKS, null, "java/lang/Object", null);
        var start = writer.visitMethod(ACC_PUBLIC | ACC_STATIC, "startClient", "(Ljava/io/File;Ljava/lang/Object;)V", null, null);
        start.visitCode();
        for (Entry entry : entries) {
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
                continue;
            }
            String owner = entry.definition().replace('.', '/');
            start.visitTypeInsn(NEW, owner);
            start.visitInsn(DUP);
            start.visitMethodInsn(INVOKESPECIAL, owner, "<init>", "()V", false);
            start.visitMethodInsn(INVOKEINTERFACE, entry.type(), entry.method(), "()V", true);
        }
        start.visitInsn(RETURN);
        start.visitMaxs(0, 0);
        start.visitEnd();
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
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static byte[] utf8(String text) {
        return text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    private static String hash(byte[] data) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
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
