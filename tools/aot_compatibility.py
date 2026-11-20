"""Static facts from the exact Native Image classpath, without loading Mod classes."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct
import time
from uuid import uuid4
import zipfile

from capture import redact_log
from bootstrap_toolchain import sha256
from config_reflection import class_shape, reflection_from_jar
from mod_file_policy import is_metadata

METAL_PREFIX = "fabricaot/metal/"
RENDER_PIPELINES = "net/minecraft/client/renderer/RenderPipelines"
FABRIC_DISPATCH = "mcfao/aot/Entrypoints"
PLATFORM_TYPES = ("java/", "javax/", "jdk/", "sun/", "com/sun/", "org/w3c/", "org/xml/", "org/ietf/")
MEMBER_TYPES = re.compile(r"L([^;<:]+)(?=[;<])")
GL_AFTER_41 = re.compile(r"org/lwjgl/opengl/GL4[2-6]C?$")
ISSUE_LIMIT = 160
STATIC = 0x0008
PRIVATE = 0x0002
PUBLIC = 0x0001
ABSTRACT = 0x0400
INTERFACE = 0x0200
SERVICE_PREFIX = "META-INF/services/"
REMEDIES = {
    "MISSING_TYPE": "Check the Fabric dependency graph, side filtering and the transformed classpath.",
    "MISSING_REQUIRED_TYPE": "Restore the required class or superclass in the selected client dependencies.",
    "MISSING_METHOD": "Check the dependency version, mapping namespace and transformed method descriptor.",
    "MISSING_FIELD": "Check the dependency version, mapping namespace and transformed field descriptor.",
    "METAL_REFERENCE_ON_GL41": "Regenerate the Fabric export and graphics patch for GL41.",
    "METAL_CLASS_ON_GL41": "Remove the native Metal backend input from the GL41 profile.",
    "DESKTOP_IMAGE_IOS_UNSUPPORTED": "Check whether this call runs on iOS; port it to NativeImage or use an iOS-compatible alternative.",
    "REFLECTION_METADATA_UNRESOLVED": "Check the member signature against the selected class and trace this path if needed.",
}


def type_names(value):
    return MEMBER_TYPES.findall(value) if value.startswith("[") else [value]


def issue(code, severity, target, location=None, count=1, **details):
    if code in REMEDIES:
        details.setdefault("suggestion", REMEDIES[code])
    return dict(code=code, severity=severity, target=redact_log(target),
                location=redact_log(location) if location else None, count=count, **details)


def summarise(report, findings):
    counts = Counter()
    for row in findings:
        counts[row["severity"]] += row.get("count", 1)
    priority = {"blocker": 0, "fix": 1, "warning": 2}
    return {**report, "blockers": counts["blocker"], "warnings": counts["warning"],
            "fixes": counts["fix"], "findings": sorted(findings, key=lambda row: (
                priority[row["severity"]], row["code"], row["target"], row.get("location") or ""
            ))[:ISSUE_LIMIT], "findingGroups": len(findings)}


def add_bytecode_results(report, findings, counters, categories):
    current = summarise(report, [*report["findings"], *findings])
    added = summarise({}, findings)
    for key in ("blockers", "warnings", "fixes", "findingGroups"):
        current[key] = report[key] + added[key]
    current["stages"] = {**report["stages"], "static": "FAIL" if current["blockers"] else "PASS"}
    current["graph"] = counters
    current["metadataFiles"] = sorted(categories)
    return current


def publish(path, report):
    if path is None:
        return
    pending = path.with_name(f".{path.name}.{uuid4().hex}")
    pending.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    pending.replace(path)


def transform_report(record):
    transform = record.get("transform", {})
    resolved = record.get("resolution", {})
    findings = []
    if resolved.get("status") == "UNSATISFIED":
        findings.append(issue("FABRIC_DEPENDENCIES", "blocker", resolved["reason"]))
    if record.get("error") and not findings:
        findings.append(issue("FABRIC_TRANSFORMATION", "blocker", record["error"]))
    for mod, reasons in record.get("excludedMods", {}).items():
        findings.extend(issue("FABRIC_TRANSFORMATION", "blocker", reason, mod) for reason in reasons)
    for field, code in (
            ("mixinTargetsAbsent", "MIXIN_TARGET_UNAVAILABLE"),
            ("mixinAccessorsRefused", "MIXIN_ACCESSOR_UNVERIFIED"),
            ("extrasAbsent", "MIXIN_HELPER_UNAVAILABLE"),
            ("syntheticAbsent", "GENERATED_CLASS_UNAVAILABLE"),
            ("ambiguousLiteralResources", "RESOURCE_AMBIGUOUS"),
            ("stubbedMethods", "FABRIC_RUNTIME_RESIDUE")):
        findings.extend(issue(code, "warning", value) for value in transform.get(field, ()))
    findings.extend(issue("BYTECODE_ADAPTATION", "fix", value)
                    for value in transform.get("staticAdaptations", ()))
    findings.extend(issue("RESOURCE_RETAINED", "fix", value)
                    for value in transform.get("retainedLiteralResources", ()))
    completed = record.get("status") == "FABRIC_AOT_INPUT_PREPARED"
    failed = bool(record.get("error")) or any(row["severity"] == "blocker" for row in findings)
    mods = transform.get("resolvedMods", record.get("mods", ()))
    mod_count = len({mod["id"] for mod in mods if mod.get("client", True)})
    return summarise(dict(
        schemaVersion=1, renderer=record.get("renderer"), modCount=mod_count,
        stages=dict(static="FAIL" if failed else "UNVERIFIED",
                    transform="FAIL" if failed else "PASS" if completed else "SKIPPED",
                    aot="SKIPPED", startup="UNVERIFIED", device="UNVERIFIED"),
    ), findings)


def scan_archive(archive):
    entries = [name for name in archive.namelist() if not is_metadata(name)]
    manifest_entry = "META-INF/MANIFEST.MF"
    multi_release = False
    if manifest_entry in entries:
        manifest = archive.read(manifest_entry).replace(b"\r\n", b"\n").split(b"\n\n", 1)[0]
        multi_release = bool(re.search(rb"(?im)^Multi-Release:[ \t]*true[ \t]*$", manifest))
    resources = set(entries)
    selected = {}
    for name in entries:
        logical = name
        version = 0
        if name.startswith("META-INF/versions/"):
            pieces = name.split("/", 3)
            if (not multi_release or len(pieces) != 4 or not pieces[2].isdecimal()
                    or not 9 <= int(pieces[2]) <= 25):
                continue
            version, logical = int(pieces[2]), pieces[3]
            resources.add(logical)
        if (logical.endswith(".class") and logical != "module-info.class"
                and not logical.startswith(("META-INF/", "mcfao/mod-files/"))):
            internal = logical[:-6]
            if internal not in selected or version > selected[internal][0]:
                selected[internal] = version, name
    services = [name for name in entries if name.startswith(SERVICE_PREFIX) and not name.endswith("/")]
    return selected, resources, services


class Classpath:
    """First-definition-wins classpath and JDK index. Class bodies are read lazily."""
    def __init__(self, stack, paths, java_home):
        self.classes = {}
        self.resources = set()
        self.shapes = {}
        self.jdk = {}
        self.services = []
        if java_home:
            for path in sorted((java_home / "jmods").glob("*.jmod")):
                if is_metadata(path.name):
                    continue
                archive = stack.enter_context(zipfile.ZipFile(path))
                self.jdk.update((name[8:-6], (archive, name)) for name in archive.namelist()
                                if name.startswith("classes/") and name.endswith(".class"))
        archives = [stack.enter_context(zipfile.ZipFile(path)) for path in paths]
        # Inspect archives independently, then merge in classpath order to preserve shadowing.
        with ThreadPoolExecutor(max_workers=4) as executor:
            for archive, (selected, resources, services) in zip(archives, executor.map(scan_archive, archives)):
                self.resources.update(resources)
                self.services.extend((archive, name) for name in services)
                for internal, (_, name) in selected.items():
                    self.classes.setdefault(internal, (archive, name))

    def has_type(self, name):
        return name in self.classes or name in self.jdk or (
            not self.jdk and name.startswith(PLATFORM_TYPES))

    def shape(self, name):
        source = self.jdk.get(name) or self.classes.get(name)
        if source and name not in self.shapes:
            self.shapes[name] = self.read_shape(source, declarations_only=True)
        return self.shapes.get(name)

    @staticmethod
    def read_shape(source, **options):
        archive, entry = source
        try:
            return class_shape(archive.read(entry), **options)
        except (ValueError, IndexError, struct.error, StopIteration) as error:
            raise ValueError(f"Invalid classfile {archive.filename}!{entry}: {error}") from error

    def resolve_member(self, owner, name, descriptor, field):
        """Return a declaration, False for known absence, or None for an opaque hierarchy."""
        visited = set()

        def resolve(current, inherited=False):
            if not current or current in visited:
                return False
            visited.add(current)
            shape = self.shape(current)
            if shape is None:
                return False if name == "<init>" and inherited else None
            flags = (shape["fieldFlags"].get((name, descriptor)) if field
                     else shape["methodFlags"].get(name + descriptor))
            if (flags is not None and not (
                    inherited and not field and shape["access"] & INTERFACE and flags & (STATIC | PRIVATE))):
                return current, flags
            if name == "<init>":
                return False
            # The JVMS searches interfaces before the superclass for fields, and the superclass
            # before interfaces for methods. Object methods may also resolve on an interface.
            parents = [*shape["interfaces"], shape["parent"]] if field else [
                shape["parent"], *shape["interfaces"]]
            opaque = False
            for parent in parents:
                declaration = resolve(parent, inherited=True)
                if declaration:
                    return None if opaque else declaration
                opaque |= declaration is None
            return None if opaque else False

        return resolve(owner)


def member_failure(classpath, resolve_member, caller, opcode, reference):
    tag, owner, name, descriptor = reference
    if owner.startswith("["):  # The VM supplies array.clone.
        return None
    owner_shape = classpath.shape(owner)
    if owner_shape is None:
        return None if classpath.has_type(owner) else "MISSING_TYPE"
    if owner in ("java/lang/invoke/MethodHandle", "java/lang/invoke/VarHandle") and any(
            key.startswith(name + "(") and flags & 0x0180 == 0x0180
            for key, flags in owner_shape["methodFlags"].items()):
        return None  # Signature-polymorphic descriptors are specialized at each call site.
    if tag != 9 and bool(owner_shape["access"] & INTERFACE) != (tag == 11):
        return "INCOMPATIBLE_MEMBER_OWNER"
    result = resolve_member(owner, name, descriptor, tag == 9)
    if result is None:
        return None
    if result is False:
        if owner.startswith("org/lwjgl/"):
            return "LWJGL_MEMBER_MISSING"
        return "MISSING_FIELD" if tag == 9 else "MISSING_METHOD"
    declaring, flags = result
    if bool(flags & STATIC) != (opcode in (0xb2, 0xb3, 0xb8)):
        return "INCOMPATIBLE_MEMBER_KIND"
    if opcode == 0xb7 and flags & ABSTRACT:
        return "ABSTRACT_SPECIAL_TARGET"
    if flags & PRIVATE and classpath.shape(declaring)["nestHost"] != classpath.shape(caller)["nestHost"]:
        return "ILLEGAL_PRIVATE_ACCESS"
    return None


HANDLE_OPCODES = (None, 0xb4, 0xb2, 0xb5, 0xb3, 0xb6, 0xb8, 0xb7, 0xb7, 0xb9)


def symbolic_operands(opcode, operand):
    tag = operand[0]
    if tag == 15:
        yield HANDLE_OPCODES[operand[1]], operand[2]
    elif tag in (17, 18):
        yield opcode, (16, operand[1])
        for argument in operand[2]:
            yield from symbolic_operands(opcode, argument)
    else:
        yield opcode, operand


def bytecode_report(client, libraries, renderer, *, java_home=None, required=(), entrypoint=None,
                    fabric_entries=()):
    """Collect symbolic references and check hard roots plus backend invariants.

    Symbols in optional branches can be absent legitimately. Their presence in a classfile
    provides a diagnostic, while the inheritance chain of a required root is mandatory.
    """
    findings = []
    grouped = {}
    counters = Counter()
    static_resources = set()
    with ExitStack() as stack:
        classpath = Classpath(stack, libraries, java_home)
        resolve_member = lru_cache(maxsize=131072)(classpath.resolve_member)
        original = client.resolve()
        archive_paths = {archive: Path(archive.filename).resolve()
                         for archive, _ in classpath.classes.values()}

        def add(code, severity, target, location, source=None):
            key = (code, severity, target)
            if key not in grouped:
                grouped[key] = issue(code, severity, target, location, count=0,
                                     stage="final-classpath", renderer=renderer,
                                     **({"archive": Path(source.filename).name} if source else {}))
            grouped[key]["count"] += 1

        def inspect(shape):
            internal = shape["name"]
            source, _ = classpath.classes[internal]
            counters["classes"] += 1
            counters["methods"] += len(shape["methods"])
            counters["constructors"] += len(shape["constructors"])
            counters["fields"] += len(shape["fields"])
            counters["classInitializers"] += "<clinit>" in shape["methods"]
            symbols = shape["memberReferences"]
            types = {name for value in shape["classReferences"] for name in type_names(value)}
            for owner, _, descriptor in symbols:
                types.update(type_names(owner))
                types.update(MEMBER_TYPES.findall(descriptor))
            for declaration in shape["declaredFields"] + shape["methodSignatures"]:
                types.update(MEMBER_TYPES.findall(declaration[declaration.find("("):]
                                                  if "(" in declaration else declaration))
            counters["typeEdges"] += len(types - {internal})
            mod_code = not internal.startswith(("net/minecraft/", "com/mojang/", "org/lwjgl/"))
            if mod_code:
                for native in shape["nativeMethods"]:
                    add("MOD_NATIVE_METHOD", "warning", internal + "#" + native, internal)
            for method, operations in shape["bytecode"]:
                previous = receiver = None
                location = internal + "#" + method
                split_initializer = method.startswith("fabricaot$init$clinit$")
                counters["splitInitializers"] += split_initializer
                dispatch = (internal == FABRIC_DISPATCH
                            and method == "startClient(Ljava/io/File;Ljava/lang/Object;)V")
                mandatory = (internal == entrypoint and method in ("<clinit>()V", "main([Ljava/lang/String;)V")
                             and method not in shape["handledMethods"])
                for opcode, operand in operations:
                    if 0x99 <= opcode <= 0xab or 0xac <= opcode <= 0xb1 or opcode in (
                            0xbf, 0xc6, 0xc7, 0xc8, 0xc9):
                        mandatory = False
                    severity = "blocker" if (mandatory or dispatch) else "warning"
                    if not isinstance(operand, tuple):
                        receiver, previous = previous, operand
                        continue
                    for instruction, symbol in symbolic_operands(opcode, operand):
                        tag = symbol[0]
                        if tag == 7:
                            referenced = type_names(symbol[1])
                        elif tag == 16:
                            referenced = MEMBER_TYPES.findall(symbol[1])
                        elif tag in (9, 10, 11):
                            referenced = type_names(symbol[1]) + MEMBER_TYPES.findall(symbol[3])
                        else:
                            continue
                        for name in referenced:
                            types.discard(name)
                            if renderer == "gl41" and name.startswith(METAL_PREFIX):
                                add("METAL_REFERENCE_ON_GL41", "blocker", name, location, source)
                            elif not classpath.has_type(name):
                                # Descriptors may name a type the VM can resolve later. Only an
                                # unavoidable instruction that names the actual owner is hard.
                                hard = tag in (7, 9, 10, 11) and symbol[1] == name
                                add("MISSING_TYPE", severity if hard else "warning", name, location, source)
                        if tag not in (9, 10, 11):
                            continue
                        failure = member_failure(classpath, resolve_member, internal, instruction, symbol)
                        if failure and failure != "MISSING_TYPE":
                            _, owner, name, descriptor = symbol
                            add(failure, severity, f"{owner}.{name}{descriptor}", location, source)
                    if operand[0] in (9, 10, 11):
                        tag, owner, name, descriptor = operand
                        counters["fieldEdges" if tag == 9 else "callEdges"] += 1
                        if name == "<init>":
                            counters["constructorEdges"] += 1
                        if method == "<clinit>()V" or split_initializer:
                            counters["classInitializerEdges"] += 1
                        if owner == "java/lang/Class" and name in ("getResource", "getResourceAsStream"):
                            if (isinstance(receiver, tuple) and receiver[0] == 7
                                    and isinstance(previous, tuple) and previous[0] == 8):
                                literal = previous[1]
                                owner_package = receiver[1].rpartition("/")[0]
                                resource = literal[1:] if literal.startswith("/") else "/".join(
                                    filter(None, (owner_package, literal)))
                                if resource in classpath.resources:
                                    if mod_code and not resource.startswith(("assets/", "data/")):
                                        static_resources.add(resource)
                                elif mod_code:
                                    add("RESOURCE_NOT_ON_CLASSPATH", "warning", resource, location)
                            elif mod_code:
                                add("DYNAMIC_RESOURCE", "warning", owner + "." + name, location)
                        if mod_code:
                            category = dynamic_risk(owner, name, renderer)
                            if category:
                                add(category, "warning", owner + "." + name, location)
                    receiver, previous = previous, operand
            for name in sorted(types - {internal}):
                if renderer == "gl41" and name.startswith(METAL_PREFIX):
                    add("METAL_REFERENCE_ON_GL41", "blocker", name, internal, source)
                elif not classpath.has_type(name):
                    add("MISSING_TYPE", "warning", name, internal, source)
        def is_client_base(entry):
            source = classpath.classes.get(entry[:-6])
            return bool(source and archive_paths[source[0]] == original and source[1] == entry)

        def library_shapes():
            for name, source in classpath.classes.items():
                if is_client_base(name + ".class"):
                    continue
                shape = classpath.read_shape(source, graph=True)
                if shape["name"] != name:
                    raise ValueError(f"Class path mismatch: {source[0].filename}!{source[1]}")
                yield shape

        reflection = reflection_from_jar(client, class_visitor=inspect, diagnostics=findings,
                                         include_entry=is_client_base, extra_shapes=library_shapes())
        for archive, service in classpath.services:
            contents = archive.read(service).decode("utf-8", errors="replace")
            for line in contents.splitlines():
                provider = line.partition("#")[0].strip().replace(".", "/")
                if provider and not classpath.has_type(provider):
                    add("SERVICE_PROVIDER_MISSING", "warning", provider, service, archive)
                elif provider in classpath.classes:
                    shape = classpath.shape(provider)
                    if (shape["access"] & ABSTRACT
                            or not shape["methodFlags"].get("<init>()V", 0) & PUBLIC):
                        add("INVALID_CLASSPATH_SERVICE_PROVIDER", "warning", provider, service, archive)
        for row in fabric_entries:
            if row["stage"] not in ("main", "client") or row.get("refOwner"):
                continue
            owner = row["definition"].replace(".", "/")
            method = row["method"]
            target = resolve_member(owner, method, "()V", False)
            if target is False or (target and (target[1] & (ABSTRACT | STATIC) or not target[1] & PUBLIC)):
                findings.append(issue("INVALID_FABRIC_ENTRYPOINT", "blocker", owner + "." + method + "()V",
                                      FABRIC_DISPATCH + "#startClient", mod=row["mod"], renderer=renderer,
                                      stage="final-classpath",
                                      suggestion="Check the concrete implementation emitted by Fabric and its Mixins."))
        seen = set()
        pending = [(root, root) for root in required]
        while pending:
            name, root = pending.pop()
            if (name, root) in seen:
                continue
            seen.add((name, root))
            if not classpath.has_type(name):
                add("MISSING_REQUIRED_TYPE", "blocker", name, root)
            elif name in classpath.classes:
                shape = classpath.shape(name)
                pending.extend((related, root) for related in [shape["parent"], *shape["interfaces"]]
                               if related)
        if renderer == "gl41":
            for name in sorted(classpath.classes):
                if name.startswith(METAL_PREFIX):
                    add("METAL_CLASS_ON_GL41", "blocker", name, "Native Image classpath")
        elif RENDER_PIPELINES in classpath.classes and "fabricaot/metal/MetalBackend" in classpath.classes:
            if "fabricaot/metal/BundledPipelines" not in classpath.classes:
                add("METAL_PIPELINE_BUNDLE_CLASS_MISSING", "blocker",
                    "fabricaot/metal/BundledPipelines", RENDER_PIPELINES)

    findings.extend(grouped.values())
    findings.extend(issue("RESOURCE_METADATA", "fix", name) for name in sorted(static_resources))
    resources = {"resources": {"includes": [{"pattern": re.escape(name)} for name in sorted(static_resources)]}}
    return reflection, resources, findings, dict(counters)


def dynamic_risk(owner, member, renderer):
    if owner.startswith(("javax/imageio/", "java/awt/image/")) or owner in ("java/awt/Toolkit", "sun/awt/AppContext"):
        return "DESKTOP_IMAGE_IOS_UNSUPPORTED"
    if (member == "defineClass" or member.startswith("defineHiddenClass")) and (
            owner.endswith("ClassLoader") or owner == "java/lang/invoke/MethodHandles$Lookup"):
        return "RUNTIME_CLASS_DEFINITION"
    if (owner, member) in {("java/lang/System", "load"), ("java/lang/System", "loadLibrary"),
                           ("java/lang/Runtime", "load"), ("java/lang/Runtime", "loadLibrary")}:
        return "NATIVE_LIBRARY_LOAD"
    if owner == "java/lang/Class" and member in (
            "forName", "getField", "getDeclaredField", "getMethod", "getDeclaredMethod",
            "getConstructor", "getDeclaredConstructor", "getDeclaredFields", "getDeclaredConstructors"):
        return "REFLECTION_CALL"
    if owner == "java/lang/reflect/Proxy" and member in ("newProxyInstance", "getProxyClass"):
        return "PROXY_CALL"
    if owner in ("java/io/ObjectInputStream", "java/io/ObjectOutputStream") and member in (
            "readObject", "writeObject", "readUnshared", "writeUnshared"):
        return "SERIALIZATION_CALL"
    if owner == "java/util/ServiceLoader" and member.startswith("load"):
        return "SERVICE_LOADER_CALL"
    if owner == "oshi/SystemInfo" and member == "<init>":
        return "OSHI_IOS_UNSUPPORTED"
    if renderer == "gl41" and GL_AFTER_41.fullmatch(owner):
        return "OPENGL_AFTER_41"
    return None


def cached_bytecode_report(cache, client, libraries, renderer, *, java_home, required, entrypoint,
                           fabric_entries=()):
    """Key results by the ordered bytes Native Image reads and the scanner implementation."""
    started = time.monotonic()
    required = sorted(set(required))
    jmods = sorted(path for path in (java_home / "jmods").glob("*.jmod") if not is_metadata(path.name))
    scanner = [Path(__file__), Path(__file__).with_name("config_reflection.py"),
               Path(__file__).with_name("mod_file_policy.py")]
    paths = [*libraries, *jmods, *scanner]
    with ThreadPoolExecutor(max_workers=4) as executor:
        digests = list(executor.map(sha256, paths))
    client_index = next(index for index, path in enumerate(libraries) if path.resolve() == client.resolve())
    inputs = dict(renderer=renderer, entrypoint=entrypoint, required=required, clientIndex=client_index,
                  fabricEntries=list(fabric_entries),
                  orderedArchiveSHA256=list(zip((path.name for path in paths), digests)))
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    path = cache / f"{key}.json" if cache else None
    if path and path.is_file() and not path.is_symlink():
        try:
            record = json.loads(path.read_text())
            data = record["result"]
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            if (record["key"] == key and record["sha256"] == digest
                    and len(data) == 4 and isinstance(data[3], dict)):
                return (*data, dict(key=key, cacheHit=True, seconds=time.monotonic() - started))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    result = bytecode_report(client, libraries, renderer, java_home=java_home, required=required,
                             entrypoint=entrypoint, fabric_entries=fabric_entries)
    if path:
        digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        try:
            cache.mkdir(parents=True, exist_ok=True)
            publish(path, {"key": key, "sha256": digest, "result": result})
        except OSError:
            pass  # A local optimization must not affect the preflight verdict.
    return (*result, dict(key=key, cacheHit=False, seconds=time.monotonic() - started))
