# GL41 branch audit

Checked 2026-11-15 (Asia/Shanghai) using live git ls-remote, GitHub PR query, fetch, merge-base, rev-list, log, diff, cherry and merge-tree. Hashes are this snapshot.

| Ref | SHA | Merge base | Behind / ahead | Predicted conflicts with main |
|---|---|---|---|---|
| `main` | `236c161d4cff497530f39f8b239b7259bf4f3015` | `236c161d4cff` | 0 / 0 | none |
| `archive/main-pre-gl41-20261115` | `236c161d4cff497530f39f8b239b7259bf4f3015` | `236c161d4cff` | 0 / 0 | none |
| `integration/gl41-gui-ipa-20261115` | `236c161d4cff497530f39f8b239b7259bf4f3015` | `236c161d4cff` | 0 / 0 | none |
| `fix/v21-baseline-input-layout` | `50e3a17fec16db82f2ad9109571df70cd30fed95` | `d7468f22e558` | 4 / 4 | CONFLICT (content): Merge conflict in .github/workflows/launcher-metal-checks.yml |
| `codex/mdaf` | `6b494a74bbef50a4351f5bbe82c69615492562b6` | `4533508fd658` | 3 / 1 | none |
| `fix/recollection3-fabric-pipeline` | `f0a6d8c7dad748467ad28ba7bcbb945e5ab04fc0` | `d7468f22e558` | 4 / 48 | CONFLICT (content): Merge conflict in .github/workflows/launcher-metal-checks.yml |
| `archive/gl41-v14-operations` | `f0a6d8c7dad748467ad28ba7bcbb945e5ab04fc0` | `d7468f22e558` | 4 / 48 | CONFLICT (content): Merge conflict in .github/workflows/launcher-metal-checks.yml |
| `fix/metal-resource-lifetime-p0` | `958a2706f03493b14b9e6d5bca124a5d5908083c` | `4533508fd658` | 3 / 14 | none |
| `feature/performance-launcher-size-2026-11-13` | `75cce3c4ee6966359fcc754862b734b7f72d07ba` | `163d02974163` | 28 / 2 | none |
| `codex/fix-metal-vsync-startup` | `84f3ade907e25ffb9461401c0137e5de40fe323c` | `e5e3655e1827` | 5 / 2 | none |
| `circleci-project-setup` | `61c21424353577ab31f9487f034a62690f2af6be` | `e337d0bacb81` | 82 / 2 | CONFLICT (add/add): Merge conflict in .circleci/config.yml |

## Decisions

- main, backup and initial integration head all match 236c161d4cff497530f39f8b239b7259bf4f3015. PR #11 desktop and #12 CI cleanup are already merged and retained.
- v21 is an ancestor of GL41 (merge-base --is-ancestor exit 0). Integrate its four commits once before GL41.
- MDAF is a distinct commit; preserve isolated tracing and metadata merging. PR #10 stays open.
- P0: transplant c9c4659, 7d7f945, 1f46004. Native Metal resource and presentation optimizations are not GL41 dependencies.
- Both GL41 refs point to f0a6d8c7dad748467ad28ba7bcbb945e5ab04fc0. Preserve complete implementation, tests and history. gl41-v14 tag 4cf11f3 peels to e0cb34f and is retained.
- Performance and vsync branches contain native Metal work; evaluate independently, do not merge indiscriminately.
- CircleCI setup diverges far behind main; retain main workflows and commit pinning.
- git cherry found no patch-equivalent unique commits against main; shared ancestry is handled separately.

## Unique commits and changed files

Raw command results: local artifacts/integration-20261115/logs/branch-audit.json.

### fix/v21-baseline-input-layout

