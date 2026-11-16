"""Validate the actual GLFW renderer ABI, including old binaries with valid hashes."""
from __future__ import annotations
from pathlib import Path
import subprocess

CONTRACT = b'FAOT_GLFW_CLIENT_APIS:v1:NO_API,OPENGL_OSMESA'
GL41_EXPORTS = frozenset({'faot_glfw_client_api_contract', 'faot_gl41_make_current',
                         'faot_gl41_swap', 'faot_gl41_release'})


def validate_bytes(data, symbols, renderer):
    if renderer not in ('gl41', 'metal'): raise ValueError('Unknown renderer: ' + str(renderer))
    if renderer == 'gl41':
        missing = GL41_EXPORTS - symbols
        if CONTRACT + b'\0' not in data or missing:
            raise ValueError('GL41 requires the OpenGL/OSMesa GLFW bridge; rebuild libglfw.dylib '
                             '(an older Metal-only library cannot create this window). Missing exports: ' + str(sorted(missing)))
    return dict(renderer=renderer, status='GLFW_RENDERER_ABI_VERIFIED',
                contract=CONTRACT.decode() if renderer == 'gl41' else 'NO_API')


def validate_glfw_renderer(path: Path, renderer: str):
    if renderer == 'metal': return validate_bytes(b'', set(), renderer)
    text = subprocess.check_output(['xcrun', 'nm', '-gUj', str(path)], text=True)
    symbols = {line.split()[-1].removeprefix('_') for line in text.splitlines() if line.split()}
    return validate_bytes(Path(path).read_bytes(), symbols, renderer)
