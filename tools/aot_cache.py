"""Index verified local AOT objects by their compilation inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from bootstrap_toolchain import sha256
from artifact_copy import copy_artifact


PACKAGING_FIELDS = {"unsigned", "bundleID", "appIcon", "requestedDevice", "instanceSHA256", "testVersion"}
REQUIRED_FILES = ("client-graph.o", "result.json", "compatibility.json", "analysis/command.json")


def mod_fingerprints(files):
    """Mod discovery sorts root JARs by path within one staging directory."""
    return sorted([Path(path).name, digest] for path, digest in files.items())


def cache_key(inputs):
    compile_inputs = {key: value for key, value in inputs.items()
                      if key not in PACKAGING_FIELDS and key != "modsSHA256"}
    if "modsSHA256" in inputs:
        compile_inputs["modsSHA256"] = mod_fingerprints(inputs["modsSHA256"])
    return hashlib.sha256(json.dumps(compile_inputs, sort_keys=True).encode()).hexdigest()


def record(cache, key, aot, image_object, loader_report):
    """Publish one complete reference after the object has passed the iOS linker."""
    files = {
        "client-graph.o": image_object,
        "result.json": aot / "result.json",
        "compatibility.json": aot / "compatibility.json",
        "analysis/command.json": aot / "analysis/command.json",
    }
    if loader_report:
        files["fabric-result.json"] = loader_report
    cache.mkdir(parents=True, exist_ok=True)
    entries = {name: {"path": str(path), "sha256": sha256(path)} for name, path in files.items()}
    with TemporaryDirectory(dir=cache) as temporary:
        pending = Path(temporary) / "record.json"
        pending.write_text(json.dumps({"schemaVersion": 2, "key": key, "files": entries}, indent=2) + "\n")
        pending.replace(cache / (key + ".json"))


def restore(cache, key, output, inputs):
    """Stage a private verified copy so old build cleanup cannot affect this build."""
    index = cache / (key + ".json")
    expected = set(REQUIRED_FILES)
    if inputs["loader"] == "fabric":
        expected.add("fabric-result.json")
    try:
        if index.is_symlink():
            return None
        record = json.loads(index.read_text())
        if (record["schemaVersion"] != 2 or record["key"] != key or set(record["files"]) != expected):
            return None
        stage = output / "aot"
        stage.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=stage) as temporary:
            pending = Path(temporary) / "product"
            for name in sorted(expected):
                entry = record["files"][name]
                source = Path(entry["path"])
                if source.resolve(strict=True) != source or not source.is_file():
                    return None
                destination = pending / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                copy_artifact(source, destination)
                if sha256(destination) != entry["sha256"]:
                    return None
            if inputs["loader"] == "fabric":
                fabric = json.loads((pending / "fabric-result.json").read_text())
                if (fabric["status"] != "FABRIC_AOT_INPUT_PREPARED" or fabric["renderer"] != inputs["renderer"]
                        or fabric.get("excludedMods") or fabric.get("retiredJars")
                        or mod_fingerprints(fabric["modSHA256"]) != mod_fingerprints(inputs["modsSHA256"])):
                    return None
            result_path = pending / "result.json"
            result = json.loads(result_path.read_text())
            compatibility = json.loads((pending / "compatibility.json").read_text())
            flags = json.loads((pending / "analysis/command.json").read_text())["argv"]
            if (result["targetCodeGeneration"] != "RELOCATABLE_OBJECT" or result.get("analysisFailure")
                    or result.get("analysisExitCode") != 0 or result.get("sandboxProbe") != "PASS"
                    or result.get("renderer") != inputs["renderer"]
                    or compatibility.get("renderer") != inputs["renderer"]
                    or compatibility.get("blockers") != 0 or compatibility["stages"]["static"] != "PASS"
                    or not result.get("compiledMetadataSHA256") or not result.get("bytecodePreflight")
                    or result.get("builderGC") != inputs["builderGC"]
                    or result["imageObject"]["sha256"] != record["files"]["client-graph.o"]["sha256"]
                    or not {"--no-fallback", "-H:+ExitAfterRelocatableImageWrite", inputs["optimizationLevel"],
                            f"--parallelism={inputs['parallelism']}", f"-J-Xmx{inputs['heapGiB']}g"} <= set(flags)):
                return None
            attempt = stage / uuid4().hex
            product = attempt / "product"
            result["reusedFrom"] = record["files"]["result.json"]["path"]
            result["imageObject"]["path"] = str(product / "client-graph.o")
            result["imageArtifacts"] = [result["imageObject"]]
            result["filesSHA256"] = {name: record["files"][name]["sha256"]
                                     for name in sorted(expected - {"result.json"})}
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            attempt.mkdir()
            pending.rename(product)
        return product, product / "fabric-result.json" if inputs["loader"] == "fabric" else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return None
