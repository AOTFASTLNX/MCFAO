"""Execute transformed first-party handlers, including Netty handoff and early returns."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PacketDiagnosticsInjectionTests(unittest.TestCase):
    def test_ios_hardware_diagnostics_keep_cpu_and_storage_without_initializing_oshi(self):
        prepared_path = Path(os.environ.get("MCFAO_TEST_PREPARED", ROOT / "artifacts/b0/prepared-04"))
        prepared_file = prepared_path / "result.json"
        if not prepared_file.is_file():
            self.skipTest("Requires pinned Java 25 / ASM")
        prepared = json.loads(prepared_file.read_text())
        home = Path(prepared["javaHome"])
        asm = [row["path"] for row in prepared["engineLibraries"]
               if Path(row["path"]).name.startswith(("asm-9.", "asm-tree-9."))]
        if not (home / "bin/java").is_file() or len(asm) != 2 or not all(Path(p).is_file() for p in asm):
            self.skipTest("Pinned Java 25 / ASM paths are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixtures = {
                "oshi/SystemInfo.java": """package oshi;
public final class SystemInfo {
    static { if (true) throw new AssertionError("OSHI initialization"); }
}
""",
                "net/minecraft/SystemReport.java": """package net.minecraft;
import java.util.*;
import oshi.SystemInfo;
public final class SystemReport {
    public final Map<String,String> entries = new HashMap<>();
    public SystemReport() { putHardware(new SystemInfo()); }
    public void setDetail(String name, String value) { entries.put(name, value); }
    private void putHardware(SystemInfo ignored) { throw new AssertionError("OSHI hardware"); }
    private void putStorage() { setDetail("storage", "fixture storage"); }
}
""",
                "com/mojang/blaze3d/platform/GLX.java": """package com.mojang.blaze3d.platform;
public final class GLX {
    public static String _getCpuInfo() { return new oshi.SystemInfo().toString(); }
}
""",
                "HardwareCheck.java": """import java.nio.file.*;
