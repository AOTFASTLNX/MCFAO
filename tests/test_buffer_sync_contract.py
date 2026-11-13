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

    def test_copy_uses_snapshot_and_preserves_overlap_semantics(self):
        source = (ROOT / "compiler/metal-backend/src/fabricaot/metal/MetalCommandEncoder.java").read_text(encoding="utf-8")
        copy = source.split("public void copyToBuffer(", 1)[1].split("public void writeToTexture(", 1)[0]
        self.assertLess(copy.index("prepareCpuWrite(d)"), copy.index("nmemmove("))
        self.assertIn("s.mappings!=0||d.mappings!=0", copy)


if __name__ == "__main__":
    unittest.main()
