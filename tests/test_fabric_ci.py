import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
from check_fabric_result import check
from fetch_locked_mods import check_url

class FabricCIGateTests(unittest.TestCase):
    def fixture(self, root):
        mods=root/"mods";mods.mkdir();jar=mods/"sample.jar";jar.write_bytes(b"mod")
        out=root/"transform";out.mkdir();client=out/"client.jar";client.write_bytes(b"client")
        r={"status":"FABRIC_AOT_INPUT_PREPARED","modSHA256":{str(jar.resolve()):hashlib.sha256(b"mod").hexdigest()},"outputJarSHA256":hashlib.sha256(b"client").hexdigest()}
        return mods,out,r
    def test_verified_transform_and_tampered_mod(self):
        with tempfile.TemporaryDirectory() as d:
            mods,out,r=self.fixture(Path(d));report=out/"result.json";report.write_text(json.dumps(r))
            self.assertEqual(check(report,mods),1)
            (mods/"sample.jar").write_bytes(b"changed")
            with self.assertRaises(ValueError):check(report,mods)
    def test_excluded_mod_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            mods,out,r=self.fixture(Path(d));r["excludedMods"]={"sample":"unsupported"}
            report=out/"result.json";report.write_text(json.dumps(r))
            with self.assertRaises(ValueError):check(report,mods)
    def test_modified_client_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            mods,out,r=self.fixture(Path(d));report=out/"result.json";report.write_text(json.dumps(r))
            (out/"client.jar").write_bytes(b"tampered")
            with self.assertRaises(ValueError):check(report,mods)
    def test_fetch_only_uses_trusted_https_hosts(self):
        self.assertTrue(check_url("https://cdn.modrinth.com/data/test.jar"))
        for url in ("http://cdn.modrinth.com/a", "https://cdn.modrinth.com.evil.invalid/a", "https://user@cdn.modrinth.com/a", "https://127.0.0.1/a"):
            with self.assertRaises(ValueError):check_url(url)

if __name__=="__main__":unittest.main()
