"""Keep the login and lazy service-key JSON closure in the effective AOT metadata."""
import json
import contextlib
import io
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mdaf import build_native_image_config
from probe_authlib_json import reflection_entries
from probe_authlib_json import main as probe_main
from external_storage import ExternalStorageUnavailable


class AuthlibReflectionTests(unittest.TestCase):
    def test_login_and_service_key_records_survive_metadata_merging(self):
        maintained = json.loads((ROOT / "compiler/reflection-config.json").read_text())
        documents, conflicts = build_native_image_config(maintained, [], {})
        self.assertFalse(conflicts)
        entries = {entry["name"]: entry for entry in documents["reflect-config.json"]}
        required = {
            "com.mojang.authlib.yggdrasil.YggdrasilServicesKeyInfo$KeySetResponse",
            "com.mojang.authlib.yggdrasil.YggdrasilServicesKeyInfo$KeyData",
            "com.mojang.authlib.yggdrasil.request.JoinMinecraftServerRequest",
            "com.mojang.authlib.yggdrasil.response.HasJoinedMinecraftServerResponse",
            "com.mojang.authlib.yggdrasil.response.ProfileAction",
            "com.mojang.authlib.yggdrasil.response.MinecraftProfilePropertiesResponse",
            "com.mojang.authlib.yggdrasil.response.KeyPairResponse",
            "com.mojang.authlib.yggdrasil.response.KeyPairResponse$KeyPair",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse$Privileges",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse$Privileges$Privilege",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse$ProfanityFilterPreferences",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse$BanStatus",
            "com.mojang.authlib.yggdrasil.response.UserAttributesResponse$BanStatus$BannedScope",
        }
        for name in required:
            with self.subTest(name=name):
                for flag in ("allDeclaredMethods", "allDeclaredConstructors", "allDeclaredFields"):
                    self.assertIs(entries[name].get(flag), True, flag)

    def test_probe_uses_only_authlib_metadata_without_unrelated_mods(self):
        selected = reflection_entries(ROOT / "compiler/reflection-config.json")
        self.assertTrue(selected)
        self.assertTrue(all(item["name"].startswith("com.mojang.authlib.") for item in selected))
        self.assertEqual(len(selected), len({item["name"] for item in selected}))

    def test_missing_external_disk_pauses_before_creating_probe_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe"
            with patch("probe_authlib_json.require_mount",
                       side_effect=ExternalStorageUnavailable("PAUSED: external disk required")):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = probe_main(["--libraries", "missing.jar", "--output", str(output)])
            self.assertEqual(code, 3)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
