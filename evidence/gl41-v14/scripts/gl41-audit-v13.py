import hashlib
import plistlib
import struct
import sys
import zipfile
from pathlib import Path

ipa, expected = Path(sys.argv[1]), sys.argv[2].lower()
with ipa.open('rb') as f:
    digest = hashlib.file_digest(f, 'sha256').hexdigest()
assert digest == expected, (digest, expected)
with zipfile.ZipFile(ipa) as z:
    assert z.testzip() is None
    root = 'Payload/C0Harness.app/'
    info = plistlib.loads(z.read(root + 'Info.plist'))
    names = z.namelist()
    assert not any(n.startswith(root) and ('/_CodeSignature/' in n or n.endswith('/embedded.mobileprovision')) for n in names)
    binaries = [root + info['CFBundleExecutable']]
    binaries += [root + 'Frameworks/' + n for n in (
        'client-graph.dylib', 'libglfw.dylib', 'liblwjgl_opengl.dylib', 'libOSMesa.8.dylib', 'libMoltenVK.dylib')]
    for binary in binaries:
        with z.open(binary) as f:
            magic, cpu, _, _, count, size, _, _ = struct.unpack('<8I', f.read(32))
            assert (magic, cpu) == (0xfeedfacf, 0x0100000c), binary
            commands = f.read(size)
            offset = 0
            for i in range(count):
                command, length = struct.unpack_from('<2I', commands, offset)
                assert 8 <= length <= len(commands) - offset
                assert command != 0x1d, binary
                offset += length
            if binary.endswith('/libglfw.dylib'):
                contents = f.read()
                for marker in (b'[GL41] display fps=', b'[GL41] refresh request=', b'org.fabricaot.gl41.present'):
                    assert marker in contents, marker
            if binary.endswith('/client-graph.dylib'):
                contents = f.read()
                for marker in (b'configuration_to_play', b'level_load_ready', b'client_tick_stall', b'frame limiter=fixed-timeline'):
                    assert marker in contents, marker
                assert b'frame limiter caps' not in contents
    assert root + 'assets/indexes/30.json' in names
print(f'{ipa.stat().st_size} bytes | SHA-256 {digest}')
print(f"Bundle {info['CFBundleIdentifier']} | ZIP pass | arm64 unsigned | GL41 native libraries and join diagnostics verified")

