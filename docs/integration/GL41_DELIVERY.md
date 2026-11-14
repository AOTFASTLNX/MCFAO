# GL41 integration delivery record — 2026-11-15

Status: **EXPERIMENTAL / physical-device acceptance BLOCKED**. This integration produces a real macOS builder and genuine Minecraft 26.1.2 native iOS packages. It has not passed playable-device acceptance. No new `FUNCTION_PASS` is granted.

## Source and branch protection

- Worktree: sibling `MCFAO-integration-gl41-20261115`; branch `integration/gl41-gui-ipa-20261115`. The original dirty `MCFAO` checkout was preserved.
- Verified remote main and `archive/main-pre-gl41-20261115`: `236c161d4cff497530f39f8b239b7259bf4f3015`, both before integration and before delivery. Only the integration branch is authorized for push; the review is a Draft PR, never a merge.
- Runtime/GUI artifact source: clean `70d5cbe7fee35fa386302721edb5424f75181bce`, with empty tracked diff SHA-256 `e3b0c442…`. Later delivery documentation and workflow source-list fixes do not alter compiled runtime code.
- v21 merged at `da5616e`; MDAF at `c714f64`; P0 originals c9c4659/7d7f945/1f46004 transplanted as `4b851eb`/`b99bc1a`/`ff0dca9`; complete GL41 through f0a6d8c merged at `61d00fb`. Full history and the v14 tag remain available.
- Both workflow merge conflicts retained main's unrestricted push trigger. Shared CLI/probe changes were integrated semantically. Native Metal lifetime/performance/vsync branches and stale CircleCI setup were evaluated without indiscriminate merging. Other developers' PRs remain untouched. See [branch audit](GL41_BRANCH_AUDIT.md).

## Local artifacts

Paths below are relative to the integration worktree and are intentionally not committed or uploaded.

| Artifact | Path | Evidence |
|---|---|---|
| ARM64 macOS app | `artifacts/integration-20261115/output/macos/FabricAOT.app` | Local ad-hoc bundle signature verified; not notarized. Process launched. Native window interaction BLOCKED by Mac lock screen. |
| Unsigned Vanilla GL41 IPA | `artifacts/integration-20261115/output/tauri-vanilla-gl41-01/FabricAOT-game.ipa` | 480,079,754 bytes; SHA-256 `4f55691df3e32930a22677223c6f31d46add75c632d6b4aa16622888742919a4`. Cannot install directly. |
| Development-signed Vanilla GL41 IPA | `artifacts/integration-20261115/output/signed-gl41-02/FabricAOT-GL41-development.ipa` | 481,335,024 bytes; SHA-256 `91a978d41a36a731fb3fbba618b89a6400c2837449078f340d2396e5ed79f5f6`. Existing local development certificate/profile reused; no credentials created/uploaded. Installed under a separate test Bundle ID that was absent before this task. |

Build environment: Apple Silicon, Xcode 27.2 (27B52), iPhoneOS SDK 27.2, Java/GraalVM CE 25.0.2, task-local ARM64 Rust 1.100.0. The GUI invokes full `mcfao build` with GL41, 7 GiB image-build heap and 3 compiler threads. Native Image produces a relocatable ARM64 object; the iOS runtime, real JNI libraries and genuine assets are linked/packaged and verified. No JIT entitlement or debugger prerequisite is added.

GL41 runtime pins Amethyst-iOS `54d20f9a7b22c8cadc026cbad8eb1a386a1e6efe`: OSMesa SHA `081a4895…`, MoltenVK SHA `e513ae03…`. OSMesa binary identifies Mesa 25.0.7 (`742a20f48c`). The precise upstream MoltenVK release version has not been independently established; binary identity is exact. Its Mach-O compatibility version is not treated as its upstream release version. GL41 does not package Java MetalBackend/JNI/shader artifacts; native Metal remains a separate option.

## Validation

