"""Static facts from the exact Native Image classpath, without loading Mod classes."""
from collections import Counter
from contextlib import ExitStack
import json
import re
from uuid import uuid4
import zipfile

from capture import redact_log
from config_reflection import class_shape, reflection_from_jar
from mod_file_policy import is_metadata

METAL_PREFIX = "fabricaot/metal/"
RENDER_PIPELINES = "net/minecraft/client/renderer/RenderPipelines"
PLATFORM_TYPES = ("java/", "javax/", "jdk/", "sun/", "com/sun/", "org/w3c/", "org/xml/", "org/ietf/")
MEMBER_TYPES = re.compile(r"L([^;<:]+)(?=[;<])")
GL_AFTER_41 = re.compile(r"org/lwjgl/opengl/GL4[2-6]C?$")
ISSUE_LIMIT = 160


def type_names(value):
    return MEMBER_TYPES.findall(value) if value.startswith("[") else [value]


def issue(code, severity, target, location=None, count=1):
    return dict(code=code, severity=severity, target=redact_log(target),
                location=redact_log(location) if location else None, count=count)


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


class Classpath:
    """First-definition-wins classpath and JDK index. Class bodies are read lazily."""
    def __init__(self, stack, paths, java_home):
        self.classes = {}
        self.resources = set()
        self.shapes = {}
        self.jdk = set()
        if java_home:
            for path in (java_home / "jmods").glob("*.jmod"):
                with zipfile.ZipFile(path) as archive:
                    self.jdk.update(name[8:-6] for name in archive.namelist()
                                    if name.startswith("classes/") and name.endswith(".class"))
        for path in paths:
            archive = stack.enter_context(zipfile.ZipFile(path))
            multi = False
            if "META-INF/MANIFEST.MF" in archive.namelist():
                manifest = archive.read("META-INF/MANIFEST.MF").split(b"\n\n", 1)[0].replace(b"\r", b"")
                multi = bool(re.search(rb"(?im)^Multi-Release:\s*true\s*$", manifest))
            selected = {}
            for name in archive.namelist():
                if is_metadata(name):
                    continue
                self.resources.add(name)
                logical = name
                version = 0
                if name.startswith("META-INF/versions/"):
                    _, _, level, logical = (name.split("/", 3) + [""])[:4]
                    if not multi or not level.isdecimal() or not 9 <= int(level) <= 25:
                        continue
                    version = int(level)
                    self.resources.add(logical)
                if logical.endswith(".class") and not logical.startswith("META-INF/"):
                    internal = logical[:-6]
                    if internal not in selected or version > selected[internal][0]:
                        selected[internal] = (version, name)
            for internal, (_, name) in selected.items():
                self.classes.setdefault(internal, (archive, name))

    def has_type(self, name):
        return name in self.classes or name in self.jdk or (
            not self.jdk and name.startswith(PLATFORM_TYPES))

    def shape(self, name):
        if name in self.classes and name not in self.shapes:
            archive, entry = self.classes[name]
            self.shapes[name] = class_shape(archive.read(entry))
        return self.shapes.get(name)

    def has_member(self, owner, name, descriptor, field):
        """False only when every relevant declaring type could be inspected."""
        pending = [owner]
        visited = set()
        opaque = False
        while pending:
            current = pending.pop()
            if not current or current in visited:
                continue
            visited.add(current)
            shape = self.shape(current)
            if shape is None:
                opaque |= current != "java/lang/Object" or not field
                continue
            if field:
                if (name, descriptor) in shape["fields"]:
                    return True
            elif name + descriptor in shape["methodSignatures"]:
                return True
            if name != "<init>":
                pending.extend([shape["parent"], *shape["interfaces"]])
        return None if opaque else False


def bytecode_report(client, libraries, renderer, *, java_home=None, required=()):
    """Collect symbolic references and check hard roots plus backend invariants.

    Symbols in optional branches can be absent legitimately. Their presence in a classfile
    provides a diagnostic, while the inheritance chain of a required root is mandatory.
    """
    findings = []
    grouped = {}
    counters = Counter()
    static_resources = set()
    checked_members = {}
    with ExitStack() as stack:
        classpath = Classpath(stack, libraries, java_home)

        def add(code, severity, target, location):
            key = (code, target)
            if key not in grouped:
                grouped[key] = issue(code, severity, target, location, count=0)
            grouped[key]["count"] += 1

        def inspect(shape):
            internal = shape["name"]
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
            for name in sorted(types - {internal}):
                if renderer == "gl41" and name.startswith(METAL_PREFIX):
                    add("METAL_REFERENCE_ON_GL41", "blocker", name, internal)
                elif not classpath.has_type(name):
                    add("MISSING_TYPE", "warning", name, internal)
            mod_code = not internal.startswith(("net/minecraft/", "com/mojang/", "org/lwjgl/"))
            if mod_code:
                for native in shape["nativeMethods"]:
                    add("MOD_NATIVE_METHOD", "warning", internal + "#" + native, internal)
            for method, operations in shape["bytecode"]:
                previous = receiver = None
                for _, operand in operations:
                    if isinstance(operand, tuple) and operand[0] in (9, 10, 11):
                        tag, owner, name, descriptor = operand
                        counters["fieldEdges" if tag == 9 else "callEdges"] += 1
                        if name == "<init>":
                            counters["constructorEdges"] += 1
                        if method == "<clinit>()V":
                            counters["classInitializerEdges"] += 1
                        location = internal + "#" + method
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
                            if owner.startswith("org/lwjgl/") and owner in classpath.classes:
                                key = (owner, name, descriptor, tag == 9)
                                if key not in checked_members:
                                    checked_members[key] = classpath.has_member(*key)
                                if checked_members[key] is False:
                                    add("LWJGL_MEMBER_MISSING", "warning", owner + "." + name + descriptor,
                                        location)
                    receiver, previous = previous, operand
        reflection = reflection_from_jar(client, class_visitor=inspect, diagnostics=findings)
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

    findings.extend(grouped.values())
    findings.extend(issue("RESOURCE_METADATA", "fix", name) for name in sorted(static_resources))
    resources = {"resources": {"includes": [{"pattern": re.escape(name)} for name in sorted(static_resources)]}}
    return reflection, resources, findings, dict(counters)


def dynamic_risk(owner, member, renderer):
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
    if renderer == "gl41" and GL_AFTER_41.fullmatch(owner):
        return "OPENGL_AFTER_41"
    return None
