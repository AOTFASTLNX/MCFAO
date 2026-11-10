#!/usr/bin/env python3
"""The C0 iOS link step must refuse mismatched runtimes and report undefineds honestly."""
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from link_c0_ios import (RUNTIME_ARCHIVES, jni_entrypoints, link_command, stub_source,  # noqa: E402
                         undefined_symbols, validate_runtime)


class ValidateRuntime(unittest.TestCase):
    def test_accepts_the_verified_device_runtime(self):
        report = {"status": "COMPILED", "target": "arm64-apple-ios17.0"}
        self.assertEqual(validate_runtime(report, "iphoneos"), "arm64-apple-ios17.0")

    def test_rejects_an_uncompiled_runtime(self):
        with self.assertRaises(ValueError):
            validate_runtime({"status": "BLOCKED", "target": "arm64-apple-ios17.0"}, "iphoneos")

    def test_rejects_relabelling_a_simulator_runtime(self):
        with self.assertRaises(ValueError):
            validate_runtime({"status": "COMPILED", "target": "arm64-apple-ios17.0-simulator"},
                             "iphoneos")

    def test_rejects_a_macos_runtime(self):
        with self.assertRaises(ValueError):
            validate_runtime({"status": "COMPILED", "target": "arm64-apple-macos27.2"}, "iphoneos")


class LinkCommand(unittest.TestCase):
    def setUp(self):
        self.command = link_command("arm64-apple-ios17.0", [Path("/w/client-graph.o")],
                                    [Path("/r") / name for name in RUNTIME_ARCHIVES],
                                    Path("/out/client-graph.dylib"), "iphoneos",
                                    "@rpath/FabricAOTClient.dylib")

    def test_links_through_xcrun_with_the_ios_sdk(self):
        self.assertEqual(self.command[:4], ["xcrun", "--sdk", "iphoneos", "clang"])
        self.assertIn("-target", self.command)
        self.assertEqual(self.command[self.command.index("-target") + 1], "arm64-apple-ios17.0")
        self.assertIn("-dynamiclib", self.command)

    def test_carries_every_runtime_archive(self):
        for name in RUNTIME_ARCHIVES:
            self.assertIn(str(Path("/r") / name), self.command)

    def test_sets_a_framework_install_name(self):
        self.assertIn("-Wl,-install_name,@rpath/FabricAOTClient.dylib", self.command)

    def test_never_reuses_the_host_sysroot(self):
        # A macOS sysroot on this line is exactly what made round 34 fail.
        self.assertNotIn("-isysroot", self.command)
        self.assertFalse(any("MacOSX.sdk" in part for part in self.command))


class UndefinedSymbols(unittest.TestCase):
    def test_extracts_names_from_the_ld_report(self):
        log = ("Undefined symbols for architecture arm64:\n"
               '  "_JVM_FindClassFromBootLoader", referenced from:\n'
               '      _Java_net_minecraft_client_main_Main_main in client-graph.o\n'
               '  "_JNI_CreateJavaVM", referenced from:\n'
               '      _main in client-graph.o\n'
               "\nld: symbol(s) not found for architecture arm64\n")
        self.assertEqual(undefined_symbols(log),
                         ["_JNI_CreateJavaVM", "_JVM_FindClassFromBootLoader"])

    def test_clean_link_reports_nothing(self):
        self.assertEqual(undefined_symbols(""), [])
        self.assertEqual(undefined_symbols("ld: warning: -U option is redundant"), [])


class UnsupportedEntrypoints(unittest.TestCase):
    def test_only_jvm_natives_are_stubbable(self):
        stubbable, other = jni_entrypoints([
            "_Java_jdk_net_MacOSXSocketOptions_getSoPeerCred0", "_JNI_OnLoad_extnet",
            "_some_library_function"])
        self.assertEqual(stubbable, ["_Java_jdk_net_MacOSXSocketOptions_getSoPeerCred0",
                                     "_JNI_OnLoad_extnet"])
        self.assertEqual(other, ["_some_library_function"])

    def test_stub_aborts_with_the_symbol_name(self):
        source = stub_source(["_JNI_OnLoad_extnet"])
        self.assertIn("void JNI_OnLoad_extnet(void)", source)
        self.assertIn('fabricaot_unsupported("JNI_OnLoad_extnet")', source)
        self.assertIn("abort();", source)

    def test_stubs_are_sorted_for_stable_output(self):
        source = stub_source(["_Java_b", "_Java_a"])
        self.assertLess(source.index("void Java_a(void)"), source.index("void Java_b(void)"))


if __name__ == "__main__":
    unittest.main()
