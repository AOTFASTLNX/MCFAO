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
