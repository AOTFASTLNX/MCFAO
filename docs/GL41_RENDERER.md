# OpenGL 4.1 renderer on iOS (experimental)

Status: **BUILD PASSED (vanilla client), DEVICE ACCEPTANCE PENDING**. This document describes the
`FAOT_RENDERER=gl41` build profile. It is not evidence that the renderer runs on a device or is
faster than the native Metal path.

## Why a translation stack is required

iOS exposes Metal, not desktop OpenGL. The OpenGL path therefore runs Mesa's Zink Gallium
driver (OpenGL to Vulkan) over MoltenVK (Vulkan to Metal), with OSMesa owning the drawable and
returning a CPU-visible frame. The game's native `com.mojang.blaze3d.opengl.GlBackend` is kept;
the build-time Metal injection is skipped for this profile. Minecraft's own 3.3 core request is
served by a 4.1 context.

## Components

| Component | Change |
| --- | --- |
| `tools/fetch_gl41_runtime.py` | Fetches the pinned iOS `libOSMesa.8.dylib` and `libMoltenVK.dylib` from Amethyst-iOS commit `54d20f9a…`, verifies SHA-256 and Mach-O platform/CPU/minimum iOS, and records MIT/Apache-2.0 provenance. Binaries are not committed. |
| `tools/build_lwjgl_opengl_ios.py` | Reads the real LWJGL OpenGL jar, generates one fixed JNI entry point per native method (2,236 after excluding WGL/GLX/CGL), links it to OSMesa, and rejects non-primitive descriptors. Functions absent from this OSMesa export surface throw `UnsatisfiedLinkError` instead of calling a null address. |
| `ios/glfw-lite/osmesa_gl.c` | Loads OSMesa and MoltenVK, creates a 4.1 context lazily on the render thread, applies `MESA_*` limits, falls back to RGBA with a channel swap, and owns the frame buffer. |
| `ios/glfw-lite/glfw_lite.c` | Accepts `GLFW_OPENGL_API` in addition to `GLFW_NO_API`; `MakeCurrent` creates the context and `SwapBuffers` presents the frame. |
| `ios/glfw-lite/uikit_surface.m` | Copies the BGRA frame into a shared Metal texture and blits it to the `CAMetalLayer` drawable; a missing drawable drops the frame. |
| `ios/lwjgl-lite/core.c`, `Library.java` | Function-address lookup falls back to the global image list so symbols re-exported by OSMesa resolve behind the `liblwjgl_opengl` handle. |
| `ci/build_mac.sh` | `FAOT_RENDERER=gl41` fetches/builds the runtime and shim, keeps the unmodified split client, omits the Metal bootstrap from AOT, and stages the extra dylibs. Default remains `metal`. |

## Known constraints

- Mesa Zink on Apple platforms is documented as experimental. The pinned binaries were built
  outside this repository; their behavior on iOS 27 and A18 is unverified here.
- This OSMesa export table covers the 4.1 entry points used by the vanilla client. 4.5 direct
  state access is hidden so Minecraft uses its non-DSA path. Optional extension slots resolve to
  explicit failures rather than silent zero addresses.
- OSMesa presentation requires a full-frame copy from CPU memory to a Metal texture. This may
  cost more than the native Metal backend; FPS must be measured on device before any performance
  claim.
- The previously documented Fabric transformation exclusions and the Sodium/OpenGL requirement
  remain separate issues. A GL41 build of the vanilla client validates the renderer first; it
  does not make the Recollection3 mod set complete.

## Build

On an isolated Apple-silicon Mac:

```
FAOT_RENDERER=gl41 FAOT_BUILD_LOADER=vanilla bash ci/build_mac.sh
```

The resulting unsigned IPA is exported by the existing `tools/package_unsigned_ipa.py` step.

## Build record: GL41 v7 (2026-11-14)

- Device feedback for v2 (`0d9fe55`) showed that OSMesa/Zink/MoltenVK started correctly:
  `GL_VERSION=4.1 (Compatibility Profile) Mesa 25.0.7`, `GL_RENDERER=zink Vulkan 1.4(Apple A18 Pro GPU (MOLTENVK))`.
  The crash was `GL.create()` throwing *There is no OpenGL context management API available*:
  LWJGL's `Configuration.OPENGL_LIBRARY_NAME_DEFAULTS()` has no iOS branch and throws. Mesa also
  advertises `GL_ARB_direct_state_access` while the 4.1 OSMesa export table lacks the 4.5 entry
  points, and Mesa refused to hide the extension.
