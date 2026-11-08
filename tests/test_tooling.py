import hashlib
import io
import json
import struct
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bootstrap_toolchain import extract_jdk, fetch, validate_url
from capture import capture
from doctor import client_metadata
from inspect_ios_candidate import archive_platforms, inspect
from verify_evidence import verify


def ar_object(platform=2, cpu=0x100000c):
    macho = struct.pack("<IIIIIIII", 0xfeedfacf, cpu, 0, 1, 1, 24, 0, 0)
    macho += struct.pack("<IIIIII", 0x32, 24, platform, 0x110000, 0x1b0000, 0)
    header = f"{'probe.o/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(macho):<10}`\n".encode()
    return b"!<arch>\n" + header + macho


class ToolingTests(unittest.TestCase):
    def test_fixed_url_policy(self):
        validate_url("https://github.com/graalvm/graalvm-ce-builds/releases/download/test/jdk.tar.gz")
        for url in ("http://github.com/a", "https://127.0.0.1/a", "https://github.com:8443/a",
                    "https://github.com.evil.example/a", "https://user@github.com/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_cached_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jdk.tar.gz"
            path.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "failed pinned hash"):
                fetch({"url": "https://github.com/a", "size": 8, "sha256": "0" * 64}, path)
            self.assertEqual(path.read_bytes(), b"modified")

    def test_cached_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "source"
            target.write_text("preserve")
            link = root / "download"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                fetch({"url": "https://github.com/a"}, link)
            self.assertEqual(target.read_text(), "preserve")

    def test_tar_traversal_fails_without_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                member = tarfile.TarInfo("../escaped")
                member.size = 1
                out.addfile(member, io.BytesIO(b"x"))
            with self.assertRaises(tarfile.FilterError):
                extract_jdk(archive, root / "jdk")
            self.assertFalse((root / "escaped").exists())

    def test_tar_escaping_link_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                member = tarfile.TarInfo("link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../outside"
                out.addfile(member)
            with self.assertRaises(tarfile.FilterError):
                extract_jdk(archive, root / "jdk")

    def test_capture_preserves_failure_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            result = capture([sys.executable, "-c", "import sys; print('diagnostic'); sys.exit(7)"], Path(directory) / "run")
            self.assertEqual(result["exitCode"], 7)
            self.assertFalse(result["timedOut"])
            self.assertEqual((Path(directory) / "run/stdout.log").read_text(), "diagnostic\n")
            self.assertEqual(result["logs"]["stdout.log"]["sha256"], hashlib.sha256(b"diagnostic\n").hexdigest())

    def test_capture_timeout_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = capture([sys.executable, "-c", "import time; time.sleep(10)"], Path(directory) / "run", timeout=1)
            self.assertTrue(result["timedOut"])
            self.assertNotEqual(result["exitCode"], 0)

    def test_capture_missing_executable_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = capture([str(Path(directory) / "missing")], Path(directory) / "run")
            self.assertEqual(result["exitCode"], 127)
            self.assertTrue((Path(directory) / "run/command.json").is_file())

    def test_capture_will_not_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                capture([sys.executable, "-c", "pass"], Path(directory))

    def test_modified_log_cannot_pass_evidence_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture([sys.executable, "-c", "print('original')"], root / "run")
            self.assertEqual(verify(root)["status"], "PASS")
            (root / "run/stdout.log").write_text("modified\n")
            self.assertEqual(verify(root)["status"], "FAIL")

    def test_macho_ios_architecture(self):
        self.assertEqual(archive_platforms(ar_object())[0]["platform"], 2)
        self.assertEqual(archive_platforms(ar_object())[0]["cpu"], "0x100000c")

    def test_malformed_static_archive_rejected(self):
        for data in (b"not an archive", b"!<arch>\n", ar_object()[:-1]):
            with self.subTest(data=data[:12]), self.assertRaises(ValueError):
                archive_platforms(data)

    def test_client_inventory_does_not_read_account_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version = root / "versions/26.1.2"
            version.mkdir(parents=True)
            (version / "26.1.2.json").write_text(json.dumps({"id": "26.1.2", "javaVersion": {"majorVersion": 25}}))
            # Intentionally invalid: account files must never be parsed here.
            (root / "launcher_accounts.json").write_bytes(b"\xffprivate")
            result = client_metadata(root)
            self.assertEqual(result["version"], "26.1.2")
            self.assertEqual(result["ownership"], "NOT CHECKED")
            self.assertFalse(result["clientJarPresent"])

    def candidate(self, directory, platform=2, tamper=False):
        root = Path(directory)
        spec = {"requiredGraalVM": "25.0.2", "jdkSourceCommit": "a" * 40,
                "graalSourceCommit": "b" * 40, "licenseStatus": "UNKNOWN"}
        files = {"libjava-release.a": ar_object(platform), "caps/one.cap": b"CAP",
                 "caps/cap-cache-files.txt": b"one.cap\n"}
        manifest = {"jdkVersion": "25", "graalVmVersion": "25.0.2", "labsOpenJdkCommit": "a" * 40,
                    "graalCommit": "b" * 40, "artifacts": ["libjava-release.a", "caps/one.cap"],
                    "capCacheIndex": "caps/cap-cache-files.txt"}
        checksums = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in files.items())
        if tamper:
            files["caps/one.cap"] = b"modified"
        files["manifest.json"] = json.dumps(manifest).encode()
        files["SHA256SUMS"] = checksums.encode()
        path = root / "candidate.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        spec.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return path, spec

    def test_static_integrity_never_verifies_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect(*self.candidate(directory))
            self.assertEqual(result["staticIntegrity"], "PASS")
            self.assertEqual(result["runtimeCompatibility"], "UNKNOWN")
            self.assertEqual(result["gateA1"], "BLOCKED")
            self.assertFalse(result["executionAllowed"])

    def test_macos_archive_cannot_pass_as_ios(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not exclusively arm64/iOS"):
                inspect(*self.candidate(directory, platform=1))

    def test_inner_corruption_rejected_despite_valid_outer_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Inner checksum mismatch"):
                inspect(*self.candidate(directory, tamper=True))


if __name__ == "__main__":
    unittest.main()
