#!/usr/bin/env python3
"""Link the first-party A1 image with locally built upstream iOS archives."""
from __future__ import annotations

import argparse
import json
import plistlib
import shutil
from pathlib import Path

from bootstrap_toolchain import ROOT, sha256
from capture import capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish-framework", type=Path)
    parser.add_argument("--sdk", choices=("iphoneos", "iphonesimulator"), default="iphoneos")
    args = parser.parse_args(argv)
    runtime, probe, output = args.runtime.absolute(), args.probe.absolute(), args.output.absolute()
    report = json.loads((runtime / "result.json").read_text())
    if report["status"] != "COMPILED":
        parser.error("Runtime translation units have not all compiled")
    target = "arm64-apple-ios17.0" + ("-simulator" if args.sdk == "iphonesimulator" else "")
    if report.get("target") != target:
        parser.error("Runtime target does not match requested SDK; device/simulator archives cannot be relabelled")
    probe_report = json.loads((probe / "result.json").read_text())
    objects = [probe / name for name in probe_report["binaries"] if name.endswith("a1probe.o")]
    if len(objects) != 1:
        parser.error("Expected exactly one retained A1 native image object")
    output.mkdir(parents=True, exist_ok=False)
    framework = output / "FabricAOTProbe.framework"
    (framework / "Headers").mkdir(parents=True)
    binary = framework / "FabricAOTProbe"
    archives = [runtime / name for name in ("libjava.a", "libnet.a", "libnio.a", "libzip.a", "libsvm.a", "libfallback.a")]
    for archive in archives:
        entry = report["archives"][archive.stem]
        if sha256(archive) != entry["sha256"]:
            raise ValueError(f"Runtime archive modified: {archive}")
    command = ["xcrun", "--sdk", args.sdk, "clang", "-target", target,
               "-dynamiclib", "-Wl,-dead_strip", "-Wl,-install_name,@rpath/FabricAOTProbe.framework/FabricAOTProbe",
               "-o", str(binary), str(objects[0]), *[str(p) for p in archives],
               "-framework", "Foundation", "-framework", "CoreFoundation", "-framework", "CFNetwork",
               "-framework", "SystemConfiguration", "-framework", "Security", "-framework", "MobileCoreServices",
               "-lz", "-liconv", "-lresolv", "-lpthread", "-ldl", "-lobjc"]
    result = capture(command, output / "link", 180)
    if result["exitCode"] == 0:
        for header in probe.glob("*.h"):
            shutil.copy2(header, framework / "Headers" / header.name)
        info = {"CFBundleIdentifier": "org.fabricaot.research.runtime", "CFBundleName": "FabricAOTProbe",
                "CFBundleExecutable": "FabricAOTProbe", "CFBundlePackageType": "FMWK",
                "CFBundleVersion": "1", "CFBundleShortVersionString": "0.1", "MinimumOSVersion": "17.0"}
        with (framework / "Info.plist").open("wb") as stream:
            plistlib.dump(info, stream)
        if args.publish_framework:
            shutil.copytree(framework, args.publish_framework)
    outcome = {"status": "LINKED" if result["exitCode"] == 0 else "BLOCKED", "link": result,
               "deviceRun": "NOT RUN", "iosGateA1": "BLOCKED", "framework": str(framework),
               "target": target,
               "sha256": sha256(binary) if binary.exists() else None,
               "runtime": str(runtime), "probe": str(probe),
               "unsupportedJVMEntrypoints": report.get("unsupportedJVMEntrypoints", [])}
    (output / "result.json").write_text(json.dumps(outcome, indent=2) + "\n")
    print(json.dumps({k: v for k, v in outcome.items() if k not in ("link", "unsupportedJVMEntrypoints")}, indent=2))
    return 0 if result["exitCode"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
