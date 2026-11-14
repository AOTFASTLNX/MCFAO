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

## Build record: GL41 v1 (2026-11-14)

- CircleCI job 104 (`build/gl41-renderer-2026-11-14`, source `79f3032`): **success**.
- Stage 3a GLFW host state fixture: PASS. Stage 3c2: runtime fetched and verified; GL shim built
  with 2,236 JNI exports (554,808 bytes). Stage 3d/3e: shader and Metal/OpenAL inputs built.
- Stage 4d native-image analysis: 6m21s, object 168,365,440 bytes. Stage 4e link: only the
  pre-existing `OperatingSystemImpl.initialize0` JDK management native was stubbed; no GL symbols
  were stubbed. Stage 4g Xcode build: `BUILD SUCCEEDED`.
- Unsigned IPA: `FabricAOT-game.ipa`, 441,611,541 bytes, SHA-256
  `a4bf4e223b44f918ca954fcd670b5e35275a75f92f20998136a41e7feaf1b683`.
- Package audit: `client-graph.dylib` contains `GlBackend`/`GlDevice` and no `MetalBackend`;
  `liblwjgl_opengl.dylib` depends on `@rpath/libOSMesa.8.dylib` and exports the generated GL JNI
  entries; `libOSMesa.8.dylib` and `libMoltenVK.dylib` are in `Payload/C0Harness.app/Frameworks`.
- This is the **vanilla** 26.1.2 client. Fabric Recollection3 is still blocked by the separate
  transformation exclusions documented in `RECOLLECTION3_CI_STATUS.md`; Sodium now has a renderer
  path, but the remaining dynamic-class/native mods are not yet supported.