import fabricaot.metal.InjectBackend;
public final class HardwareCheck extends ClassLoader {
    Class<?> patch(String path) throws Exception {
        byte[] bytes = InjectBackend.useIosHardwareDiagnostics(Files.readAllBytes(Path.of(path)));
        return defineClass(null, bytes, 0, bytes.length);
    }
    public static void main(String[] args) throws Exception {
        var loader = new HardwareCheck();
        var report = loader.patch(args[0]);
        var entries = (java.util.Map<?,?>) report.getField("entries")
                .get(report.getConstructor().newInstance());
        if (!entries.get("Hardware inventory").toString().endsWith("unavailable on iOS")
                || !"fixture storage".equals(entries.get("storage"))) throw new AssertionError(entries);
        var glx = loader.patch(args[1]);
        String cpu = (String) glx.getMethod("_getCpuInfo").invoke(null);
        String expected = Runtime.getRuntime().availableProcessors() + " logical CPUs, "
                + System.getProperty("os.arch", "unknown");
        if (!expected.equals(cpu)) throw new AssertionError(cpu);
    }
}
""",
            }
            sources = []
            for name, data in fixtures.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data)
                sources.append(path)
            sources.append(ROOT / "compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java")
            subprocess.run([str(home / "bin/javac"), "--release", "25", "-proc:none", "-cp", ":".join(asm),
                            "-d", directory, *sources], check=True, capture_output=True, timeout=60)
            subprocess.run([str(home / "bin/java"), "-Xverify:all", "-cp", ":".join([str(directory), *asm]),
                            "HardwareCheck", directory / "net/minecraft/SystemReport.class",
                            directory / "com/mojang/blaze3d/platform/GLX.class"],
                           check=True, capture_output=True, timeout=60)

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires pinned Java 25 / ASM")
    def test_hooks_run_after_handoff_and_preserve_returns_and_errors(self):
        prepared = json.loads((ROOT / "artifacts/b0/prepared-04/result.json").read_text())
        home = Path(prepared["javaHome"])
        asm = [row["path"] for row in prepared["engineLibraries"]
               if Path(row["path"]).name.startswith(("asm-", "asm-tree-"))]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sources = {
                "fabricaot/diag/PlayDiagnostics.java": '''package fabricaot.diag;
public class PlayDiagnostics {
  public static int begins, ends;
  public static String handler;
  public static void packetBegin(String value) { begins++; handler=value; }
  public static void packetEnd() { ends++; }
}''',
                "net/minecraft/network/protocol/PacketUtils.java": '''package net.minecraft.network.protocol;
public class PacketUtils {
  public static void ensureRunningOnSameThread(Object packet, Object listener, Object processor) {
    if ("handoff".equals(packet)) throw new IllegalStateException("handoff");
  }
}''',
                "fixture/PacketFixture.java": '''package fixture;
import net.minecraft.network.protocol.PacketUtils;
public class PacketFixture {
  public void handlePacket(Object packet) {
    PacketUtils.ensureRunningOnSameThread(packet, this, null);
    if ("early".equals(packet)) return;
    if ("failure".equals(packet)) throw new IllegalArgumentException("original failure");
  }
  public void handleWithoutHandoff(Object packet) {}
}''',
                "fabricaot/metal/PacketCheck.java": '''package fabricaot.metal;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import fabricaot.diag.PlayDiagnostics;
import java.nio.file.*;
import java.lang.reflect.*;
public class PacketCheck extends ClassLoader {
  static void check(boolean value) { if(!value) throw new AssertionError(); }
  public static void main(String[] args) throws Exception {
    ClassNode node=new ClassNode();
    new ClassReader(Files.readAllBytes(Path.of(args[0]))).accept(node,0);
    InjectBackend.instrumentClientHandlers(node);
    ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);node.accept(writer);
    byte[] bytes=writer.toByteArray();
    Class<?> type=new PacketCheck().defineClass("fixture.PacketFixture",bytes,0,bytes.length);
    Object fixture=type.getConstructor().newInstance();
    Method handle=type.getMethod("handlePacket",Object.class);
    try {handle.invoke(fixture,"handoff");throw new AssertionError();}
    catch(InvocationTargetException expected){check(expected.getCause() instanceof IllegalStateException);}
    check(PlayDiagnostics.begins==0 && PlayDiagnostics.ends==0);
    handle.invoke(fixture,"normal");
    handle.invoke(fixture,"early");
    check(PlayDiagnostics.begins==2 && PlayDiagnostics.ends==2);
    check("handlePacket".equals(PlayDiagnostics.handler));
    try {handle.invoke(fixture,"failure");throw new AssertionError();}
    catch(InvocationTargetException expected){check("original failure".equals(expected.getCause().getMessage()));}
    check(PlayDiagnostics.begins==3 && PlayDiagnostics.ends==2);
    type.getMethod("handleWithoutHandoff",Object.class).invoke(fixture,"normal");
    check(PlayDiagnostics.begins==3 && PlayDiagnostics.ends==2);
    handle.invoke(fixture,"normal");
    check(PlayDiagnostics.begins==4 && PlayDiagnostics.ends==3);
    System.out.println("PACKET_DIAGNOSTICS_INJECTION_PASS");
  }
}''',
            }
            paths = []
            for name, text in sources.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                paths.append(path)
            paths.append(ROOT / "compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java")
            subprocess.run([str(home / "bin/javac"), "--release", "25", "-proc:none",
                            "-cp", ":".join(asm), "-d", str(directory), *map(str, paths)],
                           check=True, capture_output=True, text=True, timeout=120)
            result = subprocess.run([str(home / "bin/java"), "-Xverify:all", "-cp",
                                     str(directory) + ":" + ":".join(asm),
                                     "fabricaot.metal.PacketCheck",
                                     str(directory / "fixture/PacketFixture.class")],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PACKET_DIAGNOSTICS_INJECTION_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
