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

Fresh matching AOT/link/sign/export is required before delivery. Host proof
does not establish iPhone world entry or long-run acceptance. Gate C/E remains
incomplete pending new device evidence.
