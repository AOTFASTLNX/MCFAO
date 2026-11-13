"""Run the WorldUITests functional probe against a built Fabric pack's smoke save.

The smoke script proves the pack joins a world; this probe *interacts* with it - move,
look at a block, pick it, open the inventory, pause - and attaches one screenshot per
interaction. Per-mod FUNCTION_PASS upgrades in docs/MOD_MATRIX_EVIDENCE.json must cite
these attachments (observed behaviour), not log lines.

Reuses the disposable world the smoke run already copied into the simulator container
("MCFAO Smoke <pack>-simulator") and the staged libraries under <pack>-simulator/staged;
nothing here rebuilds the AOT image.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from capture import ROOT, capture
from mcfao import read_json, tree_files, write_json
from build_c0_harness import validate_dylib

PROBE_TEST = "WorldUITests/WorldUITests/testFabricModFunctions"

#: The test method reads MCFAO_QUICK_WORLD from the *runner* process. xcodebuild does not
#: forward arbitrary variables to the runner, only TEST_RUNNER_-prefixed ones (prefix
#: stripped), so the caller-facing name doubles as the runner-facing one.
RUNNER_ENV = "MCFAO_QUICK_WORLD"
EXPECTED_ATTACHMENTS = ("probe-joined", "probe-moved", "probe-aim-down", "probe-picked",
                        "probe-inventory", "probe-inventory-slot", "probe-pause")


def WORLD_NAME(pack: Path) -> str:
    """smoke_mcfao_simulator.py names the save "MCFAO Smoke <output dir>"; derive it."""
    return f"MCFAO Smoke {pack.name}-simulator"


def export_attachments(bundle: Path, out: Path) -> list[str]:
    """Pull every kept-always screenshot attachment out of the .xcresult bundle."""
    result = capture(["/usr/bin/xcrun", "xcresulttool", "export", "attachments",
                      "--path", str(bundle), "--output-path", str(out)], out / "export", 120)
    if result["exitCode"] or result["timedOut"]:
        raise RuntimeError(f"xcresulttool export failed. Logs: {out / 'export'}")
    manifest = json.loads((out / "manifest.json").read_text())
    return retain_attachment_names(manifest, out)


def retain_attachment_names(manifest: list[dict], out: Path) -> list[str]:
    """Rename each exported PNG back to the name the test gave it.

    xcresulttool writes attachments under a UUID file name and puts the test's own
    `attachFrame:` label in `suggestedHumanReadableName`; the evidence table cites the
    label, so the export has to carry it too.
    """
    names = []
    for test in manifest:
        for attachment in test.get("attachments", []):
            exported = out / attachment["exportedFileName"]
            if not exported.is_file():
                raise RuntimeError(f"manifest names a missing attachment: {exported}")
            readable = Path(attachment.get("suggestedHumanReadableName")
                            or attachment["exportedFileName"]).name
            target = out / readable
            if target.exists():
                target = out / f"{exported.stem}-{readable}"
            exported.replace(target)
            names.append(target.name)
    return names


def run(args):
    pack = args.pack.resolve()
    simulator_output = Path(f"{pack}-simulator")
    result = read_json(simulator_output / "result.json")
    if not str(result["status"]).endswith("SMOKE_PASS"):
        raise ValueError(f"{simulator_output} is not a passing smoke run: {result['status']}")
    staged = simulator_output / "staged"
    for name in ("libglfw.dylib", "liblwjgl.dylib", "libfaot_metal.dylib", "libopenal.dylib"):
        validate_dylib(staged / name, simulator=True)
    out = simulator_output / "probe"
    if out.exists():
        raise ValueError(f"Probe output already exists (reruns must be explicit): {out}")
    out.mkdir()
    world = WORLD_NAME(pack)
    bundle = out / "result.xcresult"
    # capture() preserves the process environment, so the runner inherits the world name
    # from here; the app itself gets it via launchEnvironment in the test method. The
    # TEST_RUNNER_ prefix must be a *process environment variable*: xcodebuild forwards
    # those to the runner with the prefix stripped, but a NAME=value argv build setting
    # never reaches it.
    previous = (os.environ.get(RUNNER_ENV), os.environ.get(f"TEST_RUNNER_{RUNNER_ENV}"))
    os.environ[RUNNER_ENV] = world
    os.environ[f"TEST_RUNNER_{RUNNER_ENV}"] = world
    try:
        step = capture([
            "/usr/bin/xcodebuild", "test",
            "-project", str(ROOT / "ios/C0Harness/C0Harness.xcodeproj"),
            "-scheme", "WorldSimulatorTests",
            "-destination", f"id={args.simulator}",
            "-derivedDataPath", str(simulator_output / "probe-derived"),
            "-resultBundlePath", str(bundle),
            "-only-testing", PROBE_TEST,
            f"FAOT_GRAPHICS_NATIVE_DIR={staged}",
            f"FAOT_CLIENT_LIBRARY={staged / 'client-graph.dylib'}",
        ], out / "xcodebuild-test", 900)
    finally:
        for name, old in zip((RUNNER_ENV, f"TEST_RUNNER_{RUNNER_ENV}"), previous):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
    if step["exitCode"] or step["timedOut"]:
        raise RuntimeError(f"Probe test failed. Logs: {out / 'xcodebuild-test'}")
    names = export_attachments(bundle, out / "attachments")
    missing = [name for name in EXPECTED_ATTACHMENTS if not any(name in n for n in names)]
    if missing:
        raise RuntimeError(f"Probe screenshots missing from the result bundle: {missing}")
    write_probe_result(out, args.simulator, world, names, staged)


def write_probe_result(out: Path, simulator: str, world: str, names: list[str], staged: Path):
    write_json(out / "result.json", {
        "status": "SIMULATOR_FUNCTION_PROBE_PASS",
        "simulator": simulator,
        "world": world,
        "test": PROBE_TEST,
        "attachments": sorted(names),
        "stagedSHA256": tree_files(staged),
    })

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True,
                        help="Build directory, e.g. artifacts/mcfao/fabric-pack-88")
    parser.add_argument("--simulator", required=True, help="iPhone simulator UDID")
    try:
        run(parser.parse_args(argv))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Function probe failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
