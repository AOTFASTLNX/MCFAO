# 2026-11-13 performance and launcher iteration

Baseline: daily/2026-11-12 at 7c3b161. New work lives on feature/performance-launcher-size-2026-11-13.

- Metal texel bindings use an independent shared snapshot texture on physical devices when supported. This removes the private-buffer allocation, blit submission and CPU wait from that path. Simulator and unsupported-view cases retain the old private upload. Each bind still copies CPU data to preserve earlier draws; never alias mutable Java buffers. Default retained-reference command buffers keep encoded resources alive. Frame presentation remains synchronous pending measurements and a resource-lifetime audit.
- GPU work stays on the rendering thread. Moving every JNI call to UIKit introduces thread hops and risks UI/render dependency cycles. Only UIKit-owned surface work should require the main queue. This is a hypothesis-driven change, with no FPS claim before device measurements.
- Launcher now uses a navy/teal gradient, bordered card, mint title and Chinese primary actions. Landscape scrolling remains available.
- Control toolbar adds Size: independent width/height in points, validated 28–240, clamped to the safe area, using existing normalized persistence. New-button height uses screen height rather than width.

Validation: Windows cannot compile UIKit/Metal. A macOS workflow checks both device and simulator paths and runs graphics/input regressions. Real-device resource-loading, frame-time, GPU/CPU timing and 30-minute stability remain required. Do not advertise a verified speedup or distribute this as a tested IPA yet.

Apple references:
- https://developer.apple.com/library/archive/documentation/Miscellaneous/Conceptual/MetalProgrammingGuide/Cmd-Submiss/Cmd-Submiss.html
- https://developer.apple.com/documentation/metal/mtlbuffer/maketexture(descriptor:offset:bytesperrow:)

## Native timing telemetry

The earlier `final_command_gpu_ms` was sampled immediately after commit, before Metal's GPU
timestamps are valid. Old zero values are therefore unavailable measurements, not proof that
the GPU was idle. The old `submit_wait_ms` combined command completion and frame-slot waits.

`[MetalPerf]` reports every 300 submissions: submission interval; CPU command-completion,
frame-slot, drawable-acquisition and fence wait separately; completed command-buffer GPU time
summed per submitted frame; command counts and unavailable timestamps; texel bindings and
upload waits; and snapshot counts/fallbacks. The GPU sum is sampled on completion and may span
adjacent reporting windows; it is not an end-to-end frame time, GPU utilization or a substitute
for a Metal System Trace. CPU/GPU work can overlap and their durations must not be added.

`[MetalPresented]` reports actual drawable presentation timestamps in independent windows of
300 valid intervals: real presentation FPS, mean, P95 and P99 interval, and invalid, dropped
or out-of-order callbacks observed in the window. Background pauses and loading are included;
compare only equivalent warmed-up scenes and record thermal state, settings and duration.
Zero presentation timestamps are not counted as displayed frames. Counters do not modify game
rendering, world state or GPU synchronization.

## Completed validation and delivery

- Native code at b28d508 passes device/simulator compilation, the Metal GPU snapshot lifetime regression, and existing graphics/input/C0 tests. Launcher/editor simulator screenshots were captured and inspected; the landscape layout now keeps the launch action and settings visible together.
- Checks: https://github.com/AOTFASTLNX/MCFAO/actions/runs/43265692059
- Full AOT game build succeeded in CircleCI job 71 from source 66a1f09. Native libraries were byte-for-byte preserved while the UIKit launcher was refreshed from 805dd53 in the private signing pipeline. The refresh guard rejects changes outside launcher/CI/docs before reusing an AOT image.
- Private refresh/sign run: https://github.com/zhangrongxue/mc-aot-sign/actions/runs/43266944897
- v8 installed successfully over the same app on the USB-connected iPhone. All 37 backed-up world files retain their SHA-256 hashes after installation. The existing Documents asset index remains available.
- Self-signable full-resource local deliverable: FabricAOT-game-unsigned-v8.ipa, 459653072 bytes, SHA-256 6e90a5883faa65d3cf113ea90f501b5ee112b2aee7e23247ca4760994562e1d6. All 4752 distinct indexed asset objects passed size/SHA-1 checks; ZIP integrity passed. Game binaries/assets are not committed here.
- New device gameplay/FPS/thermal tests remain NOT RUN: the device returned a black screenshot and the developer launch request timed out. Host GPU correctness does not establish a game FPS improvement.
