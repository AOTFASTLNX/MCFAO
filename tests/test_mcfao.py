import io
import json
from datetime import datetime, timezone
from pathlib import Path
import plistlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from mcfao import (Build, device_xcode, export_ipa, load_config, resolve_development_team,
                   select_development_team, tree_files, write_json)
from prepare_fabric_aot import MAX_TRANSFORM_ARCHIVES
from prepare_fabric_aot import inspect_archives, inspect_compatibility, main as prepare_fabric
from prepare_fabric_aot import merge_client, root_mod_ids, runtime_overlay_sources
from prepare_fabric_aot import transformation_checks


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as jar:
        for name, data in entries:
            jar.writestr(name, data)
    return output.getvalue()


class StageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_verified_stage_is_reused_and_tampering_causes_a_new_attempt(self):
        def capture(argv, folder, _timeout):
            folder.mkdir()
            write_json(folder / "command.json", {"argv": argv})
            destination = Path(argv[1])
            destination.mkdir()
            (destination / "result.txt").write_text("complete")
            return {"exitCode": 0, "timedOut": False}

        with patch("mcfao.capture", side_effect=capture) as runner:
            build = Build(self.root, "first")
            first = build.step("fixture", ["builder", "{product}"])
            self.assertEqual(build.step("fixture", ["builder", "{product}"]), first)
            self.assertEqual(runner.call_count, 1)
            (first / "result.txt").write_text("corrupted")
            second = build.step("fixture", ["builder", "{product}"])
            self.assertNotEqual(first, second)
            self.assertEqual((first / "result.txt").read_text(), "corrupted")
            third = Build(self.root, "new inputs").step("fixture", ["builder", "{product}"])
            self.assertNotEqual(second, third)
            self.assertEqual(runner.call_count, 3)

    def test_failed_stage_has_logs_and_no_checkpoint(self):
        def capture(_argv, folder, _timeout):
            folder.mkdir()
            (folder / "stderr.log").write_text("bad dependency")
            (folder / "stdout.log").write_text("")
            return {"exitCode": 2, "timedOut": False}

        with patch("mcfao.capture", side_effect=capture):
            with self.assertRaisesRegex(RuntimeError, "fixture failed.*Logs:"):
                Build(self.root, "key").step("fixture", ["builder", "{product}"])
        self.assertFalse((self.root / "fixture/checkpoint.json").exists())

    def test_development_team_is_selected_from_an_installed_profile(self):
        now = datetime(2026, 11, 11, tzinfo=timezone.utc)
        profiles = [
            {"team": "AAAAAAAAAA", "application": "org.example.app", "name": "expired",
             "expires": datetime(2026, 11, 1, tzinfo=timezone.utc)},
            {"team": "BBBBBBBBBB", "application": "org.example.other", "name": "unrelated",
             "expires": datetime(2026, 12, 1, tzinfo=timezone.utc)},
            {"team": "CCCCCCCCCC", "application": "org.example.app", "name": "current",
             "expires": datetime(2026, 11, 20, tzinfo=timezone.utc)},
            {"team": "DDDDDDDDDD", "application": "org.example.app", "name": "longer",
             "expires": datetime(2026, 11, 28, tzinfo=timezone.utc)},
        ]
        self.assertEqual(select_development_team(profiles, "org.example.app", now), "DDDDDDDDDD")
        # A wildcard profile covers any app on the same team; expired entries never win.
        self.assertEqual(select_development_team(profiles[:1], "*", now), None)

    def test_development_team_override_wins_and_is_validated(self):
        profiles = [{"team": "P57SZ9Z7G2", "application": "org.example.app", "name": "installed",
                     "expires": None}]
        with patch.dict("os.environ", {"MCFAO_DEVELOPMENT_TEAM": "ZZZZZZZZZZ"}):
            self.assertEqual(resolve_development_team("org.example.app", profiles), "ZZZZZZZZZZ")
        with patch.dict("os.environ", {"MCFAO_DEVELOPMENT_TEAM": "not-a-team"}):
            with self.assertRaisesRegex(ValueError, "10-character Apple team identifier"):
                resolve_development_team("org.example.app", profiles)
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "No installed provisioning profile"):
                resolve_development_team("org.example.unknown", profiles)

    def test_device_packaging_passes_the_resolved_team_on_the_command_line(self):
        argv = list(map(str, device_xcode(self.root / "staged", self.root / "assets", team="P57SZ9Z7G2")))
        self.assertIn("DEVELOPMENT_TEAM=P57SZ9Z7G2", argv)
        self.assertEqual(sum(arg.startswith("DEVELOPMENT_TEAM=") for arg in argv), 1)

    def test_tree_hash_rejects_links(self):
        (self.root / "link").symlink_to("/dev/null")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            tree_files(self.root)

    def test_config_rejects_unknown_schema(self):
        path = self.root / "config.json"
        write_json(path, {"loader": "fabric"})
        with self.assertRaisesRegex(ValueError, "Config requires"):
            load_config(path)

    def test_export_rejects_distribution_method_before_creating_output(self):
        options = self.root / "options.plist"
        options.write_bytes(plistlib.dumps({"method": "app-store-connect"}))
        args = SimpleNamespace(build=self.root, output=self.root / "output", export_options=options)
        with self.assertRaisesRegex(ValueError, "method=debugging"):
            export_ipa(args)
        self.assertFalse(args.output.exists())


class FabricInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def jar(self, entries):
        path = self.root / "test.jar"
        path.write_bytes(archive(entries))
        return path

    def test_prepare_reports_the_original_archive_error(self):
        output = self.root / "output"
        stderr = io.StringIO()
        with (patch("prepare_fabric_aot.prepare", side_effect=ValueError("invalid Fabric metadata")),
              patch("sys.stderr", stderr)):
            code = prepare_fabric(["--prepared", str(self.root), "--client", str(self.root / "client.jar"),
                                   "--mods", str(self.root), "--output", str(output), "--inspect"])
        self.assertEqual(code, 2)
        self.assertIn("Fabric preparation failed: invalid Fabric metadata", stderr.getvalue())

    def test_nested_metadata_is_read_without_extracting_archive_paths(self):
        nested = archive([("fabric.mod.json", '{"id":"test_nested","schemaVersion":1}')])
        root = self.jar([("fabric.mod.json", '{"id":"test_parent","schemaVersion":1,'
                         '"jars":[{"file":"META-INF/jars/child.jar"}]}'),
                         ("META-INF/jars/child.jar", nested)])
        report = inspect_archives([root], self.root)
        self.assertEqual([item[1] for item in report], ["test.jar", "test.jar!META-INF/jars/child.jar"])
        self.assertEqual([item[2]["id"] for item in report], ["test_parent", "test_nested"])

    def test_unsafe_archive_member_is_rejected(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod"}'), ("../outside", "content")])
        with self.assertRaisesRegex(ValueError, "Unsafe or duplicate"):
            inspect_archives([root], self.root)

    def test_duplicate_metadata_key_is_rejected(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod","id":"other"}')])
        with self.assertRaisesRegex(ValueError, r"test\.jar!fabric\.mod\.json: Duplicate JSON key"):
            inspect_archives([root], self.root)

    def test_literal_linebreak_in_description_matches_loader(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod","description":"first\nsecond"}')])
        self.assertEqual(inspect_archives([root], self.root)[0][2]["description"], "first\nsecond")

    def test_description_exception_does_not_apply_to_other_fields(self):
        for metadata in ('{"id":"test_mod\nother","description":"first\nsecond"}',
                         '{"id":"test_mod","description":"first\nsecond","jars":[{"file":"bad\n.jar"}]}',
                         '{"id":"test_mod","description":"first\u0000second"}'):
            with self.subTest(metadata=metadata):
                root = self.jar([("fabric.mod.json", metadata)])
                with self.assertRaisesRegex(ValueError, "Invalid control character"):
                    inspect_archives([root], self.root)

    def test_metadata_scan_has_its_own_archive_count_limit(self):
        nested = archive([("fabric.mod.json", '{"id":"test_nested"}')])
        root = self.jar([("fabric.mod.json", '{"id":"test_parent","jars":[{"file":"nested.jar"}]}'),
                         ("nested.jar", nested)])
        with (patch("prepare_fabric_aot.MAX_TRANSFORM_ARCHIVES", 1),
              patch("prepare_fabric_aot.MAX_INSPECTION_ARCHIVES", 2)):
            self.assertEqual(len(inspect_archives([root], self.root, metadata_only=True)), 2)
            attempt = self.root / "transform"
            attempt.mkdir()
            with self.assertRaisesRegex(ValueError, "Fabric archive budget exceeded"):
                inspect_archives([root], attempt)

    def test_compatibility_reports_all_blocked_roots_and_duplicate_ids(self):
        first = self.root / "first!.jar"
        second = self.root / "second.jar"
        for root in (first, second):
            root.write_bytes(archive([("fabric.mod.json", '{"id":"test_mod","schemaVersion":1}')]))
        inventory = inspect_archives([first, second], self.root)
        parsed = [{"id": "test_mod", "client": True, "entrypoints": {stage: []}}
                  for stage in ("preLaunch", "custom-extension")]
        report = inspect_compatibility(inventory, parsed, {first, second})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["rootJarsWithBlockers"], ["first!.jar", "second.jar"])
        self.assertEqual(report["duplicateRootModIds"], {"test_mod": ["first!.jar", "second.jar"]})
        self.assertEqual([item["path"] for item in report["findings"]], ["first!.jar", "second.jar"])

    def test_optional_modmenu_entrypoint_is_recorded_not_rejected(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod","schemaVersion":1}')])
        inventory = inspect_archives([root], self.root)
        parsed = [{"id": "test_mod", "client": True, "mixins": [],
                   "entrypoints": {"modmenu": [{"adapter": "default", "value": "mod.Config"}]}}]
        expected = [{"mod": "test_mod", "stage": "modmenu", "provider": "modmenu",
                     "entrypoint": "mod.Config"}]
        self.assertEqual(transformation_checks(inventory, parsed), expected)
        # The container is unsupported either way, so the stage stays unreachable.
        self.assertEqual(transformation_checks(inventory, parsed, client_ids={"test_mod", "modmenu"}),
                         expected)

    def test_optional_provider_stage_is_skipped_only_when_the_provider_is_absent(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod","schemaVersion":1}')])
        inventory = inspect_archives([root], self.root)
        parsed = [{"id": "test_mod", "client": True, "mixins": [],
                   "entrypoints": {"jei_mod_plugin": [{"adapter": "default", "value": "mod.Jei"}]}}]
        self.assertEqual(transformation_checks(inventory, parsed, client_ids={"test_mod"}),
                         [{"mod": "test_mod", "stage": "jei_mod_plugin", "provider": "jei",
                           "entrypoint": "mod.Jei"}])
        self.assertEqual(transformation_checks(inventory, parsed, client_ids={"test_mod", "jei"}),
                         [{"mod": "test_mod", "stage": "jei_mod_plugin", "provider": "jei",
                           "entrypoint": "mod.Jei",
                           "reason": "custom stage is dispatched by its provider mod or the Loader "
                                     "outside the generated main/client hooks"}])

    def test_transform_budget_covers_the_recollection3_inventory(self):
        # The audited local instance resolves 53 root and 168 nested archives (221 total).
        self.assertGreaterEqual(MAX_TRANSFORM_ARCHIVES, 221)

    def test_fabric_api_namespace_is_distinct_from_the_loader(self):
        metadata = '{"id":"test_mod","schemaVersion":1}'
        parsed = [{"id": "test_mod", "client": True, "entrypoints": {}, "mixins": []}]
        root = self.jar([("fabric.mod.json", metadata),
                         ("net/fabricmc/fabric/api/Example.class", "example")])
        transformation_checks(inspect_archives([root], self.root), parsed)
        root = self.jar([("fabric.mod.json", metadata),
                         ("net/fabricmc/loader/api/Example.class", "example")])
        with self.assertRaisesRegex(ValueError, "Unsupported host configuration"):
            transformation_checks(inspect_archives([root], self.root), parsed)

    def test_custom_stages_are_recorded_and_language_adapters_still_block(self):
        raw = {"schemaVersion": 1}
        root = self.jar([("fabric.mod.json", json.dumps(raw))])
        inventory = inspect_archives([root], self.root)
        metadata = {"client": True, "id": "test_mod", "mixins": [], "entrypoints": {"preLaunch": []}}
        self.assertEqual(transformation_checks(inventory, [metadata]), [])
        metadata["entrypoints"] = {"sodium:config_api_user": [{"adapter": "default", "value": "mod.Hook"}]}
        skipped = transformation_checks(inventory, [metadata])
        self.assertEqual((skipped[0]["stage"], skipped[0]["provider"]),
                         ("sodium:config_api_user", "sodium"))
        self.assertIn("outside the generated main/client hooks", skipped[0]["reason"])
        # A stage named after main/client is a typo, not a third-party consumer.
        metadata["entrypoints"] = {"main:extra": [{"adapter": "default", "value": "mod.Hook"}]}
        with self.assertRaisesRegex(ValueError, "Unsupported lifecycle stage main:extra"):
            transformation_checks(inventory, [metadata])
        metadata["entrypoints"] = {"client": [{"adapter": "custom", "value": "mod.Test"}]}
        with self.assertRaisesRegex(ValueError, "Entrypoint language adapter custom"):
            transformation_checks(inventory, [metadata])

    def test_multi_release_descriptor_and_host_metadata_are_normalised_at_export(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": []}
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("module-info.class", "descriptor"),
                         ("META-INF/versions/9/mod/Api.class", "class"),
                         ("META-INF/services/mod.Platform", "mod.PlatformImpl\n"),
                         ("META-INF/native-image/mod/reflect-config.json", "[]")])
        report = inspect_compatibility(inspect_archives([root], self.root), [metadata], {root})
        self.assertEqual(report["status"], "NO_METADATA_BLOCKERS")
        self.assertEqual(report["normalisedAtExport"]["multiRelease"], ["test_mod"])
        self.assertEqual(report["normalisedAtExport"]["serviceRegistrations"],
                         ["test_mod: mod.Platform"])
        self.assertEqual(report["normalisedAtExport"]["moduleDescriptor"], ["test_mod"])

    def test_resource_paths_reject_traversal_but_allow_spaces(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": []}
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("assets/test_mod/mod icon.png", "png")])
        transformation_checks(inspect_archives([root], self.root), [metadata])
        # The archiver already refuses traversal members, so exercise the guard directly.
        forged = [(root, "test.jar", {"schemaVersion": 1}, ["assets/test_mod/..\\..\\escape.png"])]
        with self.assertRaisesRegex(ValueError, "Unsupported resource path"):
            transformation_checks(forged, [metadata])

    def test_a_nested_copy_of_a_provided_runtime_is_dropped_not_blocked(self):
        metadata = {"client": True, "id": "mixinextras", "entrypoints": {}, "mixins": []}
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}')])
        nested = self.jar([("fabric.mod.json", '{"id":"mixinextras","schemaVersion":1}')])
        inventory = inspect_archives([root], self.root)
        self.assertEqual(transformation_checks(inventory, [metadata], nested=[True])[0]["stage"],
                         "provided")
        with self.assertRaisesRegex(ValueError, "Reserved Fabric/Minecraft dependency identity"):
            transformation_checks(inventory, [metadata], nested=[False])

    def test_mixin_plugin_is_a_build_time_hook_only(self):
        # The real Knot applies the plugin while the image is assembled, so the config is
        # accepted; a parent config still overrides which Mixins Mixin emits.
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": ["test.mixins.json"]}
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("test.mixins.json",
                          '{"required":true,"package":"test.mixin","plugin":"test.Plugin"}')])
        transformation_checks(inspect_archives([root], self.root), [metadata])
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("test.mixins.json",
                          '{"required":true,"package":"test.mixin","parent":"test.Parent"}')])
        with self.assertRaisesRegex(ValueError, "must not use parents or dynamic selectors"):
            transformation_checks(inspect_archives([root], self.root), [metadata])

    def test_declared_refmap_can_be_absent_or_empty_but_cannot_remap(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": ["test.mixins.json"]}
        entries = [("fabric.mod.json", '{"schemaVersion":1}'),
                   ("test.mixins.json", '{"required":true,"package":"test.mixin","refmap":"test.refmap.json"}')]
        for extra in ([], [("test.refmap.json", '{"mappings":{},"data":{}}')]):
            root = self.jar(entries + extra)
            transformation_checks(inspect_archives([root], self.root), [metadata])
        # A populated refmap only matters in development; it is retained and reported, not fatal.
        root = self.jar(entries + [("test.refmap.json", '{"mappings":{"test":{"a":"b"}}}')])
        skipped = transformation_checks(inspect_archives([root], self.root), [metadata])
        self.assertEqual([row["stage"] for row in skipped], ["mixin"])
        self.assertIn("inert outside development", skipped[0]["reason"])

    def test_a_non_required_mixin_config_is_reported_instead_of_blocked(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": ["test.mixins.json"]}
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("test.mixins.json", '{"required":false,"package":"test.mixin"}')])
        skipped = transformation_checks(inspect_archives([root], self.root), [metadata])
        self.assertEqual(skipped[0]["stage"], "mixin")
        self.assertIn("not required:true", skipped[0]["reason"])

    def test_a_declared_language_adapter_is_resolved_at_build_time(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {},
                    "mixins": [], "languageAdapters": {"kotlin": "net.fabricmc.language.kotlin.KotlinAdapter"}}
        raw = {"schemaVersion": 1, "languageAdapters": {"kotlin": "net.fabricmc.language.kotlin.KotlinAdapter"}}
        root = self.jar([("fabric.mod.json", json.dumps(raw))])
        skipped = transformation_checks(inspect_archives([root], self.root), [metadata])
        self.assertEqual(skipped[0]["stage"], "language-adapter")
        self.assertEqual(skipped[0]["provider"], "kotlin")
        raw["languageAdapters"] = {"kotlin": "Not.A.Class::init"}
        root = self.jar([("fabric.mod.json", json.dumps(raw))])
        with self.assertRaisesRegex(ValueError, "must name a class"):
            transformation_checks(inspect_archives([root], self.root), [metadata])

    def test_merge_rejects_unreported_overwrite(self):
        base = self.jar([("net/minecraft/Target.class", "original")])
        overlay = self.root / "overlay.jar"
        overlay.write_bytes(archive([("net/minecraft/Target.class", "modified")]))
        with self.assertRaisesRegex(ValueError, "undocumented client entries"):
            merge_client(base, overlay, self.root / "merged.jar", {})

    def test_merge_accepts_a_declared_resource_override(self):
        # A single jar cannot express pack layering, so a Mod file that replaces a vanilla file
        # is allowed only when the export report listed it.
        base = self.jar([("pack.mcmeta", "{}")])
        overlay = self.root / "overlay.jar"
        overlay.write_bytes(archive([("pack.mcmeta", '{"pack": {"description": "mods"}}')]))
        output = self.root / "merged.jar"
        merge_client(base, overlay, output, {}, ["pack.mcmeta"])
        with zipfile.ZipFile(output) as jar:
            self.assertEqual(json.loads(jar.read("pack.mcmeta"))["pack"]["description"], "mods")
        overlay2 = self.root / "overlay2.jar"
        overlay2.write_bytes(archive([("pack.mcmeta", "{}")]))
        with self.assertRaisesRegex(ValueError, "undocumented client entries: pack.mcmeta"):
            merge_client(base, overlay2, self.root / "merged2.jar", {}, [])

    def test_merge_preserves_resources_and_drops_stale_signatures(self):
        base = self.jar([("META-INF/CLIENT.RSA", "old signature"), ("pack.mcmeta", "{}"),
                         ("net/minecraft/Target.class", "original")])
        overlay = self.root / "overlay.jar"
        overlay.write_bytes(archive([("net/minecraft/Target.class", "modified"),
                                     ("assets/mod/proof.txt", "proof")]))
        output = self.root / "merged.jar"
        merge_client(base, overlay, output, {"net/minecraft/Target.class": {}})
        with zipfile.ZipFile(output) as jar:
            self.assertEqual(jar.read("net/minecraft/Target.class"), b"modified")
            self.assertEqual(jar.read("pack.mcmeta"), b"{}")
            self.assertEqual(jar.read("assets/mod/proof.txt"), b"proof")
            self.assertNotIn("META-INF/CLIENT.RSA", jar.namelist())


