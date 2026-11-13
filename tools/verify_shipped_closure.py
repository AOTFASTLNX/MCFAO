#!/usr/bin/env python3
"""Report every type a shipped client.jar names in its constant pool but does not contain.

A merged class that names a type outside the jar AND outside the image classpath cannot be
linked; Native Image then silently drops the whole class and every call into it becomes a
run-time error. Skips JDK types and types present on the recorded image classpath.
"""
import argparse, glob, json, os, struct, sys, zipfile
from collections import defaultdict

def cp_class_refs(data):
    i = 8
    cpn = struct.unpack(">H", data[i:i+2])[0]; i += 2
    c = {}; n = 1
    while n < cpn:
        tag = data[i]; i += 1
        if tag == 1:
            ln = struct.unpack(">H", data[i:i+2])[0]
            c[n] = data[i+2:i+2+ln].decode("utf-8", "replace"); i += 2 + ln
        elif tag == 15: i += 3
        elif tag in (5, 6): i += 8; n += 1
        elif tag in (7, 8, 16, 19, 20): i += 2
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18): i += 4
        n += 1
    # Class entries point at Utf8 via 2-byte index; tags 7 store that index
    out = set(); n = 1; i = 8; cpn = struct.unpack(">H", data[i:i+2])[0]; i += 2
    while n < cpn:
        tag = data[i]; i += 1
        if tag == 1:
            ln = struct.unpack(">H", data[i:i+2])[0]; i += 2 + ln
        elif tag == 15: i += 3
        elif tag in (5, 6): i += 8; n += 1
        elif tag == 7:
            idx = struct.unpack(">H", data[i:i+2])[0]; i += 2
            s = c.get(idx)
            if s: out.add(s)
        elif tag in (8, 16, 19, 20): i += 2
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18): i += 4
        n += 1
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jar", required=True)
    p.add_argument("--image-cp", help="command.json of the recorded AOT analysis for the classpath")
    p.add_argument("--output")
    args = p.parse_args()

    cp_jars = []
    if args.image_cp:
        d = json.load(open(args.image_cp))
        argv = d.get("argv", [])
        cp = argv[argv.index("-cp") + 1].split(":")
        cp_jars = [q for q in cp if q.endswith(".jar")]
    outside = set()
    for q in cp_jars:
        try:
            with zipfile.ZipFile(q) as z:
                outside |= {n[:-6] for n in z.namelist() if n.endswith(".class")}
        except zipfile.BadZipFile:
            pass

    present = set(); refs = defaultdict(set)
    with zipfile.ZipFile(args.jar) as z:
        for n in z.namelist():
            if n.endswith(".class") and not n.startswith("module-info"):
                present.add(n[:-6])
        for n in z.namelist():
            if not n.endswith(".class") or n.startswith("module-info"): continue
            for r in cp_class_refs(z.read(n)):
                # Constant-pool Class entries may hold array descriptors; reduce to the
                # component type so "[Lfoo/Bar;" counts as a reference to foo/Bar.
                while r.startswith("["):
                    r = r[1:]
                    if r.startswith("L") and r.endswith(";"):
                        r = r[1:-1]
                if "/" not in r: continue
                if r.startswith(("java/", "javax/", "jdk/", "sun/", "com/sun/", "org/w3c/", "org/xml/", "org/ietf/")): continue
                if r not in present: refs[r].add(n)

    missing = {r: sorted(h) for r, h in refs.items() if r not in outside}
    report = {"jar": args.jar, "classpathJars": len(cp_jars),
              "missingTypes": {k: v for k, v in sorted(missing.items())}}
    text = json.dumps(report, indent=1)
    if args.output:
        open(args.output, "w").write(text)
    print(f"jar 内类数 {len(present)} | 缺失类型 {len(missing)}")
    for r, hosts in sorted(missing.items()):
        print(f"  {r}  <- {len(hosts)} 处, 如 {hosts[0]}")
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
