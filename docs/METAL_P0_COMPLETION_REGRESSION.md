# Post-commit snapshot release regression — 2026-11-14

User device log run-1794660947910.log aborts in Metal after compiling the blur
pipeline. The stack is recycleOwnedBuffer → MetalNative.release →
prepareCpuWrite → mapBuffer → PostPass → processBlurEffect → GuiRenderer.draw.
Metal reports "Completed handler provided after commit call". This is a
native lifecycle assertion, not an allocation failure or the previous missing
GLFW mouse polling entrypoint. At ten seconds currentAllocatedSize is
321683456 bytes, tracked live is 241190672, pool is 27755456, transient backing
is 27828704, and allocation failures are zero. These metrics are distinct
from the HUD and process memory, and do not establish long-run stability.

The bridge retains the latest submitted command buffer as the target for late
snapshot reclamation. Previously recycleOwnedBuffer added a Metal completion
handler at Java release time, which is illegal after commit. Clearing that
target or immediately pooling the resource would allow GPU data corruption.

Install one completion mailbox when commands(ctx) creates the command buffer,
before any commit. Reclamation after commit enqueues an action in that mailbox;
the existing Metal completion callback drains it. Release after completion
executes the action immediately. Enqueue/completion are serialized; actions
execute outside the mailbox lock. The mailbox never retains its command
buffer, and drains its resource-owning actions at completion. No extra CPU/GPU
wait, quality change, Mod removal, or memory-policy expansion is introduced.
Java signatures and JNI exports are unchanged.

Evidence under the main checkout's artifacts directory:

- metal-p0-completion-baseline-01: same new JNI regression compiled against
  bf38a84 source aborts with exit -6 and the identical Metal assertion.
- graphics/metal-p0-completion-01: iPhoneOS backend compiles with warnings as
  errors. All host contracts pass. The exact JNI release regression verifies
  delayed GPU work, post-commit and post-completion releases, reuse and GPU
  readback. ASan/UBSan upload stress validates two runs of 20000 uploads.
- The lifetime fixture validates 16 concurrent releases, two queues completed
  out of order, 32 registration/completion races and the existing 1200-frame
  bounded-resource workload.
- metal-p0-completion-python-tests-01.log: 317 tests, 314 passed, 3 skipped.

## Matching signed export

Source: 2a6a7b11556b8079dbe92d3d0347ff1df5ae9c9c. Fresh Minecraft 26.1.2 /
Fabric iOS ARM64 AOT completed in 712.6 seconds. Object SHA256:
4e636d351af686db053df873c317dd88f34ba8e1121171abcbf6db630cf567cf.
Full link has no unresolved symbols. The existing unsupported
OperatingSystemImpl.initialize0 entrypoint remains; Mod compatibility is not
established by this build.

Local licensed IPA:
artifacts/mcfao/metal-p0-completion-full-game-signed-01/export/FabricAOT World.ipa
(714522739 bytes). SHA256:
08c1f99b916b7254d888454ca20dc4ad830046cf586260b55c908e5855217e0c.
Export status DEVELOPMENT_IPA_VERIFIED; profile covers the requested iPhone,
expires 2026-11-17 13:48:54 UTC, and has no dynamic-code entitlements.

Packaged AOT/Metal/GLFW/LWJGL UUIDs and shader hashes match staged inputs;
the Metal UUID matches the newly rebuilt backend. All tracked source inputs
match: Metal 24, GLFW 5, LWJGL 14. All 35 Java classes and 33 JNI exports are
unchanged from the preceding backend. The separate lifetime fixture also
passes ASan/UBSan, including completion races; fixture device bytes stay at
1540096 from frame 200 to 1200. This is host fixture data, not an iPhone curve.

Evidence: artifacts/metal-p0-completion-delivery.json,
metal-p0-completion-source-check.json, metal-p0-completion-abi-inputs.json,
metal-p0-completion-lifetime-sanitized-01, build/export logs and manifests.
No binary is published. No installation or uninstall was performed. The
installed app uses another re-signing identity: preserve its original signing
settings when updating to retain its container and saves.

Host proof and signed packaging do not establish iPhone world entry, memory
stability, sync percentiles or the 10/10/15-minute device scenarios. No new
device measurements exist. Gate C/E acceptance remains incomplete pending
new device evidence; P0 is not declared complete.
