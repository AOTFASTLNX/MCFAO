# OpenGL 4.1 renderer on iOS (experimental)

Status: **CODE INTEGRATED, BUILD AND DEVICE ACCEPTANCE PENDING**. This document describes the
`FAOT_RENDERER=gl41` build profile. It is not evidence that the renderer runs or is faster.

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
