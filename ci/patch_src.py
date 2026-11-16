#!/usr/bin/env python3
"""Validate integrated portability contracts in a source checkout; never patch it."""
from __future__ import annotations
import sys
from pathlib import Path


def validate(root):
    root = Path(root).resolve(strict=True)
    required = {
        'tools/build_method_splitter.py': ['compiler/asm.lock.json', 'for spec in'],
        'tools/prepare_shader_toolchain.py': ['developer_dir', 'xcode_tool', "'TMPDIR'"],
        'tools/build_openal_soft.py': ['developer_dir', 'xcode_tool', "'TMPDIR'"],
        'tools/prepare_b0.py': ['--client-dir', 'MCFAO_A0'],
        'tools/probe_client_graph.py': ['-H:+SharedArenaSupport', 'reflection_from_jar', 'MCFAO_OPT_LEVEL'],
        'ios/glfw-lite/uikit_surface.m': ['[NSThread isMainThread]'],
    }
    for relative, anchors in required.items():
        text = (root / relative).read_text()
        if not all(anchor in text for anchor in anchors):
            raise ValueError('Integrated portability contract drift: ' + relative)
    return {'status': 'INTEGRATED_PORTABILITY_VERIFIED', 'sourceMutations': 0}


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('usage: python3 ci/patch_src.py <source-checkout>')
    print(validate(sys.argv[1]))
