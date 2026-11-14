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

## Corrected full-game package

Runtime source: `7e73a60be81a422b06f3c30ed3c60997324e2fc4`.
Fresh Minecraft 26.1.2/Fabric iOS ARM64 AOT completed in 11m 36s.
Build: `SIGNED_DEVICE_APP`; export: `DEVELOPMENT_IPA_VERIFIED`.
AOT object SHA256: `71cd47a7a75405d930041885c8830b266dfb3d1dbb68297efb8d668437976b4c`.
No unresolved symbols remain; the existing unsupported trapping entrypoint
`OperatingSystemImpl.initialize0` remains a compatibility limitation.

Local IPA, not for public redistribution:
`artifacts/mcfao/metal-p0-startup-full-game-signed-03/export/FabricAOT World.ipa`.
Size: 714,479,225 bytes. SHA256:
`d091ba15b66c692ed6950881c6667ccc543ba844b4898b356c14620d09553b8d`.
Signed AOT dylib: `1dd91ac31d227826f665007b5a6f60cfeb5dd515427832f21283ec3df2d0afd4`.
Signed Metal dylib: `d996308fb5c15b4a35eb79d07d8898d88cda1c007d7a10db065a4e431516b521`.

All 24 backend source hashes match the runtime source. All 35 Java class
hashes match the previous backend; JNI `synchronize(long)` remains `(J)V`
with its native export. The profile covers the requested iPhone and
dynamic-code entitlements are absent. Python: 315 run, 312 passed, 3 skipped.

Local manifests: `artifacts/mcfao/metal-p0-startup-full-game-03/result.json`,
`artifacts/mcfao/metal-p0-startup-full-game-signed-03/result.json`.
Logs: `artifacts/metal-p0-startup-full-game-03.log`,
`artifacts/metal-p0-startup-full-game-export-03.log`.
ABI evidence: `artifacts/metal-p0-startup-abi.json`.

## Device update attempt

The in-place update was rejected with `MismatchedApplicationIdentifierEntitlement`
(`MIInstallerErrorDomain` 64): the installed app was re-signed under a different
application identifier/team from this Xcode development export. Installation
log: `artifacts/metal-p0-startup-device-install-03.log`. The installed app was
not uninstalled and its worlds were not deleted. Updating while preserving
that container requires the same signing identity and identifier used for the
installed app. The corrected package has not run on the device; startup/world
entry and long-duration memory/synchronization acceptance remain unverified.
