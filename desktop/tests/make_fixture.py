"""Create a first-party metadata-only pack; no game assets or executable classes."""
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from preflight import scan_pack


def create(directory):
    directory.mkdir(parents=True, exist_ok=True)
    jar = io.BytesIO()
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({
            "schemaVersion": 1, "id": "fabricaot_ui_fixture", "version": "1.0.0",
            "name": "First-party metadata fixture", "mixins": ["fixture.mixins.json"],
        }))
    manifest = {"formatVersion": 1, "game": "minecraft", "versionId": "fixture-1",
                "name": "第一方元数据夹具", "dependencies": {"minecraft": "26.1.2", "fabric-loader": "0.19.3"}, "files": []}
    pack = directory / "中文 UI fixture.mrpack"
    with zipfile.ZipFile(pack, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(manifest))
        archive.writestr("overrides/mods/fixture.jar", jar.getvalue())
    prism = directory / "Prism fixture"
    (prism / ".minecraft/mods").mkdir(parents=True, exist_ok=True)
    (prism / "mmc-pack.json").write_text(json.dumps({"components": [
        {"uid": "net.minecraft", "version": "26.1.2"},
        {"uid": "net.fabricmc.fabric-loader", "version": "0.19.3"}]}))
    (prism / ".minecraft/mods/fixture.jar").write_bytes(jar.getvalue())
    return scan_pack(pack)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(create(Path(sys.argv[1])), ensure_ascii=False))
    else:
        with tempfile.TemporaryDirectory(prefix="fabricaot-ui-") as temporary:
            print(json.dumps(create(Path(temporary)), ensure_ascii=False))
