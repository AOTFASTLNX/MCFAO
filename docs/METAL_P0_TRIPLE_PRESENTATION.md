# Three-drawable presentation investigation

The user reports a reduction from 120 FPS to about 30 FPS after the P0
changes. There is no run log for that version and scene yet. The latest
available device log, `run-1794660947910.log`, predates the completion-mailbox
fix and ends in an assertion. It cannot establish the cause of the new FPS
report. No restoration to 120 FPS or stable memory curve is claimed.

## Source findings and change

`MetalNative_create` configured both `maximumDrawableCount` and the presentation
semaphore to two. They now share a depth of three, as requested. The frame
semaphore remains bounded and is released by GPU completion.

`MetalNative_presentFrame` previously acquired a drawable before committing
pending offscreen rendering. A blocked `nextDrawable` therefore also delayed
submission of work that did not need the drawable. The pending offscreen
command buffer is now committed after acquiring the frame slot and before
acquiring the drawable. Presentation is encoded afterward on the same queue.
This preserves render-before-presentation order without a CPU completion wait.
The shared `commit` helper and preinstalled completion mailbox remain in use
for both command buffers. This adds at most one command buffer per presented
frame with pending offscreen work; compare its submission overhead on device.

The 64 KiB CPU-write snapshot limit and 64 MiB transient backing cap are
unchanged. Hazardous large writes still wait for GPU completion; snapshot
fallback waits remain required for correctness. `MetalBufferHazards` now
reports `large_wait_total_ms`, `clone_fallback_waits`, and
`clone_fallback_wait_total_ms` separately per 300 submitted frames. These
are totals, including JNI overhead, not percentile or per-frame values.
`MetalPresentation` identifies the configured drawable/frame depth and
early-render submission count. Existing `MetalPerf` separates slot, drawable,
CPU synchronization, fence, readback and private texel-upload waits.

## Validation boundary

The host lifetime test queues three delayed pairs of command buffers on the
same serial Metal queue. It checks that post-commit resource releases do not
recycle GPU-held backing and that each simulated presentation sees its own
rendered bytes. This exercises queue dependencies and completion-mailbox
reclamation; it does not exercise iPhone scanout or establish game FPS.

Python contract tests check the shared depth and submission order. A fresh
iOS ARM64 AOT image and signed IPA are required before device comparison.
Gate E remains BLOCKED until matching device logs establish FPS, frame-time
percentiles, memory stability and correctness in the requested scenarios.

## Matching integration build (2026-11-14)

Runtime source: `3a92a229ef97a637065114d1e6def4a2f15a40c2`.
Python: 319 tests run, 316 passed, 3 skipped. iPhoneOS backend compilation,
Java contracts, native pixel layout, resource lifetime and upload-burst
checks pass. The delayed three-frame lifetime test also passes ASan/UBSan.
All 24 backend source hashes match. Java native descriptors, C JNI
declarations and the 33 exported JNI symbols are unchanged.

Fresh iOS ARM64 AOT completed in 928.323 seconds. The image object SHA-256 is
`57e5565fa182eace50bed6a29de54ff71b15825539d1151a6e315c4b181c6822`.
Full linking completed with no unresolved symbols. Its status remains
`LINKED_WITH_UNSUPPORTED_ENTRYPOINTS` because of the previously documented
`OperatingSystemImpl.initialize0`; this is not full runtime compatibility proof.
The app build is `SIGNED_DEVICE_APP` and export is
`DEVELOPMENT_IPA_VERIFIED`, with the requested device covered by the profile.

The IPA is `artifacts/mcfao/metal-p0-triple-full-game-signed-01/export/FabricAOT World.ipa`,
714445502 bytes, SHA-256
`1331e734f9c3be48a7e7cff46d7a46b13e02687cfd5eeaef9ac8145a2db905ef`.
Stage/package UUIDs match for AOT, Metal, GLFW and LWJGL; shader hashes,
input hashes and the newly compiled Metal binary also match.

Reproduction/evidence:

- `artifacts/metal-p0-triple-full-game-config.json`
- `artifacts/metal-p0-triple-full-game-01.log`
- `artifacts/metal-p0-triple-export-01.log`
- `artifacts/metal-p0-triple-abi-inputs.json`
- `artifacts/metal-p0-triple-delivery.json`
- `artifacts/metal-p0-triple-python-01.log`
- `artifacts/metal-p0-triple-backend-02.log`
- `artifacts/metal-p0-triple-lifetime-sanitized-01/run.log`

No new device install, gameplay, FPS or memory run was performed. Updating
the existing user-re-signed installation requires preserving its signing
identity and container; no uninstall or world deletion is authorized.