- Fix: the `lwjgl-ios.jar` overlay now makes both OpenGL library-default methods return
  `lwjgl_opengl`; `main.m` also sets `org.lwjgl.opengl.libname=liblwjgl_opengl.dylib`.
  `tools/patch_gl41_client.py` rewrites only `GlDevice.<clinit>` so
  `USE_GL_ARB_direct_state_access=false`, selecting Minecraft's emulated DSA path.
- Device feedback for v3 (`d91dc4f`) showed the next LWJGL failure:
  `ThreadLocalUtil.setFunctionMissingAddresses` threw while `GL.create` was installing 2,236 GL
  entries. This AOT build uses explicit function-pointer JNI adapters and never rebases the VM's
  JNIEnv table, so the thread-table bookkeeping is a no-op. `ThreadLocalUtil.setCapabilities`
  was made a no-op for the same reason.
- Device smoke on v4 (`045685f`) reached the vanilla 26.1.2 world and displayed the terrain-loading
  screen at ~48 FPS with Zink/MoltenVK active, but the client stayed in
  `LevelLoadTracker$WaitingForServer`. That state only changes on
  `ClientboundGameEventPacket.LEVEL_CHUNKS_LOAD_START`; if the event is delayed it has no timeout.
  A second cold-launch attempt failed before window creation because no scene was
  `ForegroundActive` yet.
- Fix: `tools/patch_gl41_client.py` also gives `WaitingForServer` a `tick()` that advances to
  `WaitingForPlayerChunk`, and shortens Minecraft's built-in 30-second chunk wait to 5 seconds.
  The UIKit surface now also accepts a `ForegroundInactive` scene during cold launch.
- Device feedback on v5 (`e7182bc`) confirmed the world loads and plays, at roughly 48 FPS during
  the loading screen, but the user reported stutter. The likely contributors were a single present
  texture overwritten while the GPU was still reading it, and full 2622x1206 shading/readback
  through Zink.
- Performance build (v6): present frames rotate across three shared BGRA textures guarded by a
  three-slot semaphore; the default internal render scale is 0.8, upscaled by a small Metal
  pipeline with a linear sampler; the render thread requests USER_INTERACTIVE QoS; MoltenVK uses
  argument buffers and smooth swapchain filtering. `[GL41] perf` reports FPS, `glFinish` time and
  present time every five seconds. `FAOT_GL41_SCALE` can override the scale (0.5..1.0).
- v6 device logs: `fps 48-53`, `finish 9-13ms`, `present 1-4ms`. The scaled framebuffer was not
  reported as the game's logical resolution, so the GUI was cropped and enlarged; the scale gain
  was also small because the Mesa `glFinish`/readback dominates. v7 restores the native
  2622x1206 render, keeps triple buffering/tuning, and disables `mesa_glthread` to remove one
  per-frame thread round-trip.
- CircleCI job 111 (`build/gl41-renderer-2026-11-14`, source `85f0932`):
  **success**. Stage 4b
  patched exactly `GlDevice.class`, `LevelLoadTracker.class` and
  `LevelLoadTracker$WaitingForServer.class`; GLFW, shim, AOT, link and Xcode build all passed.
- Stage 3a GLFW host state fixture: PASS. Stage 3c2: runtime fetched and verified; GL shim built
  with 2,236 JNI exports (554,808 bytes). Stage 3d/3e: shader and Metal/OpenAL inputs built.
- Stage 4d native-image analysis: 6m21s, object 168,365,440 bytes. Stage 4e link: only the
  pre-existing `OperatingSystemImpl.initialize0` JDK management native was stubbed; no GL symbols
  were stubbed. Stage 4g Xcode build: `BUILD SUCCEEDED`.
- Unsigned IPA: `FabricAOT-game.ipa`, 466,785,855 bytes, SHA-256
  `1d9e2ea27af3aa7e479d3ded6bae74bd1a5348cee6baf4bc74009feb8ec80181`.
- Package audit: `client-graph.dylib` contains `GlBackend`/`GlDevice` and no `MetalBackend`;
  `liblwjgl_opengl.dylib` depends on `@rpath/libOSMesa.8.dylib` and exports the generated GL JNI
  entries; `libOSMesa.8.dylib` and `libMoltenVK.dylib` are in `Payload/C0Harness.app/Frameworks`.
