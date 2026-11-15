import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from preflight import scan_pack, safe_archive_path, scan_mod_bytes


def jar_data(*, mixin=False, nested=False, native=False):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        m = {"schemaVersion": 1, "id": "example", "version": "1.0", "mixins": ["example.mixins.json"] if mixin else []}
        if nested:
            m["jars"] = [{"file": "META-INF/jars/lib.jar"}]
        z.writestr("fabric.mod.json", json.dumps(m))
        if native:
            z.writestr("lib/osx/libfoo.dylib", b"not a real library")
    return raw.getvalue()


def pack_data(path, *, minecraft="26.1.2", loader="0.19.3", files=None, extras=None):
    m = {"formatVersion": 1, "game": "minecraft", "name": "Example", "versionId": "1", "dependencies": {"minecraft": minecraft}, "files": files or []}
    if loader:
        m["dependencies"]["fabric-loader"] = loader
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("modrinth.index.json", json.dumps(m))
        z.writestr("overrides/mods/example.jar", jar_data(mixin=True))
        for key, value in (extras or []):
            z.writestr(key, value)


class PreflightTests(unittest.TestCase):
    def test_resource_client_grades_follow_manifest_not_local_default_selection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'graded.mrpack'
            files = [dict(path='mods/' + side + '.jar', hashes=dict(sha1='a' * 40, sha512='b' * 128), downloads=['https://cdn.modrinth.com/data/example.jar'], env=dict(client=side)) for side in ('required', 'optional', 'unsupported')]
            files.append(dict(path='resourcepacks/default.zip', hashes=dict(sha1='a' * 40, sha512='b' * 128), downloads=['https://cdn.modrinth.com/data/resources.zip']))
            pack_data(p, files=files, extras=[('client-overrides/config/a.json', '{}')])
            report = scan_pack(p)
            rows = {r['id']: r for r in report['resources']}
            for side in ('required', 'optional', 'unsupported'):
                self.assertEqual(rows['manifest:mods/' + side + '.jar']['client_requirement'], side)
                self.assertEqual(rows['manifest:mods/' + side + '.jar']['requirement_basis'], 'mrpack_client')
            self.assertEqual(rows['manifest:resourcepacks/default.zip']['client_requirement'], 'required')
            for key in ('overrides:mods/example.jar', 'client-overrides:config/a.json'):
                self.assertEqual(rows[key]['client_requirement'], 'unknown')
                self.assertTrue(rows[key]['default_selected'])
            self.assertEqual(report['resources_fingerprint'], scan_pack(p)['resources_fingerprint'])

    def test_resources_group_packs_keep_shader_files_and_omit_private_instance_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['mods/one.jar', 'shaderpacks/folder/shaders/main.glsl', 'shaderpacks/folder/pack.mcmeta', 'resourcepacks/textures.zip', 'config/example.json', 'saves/private/level.dat', 'accounts.json']:
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(jar_data() if name.endswith('.jar') else b'fixture')
            report=scan_pack(root)
            resources={r['id']:r for r in report['resources']}
            self.assertEqual(resources['local:shaderpacks/folder']['file_count'],2)
            self.assertEqual(resources['local:resourcepacks/textures.zip']['category'],'resourcepacks')
            self.assertFalse(any('private' in name or 'accounts' in name for name in resources))
            self.assertEqual(len(report['resources_fingerprint']),64)

    def test_inventory_lists_remote_sides_without_downloading_resources(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "inventory.mrpack"
            files = [dict(path="mods/" + side + ".jar", hashes=dict(sha1="a" * 40, sha512="b" * 128), downloads=["https://cdn.modrinth.com/data/example.jar"], env=dict(client=side)) for side in ("required", "optional", "unsupported")]
            files.append(dict(path="resourcepacks/resources.zip", hashes=dict(sha1="a" * 40, sha512="b" * 128), downloads=["https://cdn.modrinth.com/data/resources.zip"]))
            pack_data(p, files=files, extras=[("overrides/mods/disabled.jar.disabled", b"never read"), ("overrides/mods/broken.jar", b"broken")])
            report = scan_pack(p)
            rows = {row["path"]: row for row in report["mod_inventory"]}
            self.assertEqual(rows["mods/required.jar"]["status"], "pending_download")
            self.assertNotIn("mod", rows["mods/required.jar"])
            self.assertEqual(rows["mods/optional.jar"]["status"], "skipped_optional")
            self.assertEqual(rows["mods/unsupported.jar"]["status"], "server_only")
            self.assertEqual(rows["overrides/mods/disabled.jar.disabled"]["status"], "disabled")
            self.assertEqual(rows["overrides/mods/broken.jar"]["status"], "unreadable")
            self.assertEqual([f["code"] for f in rows["overrides/mods/broken.jar"]["findings"]], ["INVALID_MOD_JAR"])
            self.assertEqual(rows["overrides/mods/example.jar"]["mod"]["id"], "example")
            self.assertNotIn("INVALID_MOD_JAR", [f["code"] for f in rows["overrides/mods/example.jar"]["findings"]])
            self.assertNotIn("resourcepacks/resources.zip", rows)

    def test_inventory_retains_manifest_failure_on_own_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.mrpack"
            pack_data(p, files=[dict(path="mods/bad.jar", hashes={}, downloads=[])])
            row = scan_pack(p)["mod_inventory"][0]
            self.assertEqual(row["status"], "unreadable")
            self.assertIn("INVALID_HASH_METADATA", [f["code"] for f in row["findings"]])

    def test_inventory_local_disabled_and_symlink_do_not_read_targets(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mods = root / "mods"
            mods.mkdir()
            (mods / "active.jar").write_bytes(jar_data())
            (mods / "disabled.jar.off").write_bytes(b"not a jar")
            (mods / "linked.jar").symlink_to(root / "secret")
            rows = {row["path"]: row for row in scan_pack(root)["mod_inventory"]}
            self.assertEqual(rows["active.jar"]["status"], "metadata_read")
            self.assertEqual(rows["disabled.jar.off"]["status"], "disabled")
            self.assertEqual(rows["disabled.jar.off"]["findings"], [])
            self.assertEqual(rows["linked.jar"]["status"], "unreadable")

    def test_case_sensitive_jar_members_are_reported_without_rejecting_metadata(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("fabric.mod.json", json.dumps({"id":"sample","version":"1"}))
            z.writestr("pkg/A.class", b"A")
            z.writestr("pkg/a.class", b"a")
        findings, mods = [], []
        scan_mod_bytes(data.getvalue(), "sample.jar", findings, mods)
        self.assertEqual(mods[0]["id"], "sample")
        self.assertIn("JAR_CASE_SENSITIVE_ENTRIES", [x["code"] for x in findings])
        self.assertFalse(any(x["severity"] == "error" for x in findings))

    def test_nonstandard_metadata_is_flagged_without_executing_it(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("fabric.mod.json", '{"id":"sample","version":"1","description":"line\nline"}')
        findings, mods = [], []
        scan_mod_bytes(data.getvalue(), "sample.jar", findings, mods)
        self.assertEqual(mods[0]["id"], "sample")
        self.assertIn("MOD_METADATA_NONSTANDARD_JSON", [x["code"] for x in findings])

    def test_nonstandard_metadata_still_rejects_duplicate_keys(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("fabric.mod.json", '{"id":"one","id":"two","version":"1","description":"a\nb"}')
        findings, mods = [], []
        scan_mod_bytes(data.getvalue(), "sample.jar", findings, mods)
        self.assertEqual(mods, [])
        self.assertIn("INVALID_MOD_JAR", [x["code"] for x in findings])

    def test_nonstandard_metadata_rejects_controls_in_execution_fields(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("fabric.mod.json", '{"id":"bad\nid","version":"1","description":"line\nline"}')
        findings, mods = [], []
        scan_mod_bytes(data.getvalue(), "sample.jar", findings, mods)
        self.assertEqual(mods, [])
        self.assertIn("INVALID_MOD_JAR", [x["code"] for x in findings])

    def test_duplicate_jar_entry_is_still_rejected(self):
        import warnings
        data = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(data, "w") as z:
                z.writestr("fabric.mod.json", "{}")
                z.writestr("fabric.mod.json", "{}")
        findings, mods = [], []
        scan_mod_bytes(data.getvalue(), "sample.jar", findings, mods)
        self.assertEqual(mods, [])
        self.assertIn("ZIP_PATH_COLLISION", [x["code"] for x in findings])

    def test_safe_archive_paths(self):
        for p in ("../escape", "/etc/passwd", "C:/system", "a\\b", "a//b", "a/./b", "a/../b", "x\x00z"):
            self.assertFalse(safe_archive_path(p), p)
        self.assertTrue(safe_archive_path("overrides/mods/a.jar"))

    def test_valid_pack_is_only_static_preflight(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            pack_data(p)
            r = scan_pack(p)
            self.assertFalse(r["fatal"], r)
            self.assertEqual(r["mods"][0]["id"], "example")
            self.assertFalse(r["aot_ios_verified"])
            self.assertIn("MIXIN_REQUIRES_AOT_WORK", [f["code"] for f in r["findings"]])

    def test_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            pack_data(p, minecraft="1.20.1")
            self.assertTrue(scan_pack(p)["fatal"])

    def test_loader_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            pack_data(p, loader=None)
            self.assertIn("NOT_FABRIC", [f["code"] for f in scan_pack(p)["findings"]])

    def test_path_traversal_in_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            pack_data(p, files=[{"path": "../../evil.jar", "hashes": {}, "downloads": []}])
            r = scan_pack(p)
            self.assertTrue(r["fatal"])
            self.assertIn("UNSAFE_MANIFEST_PATH", [f["code"] for f in r["findings"]])

    def test_missing_source_is_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            r = scan_pack(Path(d) / "missing.mrpack")
            self.assertTrue(r["fatal"])
            self.assertFalse(r["aot_ios_verified"])

    def test_wrong_manifest_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("modrinth.index.json", '{"formatVersion": 2, "game":"minecraft", "name":"x", "versionId":"1", "dependencies":{"minecraft":"26.1.2","fabric-loader":"0.19.3"},"files":[]}')
            self.assertIn("INVALID_FORMAT_VERSION", [f["code"] for f in scan_pack(p)["findings"]])

    def test_duplicate_zip_member_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            pack_data(p, extras=[("overrides/mods/Example.jar", b"colliding name")])
            r = scan_pack(p)
            self.assertTrue(r["fatal"])
            self.assertIn("ZIP_PATH_COLLISION", [f["code"] for f in r["findings"]])

    def test_zip_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            symlink = zipfile.ZipInfo("overrides/mods/link")
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("modrinth.index.json", "{}")
                z.writestr(symlink, "../../outside")
            self.assertIn("ZIP_SYMLINK", [f["code"] for f in scan_pack(p)["findings"]])

    def test_bad_hash_and_url(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            f = {"path": "mods/test.jar", "hashes": {"sha1": "abc"}, "downloads": ["http://127.0.0.1/bad.jar"]}
            pack_data(p, files=[f])
            codes = {x["code"] for x in scan_pack(p)["findings"]}
            self.assertIn("INVALID_HASH_METADATA", codes)
            self.assertIn("UNSAFE_DOWNLOAD_URL", codes)

    def test_missing_remote_mod_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            f = {"path": "mods/test.jar", "hashes": {"sha1": "a"*40, "sha512": "b"*128}, "downloads": ["https://cdn.modrinth.com/data/mod.jar"], "env": {"client": "required", "server": "unsupported"}}
            pack_data(p, files=[f])
            r = scan_pack(p)
            self.assertFalse(r["fatal"])
            self.assertIn("REMOTE_MOD_METADATA_NOT_FETCHED", {x["code"] for x in r["findings"]})

    def test_nested_jar_and_native_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("modrinth.index.json", json.dumps({"formatVersion": 1, "game": "minecraft", "name": "x", "versionId": "1", "dependencies": {"minecraft": "26.1.2", "fabric-loader": "0.19.3"}, "files": []}))
                z.writestr("overrides/mods/example.jar", jar_data(nested=True, native=True))
            r = scan_pack(p)
            codes = {x["code"] for x in r["findings"]}
            self.assertIn("NESTED_JARS_NOT_SCANNED", codes)
            self.assertIn("NATIVE_LIBRARIES_UNVERIFIED", codes)
            self.assertEqual(r["mods"][0]["nested_jar_count"], 1)

    def test_prism_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "mmc-pack.json").write_text(json.dumps({"components": [{"uid": "net.minecraft", "version": "26.1.2"}, {"uid": "net.fabricmc.fabric-loader", "version": "0.19.3"}]}))
            moddir = p / ".minecraft" / "mods"
            moddir.mkdir(parents=True)
            (moddir / "example.jar").write_bytes(jar_data())
            r = scan_pack(p)
            self.assertFalse(r["fatal"], r)
            self.assertEqual(len(r["mods"]), 1)

    def test_prism_mod_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "mmc-pack.json").write_text(json.dumps({"components": [{"uid": "net.minecraft", "version": "26.1.2"}, {"uid": "net.fabricmc.fabric-loader", "version": "0.19.3"}]}))
            moddir = p / "mods"
            moddir.mkdir()
            other = p / "outside.txt"
            other.write_bytes(jar_data())
            (moddir / "bad.jar").symlink_to(other)
            r = scan_pack(p)
            self.assertTrue(r["fatal"])
            self.assertIn("UNSAFE_MOD_SYMLINK", [f["code"] for f in r["findings"]])

    def test_suspicious_compression_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mrpack"
            with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("modrinth.index.json", "{}")
                z.writestr("overrides/zeroes.bin", b"\0" * (2 * 1024 * 1024))
            self.assertIn("SUSPICIOUS_COMPRESSION", [f["code"] for f in scan_pack(p)["findings"]])


if __name__ == "__main__":
    unittest.main()
