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
    jars = sorted(directory.glob("*.jar"))
    if not jars or any(p.is_symlink() or not p.is_file() for p in jars):
        raise ValueError("Expected regular local .jar files in --mods")
    if len(jars) > 128:
        raise ValueError("Too many root mod JARs")
    return jars


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


def transformation_checks(inventory, metadata, *, client_ids=None):
    if client_ids is None:
        client_ids = {mod["id"] for mod in metadata if mod["client"]}
    reserved = {"java", "minecraft", "fabricloader", "mixinextras"}
    skipped = []
    for (path, origin, raw, names), parsed in zip(inventory, metadata, strict=True):
        def unsupported(message):
            raise ValueError(f"{origin} [{parsed['id']}]: {message}")

        if not parsed["client"]:
            continue
        if parsed["id"] in reserved or reserved.intersection(raw.get("provides", [])):
            unsupported("Reserved Fabric/Minecraft dependency identity")
        if raw.get("schemaVersion") != 1 or raw.get("languageAdapters") or raw.get("initializers"):
            unsupported("Schema 1 and the built-in default language adapter are required")
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
                unsupported(f"Unsupported lifecycle stage {stage}")
            for entry in entries:
                if entry["adapter"] != "default" or not re.fullmatch(
                        r"[\w$]+(?:\.[\w$]+)+(?:::\w+)?", entry["value"], re.ASCII):
                    unsupported("Entrypoint must be a public Java class or an official method "
                                f"reference: {entry['value']}")
        for name in sorted(names):
            if name == "META-INF/services/":
                continue
            if (name.startswith(("META-INF/native-image/", "META-INF/versions/", "META-INF/services/",
                                 "mcfao/aot/", "org/spongepowered/", "com/llamalad7/"))
                    or (name.startswith("net/fabricmc/") and not (
                        name == "net/fabricmc/" or name.startswith("net/fabricmc/fabric/")))
                    or name.lower().endswith((".dylib", ".so", ".dll")) or name == "module-info.class"):
                unsupported(f"Unsupported host configuration, class or native resource {name}")
            if (name.startswith(("assets/", "data/"))
                    and not re.fullmatch(r"[a-zA-Z0-9_./-]+", name)):
                unsupported(f"Unsupported resource path {name}")
        with zipfile.ZipFile(path) as archive:
            for name in parsed["mixins"]:
                config = read_entry(archive, name)
                # A MixinConfigPlugin is a build-time hook: the real Knot applies it while the
                # image is assembled, so it never has to exist at runtime. Parent configs,
                # declared injection points and dynamic selectors still change which classes
                # Mixin emits and remain unsupported.
                if (any(config.get(key) for key in ("parent", "injectionPoints", "dynamicSelectors"))
                        or (config.get("refmap") and needs_reference_remapping(archive, config["refmap"]))
                        or config.get("required") is not True
                        or not re.fullmatch(r"[\w$]+(?:\.[\w$]+)*", config.get("package", ""), re.ASCII)):
                    unsupported(f"Mixin config must be required and use official names: {name}")
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
    for item, mod in zip(inventory, metadata, strict=True):
        path, origin, _, _ = item
        if path in root_paths:
            root = origin
            root_ids[mod["id"]].append(origin)
        try:
            skipped.extend(transformation_checks([item], [mod], client_ids=client_ids))
        except (ValueError, KeyError, IndexError, TypeError, OSError, zipfile.BadZipFile) as error:
            findings.append({"path": origin, "id": mod["id"], "reason": str(error)})
            blocked_roots.add(root)
    return {
        "status": "BLOCKED" if findings else "NO_METADATA_BLOCKERS",
        "scope": "First applicable metadata restriction per archive, plus unreachable optional "
                 "entrypoints. No Mod execution or dependency resolution.",
        "rootJarCount": len(root_paths),
        "nestedJarCount": len(inventory) - len(root_paths),
        "rootJarsWithBlockers": sorted(blocked_roots),
        "duplicateRootModIds": {key: paths for key, paths in root_ids.items() if len(paths) > 1},
        "findings": findings,
        "optionalEntrypointsSkipped": skipped,
    }


