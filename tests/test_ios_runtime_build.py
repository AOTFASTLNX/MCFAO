import io
import contextlib
import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_ios_runtime import ios_source, jdk_sources
from capture import capture
from fetch_upstream import extract_source
from link_a1_ios import main as link_main
from verify_evidence import verify
from collect_probe_result import evaluate


class IOSRuntimeBuildTests(unittest.TestCase):
    def test_platform_selection_excludes_other_os_and_overrides_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for platform in ("share", "unix", "macosx", "windows", "linux"):
                base = root / "src/java.base" / platform / "native/libjava"
                base.mkdir(parents=True)
                (base / "Same.c").write_text(platform)
            files = jdk_sources(root, "libjava")
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(), "macosx")

    def test_ios_patches_leave_unrelated_source_unchanged(self):
        source = "/* upstream license */\nint plain(void) { return 25; }\n"
        self.assertEqual(ios_source(source, "Plain.c"), source)

    def test_unavailable_network_header_is_guarded(self):
        source = "/* license */\n#include <net/if_arp.h>\n"
        patched = ios_source(source, "NetworkInterface.c")
        self.assertTrue(patched.startswith("/* license */"))
        self.assertIn("#if !TARGET_OS_IPHONE", patched)

    def test_source_root_must_match_pinned_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                entry = tarfile.TarInfo("repo-wrong/LICENSE")
                entry.size = 1
                out.addfile(entry, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "pinned commit"):
                extract_source(archive, root / "extracted", "a" * 40)
            self.assertFalse((root / "extracted").exists())

    def test_source_traversal_fails_without_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            commit = "a" * 40
            with tarfile.open(archive, "w:gz") as out:
                entry = tarfile.TarInfo("repo-" + commit + "/../../escaped")
                entry.size = 1
                out.addfile(entry, io.BytesIO(b"x"))
            with self.assertRaises(tarfile.FilterError):
                extract_source(archive, root / "extracted", commit)
            self.assertFalse((root / "escaped").exists())

    def test_capture_records_real_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cwd = root / "source"
            cwd.mkdir()
            result = capture([sys.executable, "-c", "from pathlib import Path;print(Path.cwd())"], root / "logs", cwd=cwd)
            self.assertEqual(result["cwd"], str(cwd))
            self.assertEqual((root / "logs/stdout.log").read_text().strip(), str(cwd.resolve()))

    def test_device_runtime_cannot_be_relabelled_as_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "result.json").write_text(json.dumps({"status": "COMPILED", "target": "arm64-apple-ios17.0"}))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit), patch("link_a1_ios.capture") as invoked:
                link_main(["--runtime", str(runtime), "--probe", str(root / "probe"),
                           "--output", str(root / "linked"), "--sdk", "iphonesimulator"])
            invoked.assert_not_called()

    def test_changed_runtime_archive_never_reaches_linker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime, probe = root / "runtime", root / "probe"
            runtime.mkdir()
            probe.mkdir()
            entries = {}
            for name in ("libjava", "libnet", "libnio", "libzip", "libsvm", "libfallback"):
                path = runtime / (name + ".a")
                path.write_bytes(b"native fixture")
                entries[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            (runtime / "libjava.a").write_bytes(b"modified")
            (runtime / "result.json").write_text(json.dumps({"status": "COMPILED", "target": "arm64-apple-ios17.0", "archives": entries}))
            (probe / "result.json").write_text('{"binaries":{"a1probe.o":{}}}')
            with self.assertRaisesRegex(ValueError, "Runtime archive modified"), patch("link_a1_ios.capture") as invoked:
                link_main(["--runtime", str(runtime), "--probe", str(probe), "--output", str(root / "linked")])
            invoked.assert_not_called()

    def test_evidence_verifier_checks_runtime_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "libjava.a"
            archive.write_bytes(b"original")
            log = root / "runtime.log"
            log.write_bytes(b"original report")
            (root / "result.json").write_text(json.dumps({"archives": {"libjava": {"path": str(archive), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}, "filesSHA256": {"runtime.log": hashlib.sha256(log.read_bytes()).hexdigest()}}))
            self.assertEqual(verify(root)["status"], "PASS")
            log.write_bytes(b"modified report")
            self.assertEqual(verify(root)["status"], "FAIL")
            log.write_bytes(b"original report")
            archive.write_bytes(b"modified")
            self.assertEqual(verify(root)["status"], "FAIL")

    def test_native_exit_zero_without_java_marker_does_not_pass(self):
        report = {"status": "PASS", "createIsolate": 0, "runResult": 0, "tearDownIsolate": 0}
        self.assertEqual(evaluate(report, "native exit zero\n")["status"], "BLOCKED")

    def test_simulator_assertions_never_promote_physical_device_gate(self):
        report = {"status": "PASS", "createIsolate": 0, "runResult": 0, "tearDownIsolate": 0}
        result = evaluate(report, "A1_SEMANTICS_PASS\n")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["deviceRun"], "NOT RUN")
        self.assertEqual(result["iosGateA1"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