```text
50e3a17fec16db82f2ad9109571df70cd30fed95 fix: restrict lenient mod metadata to descriptions
4910efd01c92fc316a8c3d2b320243b93185d3b5 fix: inspect case-sensitive mod jars and nonstandard metadata
09ce1cdd294ac511af46dcef2e87be820823751e fix: preserve interface initializers during AOT method splitting
47ba478876e3b74a981965328bbda9de42726023 fix: persist edited controls and build v21 input fixes from matching source
M	.github/workflows/launcher-metal-checks.yml
M	ci/build_mac.sh
A	ci/verify_interface_classes.py
M	compiler/splitter/src/fabricaot/split/MethodSplitter.java
M	ios/C0Harness/FAOTControlEditorViewController.m
M	ios/C0Harness/FAOTControlLayout.m
M	ios/C0Harness/FAOTLauncherViewController.m
M	tests/launcher_smoke_main.m
M	tests/test_preflight.py
M	tools/preflight.py
```

### codex/mdaf

```text
6b494a74bbef50a4351f5bbe82c69615492562b6 Add mechanism-driven Fabric adaptation framework
M	docs/MOD_ADAPTATION_PLAN.md
M	interop/diagnostics/ModNamespacesProbe.java
A	interop/fabric/tool/mcfao/build/AdaptationRuleEngine.java
M	interop/fabric/tool/mcfao/build/RuntimeLowering.java
M	tests/test_mcfao.py
A	tests/test_mdaf.py
M	tests/test_runtime_lowering.py
M	tests/test_verify_aot_classpath.py
M	tools/config_reflection.py
M	tools/mcfao.py
A	tools/mdaf.py
M	tools/prepare_fabric_aot.py
M	tools/probe_client_graph.py
M	tools/verify_aot_classpath.py
```

### fix/recollection3-fabric-pipeline

