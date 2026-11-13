# 2026-11-12 — iOS launcher, control layouts and frame-rate work

Branch: `feature/launcher-controls` (from `fix/ipados-mouse-trackpad-look`, which carries the
iPadOS pointer bridge).

## Shipped on device

The game boots to the main menu and into a world on iOS with no JIT: the client is AOT compiled
by GraalVM Native Image and runs against the Metal backend, `libglfw` and OpenAL Soft.

## Launcher UI (`ios/C0Harness/FAOTLauncherViewController.*`)

- Player name, memory budget, control-layout picker, `Edit controls`, `Import Pojav layout`,
  `Launch Minecraft`, `Diagnostics`, live status line.
- Card lives inside a `UIScrollView`, so landscape phones keep every row visible.
- A Graal isolate only exists once per process: after a launch the button turns into
  `Restart App` and calls `exit(0)` instead of letting the second `run_main` fail.
- Memory options are derived from the device: `floor(physicalGiB * 0.55)` capped at 8, i.e.
  4 GiB phone -> 1G/2G/3G, 7.5 GiB iPad -> 1G..4G. The caption shows the detected RAM.

## Control mapping (`FAOTControlLayout.*`, `FAOTControlsOverlay.*`, `FAOTControlEditorViewController.m`)

- Parses Pojav's `mControlDataList` JSON (dynamic expressions `${margin}`, `${width}`, `${bottom}`,
  `KEY_*` names, `scaledAt` reference canvas).
- Layouts persist as `Documents/controlmap/<name>.json` and are what the game reads at startup.
- Pinch to resize, drag to move, tap to rebind; geometry is normalised against the screen
  height as well as the width, so editor and in-game button sizes agree.
- `ios/glfw-lite/uikit_surface.m` installs the buttons from the selected layout while keeping the
  fork's pointer/trackpad bridge.

## Memory (`ios/C0Harness/main.m`)

- The picker becomes `-Xmx<n>m`; before this the picker had no effect at all.
- `-XX:ReservedAddressSpaceSize` is now derived as *heap + 1 GiB* from the same value, because
  GraalVM rejects a heap larger than the reserved address space.

## Frame rate

| Change | File |
|---|---|
| AOT at `-O3` (`MCFAO_OPT_LEVEL` overrides it) | `tools/probe_client_graph.py` |
| Frames submitted asynchronously, max 3 in flight; the render thread no longer blocks on `waitUntilCompleted` every frame | `ios/metal-bridge/metal_bridge.m` |
| `maximumDrawableCount=3`, `framebufferOnly=YES`, `allowsNextDrawableTimeout=NO` | `ios/metal-bridge/metal_bridge.m` |
| `glfwSetCursor` no longer formats a message into `stderr` on every frame | `ios/glfw-lite/glfw_lite.c` |
| Metal resource budget scales with RAM (768–1536 MiB) | `ios/C0Harness/main.m` |
| VSync actually implemented through `CAMetalLayer.displaySyncEnabled` | `MetalDevice.java`, `MetalNative.java`, `metal_bridge.m` |
| Performance-friendly `options.txt` defaults (maxFps 60, fast graphics, no clouds/shadows) | `ios/C0Harness/main.m` |

## Build pipeline

`zhangrongxue/mc-aot-ios` runs the build on CircleCI `m4pro.medium` (28 GiB), signs the IPA in
`zhangrongxue/mc-aot-sign` and installs it with `pymobiledevice3`. `ci/patch_src.py` applies the
source patches that the tool chain needs (splitter guards, ASM cache, `main.m` staged assets, ...).

## Known gaps

- The world renders at a low view distance on the current device; `options.txt` is only seeded on
  first run, so an existing container keeps its old values.
- Per-frame UBO growth (`Resizing Chunk Sections UBO ...`) is still visible in the log.
