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
