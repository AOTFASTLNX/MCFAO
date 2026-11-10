"""Stage the fingerprinted Recollection3 inventory-input compatibility profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from zipfile import ZipFile

from bootstrap_toolchain import sha256
from preflight import read_json_limited, validate_zip_members

MOUSE = "MouseTweaks-fabric-mc26.1-2.31.jar"
API = "fabric-api-0.148.0+26.1.2.jar"
LOCAL_SHA256 = {
    MOUSE: "56cabaa265034772de4e52d9a26d933a01bbab0f0a9de2ee47916a2ab9f2b660",
    API: "ba6487d2dcb8e95149b6071f27c66a806669e1f54ed4a279fc4f99c4e3a4e8af",
}
MODULE_SHA256 = {
    "fabric-api-base-2.0.3+ece063234c.jar": "3fb11050311da9df335e350971b4bd40a7149c7b7552c382b01ef38088019632",
    "fabric-screen-api-v1-5.0.1+d871b99e4c.jar": "cc7bed76eafe874833acf7a8c1306a18d75a5d7b31cb84160203b404f7c097b7",
}
PACK_FILES = {
    (60089, 7840791): MOUSE,
    (306612, 8032582): API,
}


def stage(pack: Path, local_mods: Path, output: Path) -> dict:
    with ZipFile(pack) as archive:
        findings = []
        if not validate_zip_members(archive, findings, pack.name):
            raise ValueError(f"Unsafe pack archive: {findings}")
        manifest = read_json_limited(archive, "manifest.json", 2 * 1024**2)
    refs = {(entry["projectID"], entry["fileID"]) for entry in manifest["files"]}
    if (manifest["name"] != "Recollection3" or manifest["minecraft"]["version"] != "26.1.2"
            or not PACK_FILES.keys() <= refs):
        raise ValueError("Expected the Recollection3 manifest with the audited Mouse Tweaks and Fabric API file IDs")
    for name, expected in LOCAL_SHA256.items():
        path = local_mods / name
        if not stat.S_ISREG(path.lstat().st_mode) or sha256(path) != expected:
            raise ValueError(f"Audited JAR fingerprint mismatch: {name}")

    mods = output / "mods"
    output.mkdir(parents=True, exist_ok=False)
    mods.mkdir()
    with ZipFile(local_mods / API) as archive:
        for name, expected in MODULE_SHA256.items():
            data = archive.read(f"META-INF/jars/{name}")
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"Audited Fabric API module fingerprint mismatch: {name}")
            (mods / name).write_bytes(data)

    # This exact Mouse Tweaks JAR imports the Screen API and API Base only.
    # Declare those real modules, without representing the aggregate as installed.
    adapted = mods / MOUSE
    with ZipFile(local_mods / MOUSE) as source, ZipFile(adapted, "x") as target:
        for entry in source.infolist():
            data = source.read(entry)
            if entry.filename == "fabric.mod.json":
                metadata = json.loads(data)
                if metadata["depends"].pop("fabric-api") != "*":
                    raise ValueError("Unexpected Mouse Tweaks Fabric API requirement")
                metadata["depends"].update({"fabric-api-base": "*", "fabric-screen-api-v1": "*"})
                data = (json.dumps(metadata, indent=2) + "\n").encode()
            target.writestr(entry, data)
    result = {
        "scope": "Recollection3 inventory-input profile only",
        "packSHA256": sha256(pack),
        "declaredLoader": manifest["minecraft"]["modLoaders"],
        "sources": [{"projectID": project, "fileID": file, "file": name, "sha256": LOCAL_SHA256[name]}
                    for (project, file), name in PACK_FILES.items()],
        "metadataChanges": {MOUSE: {"replacedDependency": "fabric-api", "modules": list(MODULE_SHA256)}},
        "filesSHA256": {path.name: sha256(path) for path in sorted(mods.iterdir())},
        "otherManifestReferencesNotSelected": len(refs - PACK_FILES.keys()),
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--local-mods", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        stage(args.pack, args.local_mods, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(args.output / "result.json")


if __name__ == "__main__":
    main()
