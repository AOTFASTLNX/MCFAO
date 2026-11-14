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
