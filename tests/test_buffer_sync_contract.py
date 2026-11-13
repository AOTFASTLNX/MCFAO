"""Guard the CPU-owned buffer invariant required by nonblocking reads/copies."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BufferSyncContractTests(unittest.TestCase):
    def test_texture_readback_completes_before_cpu_updates_destination(self):
        source = (ROOT / "ios/metal-bridge/metal_bridge.m").read_text(encoding="utf-8")
        readback = source.split("Java_fabricaot_metal_MetalNative_readTexture", 1)[1].split(
            "Java_fabricaot_metal_MetalNative_copyTexture", 1
        )[0]
        self.assertIn("toBuffer:staging", readback)
        self.assertLess(readback.index("submitAndWait(env,ctx)"), readback.index("buffer(destination).contents"))

    def test_fence_reuse_requires_no_pending_commands_and_invalidation_on_commit(self):
        source = (ROOT / "ios/metal-bridge/metal_bridge.m").read_text(encoding="utf-8")
        fence = source.split("Java_fabricaot_metal_MetalNative_createFence", 1)[1].split(
            "Java_fabricaot_metal_MetalNative_awaitFence", 1
        )[0]
        self.assertIn("if(!ctx.pending && ctx.lastFence)", fence)
        self.assertIn("return keep(ctx.lastFence)", fence)
        self.assertIn("ctx.lastFence=fence;[pending commit]", fence)
        sync = source.split("static BOOL submitAndWait", 1)[1].split("static NSUInteger pixelBytes", 1)[0]
        self.assertIn("if(ctx.pending){ctx.lastFence=nil;", sync)
        present = source.split("Java_fabricaot_metal_MetalNative_presentFrame", 1)[1]
        self.assertIn("ctx.lastFence=nil;ctx.lastCommitted=pending", present)

    def test_copy_uses_snapshot_and_preserves_overlap_semantics(self):
        source = (ROOT / "compiler/metal-backend/src/fabricaot/metal/MetalCommandEncoder.java").read_text(encoding="utf-8")
        copy = source.split("public void copyToBuffer(", 1)[1].split("public void writeToTexture(", 1)[0]
        self.assertLess(copy.index("prepareCpuWrite(d)"), copy.index("nmemmove("))
        self.assertIn("s.mappings!=0||d.mappings!=0", copy)


if __name__ == "__main__":
    unittest.main()
