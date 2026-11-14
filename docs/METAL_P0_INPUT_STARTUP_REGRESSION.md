# Input polling startup regression — 2026-11-14

User device log run-1794657721770.log completes initial resource reload and
renders before crashing in malilib's post-keyboard tick. The fatal call is
GLFW.glfwGetMouseButton → JNI.invokePI(JIJ)I, with a missing native pointer.
The selected historical glfw-ios-world-01/libglfw.dylib does not export
glfwGetMouseButton, although ios/glfw-lite/glfw_lite.c implements the query.
The vanilla call inventory did not require this Mod polling API.

Rebuild GLFW from the existing state implementation. Require mouse button,
key and cursor polling exports during bridge generation and full-game input
validation. Require the LWJGL report's GLFW hash to match the selected binary.
Keep the null-pointer error and actual input semantics intact. Resolve Java's
toolchain physical path so the execution allowlist matches the executable
through worktree cache symlinks, retaining the default-deny sandbox policy.

Local evidence under artifacts/:

- metal-p0-input-python-01.log: 317 tests, 314 passed, 3 skipped.
- graphics/glfw-p0-input-01/result.json: iOS build and sanitized host state
  tests passed, including press/release/focus transitions.
- graphics/lwjgl-p0-input-03/result.json: iOS native build, host JNI bridge,
  real Minecraft window and NativeImage fixtures passed. The JNI probe runs
  300 ticks × 8 mouse buttons through the exact failing Java/native call.

The device log reports at 15 seconds: Metal currentAllocatedSize 328105984,
tracked live bytes 241192480, idle pool 27757120, transient allocated 27832384,
zero allocation failures. At 300 submits CPU sync wait is 0.000 ms/submit,
sync_count is 0, snapshot fallbacks are 0. These are short startup observations,
not world-entry or sustained-memory acceptance. No resource policy expansion
is included. A matching fresh AOT and signed IPA remain required, followed by
user device retesting. Gate C/E acceptance remains incomplete.

## Matching signed export

Source: 1f46004f2a59d87a28dfe08bd3f351bdbe8b6483. Fresh full-game iOS ARM64
AOT completed in 736.8 seconds; object SHA256:
01d15560220c2ac32a55acbf145770e934a65acfc252b602888828ad1fd5baf4.
Full linking has zero unresolved symbols. The pre-existing unsupported
OperatingSystemImpl.initialize0 entrypoint remains; this is not full Mod
compatibility evidence.

Local licensed IPA:
artifacts/mcfao/metal-p0-input-full-game-signed-01/export/FabricAOT World.ipa
(714578918 bytes). SHA256:
4853877eca1d47fcdbd99ec8c2d396ac2ae3b38aefd288fdb02d3e08743b4f10.
Export status: DEVELOPMENT_IPA_VERIFIED. Signing covers the requested iPhone;
profile expiration remains 2026-11-17 13:48:54 UTC. No dynamic-code entitlements.

The packaged GLFW exports mouse/button/key/cursor polling. GLFW and LWJGL
UUIDs match their newly built inputs, and the overlay generation GLFW hash
matches the selected binary. AOT/Metal UUIDs and all shader hashes match the
staged build. All tracked source inputs match this commit: Metal 24, GLFW 5,
LWJGL 14. Evidence: artifacts/metal-p0-input-delivery.json,
artifacts/metal-p0-input-source-check.json, build/export logs and manifests.
Focused Python input checks: 27 passed after physical-toolchain-path fix.

A static top-level Mod scan also finds IAS references to desktop focus and
attention APIs absent from GLFW; those conditional paths are not validated
by this startup fix. See artifacts/metal-p0-input-mod-glfw-scan.json. No Mods
were disabled. No installation or launch was performed. The installed app
uses another re-signing identity: retain its signing settings when updating
to preserve its data. World entry, save/reload, and long-run device scenarios
remain unverified. No new device memory curve or sync latency is claimed.
