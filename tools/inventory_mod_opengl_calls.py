#!/usr/bin/env python3
"""Inventory static LWJGL OpenGL method references without loading mod code."""
import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from inventory_client_native_calls import method_references

MAX_JAR_BYTES = 96 * 1024 * 1024
MAX_CLASS_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 100000


def inventory(paths):
    methods = defaultdict(set)
    inputs = []
    classes = 0
    for path in paths:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JAR_BYTES:
            raise ValueError('unsafe or oversized JAR: ' + str(path))
        with path.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        with zipfile.ZipFile(path) as jar:
            entries = jar.infolist()
            if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_EXPANDED_BYTES:
                raise ValueError('JAR expanded size or entry limit exceeded: ' + str(path))
            for entry in entries:
                if not entry.filename.endswith('.class'):
                    continue
                if entry.file_size > MAX_CLASS_BYTES:
                    raise ValueError('oversized class: ' + entry.filename)
                classes += 1
                for owner, name, descriptor in method_references(jar.read(entry)):
                    if owner.startswith('org/lwjgl/opengl/'):
                        methods[(owner, name, descriptor)].add(path.name + ':' + entry.filename[:-6])
        inputs.append({'name': path.name, 'sha256': digest})
    return {'status': 'STATIC_INVENTORY_ONLY',
            'scope': 'Constant-pool method references in supplied root JARs; does not prove calls execute or OpenGL support; nested JARs are not scanned.',
            'inputs': inputs, 'classFilesScanned': classes,
            'uniqueMethods': len(methods),
            'methods': [{'owner': o, 'name': n, 'descriptor': d, 'referencedBy': sorted(c)}
                        for (o, n, d), c in sorted(methods.items())]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('jars', nargs='+', type=Path)
    args = p.parse_args()
    result = inventory(args.jars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('STATIC_INVENTORY_ONLY classes=%d methods=%d' % (result['classFilesScanned'], result['uniqueMethods']))


if __name__ == '__main__':
    main()