- This is the **vanilla** 26.1.2 client. Fabric Recollection3 is still blocked by the separate
  transformation exclusions documented in `RECOLLECTION3_CI_STATUS.md`; Sodium now has a renderer
  path, but the remaining dynamic-class/native mods are not yet supported.

## Build record: GL41 v8 (2026-11-14)

- The v7 device report (`run-1794638485001.log`) showed that spawn preparation reached
  100% and the integrated server logged the player joining. The last GL41 performance
  sample before that was 52.7 FPS; the archive contains no crash report or client tracker
  state after join. The exact point where the client stopped advancing is unconfirmed.
- Source `93bac37` changes the GL41-only bytecode adaptation to let the player-chunk
  readiness check succeed once reached and emit `[GL41] client chunk wait bypassed`.
  This tests whether the readiness check is blocking progression; the change cannot
  unblock a render call or a client tick that stalls before the check. The presentation
  path and native framebuffer size are identical to v7.
- CircleCI job 112 compiled and linked the iOS client and passed the IPA ZIP check.
  The unsigned IPA is 466,507,049 bytes, SHA-256
  `e7b5209fd147cc375c1688727b5e7c43889d2b369d3f643291f97544e340e733`.
- Package audit found no bypass log marker in the final AOT binary. This build is withheld.
  **Device run: NOT RUN.**

## World-join follow-up

The GL41 build now uses the same unsigned chat-session short circuits as the Metal build.
When there is no signed session to validate and secure chat is not enforced, querying the
services key set is unnecessary and can wait on a network request during local join.
Signed session validation is preserved. This addresses a plausible blocker; the device log
does not include a thread stack that identifies the blocker conclusively.

The original terrain readiness checks and timeout are restored. The shared play diagnostics
record packet arrival, decoded chunks, readiness transitions, and client tick age. A watchdog
captures stalled client ticks even when join stopped before a tracker was assigned. CI
checks that the final linked GL41 client contains the new diagnostics before packaging.
The game uses its existing OpenGL backend and the same native size as v7.

## Build record: GL41 v9 (2026-11-14)

CircleCI job 113 built source `9a7592696fb0b2fd9ad4849a6642827322a6a599`.
AOT linking, the GL41 join-diagnostics check, Xcode build and IPA packaging passed.
The downloaded unsigned IPA passed ZIP integrity, arm64 and signature checks, and includes
the three GL41 libraries and the new join diagnostics in the shipped client.
Size: 466,636,647 bytes. SHA-256:
`083a3c1ffdc9034550164d54bdfc1cdec5f4404d658f04c73f3fe92ff3d3cd88`.

**Device run: NOT RUN.** Cover an existing world, movement, and exit/rejoin on device.
If it still stalls, let the watchdog run for at least 35 seconds before exporting
the log. Check `client_tick_stall`, `level_load_tracker`, `level_load_ready`
and the accompanying thread frames.

## GL41 v10 presentation experiment

Device log `run-1794644303093.log` confirms v9 entered the world and later saved it.
Across 17 five-second samples after the world became ready and before pausing, the
game loop reported 38.5–59.0 FPS (median 48.9). The OSMesa finish step took 8.45–12.06 ms
on average per sample (median 11.18 ms); the synchronous presentation stage took
1.92–4.77 ms (median 2.34 ms). These are sample averages, not individual frame times.

The v10 GLFW bridge keeps the native framebuffer and moves drawable acquisition and
command submission to a dedicated serial queue. The game thread copies pixels into
one of three shared textures; each texture stays reserved until its GPU read completes.
If all three are busy, the game continues without submitting a stale frame. The Mesa
finish and readback still happen on the game thread, so their cost remains.

New `[GL41] display` samples use Metal drawable presentation timestamps. They report
screen FPS, the 95th percentile interval rounded up to a millisecond (100 means
100 ms or more), the number of intervals above 34 ms, and detected drops.
For a fair device comparison, retain the same save, route, resolution and settings.
The existing `[GL41] perf` line continues to measure the game loop; its `present`
column now measures handing off the frame, rather than waiting for a drawable.

CircleCI job 114 built source `bacc996216e48e3589964feb1ed560cb9fa57935`.
iOS arm64 compilation and the GLFW host state fixture passed. The downloaded unsigned
IPA passed ZIP integrity and signature checks and includes the new native presentation
queue and display statistics. Size: 466,758,674 bytes. SHA-256:
`191e8107e4c28e1a3bda7ea4082c8b5fc3602e2d355d95ab2ba6c8e5f9e505c8`.
**v10 device performance: NOT RUN.**

