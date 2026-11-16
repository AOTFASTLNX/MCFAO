"""Stage a source-only runtime tree; never traverse assets, credentials or generated trees."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TREES = {'tools', 'compiler', 'interop', 'ios', 'tests', 'ci', 'docs'}
EXTENSIONS = {'.py', '.java', '.c', '.cpp', '.cc', '.m', '.mm', '.h', '.hpp', '.swift', '.json',
              '.md', '.txt', '.sh', '.plist', '.pbxproj', '.xcscheme', '.xcworkspacedata',
              '.xcconfig', '.glsl', '.metal', '.fsh', '.vsh', '.css', '.cmake', '.classtweaker', '.accesswidener'}
EXCLUDED = {'target', 'node_modules', '__pycache__', '.codex', 'xcuserdata',
            'evidence', 'artifacts', 'saves', 'accounts', '.cache', '.git'}


def allowed(name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or any(x in EXCLUDED or x.startswith('._') for x in p.parts): return False
    if 'build' in p.parts and not name.startswith('interop/fabric/tool/mcfao/build/'): return False
    if 'assets' in p.parts and not name.startswith('interop/fabric/fixture/resources/assets/'): return False
    if name in ('AGENTS.md', 'README.md', 'LICENSE', 'LICENSE.md', 'NOTICE'): return True
    return (p.parts[0] in TREES and p.suffix in EXTENSIONS
            and not any(x in p.name.lower() for x in ('credential', 'token', 'secret', '.local.', '.env')))


def stage(output, root=ROOT):
    output = Path(output).absolute()
    # Only a fresh destination can be staged. Existing source packages remain reviewable.
    output.mkdir(parents=True, exist_ok=False)
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
    files = {}
    for name in sorted(set(filter(allowed, filter(None, names)))):
        source = root / name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError('Bundle source must be a regular project file: ' + name)
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ('tools/mcfao.py', 'tools/desktop_workbench.py', 'tools/first_run.py', 'compiler/asm.lock.json',
                 'interop/b0/src/fabricaot/b0/ParentEntrypoint.java',
                 'interop/fabric/tool/mcfao/build/AotExport.java', 'interop/b0/resources/fabricaot-b0.classtweaker',
                 'interop/fabric/fixture/resources/assets/mcfao_fixture/proof.txt',
                 'ios/C0Harness/C0Harness.xcodeproj/project.pbxproj'):
        if name not in files: raise ValueError('Missing bundled source: ' + name)
    manifest = dict(schemaVersion=1, sourceCommit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                    sourceDiffSHA256=hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD', '--'], cwd=root)).hexdigest(),
                    filesSHA256=files, gameContent='EXCLUDED', credentials='EXCLUDED')
    (output / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def source_identity(root=ROOT):
    manifest = root / 'bundle-manifest.json'
    if not manifest.is_file():
        return dict(sourceCommit=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                    sourceDiffSHA256=hashlib.sha256(subprocess.check_output(['git', '-C', str(root), 'diff', 'HEAD', '--'])).hexdigest())
    data = json.loads(manifest.read_text())
    actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
              if p.is_file() and p.name != 'bundle-manifest.json' and '__pycache__' not in p.parts}
    if any(p.is_symlink() for p in root.rglob('*')) or actual != data['filesSHA256']:
        raise ValueError('Bundled source content differs from its build manifest')
    return {key: data[key] for key in ('sourceCommit', 'sourceDiffSHA256')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({'files': len(stage(args.output)['filesSHA256']), 'output': str(args.output)}))
