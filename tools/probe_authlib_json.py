#!/usr/bin/env python3
"""Exercise synthetic authlib JSON and service-key readiness on JVM / desktop AOT."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bootstrap_toolchain import sha256
from build_method_splitter import java_home
from capture import ROOT, capture
from external_storage import ExternalStorageUnavailable, require_mount

SOURCE = ROOT / "interop/diagnostics/AuthlibJsonProbe.java"
CONFIG = ROOT / "compiler/reflection-config.json"
MODES = {
    "joined": "AUTHLIB_JOINED_RESPONSE_PASS",
    "request": "AUTHLIB_JOIN_REQUEST_PASS",
    "responses": "AUTHLIB_ACCOUNT_RESPONSES_PASS",
    "keys": "AUTHLIB_SERVICE_KEYS_PASS",
}


def reflection_entries(path):
    return [entry for entry in json.loads(Path(path).read_text())
            if entry["name"].startswith("com.mojang.authlib.")]


def run(args):
    require_mount("authlib regression probe")
    home = args.graalvm_home.resolve(strict=True) if args.graalvm_home else java_home()
    libraries = [path.resolve(strict=True) for path in args.libraries]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "BLOCKED", "deviceRun": "NOT RUN",
              "scope": "synthetic authlib JSON and lazy service keys; no network or game execution",
              "inputSHA256": {str(path): sha256(path) for path in [
                  SOURCE, CONFIG, Path(__file__).resolve(), *libraries]}}
    record = output / "result.json"

    def step(name, command, timeout=120, expected=None):
        directory = output / name
        run = capture(list(map(str, command)), directory, timeout)
        text = (directory / "stdout.log").read_text() + (directory / "stderr.log").read_text()
        if run["timedOut"] or (expected is None and run["exitCode"]):
            raise RuntimeError(f"{name} failed: {directory}")
        if expected is not None:
            if run["exitCode"] == 0 or expected not in text:
                raise RuntimeError(f"{name} did not reproduce the expected failure: {directory}")
        return text

    try:
        classes = output / "classes"
        classes.mkdir()
        classpath = os.pathsep.join(map(str, [classes, *libraries]))
        step("compile", [home / "bin/javac", "--release", "25", "-proc:none",
                         "-cp", classpath, "-d", classes, SOURCE])
        main = "fabricaot.probe.AuthlibJsonProbe"
        for mode, marker in MODES.items():
            text = step("jvm-" + mode, [home / "bin/java", "-cp", classpath, main, mode])
            if marker not in text:
                raise RuntimeError("Missing JVM marker: " + marker)
        result["jvm"] = "PASS"
        if args.native_image:
            configs = [("after", CONFIG)]
            if args.baseline_config:
                baseline = args.baseline_config.resolve(strict=True)
                result["inputSHA256"][str(baseline)] = sha256(baseline)
                configs.insert(0, ("before", baseline))
            for label, config in configs:
                metadata = output / (label + "-reflect-config.json")
                metadata.write_text(json.dumps(reflection_entries(config), indent=2) + "\n")
                binary = output / (label + "-authlib-probe")
                step(label + "-build", [home / "bin/native-image", "--no-fallback", "-O1",
                     "-J-Xmx1g", "--parallelism=2", "--initialize-at-run-time=com.mojang",
                     "--enable-url-protocols=https",
                     "-H:ReflectionConfigurationFiles=" + str(metadata),
                     "-cp", classpath, main, binary], 360)
                for mode, marker in MODES.items():
                    expected = None
                    if label == "before":
                        expected = {"keys": "AUTHLIB_SERVICE_KEYS_STALLED",
                                    "request": "Failed to write value"}.get(
                                        mode, "Record components not available")
                    text = step(label + "-" + mode, [binary, mode], 30, expected)
                    if label == "after" and marker not in text:
                        raise RuntimeError("Missing AOT marker: " + marker)
                    if label == "before" and mode == "keys":
                        if not all(item in text for item in ("Record components not available",
                                                            "CompletableFuture.join")):
                            raise RuntimeError("Baseline did not reproduce the service-key reflection deadlock")
                result[label] = "EXPECTED_FAILURES_REPRODUCED" if label == "before" else "PASS"
                result[label + "BinarySHA256"] = sha256(binary)
            result["desktopAot"] = "PASS"
        else:
            result["desktopAot"] = "NOT RUN"
        result["status"] = "AUTHLIB_JSON_PROBE_PASS"
    except Exception as error:
        result["failure"] = str(error)
        raise
    finally:
        record.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libraries", type=Path, nargs="+", required=True,
                        help="Explicit official authlib / Gson / Guava / SLF4J dependencies, no Mods")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--graalvm-home", type=Path)
    parser.add_argument("--native-image", action="store_true")
    parser.add_argument("--baseline-config", type=Path)
    args = parser.parse_args(argv)
    if args.baseline_config and not args.native_image:
        parser.error("--baseline-config requires --native-image")
    try:
        run(args)
    except ExternalStorageUnavailable as error:
        print(error, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