```text
f0a6d8c7dad748467ad28ba7bcbb945e5ab04fc0 Correct the limiter observation: 60 then 120 on every run
a2089275425d08a0d6ee1758b36e05d011854d2f Record the v14 device recheck: the Mesa disk cache already worked
68bb361e62c5183cc14321779222d0a06567b81b docs: name the archived job JSON files explicitly
a30f1dc95a6c152c97a56cac44efbb8f06e342db Archive GL41 v14 build and the 2026-11-14 operation record
17fc8b6ace40e475e53f198c4ccfe23a19e20ca6 Persist GL41 shader cache in the app Documents directory
e0cb34f85b31d15374c464a8ddee12eff3d4d7ec Document GL41 renderer configuration study
509212c02d989ebe4f9c5c0b48de15a6e1bed683 Record GL41 diagnostic IPA device results
bb65fee877fdcc339f588100c28299022e56c0c2 Measure GL41 finish and inter-swap frame timing
bff5fd1b23f4bfc4c8feafc98ae7603e52165037 Record GL41 v13 USB device performance
ff558484fe5319bad52d4d6dacd4dc8cb99223d9 Record GL41 v12 device regression and v13 build
8637ce3dc0c12fd1c1fea29df6b70ad77a770f1f Remove GL41 frame cap and fix park overshoot
ebee9b7caac3caa68246acf7153c0fdaa014766e Record GL41 v12 scaled steady-60 build
affd1c168e07a58bb43cac33bc2531e4155c74b7 Verify scaled GLFW sizes in the host fixture
bf999cd697d43f488184dd99f1e87ea54d1dcdcb Scale GL41 render to 80% and cap steady frame rate
937eb430dd69146af27bfae9fd1b9d0c61b785e3 Record GL41 v11 120 Hz build
eabc50646f9f7ec741db2c7ca006e9fa01fb3c8c Unlock 120 Hz pacing and preallocate GL41 uniforms
f1aedeff2c33595b9d63ef6da464a1d594ebe1c7 Record GL41 v10 presentation build and v9 frame baseline
bacc996216e48e3589964feb1ed560cb9fa57935 Move GL41 drawable waits off the game thread
964910aba2275532dc08d783ca08ab4887bf63ec Record verified GL41 v9 unsigned build
9a7592696fb0b2fd9ad4849a6642827322a6a599 Preserve GL41 world readiness and diagnose join stalls
93bac372ccd9268a4a0e410094a0ee135563aa71 Bypass client chunk visibility gate after join
dcd5a87de9bba258f1c08d3e9d2ceb1e88f42363 Record GL41 v7 native-resolution fix
85f09322e8edcda0cbf4f3393d4235e2b3c75675 Restore native render resolution and disable Mesa GL thread
e2093e0265dc685bf21c3c9b676828fa718c7057 Record GL41 v6 performance build
75245a9c72c801926a6e22a8ce21f3f2a1aaa114 Silence unused ARC block parameter
a716aa4bfd40d2ccf5b25feddbf625bf0dc1e779 Optimize GL41 presentation with triple buffering and scaled rendering
cd9435033531cedc466b94ed7bf17bea9077d5a9 Record GL41 v5 loading-screen fix
e7182bc79992620f5211dd4b961d5b2b3acbd2a7 Bypass stalled client load wait and accept inactive launch scene
384ef201f35edd71118dfbf130be217edeea0584 Record GL41 v4 JNI table fix
045685fca0efc3c3757519b7bc7488649697b05e Allow static JNI dispatch during GL initialization
8466c1bb6720c93d61f034d769759b0cf3353a67 Record GL41 v3 device-crash fixes
d91dc4f0f6f84be112a2f35b9ad65473967374a0 Fix LWJGL context discovery and disable 4.5 DSA on GL41
97a60f924bd0715ed5ad97c112046bf01c6c071d Record GL41 v2 build result
0d9fe55da189901d6a9d46374b8b7585ccb80952 Add minimal OSMesa context fallback
d3a52d6f2a007c5f91b27846544cf4264cf2a231 Record GL41 v1 vanilla build result
79f3032bc0df23da8f63a3b87c0a5401629488f0 Silence unavailable GL wrapper parameters
9606ef1a6db2ab7a1f02178d52bdcedc79ffc47b Allow deferred GLFW contexts and update host fixture
5eebefc3fed858a36714663d7de52cdefd565127 Add experimental OpenGL 4.1 renderer path
1e30206587797b473aac1df15795f04c29c9def9 Inventory OpenGL requirements for iOS renderer experiment
de44d9a796d04ac1ff1fe55e7d759d0a5cd19e13 Document Recollection3 Fabric compatibility blockers
a36ba15445a5e6012a0268a2c62c7ed811b40856 Reject unsupported Sodium on Metal builds
9c4dde669b758e5791f19bdebeee1aa2e27c8c88 Run Fabric compatibility checks before asset staging
3457a6b913fb2043019fb3e836825a8d2b739f57 Report Fabric export exclusions in CI
f90706cf1d4161ee2acf9661d7a3a9e20603224c build: prepare verified Recollection3 Fabric AOT input
50e3a17fec16db82f2ad9109571df70cd30fed95 fix: restrict lenient mod metadata to descriptions
4910efd01c92fc316a8c3d2b320243b93185d3b5 fix: inspect case-sensitive mod jars and nonstandard metadata
09ce1cdd294ac511af46dcef2e87be820823751e fix: preserve interface initializers during AOT method splitting
47ba478876e3b74a981965328bbda9de42726023 fix: persist edited controls and build v21 input fixes from matching source
M	.github/workflows/launcher-metal-checks.yml
M	ci/build_mac.sh
A	ci/check_fabric_result.py
A	ci/fetch_locked_mods.py
A	ci/recollection3-mods.json
A	ci/snapshots/circleci-v14.yml
A	ci/snapshots/circleci-v15.yml
A	ci/verify_interface_classes.py
A	compiler/gl41/tools/fabricaot/gl41/FramePacing.java
A	compiler/gl41/tools/fabricaot/gl41/PatchDevice.java
M	compiler/lwjgl-lite/Overlay.java
M	compiler/lwjgl-lite/src/org/lwjgl/system/Library.java
M	compiler/lwjgl-lite/src/org/lwjgl/system/ThreadLocalUtil.java
M	compiler/metal-backend/tools/fabricaot/diag/PlayDiagnostics.java
M	compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java
M	compiler/splitter/src/fabricaot/split/MethodSplitter.java
A	docs/GL41_RENDERER.md
A	docs/GL41_V14_DEVICE_RECHECK_2026-11-15.md
A	docs/GL41_V14_OPERATIONS_2026-11-14.md
A	docs/OPENGL41_IOS_INVESTIGATION.md
A	docs/RECOLLECTION3_CI_STATUS.md
A	evidence/gl41-v14/FabricAOT-GL41-v14-README.txt
A	evidence/gl41-v14/README.md
A	evidence/gl41-v14/configs/options-check.txt
A	evidence/gl41-v14/configs/options-check2.txt
A	evidence/gl41-v14/configs/options-restore.txt
A	evidence/gl41-v14/configs/watcher-status.txt
A	evidence/gl41-v14/device-2026-11-15/cache-tree.txt
A	evidence/gl41-v14/logs/gl41-jobs.json
A	evidence/gl41-v14/logs/gl41-v10-build-full.json
A	evidence/gl41-v14/logs/gl41-v11-full.json
A	evidence/gl41-v14/logs/gl41-v12-full.json
A	evidence/gl41-v14/perf-v14.md
A	evidence/gl41-v14/screenshots/diag-screen.png
A	evidence/gl41-v14/scripts/bench.ps1
A	evidence/gl41-v14/scripts/bench_run.py
A	evidence/gl41-v14/scripts/bench_stats.py
A	evidence/gl41-v14/scripts/cache_test.py
A	evidence/gl41-v14/scripts/circle-fetch-diag.js
A	evidence/gl41-v14/scripts/circle-repair-diag.js
A	evidence/gl41-v14/scripts/circle-repair-v13.js
A	evidence/gl41-v14/scripts/circle-status-diag.js
A	evidence/gl41-v14/scripts/circle-url.js
A	evidence/gl41-v14/scripts/gl41-audit-v10.py
A	evidence/gl41-v14/scripts/gl41-audit-v11.py
A	evidence/gl41-v14/scripts/gl41-audit-v12.py
A	evidence/gl41-v14/scripts/gl41-audit-v13.py
A	evidence/gl41-v14/scripts/gl41-audit-v15.py
A	evidence/gl41-v14/scripts/gl41-audit-v9.py
A	evidence/gl41-v14/scripts/install-frame-diag.ps1
A	evidence/gl41-v14/scripts/list_docs.py
A	evidence/gl41-v14/scripts/ls3.py
A	evidence/gl41-v14/scripts/ls_cache.py
A	evidence/gl41-v14/scripts/mk.py
A	evidence/gl41-v14/scripts/mkdir_docs.py
A	evidence/gl41-v14/scripts/steady_run.py
A	evidence/gl41-v14/scripts/watch_game_logs.py
M	interop/graphics/glfw_state_test.c
M	ios/C0Harness/FAOTControlEditorViewController.m
M	ios/C0Harness/FAOTControlLayout.m
M	ios/C0Harness/FAOTLauncherViewController.m
M	ios/C0Harness/embed_graphics_libraries.sh
M	ios/C0Harness/main.m
M	ios/glfw-lite/glfw_lite.c
A	ios/glfw-lite/osmesa_gl.c
A	ios/glfw-lite/osmesa_gl.h
A	ios/glfw-lite/osmesa_present_host_stub.c
M	ios/glfw-lite/uikit_surface.m
M	ios/lwjgl-lite/core.c
M	tests/launcher_smoke_main.m
A	tests/test_build_lwjgl_opengl_ios.py
A	tests/test_fabric_ci.py
A	tests/test_inventory_mod_opengl_calls.py
M	tests/test_preflight.py
M	tools/build_glfw_lite.py
A	tools/build_lwjgl_opengl_ios.py
A	tools/fetch_gl41_runtime.py
A	tools/inventory_mod_opengl_calls.py
A	tools/patch_gl41_client.py
M	tools/preflight.py
M	tools/stage_device_xcode.py
```

