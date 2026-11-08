#!/usr/bin/env python3
"""Fetch immutable upstream source revisions as data; execute no build scripts."""
from __future__ import annotations

import json
import ssl
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from bootstrap_toolchain import ROOT, sha256


def extract_source(archive: Path, destination: Path, commit: str):
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        roots = {m.name.split("/")[0] for m in members}
        if len(roots) != 1 or not next(iter(roots)).endswith("-" + commit):
            raise ValueError("Source archive does not match pinned commit root")
        if len(members) > 150000 or sum(m.size for m in members) > 2 * 1024**3:
            raise ValueError("Source archive exceeds inspection budget")
        destination.mkdir(parents=True, exist_ok=False)
        source.extractall(destination, members=members, filter="data")
        return destination / next(iter(roots))


def main():
    lock = json.loads((ROOT / "compiler/upstream.lock.json").read_text())
    output = ROOT / ".cache/upstream"
    output.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context()
    context.load_verify_locations(cafile="/etc/ssl/cert.pem")
    for name in ("jdk", "graal"):
        spec = lock[name]
        url = urlsplit(spec["url"])
        if url.scheme != "https" or url.hostname != "codeload.github.com" or url.username or url.port:
            raise ValueError("Unexpected upstream origin")
        archive = output / (name + "-" + spec["commit"] + ".tar.gz")
        if not archive.exists():
            print(f"Downloading {spec['repository']} at {spec['commit']}", flush=True)
            with urllib.request.urlopen(spec["url"], context=context, timeout=60) as response, archive.with_suffix(".part").open("xb") as dest:
                if response.url != spec["url"] or response.status != 200:
                    raise ValueError("Unexpected source download redirect/status")
                count = 0
                while block := response.read(1024**2):
                    count += len(block)
                    if count > 400 * 1024**2:
                        raise ValueError("Source download exceeds budget")
                    dest.write(block)
            archive.with_suffix(".part").rename(archive)
        if sha256(archive) != spec["archiveSHA256"]:
            raise ValueError("Upstream archive differs from reviewed immutable input")
        destination = output / name
        if not destination.exists():
            path = extract_source(archive, destination, spec["commit"])
        else:
            children = list(destination.iterdir())
            if len(children) != 1 or not children[0].name.endswith("-" + spec["commit"]):
                raise ValueError("Existing source directory is inconsistent")
            path = children[0]
        notices = {p: sha256(path / p) for p in spec["licenseFiles"] if (path / p).is_file()}
        if not notices:
            raise ValueError("No upstream license notice found")
        result = {"repository": spec["repository"], "commit": spec["commit"], "path": str(path),
                  "archiveSHA256": sha256(archive), "archiveBytes": archive.stat().st_size,
                  "transport": "verified HTTPS at immutable upstream revision; observed archive hash",
                  "licenseFilesSHA256": notices}
        (output / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
