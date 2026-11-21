#!/usr/bin/env python3
"""Execute native GL41 fault tests against functions extracted from patched Mesa source."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from capture import ROOT

def function(source: str, name: str, result: str = "bool") -> str:
    start = source.index("static " + result + "\n" + name + "(")
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mesa-source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    source = (a.mesa_source / "src/gallium/frontends/osmesa/osmesa.c").read_text()
    fixture = ROOT / "interop/graphics"
    generated = (fixture / "osmesa_readback_test.c.in").read_text()
    generated = generated.replace("@READBACK@", function(source, "osmesa_read_buffer"))
    generated = generated.replace("@VALIDATE@", function(source, "osmesa_st_framebuffer_validate"))
    (out / "readback.c").write_text(generated)
    zink = (a.mesa_source / "src/gallium/drivers/zink/zink_resource.c").read_text()
    generated_transfer = (fixture / "zink_transfer_test.c.in").read_text()
    generated_transfer = generated_transfer.replace("@CREATE@", function(zink, "create_transfer", "struct zink_transfer *"))
    generated_transfer = generated_transfer.replace("@DESTROY@", function(zink, "destroy_transfer", "void"))
    (out / "transfer.c").write_text(generated_transfer)
    records = []
    def run(name, argv, env=None):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
        (out / (name + ".log")).write_text(result.stdout)
        records.append(dict(name=name, argv=argv, exitCode=result.returncode))
        if result.returncode:
            raise RuntimeError(f"{name} failed: {out / (name + '.log')}")
    flags = ["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
             "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    for name, path, extra in [("readback",out / "readback.c",[]),
            ("transfer",out / "transfer.c",[]),
            ("bridge",fixture / "gl41_bridge_failure_test.c",[]),
            ("config",fixture / "gl41_config_test.m",["-fobjc-arc","-framework","Foundation"]),
            ("vulkan",fixture / "zink_diagnostics_test.c",["-I",str(a.mesa_source.resolve() / "include")])]:
        binary = out / name
        run(name + "-compile", flags + [str(path),*extra,"-o",str(binary)])
        if name != "vulkan":
            run(name,[str(binary)])
        else:
            for mode, settings in {"off":{},"once":{"FAOT_VK_FAIL_AFTER":"0","FAOT_VK_FAIL_COUNT":"1"},
                    "persistent":{"FAOT_VK_FAIL_AFTER":"0","FAOT_VK_FAIL_COUNT":str(2**64-1)},
                    "after":{"FAOT_VK_FAIL_AFTER":"2","FAOT_VK_FAIL_COUNT":"2"}}.items():
                env = {k:v for k,v in os.environ.items() if not k.startswith(("FAOT_VK_FAIL_","FAOT_GL41_DIAGNOSTICS"))}
                env.update(settings)
                env.update(HOME=str(out),FAOT_VK_FAIL_SIZE="13794176")
                run("vulkan-" + mode,[str(binary),mode],env)
    (out / "result.json").write_text(json.dumps({"status":"PASS","mesaSourceSHA256":hashlib.sha256(source.encode()).hexdigest(),
                                               "zinkSourceSHA256":hashlib.sha256(zink.encode()).hexdigest(),
                                               "runs":records},indent=2)+"\n")
    print(f"GL41_NATIVE_FAULT_TESTS_PASS {out}")

if __name__ == "__main__":
    main()
