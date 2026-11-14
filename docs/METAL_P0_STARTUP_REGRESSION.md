# Metal P0 startup upload regression

Last reviewed: 2026-11-14. Device acceptance remains BLOCKED.

## Device failure

`run-1794650965078.log` reaches Minecraft 26.1.2 resource reload, then
crashes after about four seconds in `CubeMapTexture.doLoad` ->
`MetalNative.writeTexture`: `Texture upload staging allocation failed`.
At the first rejection (line 391), a 4,194,304-byte request was denied with
78,928,144 tracked live bytes, including 77,859,968 texture bytes,
1,061,120 transient texel bytes, and no command buffers committed yet.
`MTLDevice.currentAllocatedSize` was 80,134,144 bytes. This is a startup
budget rejection, not evidence that the device exhausted Metal memory.

`acquireTransientBufferOfLength:` compared `totalLiveBytes + length` with
the 64 MiB transient cap. `totalLiveBytes` includes persistent textures.
Once persistent texture storage exceeded the cap, every new staging
allocation failed even though transient usage was small. The same total
also incorrectly controlled whether completed buffers entered the pool.

## Correction

`FAOTResourceTracker` now reserves transient backing lengths separately
under its existing lock. Persistent buffers/textures and alias texture
views are excluded. A transient buffer is charged exactly once while it
is checked out, Java-owned as a snapshot, GPU-held, or idle in the pool.
`transient_allocated_bytes` reports this requested-length measure; it is
not equivalent to Metal allocated size, Metal HUD memory, or process RSS.

On a size miss, only idle pool entries can be discarded to make room.
GPU-held buffers remain charged until their completion callbacks. The
existing one-second bounded pressure wait remains; no new wait, budget
increase, quality change or mod change was introduced. Concurrent misses
reserve before allocating; a failed native allocation rolls back its
reservation. Returning a buffer to the pool does not charge it twice.

Snapshot creation no longer calls `track` twice (the JNI handle helper
already tracks it). Snapshot release with no remaining command buffer
returns storage through the same budget accounting immediately.

The backend host contract runner also resolves its Java home and uses
its allowed physical output directory as cwd, so the unchanged sandbox
policy works when invoked from an isolated worktree.

## Regression evidence

`tests/metal_resource_lifetime_test.m` now exercises real Metal storage:

- Persistent texture storage above the transient cap followed by a valid
  upload: fails against the previous manager, passes with the correction.
- Exact-size reuse at the cap and eviction of idle storage on a size miss.
- A released snapshot held behind a GPU shared event stays charged and
  cannot enter the idle pool before completion.
- Sixteen concurrent requests for eight available slots admit exactly
  eight allocations and reclaim all reservations after release.
- The existing 1,200-frame lifecycle workload continues to pass.

The host fixture passes under AddressSanitizer/UndefinedBehaviorSanitizer.
The iPhoneOS backend builds with warnings treated as errors; host texture
contracts, pixel layout and resource lifecycle tests all pass.

Local evidence under the main checkout's `artifacts/`:
`metal-p0-startup-before.log`, `metal-p0-startup-after.log`,
`metal-p0-startup-backend-04.log`, `metal-p0-startup-python-tests-04.log`.

This corrects a proven startup regression. It does not establish successful
device entry into a world, long-run stability, lower sync latency or the
original memory-growth acceptance criteria.
