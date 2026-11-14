import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from mdaf import (build_native_image_config, canonical, merge_config_entries,
                  merge_agent_metadata, validate_reflection_entries)
from probe_client_graph import collect_mdaf_configuration
from test_config_reflection import class_bytes


class MdafMetadataTests(unittest.TestCase):
    def test_maintained_inferred_and_agent_members_are_unioned_deterministically(self):
        maintained = [{"name": "mod.Test", "methods": [{"name": "read",
                       "parameterTypes": ["java.lang.String"]}],
                       "fields": [{"name": "field0"}], "allDeclaredFields": False}]
        inferred = [{"name": "mod.Test", "methods": [
            {"name": "read", "parameterTypes": ["java.lang.String"]},
            {"name": "read", "parameterTypes": []}],
            "allDeclaredFields": True}]
        agent = {"reflect-config.json": [{"name": "mod.Test", "methods": [
            {"name": "read", "parameterTypes": []}],
            "fields": [{"name": "field0"}]}],
            "resource-config.json": {"resources": {"includes": [{"pattern": "assets/.*"}]}}}
        merged, conflicts = build_native_image_config(maintained, inferred, agent)
        self.assertEqual(conflicts, [])
        self.assertEqual(len(merged["reflect-config.json"]), 1)
        entry = merged["reflect-config.json"][0]
        self.assertEqual(len(entry["methods"]), 2)
        self.assertEqual(len(entry["fields"]), 1)
        self.assertTrue(entry["allDeclaredFields"])
        self.assertIn("resource-config.json", merged)
        again, _ = build_native_image_config(maintained, inferred, agent)
        self.assertEqual(canonical(merged), canonical(again))

    def test_conflicting_scalar_keeps_maintained_value_and_reports_conflict(self):
        merged, conflicts = merge_config_entries(
            [{"name": "mod.Test", "condition": {"typeReachable": "A"}}],
            [{"name": "mod.Test", "condition": {"typeReachable": "B"}}])
        self.assertEqual(merged[0]["condition"]["typeReachable"], "A")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["path"], "mod.Test.condition.typeReachable")

    def test_duplicate_metadata_directories_merge_and_retain_all_categories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            one, two = root / "one", root / "two"
            one.mkdir(); two.mkdir()
            (one / "reflect-config.json").write_text(json.dumps([
                {"name": "mod.Test", "methods": [{"name": "a"}]}]))
            (two / "reflect-config.json").write_text(json.dumps([
                {"name": "mod.Test", "methods": [{"name": "b"}]}]))
            (one / "proxy-config.json").write_text(json.dumps([["mod.Proxy", "mod.Api"]]))
            metadata, conflicts = merge_agent_metadata([one, two])
            self.assertEqual(conflicts, [])
            self.assertEqual([item["name"] for item in metadata["reflect-config.json"][0]["methods"]],
                             ["a", "b"])
            self.assertEqual(metadata["proxy-config.json"], [["mod.Proxy", "mod.Api"]])

    def test_reflection_types_members_and_parameter_signatures_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            jar = Path(temporary) / "fixture.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("mod/Test.class", class_bytes("mod/Test", methods=["read"]))
                archive.writestr("mod/Broken.class", b"not a class")
            report = validate_reflection_entries([
                {"name": "mod.Test", "methods": [
                    {"name": "read", "parameterTypes": []},
                    {"name": "missing", "parameterTypes": []},
                    {"name": "read", "parameterTypes": ["int"]}]},
                {"name": "mod.Absent"},
                {"name": "mod.Broken"},
                {"name": "java.lang.String"}], [jar])
            by_type = {entry["type"]: entry for entry in report["findings"]}
            self.assertEqual(by_type["mod.Test"]["status"], "UNRESOLVED_MEMBERS")
            self.assertEqual(len(by_type["mod.Test"]["members"]), 2)
            self.assertEqual(by_type["mod.Absent"]["status"], "UNRESOLVED_TYPE")
            self.assertEqual(by_type["mod.Broken"]["status"], "INVALID_CLASSFILE")
            self.assertEqual(by_type["java.lang.String"]["status"], "PLATFORM_NOT_ARCHIVE_CHECKED")
            self.assertEqual(report["status"], "REPORT_ONLY_FINDINGS")

    def test_invalid_entries_are_reported_and_non_reflection_agent_categories_survive(self):
        with self.assertRaisesRegex(ValueError, "must contain an array"):
            build_native_image_config([], [], {"reflect-config.json": {"name": "wrong"}})
        report = validate_reflection_entries([None], [])
        self.assertEqual(report["findings"][0]["status"], "INVALID_ENTRY")

    def test_unified_reachability_metadata_without_legacy_reflect_config_is_accepted(self):
        unified = {"reflection": [{"type": "mod.Test"}],
                   "resources": [{"glob": "assets/mod/**"}]}
        merged, conflicts = build_native_image_config(
            [{"name": "mod.Test", "allDeclaredConstructors": True}], [],
            {"reachability-metadata.json": unified})
        self.assertEqual(conflicts, [])
        self.assertEqual(merged["reachability-metadata.json"], unified)
        self.assertEqual(merged["reflect-config.json"], [
            {"name": "mod.Test", "allDeclaredConstructors": True}])
        self.assertEqual(build_native_image_config([], [], {})[0], {})

    def test_aot_configuration_directory_contains_merged_agent_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jar = root / "fixture.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("mod/Test.class", class_bytes("mod/Test", methods=["read"]))
            traced = root / "traced"
            traced.mkdir()
            (traced / "reflect-config.json").write_text(json.dumps([
                {"name": "mod.Test", "methods": [{"name": "read", "parameterTypes": []}]}]))
            (traced / "proxy-config.json").write_text(json.dumps([["mod.Proxy", "mod.Api"]]))
            (traced / "reachability-metadata.json").write_text(json.dumps({
                "reflection": [{"type": "mod.Test", "methods": [
                    {"name": "read", "parameterTypes": []}]}],
                "resources": [{"glob": "assets/mod/**"}],
            }))

            config_dir, report = collect_mdaf_configuration(
                [], [{"name": "mod.Test"}], [traced], [jar], root / "aot-work")

            reflect = json.loads((config_dir / "reflect-config.json").read_text())
            self.assertEqual(reflect, [{"name": "mod.Test", "methods": [
                {"name": "read", "parameterTypes": []}]}])
            self.assertEqual(json.loads((config_dir / "proxy-config.json").read_text()),
                             [["mod.Proxy", "mod.Api"]])
            self.assertEqual(json.loads((config_dir / "reachability-metadata.json").read_text())[
                                 "resources"], [{"glob": "assets/mod/**"}])
            self.assertEqual(report["reflectionCollection"]["tracingEntries"], 2)
            self.assertEqual(report["reflectionCollection"]["tracingEntryCounts"],
                             {"legacyReflection": 1, "unifiedReflection": 1})
            self.assertEqual(report["reflectionResolution"]["checkedTypes"], 2)
            self.assertEqual(report["reflectionResolution"]["unresolvedTypesOrMembers"], 0)
            self.assertEqual(report["reflectionResolution"]["status"],
                             "RESOLVED_IN_SHIPPED_ARCHIVES")
            self.assertEqual(report["policy"], "REPORT_ONLY")
            self.assertTrue((root / "aot-work/mdaf-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
