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

Every 300 successfully presented frames, `[MetalPerf]` reports mean presentation interval,
CPU submit-wait, drawable acquisition wait, GPU time for the final graphics command buffer,
shared/private texel bindings per frame, and CPU time blocked on fallback uploads. Values are
milliseconds per presented frame unless they are binding counts. The initial window includes
loading; compare warmed-up windows in the same world/settings. Final-command GPU timing is
not total GPU workload, and presentation interval includes pacing/GC and background pauses.
These counters make bottlenecks inspectable without asking the user to transcribe F3 numbers.
