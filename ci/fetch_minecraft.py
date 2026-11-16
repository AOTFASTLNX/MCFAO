#!/usr/bin/env python3
"""CI entry point for the same owned-client downloader as the desktop app. No synthetic Gates."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--src-root', type=Path, required=True)
    parser.add_argument('--confirm-owned', action='store_true')
    args = parser.parse_args(argv)
    if not args.confirm_owned: parser.error('--confirm-owned is required before downloading game content')
    sys.path.insert(0, str(args.src_root.resolve() / 'tools'))
    from acquire_client import acquire
    acquire(args.out, True)
    return 0


if __name__ == '__main__': raise SystemExit(main())
