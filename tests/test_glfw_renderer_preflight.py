"""Exercise the launcher's real preflight against first-party shared-library fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('clang'), 'macOS clang required')
class GLFWRendererPreflightTests(unittest.TestCase):
    def test_native_host_accepts_current_abi_and_stops_old_or_incorrect_bridges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            driver = root / 'driver.c'
            driver.write_text('''#include "renderer_preflight.h"
int main(int argc, char **argv) {
    if (argc != 2) return 9;
    char reason[512] = {0};
    int accepted = FAOTRequireGL41Bridge(argv[1], reason, sizeof reason);
    fprintf(stderr, "%s\\n", reason);
    return accepted ? 0 : 4;
}
''')
            executable = root / 'driver'
            subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT / 'ios/C0Harness'),str(driver),'-o',str(executable)],check=True,capture_output=True)
            cases = {
                'current':'const char *faot_glfw_client_api_contract(void){return "FAOT_GLFW_CLIENT_APIS:v1:NO_API,OPENGL_OSMESA";}',
                'old':'int glfwInit(void){return 1;}',
                'wrong':'const char *faot_glfw_client_api_contract(void){return "NO_API";}',
                'null':'const char *faot_glfw_client_api_contract(void){return 0;}',
            }
            for name, code in cases.items():
                with self.subTest(name=name):
                    directory = root / name; directory.mkdir()
                    source = directory / 'fixture.c'; source.write_text(code)
                    subprocess.run(['clang','-dynamiclib',str(source),'-o',str(directory / 'libglfw.dylib')],check=True,capture_output=True)
                    env = {k:v for k,v in os.environ.items() if not k.startswith('DYLD_')}
                    run = subprocess.run([str(executable),str(directory)],env=env,capture_output=True,text=True)
                    self.assertEqual(run.returncode, 0 if name == 'current' else 4, run.stderr)
                    if name == 'current': self.assertIn('glfwClientAPIs=', run.stdout)
                    else: self.assertIn('GL41 requires the OpenGL/OSMesa GLFW bridge',run.stderr)


if __name__ == '__main__': unittest.main()
