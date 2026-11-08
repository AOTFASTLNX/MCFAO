#!/usr/bin/env python3
"""Inventory static LWJGL method references in the hash-verified local client; execute no game code."""
from __future__ import annotations

import argparse
import json
import struct
import zipfile
from collections import defaultdict
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT


def method_references(data: bytes) -> set[tuple[str, str, str]]:
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("invalid class header")
    position = 8
    def take(count):
        nonlocal position
        if position + count > len(data): raise ValueError("truncated constant pool")
        result = data[position:position+count]; position += count; return result
    def u2(): return struct.unpack(">H", take(2))[0]
    count = u2(); pool = [None] * count; index = 1
    while index < count:
        tag = take(1)[0]
        if tag == 1: pool[index] = take(u2()).decode("utf-8", errors="replace")
        elif tag in (3, 4): take(4)
        elif tag in (5, 6): take(8); index += 1
        elif tag in (7, 8, 16, 19, 20): pool[index] = (tag, u2())
        elif tag in (9, 10, 11, 12, 17, 18): pool[index] = (tag, u2(), u2())
        elif tag == 15: take(3)
        else: raise ValueError("unknown constant-pool tag: " + str(tag))
        index += 1
    references = set()
    try:
        for entry in pool:
            if not isinstance(entry, tuple) or entry[0] not in (10, 11): continue
            owner = pool[pool[entry[1]][1]]
            names = pool[entry[2]]
            name, descriptor = pool[names[1]], pool[names[2]]
            if not all(isinstance(x, str) for x in (owner, name, descriptor)):
                raise ValueError("invalid method reference")
            references.add((owner, name, descriptor))
    except (IndexError, TypeError) as error:
        raise ValueError("invalid constant-pool reference") from error
    return references


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    assets = json.loads((ROOT / "artifacts/evidence/swiftcraft-assets.json").read_text())
    client = Path(assets["clientJar"])
    if sha256(client) != assets["clientSHA256"]:
        parser.error("Client changed from verified 26.1.2 input")
    users = defaultdict(set)
    classes = 0
    renderers = defaultdict(int)
    with zipfile.ZipFile(client) as archive:
        entries = archive.infolist()
        if len(entries) > 100000 or sum(e.file_size for e in entries) > 1024**3:
            parser.error("Client ZIP exceeds bounded scan size")
        for entry in entries:
            if not entry.filename.endswith(".class"): continue
            classes += 1
            if entry.filename.startswith("com/mojang/blaze3d/"):
                renderers[entry.filename.split('/')[3]] += 1
            for owner, name, descriptor in method_references(archive.read(entry)):
                if owner.startswith("org/lwjgl/"):
                    users[(owner, name, descriptor)].add(entry.filename[:-6])
    groups = defaultdict(int)
    methods = []
    for (owner, name, descriptor), callers in sorted(users.items()):
        group = owner.split('/')[2]
        groups[group] += 1
        methods.append({"owner":owner,"name":name,"descriptor":descriptor,"referencingClasses":sorted(callers)})
    result = {"status":"INVENTORIED","gateC0":"BLOCKED","gateC1":"BLOCKED","minecraft":"26.1.2",
              "scope":"static constant-pool method-reference candidates; not runtime coverage or an implemented iOS backend",
              "clientSHA256":assets['clientSHA256'],"classFilesScanned":classes,"uniqueLwjglMethodReferences":len(methods),
              "groups":dict(sorted(groups.items())),"blaze3dClassGroups":dict(sorted(renderers.items())),"methods":methods}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='methods'},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