### archive/gl41-v14-operations

```text
f0a6d8c7dad748467ad28ba7bcbb945e5ab04fc0 Correct the limiter observation: 60 then 120 on every run
a2089275425d08a0d6ee1758b36e05d011854d2f Record the v14 device recheck: the Mesa disk cache already worked
68bb361e62c5183cc14321779222d0a06567b81b docs: name the archived job JSON files explicitly
a30f1dc95a6c152c97a56cac44efbb8f06e342db Archive GL41 v14 build and the 2026-11-14 operation record
17fc8b6ace40e475e53f198c4ccfe23a19e20ca6 Persist GL41 shader cache in the app Documents directory
e0cb34f85b31d15374c464a8ddee12eff3d4d7ec Document GL41 renderer configuration study
509212c02d989ebe4f9c5c0b48de15a6e1bed683 Record GL41 diagnostic IPA device results
bb65fee877fdcc339f588100c28299022e56c0c2 Measure GL41 finish and inter-swap frame timing
bff5fd1b23f4bfc4c8feafc98ae7603e52165037 Record GL41 v13 USB device performance
ff558484fe5319bad52d4d6dacd4dc8cb99223d9 Record GL41 v12 device regression and v13 build
8637ce3dc0c12fd1c1fea29df6b70ad77a770f1f Remove GL41 frame cap and fix park overshoot
ebee9b7caac3caa68246acf7153c0fdaa014766e Record GL41 v12 scaled steady-60 build
affd1c168e07a58bb43cac33bc2531e4155c74b7 Verify scaled GLFW sizes in the host fixture
bf999cd697d43f488184dd99f1e87ea54d1dcdcb Scale GL41 render to 80% and cap steady frame rate
937eb430dd69146af27bfae9fd1b9d0c61b785e3 Record GL41 v11 120 Hz build
eabc50646f9f7ec741db2c7ca006e9fa01fb3c8c Unlock 120 Hz pacing and preallocate GL41 uniforms
f1aedeff2c33595b9d63ef6da464a1d594ebe1c7 Record GL41 v10 presentation build and v9 frame baseline
bacc996216e48e3589964feb1ed560cb9fa57935 Move GL41 drawable waits off the game thread
964910aba2275532dc08d783ca08ab4887bf63ec Record verified GL41 v9 unsigned build
9a7592696fb0b2fd9ad4849a6642827322a6a599 Preserve GL41 world readiness and diagnose join stalls
93bac372ccd9268a4a0e410094a0ee135563aa71 Bypass client chunk visibility gate after join
dcd5a87de9bba258f1c08d3e9d2ceb1e88f42363 Record GL41 v7 native-resolution fix
85f09322e8edcda0cbf4f3393d4235e2b3c75675 Restore native render resolution and disable Mesa GL thread
e2093e0265dc685bf21c3c9b676828fa718c7057 Record GL41 v6 performance build
75245a9c72c801926a6e22a8ce21f3f2a1aaa114 Silence unused ARC block parameter
a716aa4bfd40d2ccf5b25feddbf625bf0dc1e779 Optimize GL41 presentation with triple buffering and scaled rendering
cd9435033531cedc466b94ed7bf17bea9077d5a9 Record GL41 v5 loading-screen fix
e7182bc79992620f5211dd4b961d5b2b3acbd2a7 Bypass stalled client load wait and accept inactive launch scene
384ef201f35edd71118dfbf130be217edeea0584 Record GL41 v4 JNI table fix
045685fca0efc3c3757519b7bc7488649697b05e Allow static JNI dispatch during GL initialization
8466c1bb6720c93d61f034d769759b0cf3353a67 Record GL41 v3 device-crash fixes
d91dc4f0f6f84be112a2f35b9ad65473967374a0 Fix LWJGL context discovery and disable 4.5 DSA on GL41
97a60f924bd0715ed5ad97c112046bf01c6c071d Record GL41 v2 build result
0d9fe55da189901d6a9d46374b8b7585ccb80952 Add minimal OSMesa context fallback
d3a52d6f2a007c5f91b27846544cf4264cf2a231 Record GL41 v1 vanilla build result
79f3032bc0df23da8f63a3b87c0a5401629488f0 Silence unavailable GL wrapper parameters
9606ef1a6db2ab7a1f02178d52bdcedc79ffc47b Allow deferred GLFW contexts and update host fixture
5eebefc3fed858a36714663d7de52cdefd565127 Add experimental OpenGL 4.1 renderer path
1e30206587797b473aac1df15795f04c29c9def9 Inventory OpenGL requirements for iOS renderer experiment
de44d9a796d04ac1ff1fe55e7d759d0a5cd19e13 Document Recollection3 Fabric compatibility blockers
a36ba15445a5e6012a0268a2c62c7ed811b40856 Reject unsupported Sodium on Metal builds
9c4dde669b758e5791f19bdebeee1aa2e27c8c88 Run Fabric compatibility checks before asset staging
3457a6b913fb2043019fb3e836825a8d2b739f57 Report Fabric export exclusions in CI
f90706cf1d4161ee2acf9661d7a3a9e20603224c build: prepare verified Recollection3 Fabric AOT input
50e3a17fec16db82f2ad9109571df70cd30fed95 fix: restrict lenient mod metadata to descriptions
4910efd01c92fc316a8c3d2b320243b93185d3b5 fix: inspect case-sensitive mod jars and nonstandard metadata
09ce1cdd294ac511af46dcef2e87be820823751e fix: preserve interface initializers during AOT method splitting
47ba478876e3b74a981965328bbda9de42726023 fix: persist edited controls and build v21 input fixes from matching source
M	.github/workflows/launcher-metal-checks.yml
M	ci/build_mac.sh
A	ci/check_fabric_result.py
A	ci/fetch_locked_mods.py
A	ci/recollection3-mods.json
A	ci/snapshots/circleci-v14.yml
A	ci/snapshots/circleci-v15.yml
A	ci/verify_interface_classes.py
A	compiler/gl41/tools/fabricaot/gl41/FramePacing.java
A	compiler/gl41/tools/fabricaot/gl41/PatchDevice.java
M	compiler/lwjgl-lite/Overlay.java
M	compiler/lwjgl-lite/src/org/lwjgl/system/Library.java
M	compiler/lwjgl-lite/src/org/lwjgl/system/ThreadLocalUtil.java
M	compiler/metal-backend/tools/fabricaot/diag/PlayDiagnostics.java
M	compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java
M	compiler/splitter/src/fabricaot/split/MethodSplitter.java
A	docs/GL41_RENDERER.md
A	docs/GL41_V14_DEVICE_RECHECK_2026-11-15.md
A	docs/GL41_V14_OPERATIONS_2026-11-14.md
A	docs/OPENGL41_IOS_INVESTIGATION.md
A	docs/RECOLLECTION3_CI_STATUS.md
A	evidence/gl41-v14/FabricAOT-GL41-v14-README.txt
A	evidence/gl41-v14/README.md
A	evidence/gl41-v14/configs/options-check.txt
A	evidence/gl41-v14/configs/options-check2.txt
A	evidence/gl41-v14/configs/options-restore.txt
A	evidence/gl41-v14/configs/watcher-status.txt
A	evidence/gl41-v14/device-2026-11-15/cache-tree.txt
A	evidence/gl41-v14/logs/gl41-jobs.json
A	evidence/gl41-v14/logs/gl41-v10-build-full.json
A	evidence/gl41-v14/logs/gl41-v11-full.json
A	evidence/gl41-v14/logs/gl41-v12-full.json
A	evidence/gl41-v14/perf-v14.md
A	evidence/gl41-v14/screenshots/diag-screen.png
A	evidence/gl41-v14/scripts/bench.ps1
A	evidence/gl41-v14/scripts/bench_run.py
A	evidence/gl41-v14/scripts/bench_stats.py
A	evidence/gl41-v14/scripts/cache_test.py
A	evidence/gl41-v14/scripts/circle-fetch-diag.js
A	evidence/gl41-v14/scripts/circle-repair-diag.js
A	evidence/gl41-v14/scripts/circle-repair-v13.js
A	evidence/gl41-v14/scripts/circle-status-diag.js
A	evidence/gl41-v14/scripts/circle-url.js
A	evidence/gl41-v14/scripts/gl41-audit-v10.py
A	evidence/gl41-v14/scripts/gl41-audit-v11.py
A	evidence/gl41-v14/scripts/gl41-audit-v12.py
A	evidence/gl41-v14/scripts/gl41-audit-v13.py
A	evidence/gl41-v14/scripts/gl41-audit-v15.py
A	evidence/gl41-v14/scripts/gl41-audit-v9.py
A	evidence/gl41-v14/scripts/install-frame-diag.ps1
A	evidence/gl41-v14/scripts/list_docs.py
A	evidence/gl41-v14/scripts/ls3.py
A	evidence/gl41-v14/scripts/ls_cache.py
A	evidence/gl41-v14/scripts/mk.py
A	evidence/gl41-v14/scripts/mkdir_docs.py
A	evidence/gl41-v14/scripts/steady_run.py
A	evidence/gl41-v14/scripts/watch_game_logs.py
M	interop/graphics/glfw_state_test.c
M	ios/C0Harness/FAOTControlEditorViewController.m
M	ios/C0Harness/FAOTControlLayout.m
M	ios/C0Harness/FAOTLauncherViewController.m
M	ios/C0Harness/embed_graphics_libraries.sh
M	ios/C0Harness/main.m
M	ios/glfw-lite/glfw_lite.c
A	ios/glfw-lite/osmesa_gl.c
A	ios/glfw-lite/osmesa_gl.h
A	ios/glfw-lite/osmesa_present_host_stub.c
M	ios/glfw-lite/uikit_surface.m
M	ios/lwjgl-lite/core.c
M	tests/launcher_smoke_main.m
A	tests/test_build_lwjgl_opengl_ios.py
A	tests/test_fabric_ci.py
A	tests/test_inventory_mod_opengl_calls.py
M	tests/test_preflight.py
M	tools/build_glfw_lite.py
A	tools/build_lwjgl_opengl_ios.py
A	tools/fetch_gl41_runtime.py
A	tools/inventory_mod_opengl_calls.py
A	tools/patch_gl41_client.py
M	tools/preflight.py
M	tools/stage_device_xcode.py
```

