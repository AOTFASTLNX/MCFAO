"""Run a fresh MCFAO image in a disposable ARM64 simulator with a copied test world."""
from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import shutil
import sys
import time

from capture import ROOT, capture
from mcfao import read_json, script, tree_files, write_json
from build_c0_harness import validate_dylib

FABRIC_MARKERS = (
    "MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS",
    "MCFAO_F3_CLIENT_WORLD_JOIN_PASS",
)


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def step(name, argv, timeout=120):
        logs = output / name
        result = capture(list(map(str, argv)), logs, timeout)
        if result["exitCode"] or result["timedOut"]:
            raise RuntimeError(f"{name} failed. Logs: {logs}")
        return (logs / "stdout.log").read_text(errors="replace").strip()

    build = read_json(args.build / "result.json")
    aot = Path(build["aotCommand"]).parents[1]
    mode = build.get("loader", "vanilla")
    if args.expect != mode:
        raise ValueError(f"Expected {args.expect} AOT image, got {mode}")
    markers = args.require_marker or (FABRIC_MARKERS if mode == "fabric" else ())
    link = output / "link-product"
    step("link", script("link_c0_ios", "--sdk", "iphonesimulator", "--image", aot,
                        "--runtime", args.runtime.resolve(), "--output", link,
                        "--stub-unsupported-jni"))
    graphics = args.graphics.resolve()
    staged = output / "staged"
    staged.mkdir()
    for name in ("libglfw.dylib", "liblwjgl.dylib", "libfaot_metal.dylib", "libopenal.dylib"):
        validate_dylib(graphics / name, simulator=True)
        shutil.copy2(graphics / name, staged / name)
    shutil.copy2(graphics / "fabricaot-present.metallib", staged)
    shutil.copytree(graphics / "fabricaot-shaders", staged / "fabricaot-shaders")
    shutil.copy2(link / "client-graph.dylib", staged)
    derived = output / "DerivedData"
    step("xcodebuild", [
        "/usr/bin/xcodebuild", "-project", ROOT / "ios/C0Harness/C0Harness.xcodeproj",
        "-scheme", "WorldSimulator", "-destination", "generic/platform=iOS Simulator",
        "-derivedDataPath", derived, f"FAOT_GRAPHICS_NATIVE_DIR={staged}",
        f"FAOT_CLIENT_LIBRARY={staged / 'client-graph.dylib'}", "build",
    ], 300)
    apps = list((derived / "Build/Products/World Simulator-iphonesimulator").glob("*.app"))
    if len(apps) != 1:
        raise ValueError("Expected one WorldSimulator app")
    app = apps[0]
    bundle = plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"]
    simctl = ["/usr/bin/xcrun", "simctl"]
    step("boot", [*simctl, "bootstatus", args.simulator, "-b"], 180)
    step("install", [*simctl, "install", args.simulator, app])
    data = Path(step("locate", [*simctl, "get_app_container", args.simulator, bundle, "data"]))
    documents = data / "Documents"
    assets = documents / "assets"
    if not assets.exists():
        shutil.copytree(args.assets.resolve(), assets)
    if tree_files(assets) != read_json(args.build / "inputs.json")["assetsSHA256"]:
        raise ValueError("Simulator asset contents differ from the recorded build inputs")
    game = documents / "game"
    world = game / "saves" / f"MCFAO Smoke {output.name}"
    if world.exists():
        raise ValueError(f"Use a fresh disposable simulator, copied test world exists: {world}")
    if not (args.seed_world / "level.dat").is_file():
        raise ValueError("Missing generated test world level.dat")
    shutil.copytree(args.seed_world, world, ignore=shutil.ignore_patterns("session.lock"))
    log_dir = documents / "c0-logs"
    old_logs = set(log_dir.glob("run-*.log"))
    try:
        # simctl passes only SIMCTL_CHILD-prefixed environment variables to the app.
        step("launch", ["/usr/bin/env", f"SIMCTL_CHILD_FABRICAOT_SIMULATOR_QUICK_WORLD={world.name}",
                        *simctl, "launch", args.simulator, bundle])
        deadline = time.monotonic() + 160
        while time.monotonic() < deadline:
            new_logs = sorted(set(log_dir.glob("run-*.log")) - old_logs)
            if new_logs:
                text = new_logs[-1].read_text(errors="replace")
                (output / "game.log").write_text(text)
                if "[FAOT] run_main returned" in text:
                    raise RuntimeError(f"Game exited before world validation. See {output / 'game.log'}")
                if "Dev joined the game" in text and all(marker in text for marker in markers):
                    if mode == "vanilla" and any(marker in text for marker in FABRIC_MARKERS):
                        raise ValueError("Vanilla image emitted a Fabric fixture marker")
                    time.sleep(3)
                    step("screenshot", [*simctl, "io", args.simulator, "screenshot", output / "world.png"])
                    write_json(output / "result.json", {
                        "status": "SIMULATOR_WORLD_SMOKE_PASS", "loader": mode,
                        "simulator": args.simulator, "deviceRun": "NOT RUN",
                        "fabricMarkers": list(markers) if mode == "fabric" else [],
                        "runtimeMixinTarget": "Minecraft#setLevel"
                        if mode == "fabric" and not args.require_marker else None,
                        "build": str(args.build.resolve()), "image": str(link / "client-graph.dylib"),
                        "filesSHA256": tree_files(output / "staged"),
                    })
                    return
            time.sleep(2)
        raise RuntimeError(f"Expected fresh world markers did not appear. See {output / 'game.log'}")
    finally:
        capture([*simctl, "terminate", args.simulator, bundle], output / "terminate", 30)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "runtime", "graphics", "assets", "seed-world", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--simulator", required=True, help="Fresh disposable iPhone simulator UDID")
    parser.add_argument("--expect", choices=("vanilla", "fabric"), required=True)
    parser.add_argument("--require-marker", action="append",
                        help="Require this run log marker. Overrides the default Fabric fixture markers.")
    try:
        run(parser.parse_args(argv))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Simulator smoke failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
