import io
import json
from pathlib import Path
import plistlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from mcfao import Build, export_ipa, load_config, tree_files, write_json
from prepare_fabric_aot import inspect_archives, inspect_compatibility, main as prepare_fabric
from prepare_fabric_aot import merge_client, transformation_checks


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

    def test_optional_modmenu_entrypoint_requires_the_provider_to_be_absent(self):
        root = self.jar([("fabric.mod.json", '{"id":"test_mod","schemaVersion":1}')])
        inventory = inspect_archives([root], self.root)
        parsed = [{"id": "test_mod", "client": True, "entrypoints": {"modmenu": []}, "mixins": []}]
        transformation_checks(inventory, parsed)
        with self.assertRaisesRegex(ValueError, "Unsupported lifecycle stage modmenu"):
            transformation_checks(inventory, parsed, client_ids={"test_mod", "modmenu"})

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

    def test_prelaunch_and_custom_adapters_are_blocked(self):
        raw = {"schemaVersion": 1}
        root = self.jar([("fabric.mod.json", json.dumps(raw))])
        inventory = inspect_archives([root], self.root)
        metadata = {"client": True, "id": "test_mod", "entrypoints": {"preLaunch": []}}
        with self.assertRaisesRegex(ValueError, "Unsupported lifecycle stage preLaunch"):
            transformation_checks(inventory, [metadata])
        metadata["entrypoints"] = {"client": [{"adapter": "custom", "value": "mod.Test"}]}
        with self.assertRaisesRegex(ValueError, "Entrypoint must be a public Java class"):
            transformation_checks(inventory, [metadata])

    def test_plugin_mixin_config_is_rejected_before_knot(self):
        root = self.jar([("fabric.mod.json", '{"schemaVersion":1}'),
                         ("test.mixins.json", '{"required":true,"plugin":"mod.Plugin"}')])
        inventory = inspect_archives([root], self.root)
        with self.assertRaisesRegex(ValueError, "plugin-free"):
            transformation_checks(inventory, [{"client": True, "id": "test_mod",
                                                "entrypoints": {}, "mixins": ["test.mixins.json"]}])

    def test_declared_refmap_can_be_absent_or_empty_but_cannot_remap(self):
        metadata = {"client": True, "id": "test_mod", "entrypoints": {}, "mixins": ["test.mixins.json"]}
        entries = [("fabric.mod.json", '{"schemaVersion":1}'),
                   ("test.mixins.json", '{"required":true,"package":"test.mixin","refmap":"test.refmap.json"}')]
        for extra in ([], [("test.refmap.json", '{"mappings":{},"data":{}}')]):
            root = self.jar(entries + extra)
            transformation_checks(inspect_archives([root], self.root), [metadata])
        root = self.jar(entries + [("test.refmap.json", '{"mappings":{"test":{"a":"b"}}}')])
        with self.assertRaisesRegex(ValueError, "use official names"):
            transformation_checks(inspect_archives([root], self.root), [metadata])

    def test_merge_rejects_unreported_overwrite(self):
        base = self.jar([("net/minecraft/Target.class", "original")])
        overlay = self.root / "overlay.jar"
        overlay.write_bytes(archive([("net/minecraft/Target.class", "modified")]))
        with self.assertRaisesRegex(ValueError, "undocumented client entries"):
            merge_client(base, overlay, self.root / "merged.jar", {})

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


if __name__ == "__main__":
    unittest.main()