### fix/metal-resource-lifetime-p0

```text
958a2706f03493b14b9e6d5bca124a5d5908083c Document matching triple-drawable AOT and signed IPA verification
3a92a229ef97a637065114d1e6def4a2f15a40c2 Restore three-drawable pipelining and submit rendering before display waits
713c8b0c1ec6ade5778aaedf5d5c392d0b2495ad docs: record signed post-commit release regression build
2a6a7b11556b8079dbe92d3d0347ff1df5ae9c9c Fix snapshot reclamation after Metal command buffer commit
bf38a84b3312f60f34a650f31d6e230ee618a549 docs: record matched input polling IPA verification
1f46004f2a59d87a28dfe08bd3f351bdbe8b6483 fix(ios): require matching GLFW input polling exports
753bdb359c3c284d6902dfcdf95190d92d8cd814 docs: record matching upload batch IPA evidence
c99942a7924f1862d8a3aaaa166039d6af6524f0 fix(metal): submit bounded startup texture upload batches
5c80a6707f03dc3ad3dcfd5bccd35a723d8f75b9 docs: record corrected startup IPA and device update blocker
7e73a60be81a422b06f3c30ed3c60997324e2fc4 fix(metal): isolate transient backing budget from persistent textures
af0c7047d8e7feb40de7ed2a416628d75b08df35 docs: record full P0 game AOT and signed IPA evidence
7d7f9455e16cadf33ee9cf77c7bfb42aa72db91b Retain pending artifact registration when local AAR is unavailable
c9c46592d09e55103b2184dd09507a991d482b95 Fix sandbox cwd resolution for AOT probe
1d8790e9e49cf28741b9a1f44edbf710c098e701 fix(metal): bound transient resource lifetime and add memory diagnostics
M	compiler/metal-backend/src/fabricaot/metal/MetalCommandEncoder.java
M	compiler/metal-backend/src/fabricaot/metal/MetalDevice.java
A	docs/METAL_P0_COMPLETION_REGRESSION.md
A	docs/METAL_P0_INPUT_STARTUP_REGRESSION.md
A	docs/METAL_P0_IPA_20261114.md
A	docs/METAL_P0_STARTUP_REGRESSION.md
A	docs/METAL_P0_TRIPLE_PRESENTATION.md
A	docs/METAL_P0_UPLOAD_BATCH_REGRESSION.md
A	docs/METAL_RESOURCE_LIFETIME_P0.md
M	interop/graphics/LwjglProbe.java
M	ios/metal-bridge/metal_bridge.m
A	ios/metal-bridge/metal_resources.h
A	ios/metal-bridge/metal_resources.m
A	tests/metal_resource_lifetime_test.m
A	tests/metal_upload_burst_test.m
M	tests/test_buffer_sync_contract.py
M	tests/test_graphics_bridge.py
M	tests/test_high_refresh.py
A	tests/test_metal_resource_lifetime.py
M	tools/build_glfw_lite.py
M	tools/build_lwjgl_lite.py
M	tools/build_metal_backend.py
M	tools/graphics_common.py
M	tools/mcfao.py
M	tools/probe_client_graph.py
```