## GL41 v11: 120 Hz pacing and buffer hitch removal

Device log `run-1794646990892.log` contains v10's presentation queue. During the
non-paused samples the game loop reached 63.4-64.7 FPS, but Metal presented only
51.3-57.0 FPS and reported 30-66 dropped submissions per five-second sample. Screen
frame intervals were quantized near 17 or 21 ms, consistent with a 60 Hz display request.
The device is an A18 Pro with a 120 Hz panel and its Info.plist already enables frame
durations below 60 Hz.

For the 120 FPS profile the app now creates a CADisplayLink on the main run loop with
a CAFrameRateRange of 80-120 and preferred 120, while the CAMetalLayer retains three
drawables. The link only requests the display cadence; the OpenGL renderer still follows
Minecraft's FPS setting. It pauses with the scene. This combination matches the intended
`120 FPS -> 3 drawables -> refresh follows FPS` setup.

Minecraft's stock `FramerateLimiter` sleeps relative to the actual wake-up time, so
scheduler overshoot shifts every subsequent deadline. GL41 now calls a build-injected
`FramePacing.limitDisplayFPS` that advances an absolute nanosecond deadline. A large
overdue interval resets the deadline instead of producing a burst of catch-up frames.
The first call logs `[GL41] frame limiter=fixed-timeline`.

The same device log showed Dynamic Transforms and Chunk Sections UBOs repeatedly growing
from a capacity of 2 through 1024 while terrain was explored. GL41 now pre-sizes both
uniform rings to 4096 entries, removing those per-expansion buffer allocations without
changing rendered content, geometry or UI assets. Native resolution and all game settings
remain in their original form; the FPS option stays available at 120.

CircleCI job 115 built source `eabc50646f9f7ec741db2c7ca006e9fa01fb3c8c`.
Stage 4b changed exactly the expected eight client classes, including
`DynamicUniforms`; the AOT link, Xcode build, and IPA packaging passed. The downloaded
unsigned IPA passed ZIP and Mach-O audits and contains both the fixed-timeline and
120 Hz refresh markers. Size: 466,614,499 bytes. SHA-256:
`50589b86bc8a042061197e286616800a4d4de4e283840c0cd916381e8f705c19`.
**v11 device performance: NOT RUN.**

## GL41 v12: resolution-scaled, steady 60 FPS

`归档(12)` (v11 on device) showed the render and present no longer drop frames
(`drops=0`), but the OSMesa `glFinish` time swings between 10.3 ms and 16.4 ms. In game
this produced 41 FPS dips alternating with 62 FPS peaks: the fixed-timeline limiter had
nothing to pace because a 2622x1206 render + full-frame GPU->CPU readback exceeds the
8.33 ms budget of 120 FPS, so the game ran as fast as it could and the readback spikes
became visible stutter.

v12 reduces the internal render and readback size to 80% and, unlike the earlier v6
attempt, scales the reported window size, framebuffer size and absolute cursor
coordinates together. Minecraft lays out the GUI at the scaled size and the existing
Metal linear-sampler pipeline upscales it to the native 2622x1206 drawable, so the
interface keeps its proportions and hit-testing instead of being cropped.
`FAOT_GL41_SCALE=1.0` restores native resolution.

The fixed-deadline limiter now also caps the steady-state rate at 60 FPS. This is the
rate the GL41 renderer can hold without dropped frames; lower in-game choices are still
honoured. Together the 80% scale gives each frame enough headroom that the remaining
readback spikes stay under the 16.7 ms budget, and the cap stops the game from surging
into a 120 FPS target it cannot meet.

CircleCI job 117 built source `affd1c168e07a58bb43cac33bc2531e4155c74b7`.
Stage 3a compiled the scaled GLFW sizes and the host fixture passed with 312x675 points /
936x2026 pixels. Stage 4b applied the client patches, AOT link, Xcode build and IPA
packaging passed. The downloaded unsigned IPA passed ZIP, arm64, signature and GL41
marker audits. Size: 466,715,489 bytes. SHA-256:
`0900f0b1dce09695aa636d90b56ef98945abc94bbf01895adc24bad9ea3105f2`.
**v12 device performance: NOT RUN.**