def merge_client(client, overlay, output, changes):
    with (zipfile.ZipFile(client) as base, zipfile.ZipFile(overlay) as patch,
          zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as merged):
        updated = set(patch.namelist())
        if updated.intersection(base.namelist()) != set(changes):
            raise ValueError("Fabric overlay changes undocumented client entries")
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


def prepare(prepared, client, mods, output, audited):
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
    compile_java(home, classpath, TOOL.rglob("*.java"), classes, output / "compile")
    classpath.insert(0, classes)
    driver = prepared / "driver.jar"
    if sha256(driver) != report["binaries"]["driver.jar"]["sha256"]:
        raise ValueError("Sandbox control driver changed")
    java = [str(home / "bin/java"), "-XX:+DisableAttachMechanism", "-XX:-UsePerfData",
            "-Xmx1g", "-Djava.awt.headless=true", f"-Duser.home={work / 'home'}",
            f"-Djava.io.tmpdir={work / 'tmp'}"]
    if audited:
        policy = output / "policy.sb"
        policy.write_text(sandbox_policy(work, home, [driver, *classpath[1:]]))
        java = ["/usr/bin/sandbox-exec", "-f", str(policy), *java]
        outside = output / "outside-read.txt"
        outside.write_text("MCFAO first-party sandbox control\n")
        write = output / "outside-write.txt"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(0.1)
            log = output / "sandbox-control"
            result = execute([*java, "-cp", str(driver), "fabricaot.b0.bootstrap.SandboxProbe",
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
    result = execute([*java, *cp, "inspect", str(parsed), *(str(row[0]) for row in inventory)], log, work)
    if result["exitCode"] or result["timedOut"]:
        raise RuntimeError(f"Fabric Loader metadata parsing failed. Logs: {log}")
    metadata = json.loads(parsed.read_text())
    for row, (_, origin, _, _) in zip(metadata, inventory, strict=True):
        row["path"] = origin
    record = {"status": "FABRIC_METADATA_PARSED", "loader": "0.19.3", "namespace": "official",
              "modSHA256": hashes, "mods": metadata}
    if not audited:
        record["compatibility"] = inspect_compatibility(inventory, metadata, set(roots))
        resolution = work / "resolution.json"
        log = output / "resolve"
        solved = execute([*java, *cp, "resolve", str(resolution), str(client), str(work),
                          str(work / "game/mods")], log, work)
        if solved["exitCode"] or solved["timedOut"]:
            raise RuntimeError(f"Fabric Loader dependency discovery failed. Logs: {log}")
        record["resolution"] = json.loads(resolution.read_text())
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if not audited:
        return
    skipped = transformation_checks(inventory, metadata)
    if skipped:
        record["optionalEntrypointsSkipped"] = skipped
    request = work / "ids.txt"
    request.write_text("\n".join(sorted({row["id"] for row in metadata if row["client"]})) + "\n")
    log = output / "knot"
    result = execute([*java, "--enable-native-access=ALL-UNNAMED", "-Dfabric.noGui=true",
                      "-Dfabric.gameMappingNamespace=official", f"-Dfabric.gameJarPath={client}",
                      f"-Dfabric.modsFolder={work / 'game/mods'}", *cp, "export", str(client),
                      str(work), str(request), str(work / "game")], log, work, timeout=240, cpu_seconds=300,
                     file_size_bytes=MAX_ARCHIVE)
    require_run(result, log, "MCFAO_FABRIC_EXPORT_PASS")
    transform = json.loads((work / "transform.json").read_text())
    output_jar = output / "client.jar"
    merge_client(client, work / "overlay.jar", output_jar, transform["gameTransforms"])
    record.update(status="FABRIC_AOT_INPUT_PREPARED", sandbox="file and network denial controls passed",
                  transform=transform, clientSHA256=sha256(client), outputJarSHA256=sha256(output_jar))
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")


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
    args = parser.parse_args(argv)
    if not args.fixture and (not args.client or not args.mods):
        parser.error("--client and --mods are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        if args.fixture:
            build_fixture(args.prepared.resolve(), output)
        else:
            prepare(args.prepared.resolve(), args.client.resolve(), args.mods.resolve(), output, args.audited_mods)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as error:
        print(f"Fabric preparation failed: {error}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