| Check | Result | Local evidence under `artifacts/integration-20261115/` |
|---|---|---|
| Python full suite | 346 run: 341 pass, 5 skip | `logs/python-full-04.log` |
| Frontend model tests | 19 pass | `logs/gui-model-tests-03.log` |
| Playwright workflows | 11 pass | `logs/gui-playwright-05.log` |
| Rust backend / Tauri IPC / cancellation | 11 pass; expensive AOT test run separately | `logs/rust-arm64-tests-06.log` |
| Actual full AOT through Tauri IPC | PASS, 235.43 seconds | `logs/tauri-full-aot-02.log`, `output/tauri-workflow-*.json`, `output/gui-build-*.log` |
| macOS app compilation | PASS, ARM64 | `logs/tauri-app-build-02.log`, `output/macos/result.json` |
| GLFW and LWJGL host/native probes | PASS; GL41 and NO_API dimensions, input polling ABI and real client window/image probes | `cache/glfw-02/result.json`, `cache/lwjgl-05/result.json` |
| Native Metal basic rebuild | PASS, iPhoneOS JNI/Java/present metallib; host texture and pixel-layout contracts pass | `cache/metal-regression-01/result.json` |
| CI GLFW commands | Host sanitizer fixture and iPhoneOS link PASS | `logs/ci-glfw-state-test.log`, `logs/ci-iphoneos-glfw.log` |
| Unsigned package re-verification | PASS | `logs/verify-final-unsigned.log` |
| Signed package / device install | PASS | `output/signed-gl41-02/result.json`, `logs/device-install-gl41-02.json` |

The five Python skips concern historical default artifact locations: one linked-image fixture, two shipped Mod/Metal reflection fixtures, one built Fabric-pack fixture and one built Metal-backend fixture. Newly built task-specific binaries have their separate validation above; skips are not converted to passes. The first expensive IPC test invocation rejected unnormalized `..` paths before execution; normalized absolute paths passed without weakening validation. Earlier AOT/bridge failures and diagnostic logs remain retained locally.

The full workflow test invokes real Tauri commands with a mock window runtime and the actual compiler/backend. This establishes IPC → AOT → IPA behavior. Playwright screenshots are browser workflow previews (`logs/gui-browser-preview.png`), not native-window or device gameplay evidence. Native desktop clicks, import dialogs and a click-initiated build still require the unlocked Mac.

## Physical device and remaining gates

The connected physical test device reports iPhone19,4 and iOS 27.2 (24B91020). Installation succeeded using an independent test identity, preserving the pre-existing Minecraft app and its data. Initial independent launch returned CoreDevice 10002 → FBSOpenApplicationErrorDomain 7, `Locked`: the device could not be unlocked. Another attempt reported RSD allocation error 0xE8000003. Private device identifiers/profile details remain only in local logs.

| Required gameplay check | Current result |
|---|---|
| Independent game launch / real GL41 first frame / main menu | BLOCKED: locked device; no current-frame evidence |
| Touch/input, world creation, terrain/entities/GUI, movement, view | NOT RUN |
| Break/place blocks, inventory | NOT RUN |
| Save, quit, process restart and world reload | NOT RUN |
| Continuous 30-minute gameplay | NOT RUN |
| FPS, frame times / 1% low, memory, thermal state, throttling | NOT MEASURED |
| Current integrated game crash diagnosis | No game execution captured; prior launch failures are OS launch denials |

C0a/C0b/C0c/C2, D1 gameplay, D2 runnable-install acceptance and E remain BLOCKED. Unlock the Mac and connected iPhone, keep the device available, then continue the native GUI and physical-device checklist. Device interaction cannot be substituted by archived v14 results.

## Fabric / Mod compatibility

| Component | Current integration verdict |
|---|---|
| Fabric Loader 0.19.3 / Mixin / Class Tweaker / nested JAR / entrypoint toolchain | Structural/JVM conversion regression tests pass; this integrated GL41 device LOAD_PASS and FUNCTION_PASS are NOT RUN |
| Fabric API and a lightweight functional Mod | Device validation BLOCKED pending Vanilla gameplay |
| Sodium, Sodium Extra, Iris | NOT VERIFIED; independent GL/JNI, dynamic-class and semantic checks required |
| Recollection3 full pack | NOT VERIFIED; no reduced subset is presented as the complete pack |

MDAF merges reflection/resource/tracing metadata and reports unsupported mechanisms. Runtime class definition, platform JNI and transformed semantics remain explicit risks. Full builds reject `excludedMods`/`retiredJars` rather than silently shipping a reduced pack. Static metadata, transformation and BUILD_PASS do not imply LOAD_PASS or FUNCTION_PASS.

Known limits: GPU→CPU readback and intermediate Metal copy cost, Apple Zink experimentation, physical GPU/heap/thermal budgets, inherited experimental world-join behavior, unverified Sodium/Iris mechanisms, restricted import download hosts and fail-closed override collisions. No current FPS or stability claim is made.

Usage: [GUI build guide](GL41_GUI_BUILDING.md). Architecture: [ADR-009](../evidence/ADR-009.md).
