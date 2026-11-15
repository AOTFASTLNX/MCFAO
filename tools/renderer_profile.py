"""Renderer-specific runtime contracts shared by local and CI packaging."""
from __future__ import annotations
import argparse
from pathlib import Path

COMMON = ("client-graph.dylib", "libglfw.dylib", "liblwjgl.dylib", "libopenal.dylib")
RENDERERS = ("metal", "gl41")

def libraries(renderer):
    if renderer not in RENDERERS:
        raise ValueError("Unknown renderer: " + str(renderer))
    return COMMON + (("libfaot_metal.dylib",) if renderer == "metal" else
                     ("liblwjgl_opengl.dylib", "libOSMesa.8.dylib", "libMoltenVK.dylib"))

def config_names(renderer):
    libraries(renderer)
    return ("glfw", "lwjgl", "openal") + (("metal", "shaders") if renderer == "metal" else ("gl41", "lwjglOpengl"))

def validate_runtime(app: Path, renderer: str):
    from build_c0_harness import validate_dylib
    directory = app / "Frameworks"
    found = {p.name for p in directory.glob("*.dylib")}
    if found != set(libraries(renderer)):
        raise ValueError(f"Incomplete {renderer} runtime: missing={set(libraries(renderer))-found}, unexpected={found-set(libraries(renderer))}")
    for name in libraries(renderer):
        validate_dylib(directory / name)
    if renderer == "metal":
        from build_c0_harness import validate_shader_bundle
        validate_shader_bundle(directory / "fabricaot-shaders", simulator=False)
        if not (directory / "fabricaot-present.metallib").stat().st_size:
            raise ValueError("Empty Metal presentation library")
    if not (app / "assets/indexes/30.json").is_file():
        raise ValueError("Missing Minecraft asset index 30")
    if not any((app / "assets/objects").glob("*/*")):
        raise ValueError("Missing Minecraft asset objects")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--renderer", choices=RENDERERS, required=True)
    args = parser.parse_args()
    validate_runtime(args.app, args.renderer)
