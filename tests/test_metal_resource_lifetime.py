"""Source and build-contract checks for the P0 Metal resource lifetime fix."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "ios/metal-bridge/metal_bridge.m"
HEADER = ROOT / "ios/metal-bridge/metal_resources.h"
IMPL = ROOT / "ios/metal-bridge/metal_resources.m"
BUILD = ROOT / "tools/build_metal_backend.py"
LIFETIME_TEST = ROOT / "tests/metal_resource_lifetime_test.m"


class MetalResourceLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.impl = IMPL.read_text(encoding="utf-8")

    def test_transient_paths_use_bounded_pool(self):
        clone = self.bridge.split("MetalNative_cloneBuffer", 1)[1].split("MetalNative_createSampler", 1)[0]
        texel = self.bridge.split("MetalNative_bindTexelBuffer", 1)[1].split("MetalNative_vertexBuffer", 1)[0]
        self.assertIn("acquireTransientBufferOfLength", clone)
        self.assertIn("acquireTransientBufferOfLength", texel)
        self.assertIn("recycleTransientBuffer", texel)
        self.assertIn("recycleOwnedBuffer", self.bridge)
        self.assertIn("deferUntilCompleted", texel)
        self.assertNotIn("newBufferWithLength:stride options:MTLResourceStorageModeShared", texel)

    def test_completion_handler_does_not_capture_context_strongly(self):
        commands = self.bridge.split("static id<MTLCommandBuffer> commands", 1)[1].split("static void commit", 1)[0]
        self.assertIn("__weak FAOTMetalContext *weakCtx", commands)
        self.assertIn("[weakCtx.resources noteCommandBufferCompleted]", commands)

    def test_diagnostics_hold_no_metal_objects_and_log_every_five_seconds(self):
        self.assertIn("FAOTResourceCounters _counters[FAOTResourceCategoryCount]", self.impl)
        self.assertIn("now-_lastSummary<5.0", self.impl)
        self.assertIn("recordFailure:", self.impl)
        self.assertIn("[MetalAllocFailure]", self.impl)
        self.assertIn("currentAllocatedSize", self.impl)
        self.assertIn("in_flight=", self.impl)
        # The only container of Metal objects is the bounded recycle pool.
        self.assertIn("FAOT_POOL_MAX_ENTRIES 64", self.impl)
        self.assertIn("_pool.count<FAOT_POOL_MAX_ENTRIES", self.impl)

    def test_allocation_failure_reports_size_category_and_snapshot(self):
        self.assertIn("requested_bytes=%lu", self.impl)
        self.assertIn("category=%s", self.impl)
        self.assertIn("memorySnapshotLocked", self.impl)

    def test_build_compiles_both_native_sources_and_runs_lifetime_test(self):
        build = BUILD.read_text(encoding="utf-8")
        self.assertIn('"ios/metal-bridge/metal_resources.m"', build)
        self.assertIn('"tests/metal_resource_lifetime_test.m"', build)
        self.assertIn("hostResourceLifetime", build)
        self.assertTrue(LIFETIME_TEST.is_file())
        self.assertIn("METAL_RESOURCE_LIFETIME_PASS", LIFETIME_TEST.read_text(encoding="utf-8"))

    def test_java_release_path_is_single_ownership_boundary(self):
        release = self.bridge.split("MetalNative_release", 1)[1].split("MetalNative_createTexture", 1)[0]
        self.assertIn("__bridge_transfer", release)
        self.assertIn("recycleOwnedBuffer", release)
    def test_java_jni_signatures_are_unchanged(self):
        java = (ROOT / "compiler/metal-backend/src/fabricaot/metal/MetalNative.java").read_text(encoding="utf-8")
        self.assertIn("static native long createTextureView(long texture,int baseMip,int mips);", java)
        self.assertIn("createTextureView(JNIEnv *env,jclass cls,jlong handle,jint base,jint count)", self.bridge)


if __name__ == "__main__":
    unittest.main()
