"""Discover the selected Xcode and optional artifact registry without changing the host."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess


def developer_dir(required=True):
    try:
        value = os.environ.get('DEVELOPER_DIR') or subprocess.check_output(
            ['xcode-select', '-p'], text=True, timeout=15).strip()
        path = Path(value)
        if not path.is_dir(): raise ValueError('Selected Xcode directory does not exist')
        return path.resolve()
    except (OSError, ValueError, subprocess.SubprocessError):
        if required: raise ValueError('Select an installed Xcode with xcode-select or DEVELOPER_DIR')
        return None


def xcode_tool(name, sdk='macosx'):
    try:
        return subprocess.check_output(['xcrun', '--sdk', sdk, '--find', name], text=True, timeout=15).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Selected Xcode is missing required compiler tool: ' + name) from exc


def aar_program():
    return shutil.which('aar')
