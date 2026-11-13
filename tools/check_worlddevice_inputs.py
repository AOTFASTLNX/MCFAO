#!/usr/bin/env python3
"""Report locally staged WorldDevice inputs without reading game data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "artifacts/graphics/world-device-input-02"
ASSETS = ROOT / "artifacts/graphics/game-assets-01/assets"


def missing_inputs():
    files = [INPUT / name for name in (
        "client-graph.dylib", "liblwjgl.dylib", "libfaot_metal.dylib",
        "libopenal.dylib", "fabricaot-present.metallib", "fabricaot-shaders/index.json",
    )] + [ASSETS / "indexes/30.json"]
    missing = [p for p in files if not p.is_file() or p.stat().st_size == 0]
    if not (ASSETS / "objects").is_dir():
        missing.append(ASSETS / "objects")
    return missing


if __name__ == "__main__":
    missing = missing_inputs()
    print("SKIPPED" if missing else "READY")
    for path in missing:
        print(path.relative_to(ROOT))
