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

    def test_gpu_read_sites_are_tracked_and_writes_check_hazards(self):
        root = ROOT / "compiler/metal-backend/src/fabricaot/metal"
        render = (root / "MetalRenderPass.java").read_text(encoding="utf-8")
        self.assertIn("bufferHazards.read(vertex.hazard)", render)
        self.assertIn("bufferHazards.read(buffer.hazard)", render)
        self.assertIn("bufferHazards.read(index.hazard)", render)
        encoder = (root / "MetalCommandEncoder.java").read_text(encoding="utf-8")
        self.assertLess(encoder.index("needsProtection(buffer.hazard)"), encoder.index("cloneBuffer("))
        self.assertIn("bufferHazards.renamed(buffer.hazard)", encoder)
        self.assertIn("device.waitForGpu()", encoder)
        self.assertIn("device.bufferHazards.completed()", encoder)
        device = (root / "MetalDevice.java").read_text(encoding="utf-8")
        self.assertIn("MetalNative.synchronize(context);bufferHazards.completed()", device)

    def test_snapshot_limits_match_and_remain_bounded(self):
        root = ROOT / "compiler/metal-backend/src/fabricaot/metal"
        encoder = (root / "MetalCommandEncoder.java").read_text(encoding="utf-8")
        native = (ROOT / "ios/metal-bridge/metal_bridge.m").read_text(encoding="utf-8")
        self.assertIn("MAX_BUFFER_SNAPSHOT_BYTES=1024L*1024", encoder)
        self.assertIn("bytes>1024*1024", native)
        self.assertIn("ctx.snapshotBytesThisFrame+length>16*1024*1024", native)
        self.assertIn("else device.waitForGpu()", encoder)

    def test_copy_uses_snapshot_and_preserves_overlap_semantics(self):
        source = (ROOT / "compiler/metal-backend/src/fabricaot/metal/MetalCommandEncoder.java").read_text(encoding="utf-8")
        copy = source.split("public void copyToBuffer(", 1)[1].split("public void writeToTexture(", 1)[0]
        self.assertLess(copy.index("prepareCpuWrite(d)"), copy.index("nmemmove("))
        self.assertIn("s.mappings!=0||d.mappings!=0", copy)


if __name__ == "__main__":
    unittest.main()
