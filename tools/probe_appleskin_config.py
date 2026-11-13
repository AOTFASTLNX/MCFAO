"""Verify AppleSkin configuration round trips on JVM and optional desktop Native Image."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

from capture import ROOT, capture
from bootstrap_toolchain import sha256
from mcfao import write_json
from prepare_fabric_aot import load_reference


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    home, _, _, _ = load_reference(args.prepared.resolve())
    jars = list(args.build.glob("metal-injection/*/product/client-26.1.2-metal.jar"))
    if len(jars) != 1:
        raise ValueError("Expected exactly one transformed client jar")
    # Keep the probe independent of Minecraft bootstrap and unrelated Mod metadata.
    library = output / "config-library.jar"
    with zipfile.ZipFile(jars[0]) as source, zipfile.ZipFile(library, "w") as target:
        for name in source.namelist():
            if name == "squeek/appleskin/ModConfig.class" or (
                    name.startswith("squeek/appleskin/shadowed/") and name.endswith(".class")):
                target.writestr(name, source.read(name))
    classes = output / "classes"
    classes.mkdir()

    def step(name, argv, timeout=120):
        result = capture(list(map(str, argv)), output / name, timeout)
        if result["exitCode"] or result["timedOut"]:
            raise RuntimeError(f"{name} failed: {output / name}")

    step("compile", [home / "bin/javac", "-proc:none", "-cp", library, "-d", classes,
                     ROOT / "interop/diagnostics/AppleSkinConfigProbe.java"])
    classpath = f"{classes}:{library}"
    config_class = "squeek.appleskin.ModConfig"
    step("jvm", [home / "bin/java", "-cp", classpath, "AppleSkinConfigProbe", config_class])
    if args.native_image:
        entries = json.loads((ROOT / "compiler/reflection-config.json").read_text())
        metadata = output / "reflection-config.json"
        write_json(metadata, [entry for entry in entries if entry["name"] == config_class])
        binary = output / "config-probe"
        step("aot", [home / "bin/native-image", "-J-Xmx1g", "--no-fallback", "-O1",
                     f"-H:ReflectionConfigurationFiles={metadata}", "-cp", classpath,
                     "AppleSkinConfigProbe", binary], 240)
        step("native", [binary, config_class])
    write_json(output / "result.json", {
        "status": "APPLESKIN_CONFIG_ROUNDTRIP_PASS", "jvm": "PASS",
        "desktopAot": "PASS" if args.native_image else "NOT RUN",
        "deviceRun": "NOT RUN", "sourceBuild": str(args.build.resolve()),
        "inputSHA256": {str(path): sha256(path) for path in (
            ROOT / "interop/diagnostics/AppleSkinConfigProbe.java", library,
            ROOT / "compiler/reflection-config.json")},
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=ROOT / "artifacts/b0/prepared-04")
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-image", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
