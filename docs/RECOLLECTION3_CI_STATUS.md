# Recollection3 Fabric CI integration (2026-11-14)

Status: **BLOCKED**. Do not label the output as a complete working Recollection3 IPA.

The user's Recollection3 manifest and embedded overrides identify 53 root mod JARs. `ci/recollection3-mods.json` records official download URLs, sizes and SHA-512 hashes; it contains no mod binaries. CircleCI macOS build 97 verified all 53 inputs and produced a Fabric transformation, but `ci/check_fabric_result.py` correctly rejected it because the export omitted mod IDs. Build 98 repeated the transformation and printed the omitted IDs and root JARs.

The transform excluded `customskinloader`, `entity_model_features`, `net_lenni0451_reflect`, `net_lostluma_battery`, `net_neoforged_bus`, `org_javassist_javassist`, `org_jetbrains_kotlin_kotlin-reflect`, and `org_reflections_reflections`. The root JARs retired were `CustomSkinLoader_Universal-14.28.jar` and `entity_model_features_26.1-fabric-3.2.2.jar`. These are transformation findings, not evidence that the remaining mods work on iOS. Reasons include native methods and runtime class generation/definition, unsupported by the current closed-world pipeline.

There is an independent renderer blocker: the pack contains Sodium and the current iOS Metal backend does not implement desktop OpenGL. Earlier simulator evidence and technical details are in `docs/FABRIC_AOT.md` under “平台级不兼容”. The CI gate rejects Sodium so that successful bytecode export is not mistaken for a working renderer. An actual compatible graphics implementation or verified mod adaptation is needed; pretending to support the calls or skipping the check is not a fix.

The current fetch-and-transform CI path does **not** import the pack's config, resource-pack, or shader-pack overrides, and Fabric Loader 0.19.3 is used by the project while the pack requests 0.19.2. The transformed build has not been compiled into an IPA, installed, or tested on a device. Full pack compatibility, FPS, and startup therefore remain unverified. Do not publish proprietary game assets, mod JARs, user configuration, or a prebuilt IPA in the public source repository.

To reproduce on an isolated macOS build machine, run `FAOT_BUILD_LOADER=fabric FAOT_FETCH_RECOLLECTION3=1 ... bash ci/build_mac.sh` with the documented build prerequisites. The Fabric check runs before the lengthy game asset staging. Third-party build-time code must remain inside the existing `sandbox-exec` isolation and must not be executed directly on the user's host.
