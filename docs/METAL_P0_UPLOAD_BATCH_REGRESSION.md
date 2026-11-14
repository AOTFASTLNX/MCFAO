# Startup atlas upload submission regression

2026-11-14. Corrected device world entry and Gate E remain unverified.

## Device evidence

The second user log, `run-1794655944657.log`, contains the new
`transient_allocated_bytes` metric and advances past the earlier cube-map
failure. At line 554 an atlas sprite upload fails: 67,098,624 transient bytes
are held against the unchanged 67,108,864-byte cap; a further 16,384-byte
request is rejected. There are 15,012 transient allocations, zero returned
buffers, zero committed/in-flight command buffers, and 222,314,496 device
allocated bytes. The fatal stack is `SpriteContents.uploadFirstFrame` ->
`MetalNative.writeTexture`. This is actual pending transient accumulation,
not the persistent/transient accounting error fixed previously.

`writeTexture` encoded all copies into `ctx.pending`, registering reclamation
at completion. That buffer was normally committed only by a later fence,
presentation, or explicit synchronization. Initial atlas loading exceeds the
cap before reaching those calls. Waiting for its completion cannot make
progress because the command buffer has not been submitted.

## Correction

Submit texture upload batches asynchronously at 8 MiB or 256 uploads, whichever
comes first, after the current blit encoder has ended and staging reclamation
has been registered. Also submit pending work before an allocation that would
exceed currently available transient backing capacity. All batches use the
existing graphics command queue, preserving ordered uploads and subsequent
draw/readback dependencies. Active render passes are never split.

No new CPU wait or raised cap is introduced. GPU-held staging remains charged
and unreusable until completion; the existing bounded allocator pressure wait
can now wait for submitted work. The remainder of a small batch is submitted
by the usual fence/present/readback path. Batch diagnostics are logged on the
first batch and at most once per five seconds thereafter.

## Reproduction and validation

`tests/metal_upload_burst_test.m` includes the actual JNI bridge implementation
and calls `MetalNative.writeTexture` directly with real Metal textures.
The previous implementation fails at upload 16,384 with zero committed work.
The corrected implementation passes 20,000 small uploads with full pixel
readback comparison, fewer than 200 batches, and no explicit synchronous
bridge submission before readback. A 128 KiB cap forces the pre-allocation
submission path; another 20,000 uploads pass pixel comparison. A separate
40-upload workload verifies the 8 MiB byte threshold below the count limit
and compares all final pixels. ASan/UBSan are enabled.

Backend `artifacts/graphics/metal-p0-upload-02` passes iPhoneOS warnings-as-errors
compilation, host texture contracts, pixel layout, 1,200-frame resource lifecycle
and the new actual-bridge upload fixture. Python: 315 run, 312 passed, 3 skipped.
Evidence under the main checkout: `artifacts/metal-p0-upload-burst-before.log`,
`artifacts/metal-p0-upload-backend-02.log`,
`artifacts/graphics/metal-p0-upload-02/upload-burst-run/`,
`artifacts/metal-p0-upload-python-tests-01.log`.

These host results establish the reproduced upload defect and its correction.
They do not establish device world entry, long-run memory stability, or device
sync latency. Other nonfatal mod/config/audio errors in the supplied log
remain separate compatibility issues.

## Matching full-game export

Runtime source: `c99942a7924f1862d8a3aaaa166039d6af6524f0`. A fresh full-game
iOS ARM64 AOT completed in 660.3 seconds, followed by full linking and
`SIGNED_DEVICE_APP`. The link has no unresolved symbols; the pre-existing
unsupported/trapping `OperatingSystemImpl.initialize0` entrypoint remains,
so linking does not establish complete runtime compatibility.

Local licensed export:
`artifacts/mcfao/metal-p0-upload-full-game-signed-01/export/FabricAOT World.ipa`.
Export status: `DEVELOPMENT_IPA_VERIFIED`; 714,166,382 bytes. SHA256:
`e4a862ea0a13a952a670324ca5430531ce3b2bd1fcbbb8b4534571713a35b600`.
Fresh AOT object SHA256:
`399529017dbcf9af13cfc93eb25b353c463b89ca10c8e074a2d62d26b9ec527a`.

The input manifest selects `metal-p0-upload-02`. Packaged AOT and Metal
Mach-O UUIDs match the staged outputs; the Metal UUID also matches that
backend. Present metallib and all packaged shader hashes match the inputs.
Signature verification covers the requested iPhone, with no dynamic-code
entitlements. The profile expires at 2026-11-17 13:48:54 UTC.

Evidence in the main checkout: `artifacts/metal-p0-upload-delivery.json`,
`artifacts/metal-p0-upload-abi-inputs.json`,
`artifacts/metal-p0-upload-full-game-01.log`,
`artifacts/metal-p0-upload-full-game-export-01.log`, and the build/export
directories' manifests and command logs. No proprietary IPA is uploaded.

No installation or launch of this export was performed. The previously
installed app uses another re-signing identity/application identifier; the
previous in-place Xcode installation was rejected by iOS. The user must
retain the same re-signing settings for an update that preserves the app
container. No uninstall or world deletion was performed. Device world entry,
10/10/15-minute scenarios, memory curves, and sync P95/P99 remain unverified;
Gate E remains BLOCKED.
