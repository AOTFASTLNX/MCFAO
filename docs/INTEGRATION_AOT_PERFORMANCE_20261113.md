# AOT + iPad/performance integration candidate (2026-11-13)

This is a **review-only integration candidate**, not an accepted device release. Neither `main` nor the collaborator's source branch is modified by this integration.

## Exact sources

- Primary parent: `feature/performance-launcher-size-2026-11-13` at `163d029741633fd81028075f1bde7a638a83e3d1` (collaborator's launcher, pointer, Metal performance, build scripts).
- Second parent: `codex/fix-end-dragon-aot` at `e23d7b5f9ed91fdf33ac64bea0f4b9ca698204ef` (Fabric AOT pack-92/93, mod compatibility, End fixes, multiplayer diagnosis).
- Shared ancestor: `e337d0bacb8135abad21d3bc363e317c0dbb59a2`.

The candidate combines the changes to 75 AOT-side paths, including nine paths independently modified in both branches. The following nine paths were explicitly reconciled, rather than overwriting the collaborator's changes:

| File | Resolution |
| --- | --- |
| `compiler/metal-backend/src/fabricaot/metal/MetalDevice.java` | Combine partner's buffer hazard tracking with AOT backend changes |
| `compiler/metal-backend/src/fabricaot/metal/MetalRenderPass.java` | Preserve buffer hazard reads and AOT unsupported-shader gate |
| `compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java` | Preserve diagnostic instrumentation and injection of PlayDiagnostics together with partner's favicon/PIP orientation fixes |
| `compiler/reflection-config.json` | Use AOT metadata; it already includes all 11 vanilla dragon-phase constructor registrations |
| `interop/graphics/glfw_state_test.c` | Combine independent AOT and pointer regression checks |
| `ios/C0Harness/main.m` | Retain partner's launcher, language, memory picker and startup flow; reattach simulator-only multiplayer and extra CLI test parameters |
| `ios/glfw-lite/glfw_lite.c` | Combine non-overlapping GLFW runtime and pointer changes |
| `tools/inject_metal_backend.py` | Preserve the diagnostic-class injection and verify both additional GUI preview class patches |
| `tools/probe_client_graph.py` | Preserve automated reflection metadata and `-H:+SharedArenaSupport`; allow `MCFAO_OPT_LEVEL` override while keeping AOT branch's validated `-O1` default |

## Review gates still required

1. Inspect this PR against both source branch heads, especially Metal backend API and AOT transformed classes. A code-level merge does **not** prove runtime compatibility.
2. Run the GitHub Actions native/UI tests and the Python compatibility unit regressions. Resolve any failures in the integration branch only.
3. On Apple Silicon with Xcode and the legally acquired Minecraft 26.1.2 inputs: clean-build vanilla and Fabric AOT; check Java/ASM compatibility; confirm `PlayDiagnostics`, GUI preview patches, and combined Metal backend.
4. In a disposable simulator world: test single-player, a Fabric modpack, multiplayer terrain loading, entering/leaving the End, Jade and other individually supported mods. Collect new logs before claiming any `FUNCTION_PASS`.
5. On an iPad with Magic Keyboard: verify native iPad layout, pointer lock/hover fallback, camera motion, saves, and frame pacing. No iPad verification was performed by this integration.
6. Review `ci/build_mac.sh`: its default `UPSTREAM` still points at an older repository location. Explicitly pin `SOURCE_REF`/source SHA when testing integration to avoid building unrelated code.

Do not merge this candidate to `main` until these gates pass.
