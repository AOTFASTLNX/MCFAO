"""Ensure a changed optimization/input is never called a heap-only experiment."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from compare_client_graph_runs import compare


class ClientGraphComparisonTests(unittest.TestCase):
    def fixture(self, root, name, heap):
        # compare() resolves both sides; on macOS TMPDIR is /var/... behind a /private symlink,
        # so the fixture must also write resolved paths or the sandbox-policy check compares two
        # different string forms of the same directory.
        root=Path(root).resolve()
        p=root/name;p.mkdir();(p/"analysis").mkdir()
        (p/"work").mkdir();(p/"work/gc.log").write_text('[time][info][gc] Using Parallel\n')
        (p/"policy.sb").write_text('(allow file-write* "'+str(p)+'/work")')
        (p/"analysis/command.json").write_text(json.dumps({"argv":["native-image",f"-J-Xmx{heap}g","-O1","-o",str(p/"work/client")]}))
        (p/"result.json").write_text(json.dumps({"heapGiB":heap,"classpathSHA256":{"client.jar":"same"},
            "builderSHA256":"same","diagnosticsHelperSHA256":"same","filesSHA256":{"work/caps/a.cap":"same"},
            "sandboxProbe":"PASS","builderJfrEnabled":False}))
        return p

    def test_equal_configuration_and_new_paths_do_not_promote_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=compare(self.fixture(root,"left",6),self.fixture(root,"right",8))
            self.assertEqual(result["status"],"COMPARED")
            self.assertEqual(result["gateC0"],"BLOCKED")
            self.assertEqual(result["gateC1"],"NOT RUN")

    def test_changed_optimization_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=self.fixture(root,"left",6);b=self.fixture(root,"right",8)
            p=b/"analysis/command.json";p.write_text(p.read_text().replace('-O1','-O2'))
            with self.assertRaisesRegex(ValueError,"commandExceptOutputPathAndVariable"):compare(a,b)

    def test_changed_classpath_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=self.fixture(root,"left",6);b=self.fixture(root,"right",8)
            p=b/"result.json";data=json.loads(p.read_text());data["classpathSHA256"]["client.jar"]="changed";p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"sameClasspathFingerprints"):compare(a,b)

    def test_builder_gc_comparison_allows_only_explicit_jvm_collector_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=self.fixture(root,"left",8);b=self.fixture(root,"right",8)
            p=b/"result.json";data=json.loads(p.read_text());data["builderGC"]="g1";data["builderSHA256"]="option-extended";p.write_text(json.dumps(data))
            p=b/"analysis/command.json";data=json.loads(p.read_text());data["argv"][1:1]=["-J-XX:-UseParallelGC","-J-XX:+UseG1GC"];p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"recordedGCMatchesObservedLogs"):compare(a,b,"builder-gc")
            (b/"work/gc.log").write_text('[time][info][gc] Using G1\n')
            result=compare(a,b,"builder-gc")
            self.assertFalse(result["recordedBuilderSourcesIdentical"])
            self.assertTrue(all(result["checks"].values()))
            p.write_text(p.read_text().replace('-O1','-O2'))
            with self.assertRaises(ValueError):compare(a,b,"builder-gc")


if __name__=="__main__":unittest.main()