### feature/performance-launcher-size-2026-11-13

```text
75cce3c4ee6966359fcc754862b734b7f72d07ba perf: submit offscreen rendering before drawable acquisition
e10357718fbcba5f2626d6b9afdc236c4d6c13be perf: bound snapshots for medium sized GPU buffers
M	compiler/metal-backend/src/fabricaot/metal/MetalCommandEncoder.java
M	docs/performance-2026-11-13.md
M	ios/metal-bridge/metal_bridge.m
M	tests/metal_snapshot_test.m
M	tests/test_buffer_sync_contract.py
```

### codex/fix-metal-vsync-startup

```text
84f3ade907e25ffb9461401c0137e5de40fe323c Document signed Metal vsync IPA
a3ceccfbf47639b9cb584846ce36c249e7b16435 Fix Metal vsync startup crash
M	docs/STATUS.md
A	tests/test_graphics_source_fingerprints.py
M	tools/build_metal_backend.py
M	tools/graphics_common.py
M	tools/mcfao.py
M	tools/probe_client_graph.py
M	tools/stage_device_xcode.py
```

### circleci-project-setup

```text
61c21424353577ab31f9487f034a62690f2af6be ci: add manual pinned GraalVM 25 toolchain preflight
14bdf4e6a63f8da57bffecbdeeb1fd10f6e124fa ci: add opt-in Apple Silicon CircleCI environment check
A	.circleci/config.yml
```
