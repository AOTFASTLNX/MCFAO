"""Inspect Fabric jars or export an audited subset of the actual Knot client graph."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import sys
import zipfile

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from prepare_b0 import jar_bytes, select_libraries
from run_b0_reference import execute, require_run, sandbox_policy

TOOL = ROOT / "interop/fabric/tool"
FIXTURE = ROOT / "interop/fabric/fixture"
MAIN = "mcfao.build.AotExport"
MAX_ARCHIVE = 128 * 1024**2
# The overlay carries every Mod class, resource and service file in one jar, so it grows past
# the per-input archive cap as soon as a real pack is prepared. This bounds the output only.
MAX_EXPORT = 1024 * 1024**2
MAX_UNPACKED = 512 * 1024**2
# Recollection3 resolves to 221 root and nested archives (53 roots, 168 nested).
# The transform budget must be able to reach that inventory, otherwise a real pack is
# rejected as "budget exceeded" before any metadata is reported.
MAX_TRANSFORM_ARCHIVES = 256
MAX_INSPECTION_ARCHIVES = 512
# Entrypoint stages the Loader does not define are queried by a provider mod. When the
# provider cannot exist in the closed-world client, no code can query the stage, so the
# entry is unreachable and recorded instead of failing the archive.
OPTIONAL_PROVIDER_STAGES = {"modmenu": "modmenu", "jei_mod_plugin": "jei"}
# Classes under interop/fabric/tool/mcfao/aot replace bytecode a Mod would have generated at run
# time, so they implement that Mod's own API and compile against that Mod's jar. They must not be
# compiled into a pack that does not contain the Mod: the compile would fail on the missing
# package, and a class nothing references would still ship. Keyed by tool-relative path.
RUNTIME_OVERLAY_MODS = {"mcfao/aot/GenericVertexSerializer.java": "sodium"}
# Packages the pinned engine owns. A Mod that ships its own copy would shadow the very
# code the image is built against; Fabric API and language adapters live elsewhere.
LOADER_PACKAGES = ("net/fabricmc/loader/", "net/fabricmc/mappingio/",
                   "net/fabricmc/accesswidener/", "net/fabricmc/tinyremapper/")
# Identities the image supplies itself. A Mod that re-ships one of these must use the image
# copy: its own classes are never merged.
RESERVED_IDS = frozenset({"java", "minecraft", "fabricloader", "mixinextras"})


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def contains_control_characters(value):
    if isinstance(value, str):
        return any(ord(char) < 32 for char in value)
    if isinstance(value, dict):
        return any(contains_control_characters(key) or contains_control_characters(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(map(contains_control_characters, value))
    return False


def read_entry(archive, name):
    if archive.getinfo(name).file_size > 1024**2:
        raise ValueError(f"Oversized Fabric metadata: {name}")
    data = archive.read(name)
    try:
        value = json.loads(data, object_pairs_hook=unique_keys)
    except json.JSONDecodeError as error:
        if name != "fabric.mod.json" or not error.msg.startswith("Invalid control character"):
            raise
        # The pinned Loader accepts literal line breaks in descriptions. Keep the
        # exception away from ids, archive member names and execution metadata.
        value = json.loads(data, object_pairs_hook=unique_keys, strict=False)
        if not isinstance(value, dict) or not isinstance(value.get("description"), str):
            raise
        description = value["description"].replace("\n", "").replace("\r", "")
        if (contains_control_characters(description)
                or any(contains_control_characters(key) or contains_control_characters(item)
                       for key, item in value.items() if key != "description")):
            raise
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {name}")
    return value


def needs_reference_remapping(archive, name):
    # A number of official-namespace builds retain the annotation processor's
    # default filename without shipping a refmap. Knot uses identity in that case.
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
        raise ValueError(f"Unsafe Mixin refmap path: {name}")
    if name not in archive.namelist():
        return False
    refmap = read_entry(archive, name)
    return (bool(set(refmap) - {"mappings", "data"}) or bool(refmap.get("mappings"))
            or bool(refmap.get("data")))


def mod_files(directory):
    jars = sorted(p for p in directory.iterdir() if p.suffix.lower() == ".jar")
    if not jars or any(p.is_symlink() or not p.is_file() for p in jars):
        raise ValueError("Expected regular local .jar files in --mods")
    if len(jars) > 128:
        raise ValueError("Too many root mod JARs")
    return jars


def root_mod_ids(roots):
    """Ids declared by the root JARs, used to decide which run-time overlays can compile."""
    ids = set()
    for path in roots:
        with zipfile.ZipFile(path) as archive:
            try:
                metadata = read_entry(archive, "fabric.mod.json")
            except (ValueError, KeyError):
                continue
        if isinstance(metadata.get("id"), str):
            ids.add(metadata["id"])
    return ids


def runtime_overlay_sources(roots):
    """Split the run-time overlay sources into the ones this pack can compile and the rest."""
    present = root_mod_ids(roots)
    compiled, skipped = [], []
    for path in sorted((TOOL / "mcfao" / "aot").rglob("*.java")):
        relative = path.relative_to(TOOL).as_posix()
        required = RUNTIME_OVERLAY_MODS.get(relative)
        if required and required not in present:
            skipped.append({"source": relative, "requiresMod": required})
            continue
        compiled.append(path)
    return compiled, skipped


def inspect_archives(roots, work, *, metadata_only=False):
    inventory = []
    budget = MAX_UNPACKED
    max_archives = MAX_INSPECTION_ARCHIVES if metadata_only else MAX_TRANSFORM_ARCHIVES

    def inspect(path, origin, depth):
        nonlocal budget
        if depth > 4 or len(inventory) >= max_archives or path.stat().st_size > MAX_ARCHIVE:
            raise ValueError(f"Fabric archive budget exceeded: {origin}")
        with zipfile.ZipFile(path) as archive:
            names = set()
            members = archive.infolist()
            if len(members) > 25000:
                raise ValueError(f"Too many Fabric JAR members: {origin}")
            for item in members:
                name = item.filename
                relative = PurePosixPath(name)
                if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                        or str(relative) != name.rstrip("/") or name in names
                        or stat.S_ISLNK(item.external_attr >> 16)):
                    raise ValueError(f"Unsafe or duplicate JAR member: {origin}!{name}")
                names.add(name)
                budget -= item.file_size
                if budget < 0 or item.file_size > MAX_ARCHIVE:
                    raise ValueError(f"Expanded mod size budget exceeded: {origin}")
            try:
                metadata = read_entry(archive, "fabric.mod.json")
            except (ValueError, KeyError) as error:
                raise ValueError(f"{origin}!fabric.mod.json: {error}") from error
            inventory.append((path, origin, metadata, names))
            for nested in metadata.get("jars", []):
                name = nested["file"]
                if name not in names or not name.endswith(".jar"):
                    raise ValueError(f"Missing nested Fabric JAR: {origin}!{name}")
                child = work / f"nested-{len(inventory)}.jar"
                with archive.open(name) as source, child.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                inspect(child, f"{origin}!{name}", depth + 1)

    for root in roots:
        inspect(root, root.name, 0)
    return inventory


def transformation_checks(inventory, metadata, *, client_ids=None, nested=None, adapters=None):
    if client_ids is None:
        client_ids = {mod["id"] for mod in metadata if mod["client"]}
    if nested is None:
        nested = [False] * len(inventory)
    # Only an adapter that some archive in the closure actually registers can be resolved at
    # build time; anything else would need a runtime registry lookup.
    registered_adapters = {"default"} | set(adapters or ())
    reserved = RESERVED_IDS
    skipped = []
    for (path, origin, raw, names), parsed, is_nested in zip(inventory, metadata, nested, strict=True):
        def unsupported(message):
            raise ValueError(f"{origin} [{parsed['id']}]: {message}")

        if not parsed["client"]:
            continue
        if parsed["id"] in reserved or reserved.intersection(raw.get("provides", [])):
            # A nested Jar that re-ships a runtime the image already provides is redundant,
            # not conflicting: the provider is present exactly once at a higher level.
            if is_nested:
                skipped.append({"mod": parsed["id"], "stage": "provided", "provider": parsed["id"],
                                "entrypoint": None,
                                "reason": "nested Jar re-ships a runtime the image already provides; "
                                          "the packaged copy is dropped and the image copy is used"})
                continue
            unsupported("Reserved Fabric/Minecraft dependency identity")
        if raw.get("schemaVersion") != 1 or raw.get("initializers"):
            unsupported("Schema 1 without initializers is required")
        for adapter, value in sorted((raw.get("languageAdapters") or {}).items()):
            if not re.fullmatch(r"[\w$]+(?:\.[\w$]+)+", str(value), re.ASCII):
                unsupported(f"Language adapter {adapter} must name a class: {value}")
            # The adapter is only consulted while the image is assembled: it decides whether the
            # entrypoint is a Kotlin object or a class to construct. The generated hook records
            # that decision, so the image needs neither the adapter nor its registry.
            skipped.append({"mod": parsed["id"], "stage": "language-adapter", "provider": adapter,
                            "entrypoint": str(value),
                            "reason": "adapter resolved at build time into a direct construction "
                                      "or a singleton field read"})
        for stage, entries in parsed["entrypoints"].items():
            if stage in {"server", "fabric-datagen"}:
                continue
            provider = OPTIONAL_PROVIDER_STAGES.get(stage)
            # ModMenu is a configuration-screen container: it is never part of the closed-world
            # client, so this stage has no querying code until ModMenu itself is supported.
            # Other optional stages are dropped only when their provider mod is absent here.
            if provider is not None and (provider == "modmenu" or provider not in client_ids):
                skipped.extend({"mod": parsed["id"], "stage": stage, "provider": provider,
                                "entrypoint": entry.get("value")} for entry in entries)
                continue
            if stage not in {"main", "client"}:
                # Custom stages exist so one mod can call into another. The generated hooks only
                # invoke main/client, so these callbacks never run; recording them keeps the
                # loss visible instead of silently dropping behaviour.
                consumer = provider or stage.split(":", 1)[0]
                if consumer in {"main", "client"}:
                    unsupported(f"Unsupported lifecycle stage {stage}")
                skipped.extend({"mod": parsed["id"], "stage": stage, "provider": consumer,
                                "entrypoint": entry.get("value"),
                                "reason": "custom stage is dispatched by its provider mod or the Loader "
                                          "outside the generated main/client hooks"} for entry in entries)
                continue
            for entry in entries:
                if entry["adapter"] not in registered_adapters:
                    unsupported(f"Entrypoint language adapter {entry['adapter']} is not registered "
                                f"by any packaged Mod: {entry['value']}")
                if not re.fullmatch(r"[\w$]+(?:\.[\w$]+)+(?:::\w+)?", entry["value"], re.ASCII):
                    unsupported("Entrypoint must be a public Java class or an official method "
                                f"reference: {entry['value']}")
                if entry["adapter"] != "default":
                    skipped.append({"mod": parsed["id"], "stage": "entrypoint-adapter",
                                    "provider": entry["adapter"], "entrypoint": entry["value"],
                                    "reason": "adapter resolved at build time into a direct "
                                              "construction or a singleton field read"})
        for name in sorted(names):
            if name == "META-INF/services/":
                continue
            if (name.startswith(("mcfao/aot/", "org/spongepowered/", "com/llamalad7/", *LOADER_PACKAGES))
                    or name.lower().endswith((".dylib", ".so", ".dll"))):
                unsupported(f"Unsupported host configuration, class or native resource {name}")
            if name.startswith(("assets/", "data/")) and re.search(r"[\\\x00-\x1f]", name):
                unsupported(f"Unsupported resource path {name}")
        with zipfile.ZipFile(path) as archive:
            for name in parsed["mixins"]:
                config = read_entry(archive, name)
                # A MixinConfigPlugin is a build-time hook: the real Knot applies it while the
                # image is assembled, so it never has to exist at runtime. Parent configs,
                # declared injection points and dynamic selectors still change which classes
                # Mixin emits and remain unsupported.
                if (any(config.get(key) for key in ("parent", "injectionPoints", "dynamicSelectors"))
                        or not re.fullmatch(r"[\w$]+(?:\.[\w$]+)*", config.get("package", ""), re.ASCII)):
                    unsupported(f"Mixin config must not use parents or dynamic selectors and must "
                                f"use official names: {name}")
                if "required" in config and not isinstance(config["required"], bool):
                    unsupported(f"Mixin config required must be a boolean: {name}")
                if config.get("required") is not True:
                    # Mixin itself skips a non-required config whose targets are absent, so the
                    # JVM reference behaves the same way. Recording it keeps the loss visible.
                    skipped.append({"mod": parsed["id"], "stage": "mixin", "provider": "mixin",
                                    "entrypoint": name,
                                    "reason": "config is not required:true; Mixin skips it on failure "
                                              "exactly as in the JVM reference"})
                if config.get("refmap") and needs_reference_remapping(archive, config["refmap"]):
                    # Fabric only installs a refmap remapper in development. In a production
                    # closure the mod's own bytecode is authoritative, so the refmap is retained
                    # but inert; a wrong namespace still fails loudly while Mixin is applied.
                    skipped.append({"mod": parsed["id"], "stage": "mixin", "provider": "mixin",
                                    "entrypoint": f"{name} refmap {config['refmap']}",
                                    "reason": "refmap is retained but inert outside development"})
            if parsed.get("classTweaker"):
                name = parsed["classTweaker"]
                if name not in names:
                    unsupported(f"Missing Class Tweaker {name}")
                header = archive.read(name).splitlines()[0].decode("utf-8").split()
                if not header or header[-1] != "official":
                    unsupported(f"Class Tweaker must use the official namespace: {name}")
    return skipped


def inspect_compatibility(inventory, metadata, root_paths):
    findings = []
    blocked_roots = set()
    skipped = []
    root_ids = defaultdict(list)
    client_ids = {mod["id"] for mod in metadata if mod["client"]}
    adapters = {adapter for (_, _, raw, _) in inventory
                for adapter in (raw.get("languageAdapters") or {})}
    normalised = {"multiRelease": [], "serviceRegistrations": [], "hostMetadata": [], "moduleDescriptor": []}
    for item, mod in zip(inventory, metadata, strict=True):
        path, origin, _, names = item
        is_root = path in root_paths
        if is_root:
            root = origin
            root_ids[mod["id"]].append(origin)
        try:
            skipped.extend(transformation_checks([item], [mod], client_ids=client_ids,
                                                 nested=[not is_root], adapters=adapters))
        except (ValueError, KeyError, IndexError, TypeError, OSError, zipfile.BadZipFile) as error:
            findings.append({"path": origin, "id": mod["id"], "reason": str(error)})
            blocked_roots.add(root)
            continue
        if any(name.startswith("META-INF/versions/") and not name.endswith("/") for name in names):
            normalised["multiRelease"].append(mod["id"])
        for name in names:
            if name.startswith("META-INF/services/") and not name.endswith("/"):
                normalised["serviceRegistrations"].append(f"{mod['id']}: {name[len('META-INF/services/'):]}")
            elif name.startswith("META-INF/native-image/") and name.endswith((".json", ".properties")):
                normalised["hostMetadata"].append(f"{mod['id']}: {name}")
            elif name == "module-info.class":
                normalised["moduleDescriptor"].append(mod["id"])
    return {
        "status": "BLOCKED" if findings else "NO_METADATA_BLOCKERS",
        "scope": "First applicable metadata restriction per archive, plus unreachable optional "
                 "entrypoints. No Mod execution or dependency resolution.",
        "rootJarCount": len(root_paths),
        "nestedJarCount": len(inventory) - len(root_paths),
        "rootJarsWithBlockers": sorted(blocked_roots),
        "duplicateRootModIds": {key: paths for key, paths in root_ids.items() if len(paths) > 1},
        "normalisedAtExport": {key: sorted(set(value)) if isinstance(value, list) else value
                               for key, value in normalised.items()},
        "findings": findings,
        "optionalEntrypointsSkipped": skipped,
    }


def merge_client(client, overlay, output, changes, resources=()):
    """Merge the Mod overlay into the client jar.

    Overlapping entries are allowed only when the export declared them: transformed game
    classes are listed per entry, and a Mod resource that overrides a vanilla file is listed
    as an overridden resource, because a single layer cannot express pack priority.
    """
    with (zipfile.ZipFile(client) as base, zipfile.ZipFile(overlay) as patch,
          zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as merged):
        updated = set(patch.namelist())
        declared = set(changes) | set(resources)
        if updated.intersection(base.namelist()) != declared:
            raise ValueError("Fabric overlay changes undocumented client entries: "
                             + ", ".join(sorted(updated.intersection(base.namelist()) - declared)[:5]))
        for source in (base, patch):
            for member in source.infolist():
                name = member.filename
                if source == base and (name in updated or re.fullmatch(
                        r"META-INF/(?:[^/]+\.(?:SF|RSA|DSA|EC)|SIG-[^/]+)", name, re.I)):
                    continue
                merged.writestr(member, source.read(member))


def load_reference(prepared):
    report = json.loads((prepared / "result.json").read_text())
    home = Path(report["javaHome"])
    if sha256(home / "bin/java") != report["javaSHA256"]:
        raise ValueError("Prepared Java changed")
    lock = json.loads((ROOT / "compiler/fabric.lock.json").read_text())
    engine = select_libraries({"jars": report["engineLibraries"]}, lock)
    libraries = [Path(row["path"]) for row in report["referenceLibraries"]]
    for row, path in zip(report["referenceLibraries"], libraries, strict=True):
        if sha256(path) != row["sha256"]:
            raise ValueError(f"Prepared reference changed: {path}")
    return home, libraries, [Path(row["path"]) for row in engine], report


def compile_java(home, classpath, sources, classes, log):
    result = capture([str(home / "bin/javac"), "--release", "25", "-proc:none",
                      "-cp", os.pathsep.join(map(str, classpath)), "-d", str(classes),
                      *map(str, sorted(sources))], log, 180)
    if result["exitCode"] or result["timedOut"]:
        raise RuntimeError(f"javac failed. Logs: {log}")


def build_fixture(prepared, output):
    home, libraries, engine, _ = load_reference(prepared)
    classes = output / "classes"
    compile_java(home, [*engine, *libraries], (FIXTURE / "src").rglob("*.java"), classes, output / "compile")
    contents = {str(p.relative_to(classes)): p.read_bytes() for p in classes.rglob("*.class")}
    resources = FIXTURE / "resources"
    contents.update({str(p.relative_to(resources)): p.read_bytes() for p in resources.rglob("*") if p.is_file()})
    mods = output / "mods"
    mods.mkdir()
    (mods / "mcfao-fixture.jar").write_bytes(jar_bytes(contents))


def prepare(prepared, client, mods, output, audited, trace_agent=False):
    home, libraries, engine, report = load_reference(prepared)
    if client not in libraries or client.name != "26.1.2.jar":
        raise ValueError("The input must be the verified owned client in the prepared manifest")
    work = output / "work"
    for name in ("tmp", "home", "game/mods", "classes"):
        (work / name).mkdir(parents=True, exist_ok=True)
    roots = []
    hashes = {}
    for source in mod_files(mods):
        if source.stat().st_size > MAX_ARCHIVE:
            raise ValueError(f"Oversized mod: {source}")
        destination = work / "game/mods" / source.name
        shutil.copyfile(source, destination)
        hashes[str(source)] = sha256(source)
        if hashes[str(source)] != sha256(destination):
            raise ValueError(f"Mod changed while copying: {source}")
        roots.append(destination)
    inventory = inspect_archives(roots, work, metadata_only=not audited)
    # Use only the pinned Loader/ASM/Mixin copies ahead of the vanilla reference.
    engine_names = {p.name for p in engine}
    classpath = [*engine, *(p for p in libraries if p.name not in engine_names)]
    classes = work / "classes"
    # Classes that replace run-time generated Mod code implement Mod APIs, so they compile
    # against the Mod jars and never enter the tool's own classpath. Keeping the two compilations
    # apart means the AOT host still sees Mod jars only through Knot.
    tool_sources = [p for p in TOOL.rglob("*.java") if "aot" not in p.relative_to(TOOL).parts]
    compile_java(home, classpath, tool_sources, classes, output / "compile")
    classpath.insert(0, classes)
    runtime_sources, overlay_skipped = runtime_overlay_sources(roots)
    runtime_classes = None
    if runtime_sources:
        runtime_classes = work / "runtime-classes"
        compile_java(home, [*classpath, *sorted((work / "game/mods").glob("*.jar"))],
                     runtime_sources, runtime_classes, output / "compile-runtime")
    driver = prepared / "driver.jar"
    if sha256(driver) != report["binaries"]["driver.jar"]["sha256"]:
        raise ValueError("Sandbox control driver changed")
    java = [str(home / "bin/java"), "-XX:+DisableAttachMechanism", "-XX:-UsePerfData",
            "-Xmx1g", "-Djava.awt.headless=true", f"-Duser.home={work / 'home'}",
            f"-Djava.io.tmpdir={work / 'tmp'}"]
    agent_library = None
    if trace_agent:
        agent_library = home / "lib/libnative-image-agent.dylib"
        if not agent_library.is_file():
            raise RuntimeError(f"GraalVM tracing agent is unavailable: {agent_library}")
    sandbox_prefix = []
    if audited:
        policy = output / "policy.sb"
        policy.write_text(sandbox_policy(work, home, [driver, *classpath[1:]]))
        sandbox_prefix = ["/usr/bin/sandbox-exec", "-f", str(policy)]
        outside = output / "outside-read.txt"
        outside.write_text("MCFAO first-party sandbox control\n")
        write = output / "outside-write.txt"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(0.1)
            log = output / "sandbox-control"
            result = execute([*sandbox_prefix, *java, "-cp", str(driver), "fabricaot.b0.bootstrap.SandboxProbe",
                              str(outside), str(write), str(listener.getsockname()[1])], log, work)
            require_run(result, log, "B0_SANDBOX_PASS")
            if write.exists():
                raise RuntimeError("Sandbox allowed outside write")
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                pass
            else:
                connection.close()
                raise RuntimeError("Sandbox allowed loopback network access")
    cp = ["-cp", os.pathsep.join(map(str, classpath)), MAIN]
    parsed = work / "metadata.json"
    log = output / "parse"
    result = execute([*sandbox_prefix, *java, *cp, "inspect", str(parsed),
                      *(str(row[0]) for row in inventory)], log, work)
    if result["exitCode"] or result["timedOut"]:
        raise RuntimeError(f"Fabric Loader metadata parsing failed. Logs: {log}")
    metadata = json.loads(parsed.read_text())
    for row, (_, origin, _, _) in zip(metadata, inventory, strict=True):
        row["path"] = origin
    record = {"status": "FABRIC_METADATA_PARSED", "loader": "0.19.3", "namespace": "official",
              "modSHA256": hashes, "mods": metadata,
              "runtimeOverlays": {"compiled": [p.relative_to(TOOL).as_posix() for p in runtime_sources],
                                  "skipped": overlay_skipped}}
    if not audited:
        record["compatibility"] = inspect_compatibility(inventory, metadata, set(roots))
        resolution = work / "resolution.json"
        log = output / "resolve"
        solved = execute([*sandbox_prefix, *java, *cp, "resolve", str(resolution), str(client), str(work),
                          str(work / "game/mods")], log, work)
        if solved["exitCode"] or solved["timedOut"]:
            raise RuntimeError(f"Fabric Loader dependency discovery failed. Logs: {log}")
        record["resolution"] = json.loads(resolution.read_text())
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if not audited:
        return
    skipped = transformation_checks(
        inventory, metadata,
        nested=[path not in set(roots) for path, _, _, _ in inventory],
        adapters={adapter for (_, _, raw, _) in inventory
                  for adapter in (raw.get("languageAdapters") or {})})
    if skipped:
        record["optionalEntrypointsSkipped"] = skipped
    request = work / "ids.txt"
    wanted = sorted({row["id"] for row in metadata if row["client"] and row["id"] not in RESERVED_IDS})
    request.write_text("\n".join(wanted) + "\n")
    # A Mod that cannot join a closed world is excluded and recorded, and the export is retried
    # without it: one bad class must not hide the verdict for the other forty Mods, and the Mod
    # set that survives is exactly the set the image can contain.
    excluded = {}
    # Dropping a Mod must drop its dependents too: they compile against classes the image will
    # not contain, and discovering that ten minutes into a native-image build is expensive.
    depends = {raw["id"]: set((raw.get("depends") or {}).keys())
               for (_, _, raw, _) in inventory if isinstance(raw, dict) and "id" in raw}
    # Knot applies a Mod's Mixin configs because the jar sits in the mods folder, not because the
    # Mod was requested for export. Dropping only the export request therefore left Mixin patches
    # from an unexported Mod in the image, and the first game code that called into that Mod died
    # with NoClassDefFoundError. A whole jar is retired once every id it declares is excluded, so
    # the set of applied Mixins matches the set of classes the image contains.
    ids_by_jar = {}
    for _, origin, raw, _ in inventory:
        if isinstance(raw, dict) and "id" in raw:
            ids_by_jar.setdefault(str(origin), set()).add(raw["id"])
    mods_folder = (work / "game/mods").resolve()
    retired = work / "excluded"
    tracing_attempts = []
    for attempt in range(1, 6):
        log = output / ("knot" if attempt == 1 else f"knot-{attempt}")
        attempt_trace_directory = None
        attempt_java = java
        if trace_agent:
            attempt_trace_directory = work / f"tracing-agent-{attempt}"
            attempt_trace_directory.mkdir()
            attempt_java = [java[0], "-agentlib:native-image-agent=config-output-dir="
                            + str(attempt_trace_directory), *java[1:]]
        result = execute([*sandbox_prefix, *attempt_java, "--enable-native-access=ALL-UNNAMED", "-Dfabric.noGui=true",
                          "-Dfabric.gameMappingNamespace=official", f"-Dfabric.gameJarPath={client}",
                          f"-Dfabric.modsFolder={work / 'game/mods'}", *cp, "export", str(client),
                          str(work), str(request), str(work / "game"),
                          str(runtime_classes) if runtime_classes else ""], log, work, timeout=900,
                         cpu_seconds=900, file_size_bytes=MAX_EXPORT)
        if attempt_trace_directory and attempt_trace_directory.is_dir():
            published_trace = output / f"tracing-agent-attempt-{attempt}"
            shutil.move(str(attempt_trace_directory), str(published_trace))
            result_trace_files = sorted(published_trace.glob("*.json"))
            tracing_attempts.append({
                "attempt": attempt,
                "path": str(published_trace),
                "status": "COLLECTED" if result_trace_files else "NO_METADATA_EMITTED",
                "categories": [path.name for path in result_trace_files],
                "filesSHA256": {path.name: sha256(path) for path in result_trace_files},
            })
        blocked = work / "incompatible.json"
        if blocked.is_file():
            report = json.loads(blocked.read_text())
            # Retired by rename rather than deletion: each attempt keeps the verdicts it produced,
            # which is the only record of why a Mod left the pack, and a bulk-delete guard in the
            # hosting environment cannot abort the retry half way through it.
            blocked.replace(output / f"incompatible-{attempt}.json")
            fresh = {key: value for key, value in report["mods"].items() if key not in excluded}
            if fresh:
                excluded.update(fresh)
                # Transitive dependents, each with the Mod that forced it out.
                changed = True
                while changed:
                    changed = False
                    for mod in list(wanted):
                        if mod in excluded:
                            continue
                        required = depends.get(mod, set()) & set(excluded)
                        if required:
                            excluded[mod] = ["requires excluded Mod " + sorted(required)[0]]
                            changed = True
                wanted = [key for key in wanted if key not in excluded]
                request.write_text("\n".join(wanted) + "\n")
                retired.mkdir(exist_ok=True)
                for origin, declared in ids_by_jar.items():
                    if not declared or not declared <= set(excluded):
                        continue
                    # The inventory records a root jar by file name, so a bare name is resolved
                    # against the mods folder rather than the current directory.
                    jar = Path(origin)
                    if not jar.is_absolute():
                        jar = mods_folder / jar
                    jar = jar.resolve()
                    if jar.parent != mods_folder or not jar.exists():
                        continue
                    shutil.move(str(jar), str(retired / jar.name))
                continue
        break
    if trace_agent:
        final_trace = tracing_attempts[-1] if tracing_attempts else None
        record["tracingAgent"] = {
            "status": final_trace["status"] if final_trace else "NO_METADATA_EMITTED",
            "path": final_trace["path"] if final_trace else None,
            "attempts": tracing_attempts,
            "scope": "Only the final audited desktop Fabric export rehearsal is supplied to AOT; earlier retry traces are retained as evidence",
            "agentLibrary": str(agent_library),
        }
    require_run(result, log, "MCFAO_FABRIC_EXPORT_PASS")
    if excluded:
        record["excludedMods"] = {
            key: sorted({line.split(": ", 1)[-1] for line in value})
            for key, value in sorted(excluded.items())}
        # Which declared ids live in which jar, so a retired jar can be explained after the fact.
        record["jarIds"] = {Path(origin).name: sorted(declared)
                            for origin, declared in sorted(ids_by_jar.items())}
        if retired.is_dir():
            record["retiredJars"] = sorted(path.name for path in retired.glob("*.jar"))
    transform = json.loads((work / "transform.json").read_text())
    output_jar = output / "client.jar"
    merge_client(client, work / "overlay.jar", output_jar, transform["gameTransforms"],
                 transform.get("overriddenResources", []))
    record["semanticCompatibility"] = semantic_compatibility(transform)
    record.update(status="FABRIC_AOT_INPUT_PREPARED", sandbox="file and network denial controls passed",
                  transform=transform, clientSHA256=sha256(client), outputJarSHA256=sha256(output_jar))
    record["mdaf"] = transform.get("mdaf", {
        "schemaVersion": 1, "policy": "REPORT_ONLY",
        "diagnostics": {"status": "Transform report did not include MDAF data"}})
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")


def semantic_compatibility(transform):
    """Code generation and behavioral compatibility are deliberately separate verdicts."""
    methods = sorted(set(transform.get("stubbedMethods", [])))
    return {"status": "REQUIRES_REVIEW" if methods else "NO_RESIDUE_REPORTED",
            "scope": "Loader residue report only; not proof of functional equivalence",
            "unsupportedMethods": methods,
            "runtimeVerified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--client", type=Path)
    parser.add_argument("--mods", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--audited-mods", action="store_true")
    parser.add_argument("--trace-agent", action="store_true",
                        help="Collect bounded GraalVM tracing metadata during the sandboxed audited export")
    args = parser.parse_args(argv)
    if args.trace_agent and not args.audited_mods:
        parser.error("--trace-agent requires --audited-mods")
    if not args.fixture and (not args.client or not args.mods):
        parser.error("--client and --mods are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        if args.fixture:
            build_fixture(args.prepared.resolve(), output)
        else:
            prepare(args.prepared.resolve(), args.client.resolve(), args.mods.resolve(), output,
                    args.audited_mods, args.trace_agent)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as error:
        failure = {
            "schemaVersion": 1, "policy": "REPORT_ONLY",
            "status": "PREPARATION_FAILED", "failedStage": "PREPARATION",
            "failure": str(error),
            "diagnostics": {
                "compatibilityFindings": "See any partial transform.json; compatibility risks remain report-only",
                "automaticRetry": "Not attempted after an unclassified preparation failure",
            },
        }
        report_path = output / "mdaf-report.json"
        report_path.write_text(json.dumps(failure, indent=2) + "\n")
        result_path = output / "result.json"
        partial = json.loads(result_path.read_text()) if result_path.is_file() else {}
        partial.update(status="PREPARATION_FAILED", error=str(error), mdaf=failure)
        result_path.write_text(json.dumps(partial, indent=2) + "\n")
        print(f"Fabric preparation failed: {error}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