class RuntimeOverlayTests(unittest.TestCase):
    """An overlay class implements one Mod's API, so it may only compile when that Mod is present."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def jar(self, name, mod_id):
        path = self.root / name
        path.write_bytes(archive([("fabric.mod.json", json.dumps({"id": mod_id,
                                                                 "schemaVersion": 1}))]))
        return path

    def test_overlay_is_skipped_when_its_mod_is_absent(self):
        roots = [self.jar("other.jar", "othermod")]
        compiled, skipped = runtime_overlay_sources(roots)
        # ModFiles has no Mod dependency, so it compiles for every pack.
        self.assertEqual([p.name for p in compiled], ["ModCatalog.java", "ModFiles.java"])
        self.assertEqual(skipped, [{"source": "mcfao/aot/GenericVertexSerializer.java",
                                    "requiresMod": "sodium"}])

    def test_overlay_compiles_when_its_mod_is_present(self):
        roots = [self.jar("sodium.jar", "sodium")]
        compiled, skipped = runtime_overlay_sources(roots)
        self.assertEqual([p.name for p in compiled],
                         ["GenericVertexSerializer.java", "ModCatalog.java", "ModFiles.java"])
        self.assertEqual(skipped, [])

    def test_root_mod_ids_reads_every_root_jar(self):
        roots = [self.jar("a.jar", "alpha"), self.jar("b.jar", "beta")]
        self.assertEqual(root_mod_ids(roots), {"alpha", "beta"})


if __name__ == "__main__":
    unittest.main()
