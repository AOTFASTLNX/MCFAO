import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from aot_cache import cache_key, record, restore
from bootstrap_toolchain import sha256
import mcfao


class AotCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cache = self.root / "cache"
        self.output = self.root / "new-build"
        self.output.mkdir()
        self.inputs = {
            "loader": "fabric", "renderer": "gl41", "target": "ios-arm64", "builderGC": "g1",
            "heapGiB": 9, "parallelism": 4, "optimizationLevel": "-O1",
            "modsSHA256": {"/staged/job-a/fixture.jar": "mod"},
            "filesSHA256": {"/compiler/settings.json": "meta"},
            "instanceSHA256": {"options.txt": "old"},
        }

    def producer(self):
        aot = self.root / "compiled-image"
        (aot / "analysis").mkdir(parents=True)
        image = aot / "client-graph.o"
        image.write_bytes(b"first-party object fixture")
        (aot / "result.json").write_text(json.dumps({
            "targetCodeGeneration": "RELOCATABLE_OBJECT", "analysisExitCode": 0,
            "sandboxProbe": "PASS", "builderGC": "g1",
            "imageObject": {"path": str(image), "sha256": sha256(image)},
        }))
        (aot / "analysis/command.json").write_text(json.dumps({
            "argv": ["native-image", "--no-fallback", "-H:+ExitAfterRelocatableImageWrite",
                     "-O1", "--parallelism=4", "-J-Xmx9g"]
        }))
        (aot / "compatibility.json").write_text('{"schemaVersion": 1}')
        fabric = self.root / "fabric.json"
        fabric.write_text(json.dumps({
            "status": "FABRIC_AOT_INPUT_PREPARED", "renderer": "gl41",
            "modSHA256": self.inputs["modsSHA256"],
        }))
        return aot, image, fabric

    def test_key_reuses_compilation_across_staging_and_packaging_changes(self):
        other_job = {
            **self.inputs, "modsSHA256": {"/staged/job-b/fixture.jar": "mod"},
            "instanceSHA256": {"options.txt": "new"}, "appIcon": {"sha256": "icon"},
            "requestedDevice": "device", "unsigned": True,
        }
        self.assertEqual(cache_key(self.inputs), cache_key(other_job))
        for change in ({"modsSHA256": {"/staged/job-b/fixture.jar": "different bytes"}},
                       {"modsSHA256": {"/staged/job-b/different.jar": "mod"}},
                       {"filesSHA256": {"/compiler/settings.json": "other metadata"}},
                       {"tracingDirectories": ["/first", "/second"]},
                       {"heapGiB": 8}, {"parallelism": 3}, {"optimizationLevel": "-Ob"},
                       {"builderGC": "parallel"}, {"target": "arm64-simulator"}):
            with self.subTest(change=change):
                self.assertNotEqual(cache_key(self.inputs), cache_key({**other_job, **change}))

    def test_reuse_has_original_command_and_independent_artifacts(self):
        key = cache_key(self.inputs)
        aot, image, fabric = self.producer()
        record(self.cache, key, aot, image, fabric)
        new_request = {**self.inputs, "modsSHA256": {"/new/stage/fixture.jar": "mod"}}
        product, report = restore(self.cache, key, self.output, new_request)
        old_command = (aot / "analysis/command.json").read_bytes()
        image.unlink()
        self.assertEqual((product / "analysis/command.json").read_bytes(), old_command)
        self.assertEqual(report.read_bytes(), fabric.read_bytes())
        result = json.loads((product / "result.json").read_text())
        self.assertEqual(Path(result["imageObject"]["path"]), product / "client-graph.o")
        self.assertEqual(sha256(product / "client-graph.o"), result["imageObject"]["sha256"])
        self.assertIsNone(restore(self.cache, key, self.output, new_request))

    def test_corrupted_and_excluded_artifacts_do_not_publish_a_hit(self):
        key = cache_key(self.inputs)
        aot, image, fabric = self.producer()
        record(self.cache, key, aot, image, fabric)
        image.write_bytes(b"modified")
        self.assertIsNone(restore(self.cache, key, self.output, self.inputs))
        fabric.write_text(json.dumps({**json.loads(fabric.read_text()), "excludedMods": {"fixture": ["reason"]}}))
        record(self.cache, key, aot, image, fabric)
        self.assertIsNone(restore(self.cache, key, self.output, self.inputs))
        self.assertEqual(list((self.output / "aot").iterdir()), [])

    def test_quick_build_passes_restored_object_to_runtime_stage(self):
        compiled, image, fabric = self.producer()
        prepared = self.root / "prepared"
        prepared.mkdir()
        (prepared / "result.json").write_text('{"javaHome": "/fixture/java"}')
        mods = self.root / "mods"
        mods.mkdir()
        (mods / "fixture.jar").touch()
        config = {"prepared": prepared}
        manifest = {"filesSHA256": {}, "renderer": "gl41",
                    "runtimeSources": {"jdk": "/fixture/jdk", "graal": "/fixture/graal"}}
        args = SimpleNamespace(output=self.output, mods=mods, loader="fabric", renderer="gl41",
                               device=None, audited_mods=True, prepare_only=False, trace_agent=False,
                               quick_build=True)
        with (patch("mcfao.inputs", return_value=(manifest, self.root / "client.jar", [])),
              patch("mcfao.cache_path", return_value=self.cache),
              patch("mcfao.aot_cache.restore", return_value=(compiled, fabric)),
              patch("mcfao.loader_client") as transform,
              patch("mcfao.compile_client_image") as compile_image,
              patch("mcfao.verify_game_image"),
              patch.object(mcfao.Build, "step", side_effect=RuntimeError("stop at runtime")) as step,
              self.assertRaisesRegex(RuntimeError, "stop at runtime")):
            mcfao.build(args, config)
        transform.assert_not_called()
        compile_image.assert_not_called()
        name, argv = step.call_args.args
        self.assertEqual(name, "runtime")
        self.assertEqual(argv[argv.index("--aot-object") + 1], image)
