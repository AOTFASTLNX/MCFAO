# MCFAO 整合包 AOT 兼容性矩阵

> 本文件由 `tools/generate_mod_matrix.py` 从验证包自身的 `result.json` 生成，请勿手改表格；人工判定的状态升级写在 `docs/MOD_MATRIX_EVIDENCE.json`。`BLOCKED` 不能被证据表升级——必须先重新进入验证包、重新取得 `BUILD_PASS`。
> 生成命令：`python3 -B tools/generate_mod_matrix.py --build artifacts/mcfao/fabric-pack-92`

## 状态定义（严格递增，不可由构建结果自动跳级）

| 状态 | 含义 | 需要的证据 |
| --- | --- | --- |
| `NOT_TESTED` | 未进入验证包，或该包未产出镜像 | 无 |
| `BLOCKED` | 已被证明无法进入闭世界，或平台级不可用 | 导出期排除报告 / 隔离清单 / 崩溃日志 |
| `BUILD_PASS` | 类进入 AOT 镜像，静态校验核心类 0 失败 | `SIGNED_DEVICE_APP` + `classpath-check.json` |
| `LOAD_PASS` | 运行期入口点派发完成、该 Mod 初始化未抛异常 | 模拟器 `game.log` 中该 Mod 的初始化标记 |
| `FUNCTION_PASS` | 该 Mod 的实际功能在运行的游戏内被观察到 | 功能探针 / 截图 / 状态断言 + 日志 |
| `DEVICE_PASS` | 在真机上复验通过 | 真机证据（本项目当前**不做真机验证**） |

> `BUILD_PASS` 只说明「类在镜像里」，不说明「Mod 能跑」。整包已在模拟器进世界（F1 + F3 + `Dev joined the game` 齐现），但没有任何 Mod 单独通过功能断言：逐 Mod `FUNCTION_PASS` 仍要各自的功能证据。

## 当前判据与 Gate

- 最新验证包：`artifacts/mcfao/fabric-pack-92`（pack-92），`result.json.status = SIGNED_DEVICE_APP`
- 根 Mod jar：41；解析出的 Mod id：114；导出期排除：6；独立隔离：7
- 资源命名空间表：`91` 个（旧包该项为 0，即清单字段缺失）
- 模拟器冒烟：`artifacts/mcfao/fabric-pack-92-simulator`（`SIMULATOR_WORLD_SMOKE_PASS`）— F1=PASS / F3=PASS / joined=PASS
- 未出现致命崩溃：日志无 `Unreported exception thrown` / 崩溃报告段落，启动期的离线认证、Realms、`oshi` 探测异常不计入。
- **Gate C / D（模拟器口径）：判据已全中**——F1 + F3 + `Dev joined the game`，`SIMULATOR_WORLD_SMOKE_PASS`。真机 `C1/C2` 与 Gate D 的 IPA/安装/存档保留仍未做 → `NOT RUN`。

## 汇总

| 状态 | 数量 |
| --- | ---: |
| `BLOCKED` | 13 |
| `BUILD_PASS` | 56 |
| `LOAD_PASS` | 57 |
| `FUNCTION_PASS` | 1 |

## 逐 Mod 矩阵（127 行）

| Mod ID | 版本 | 类别 | 状态 | 构建 | 日志 / 证据 | 回归测试 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| jade | 26.1.0+fabric | 内容 / 客户端 Mod | `FUNCTION_PASS` | pack-92 | fabric-pack-92-simulator/probe/attachments/probe-aim-down_0_0E5B452D-A266-43C7-9F6E-91F5BD1DA054.png（Sand 提示框）、fabric-pack-92-simulator/probe/attachments/probe-inventory_0_184238C5-1386-41CD-92CB-77FD9701ADFA.png（Service Door 提示框）、fabric-pack-92-simulator/game.log#L80,#L155,#L332-L334 | tools/function_probe_simulator.py + ios/C0Harness/WorldUITests.m#testFabricModFunctions + tests/test_runtime_lowering.py::test_jade_tooltip_mod_names_answer_from_the_generated_table | 定向适配：FabricJadeMetadata 构造器元数据折叠；根 jar: Jade-mc26.1-Fabric-26.1.0.jar；证据表：Jade 的方块提示框在游戏里真实渲染：对准沙地时显示 'Sand' + 蓝色模组名 'Minecraft'，打开创造物品栏悬停时显示 'Service Door' + 'Minecraft'。getModName 的 loader 分支已被改写为 Entrypoints.optionalModName，运行期未抛 NoSuchMethodError；glog :80/:155 两条入口点派发、:332-334 三个 addon 插件加载。 |
| advancednetherite | 2.4.1-26.1.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L43 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: advancednetherite-fabric-2.4.1-26.1.2.jar；证据表：advancednetherite 的 main 入口点 com.autovw.advancednetherite.AdvancedNetheriteFabric 派发返回，未抛异常 |
| ambientsounds | 6.3.6 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L102 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: AmbientSounds_FABRIC_v6.3.6_mc26.1.2.jar；证据表：ambientsounds 的 client 入口点 team.creative.ambientsounds.AmbientSounds 派发返回，未抛异常 |
| appleskin | 3.0.9+mc26.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L44 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: appleskin-fabric-mc26.1-3.0.9.jar；证据表：appleskin 的 main 入口点 squeek.appleskin.AppleSkinCommon 派发返回，未抛异常 |
| backpacked | 3.0.4 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L43 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: backpacked-fabric-26.1.2-3.0.4.jar；证据表：backpacked 在运行期打出初始化标记（token `backpacked`），入口点未抛异常 |
| biomesoplenty | 26.1.2.0.5 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L54 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：GlitchCore 监听器事件类型构建期解析；根 jar: BiomesOPlenty-fabric-26.1.2-26.1.2.0.5.jar；证据表：biomesoplenty 在运行期打出初始化标记（token `biomesoplenty`），入口点未抛异常 |
| chat_heads | 1.2.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L98 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: chat_heads-1.2.2-fabric-26.1.jar；证据表：chat_heads 的 client 入口点 dzwdz.chat_heads.fabric.ChatHeadsFabric 派发返回，未抛异常 |
| cloth-config | 26.1.154 | 库 / 嵌套依赖 | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L99 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: cloth-config-fabric-26.1.154.jar；证据表：cloth-config 的 client 入口点 me.shedaniel.autoconfig.example.ExampleInits::exampleCommonInit 派发返回，未抛异常 |
| conditional-mixin | 0.6.4 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L45 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: conditional-mixin-fabric-0.6.4.jar；证据表：conditional-mixin 的 main 入口点 me.fallenbreath.conditionalmixin.fabric.ConditionalMixinFabric 派发返回，未抛异常 |
| continuity | 3.0.1-beta.2+26.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L100 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: continuity-3.0.1-beta.2+26.1.jar；证据表：continuity 的 client 入口点 me.pepperbell.continuity.client.ContinuityClient 派发返回，未抛异常 |
| creativecore | 2.14.14 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L46 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: CreativeCore_FABRIC_v2.14.14_mc26.1.2.jar；证据表：creativecore 的 main 入口点 team.creative.creativecore.CreativeCore 派发返回，未抛异常 |
| entity_texture_features | 7.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L104 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: entity_texture_features_26.1-fabric-7.1.jar；证据表：entity_texture_features 的 client 入口点 traben.entity_texture_features.ETFInit 派发返回，未抛异常 |
| entityculling | 1.10.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L105 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: entityculling-fabric-1.10.2-mc26.1.jar；证据表：entityculling 的 client 入口点 dev.tr7zw.entityculling.EntityCullingMod 派发返回，未抛异常 |
| fabric-api-lookup-api-v1 | 2.0.11+d5a053b64c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L49 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-api-lookup-api-v1-2.0.11+d5a053b64c.jar；证据表：fabric-api-lookup-api-v1 的 main 入口点 net.fabricmc.fabric.impl.lookup.ApiLookupImpl 派发返回，未抛异常 |
| fabric-convention-tags-v2 | 4.5.0+c52289644c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L50 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-convention-tags-v2-4.5.0+c52289644c.jar；证据表：fabric-convention-tags-v2 的 main 入口点 net.fabricmc.fabric.impl.tag.convention.v2.TranslationConventionLogWarnings 派发返回，未抛异常 |
| fabric-data-attachment-api-v1 | 2.2.4+d602a8964c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L53 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-data-attachment-api-v1-2.2.4+d602a8964c.jar；证据表：fabric-data-attachment-api-v1 的 main 入口点 net.fabricmc.fabric.impl.attachment.AttachmentEntrypoint 派发返回，未抛异常 |
| fabric-dimensions-v1 | 5.1.5+9cbf5da54c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L47 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-dimensions-v1-5.1.5+9cbf5da54c.jar；证据表：fabric-dimensions-v1 的 main 入口点 net.fabricmc.fabric.impl.dimension.DimensionModificationImpl 派发返回，未抛异常 |
| fabric-events-interaction-v0 | 5.2.0+a67251b84c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L55 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-events-interaction-v0-5.2.0+a67251b84c.jar；证据表：fabric-events-interaction-v0 的 main 入口点 net.fabricmc.fabric.impl.event.interaction.InteractionEventsRouter 派发返回，未抛异常 |
| fabric-lifecycle-events-v1 | 4.1.0+6d50a0854c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L48 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-lifecycle-events-v1-4.0.6+a9b9c17659.jar, fabric-lifecycle-events-v1-4.1.0+6d50a0854c.jar；证据表：fabric-lifecycle-events-v1 的 main 入口点 net.fabricmc.fabric.impl.event.lifecycle.LifecycleEventsImpl 派发返回，未抛异常 |
| fabric-menu-api-v1 | 2.0.12+d871b99e4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L56 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-menu-api-v1-2.0.12+d871b99e4c.jar；证据表：fabric-menu-api-v1 的 main 入口点 net.fabricmc.fabric.impl.menu.Networking 派发返回，未抛异常 |
| fabric-model-loading-api-v1 | 8.0.6+c80601bb4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L116 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-model-loading-api-v1-8.0.6+c80601bb4c.jar；证据表：fabric-model-loading-api-v1 的 client 入口点 net.fabricmc.fabric.impl.client.model.loading.CustomUnbakedBlockStateModelInit 派发返回，未抛异常 |
| fabric-networking-api-v1 | 6.3.0+50a808ce4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L51 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-networking-api-v1-6.3.0+50a808ce4c.jar；证据表：fabric-networking-api-v1 的 main 入口点 net.fabricmc.fabric.impl.networking.CommonPacketsImpl::init 派发返回，未抛异常 |
| fabric-particles-v1 | 5.0.14+b61fef434c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L57 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-particles-v1-5.0.14+b61fef434c.jar；证据表：fabric-particles-v1 的 main 入口点 net.fabricmc.fabric.impl.particle.ExtendedBlockParticleOptionSync 派发返回，未抛异常 |
| fabric-recipe-api-v1 | 9.0.14+be4b75ae4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L58 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-recipe-api-v1-9.0.14+be4b75ae4c.jar；证据表：fabric-recipe-api-v1 的 main 入口点 net.fabricmc.fabric.impl.recipe.ingredient.CustomIngredientInit 派发返回，未抛异常 |
| fabric-registry-sync-v0 | 7.0.12+b61fef434c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L61 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-registry-sync-v0-7.0.12+b61fef434c.jar；证据表：fabric-registry-sync-v0 的 main 入口点 net.fabricmc.fabric.impl.registry.sync.FabricRegistryInit 派发返回，未抛异常 |
| fabric-renderer-api-v1 | 13.0.3+c80601bb4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L115 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-renderer-api-v1-13.0.3+c80601bb4c.jar；证据表：fabric-renderer-api-v1 的 client 入口点 net.fabricmc.fabric.impl.client.renderer.DebugOverlayClient 派发返回，未抛异常 |
| fabric-renderer-indigo | 8.1.0+1403e82c4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L60 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：shouldApplyIndigo 门控折叠；嵌套 jar: fabric-renderer-indigo-8.1.0+1403e82c4c.jar；证据表：fabric-renderer-indigo 在运行期打出初始化标记（token `Indigo`），入口点未抛异常 |
| fabric-rendering-v1 | 23.1.0+1403e82c4c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L114 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-rendering-v1-23.1.0+1403e82c4c.jar；证据表：fabric-rendering-v1 的 client 入口点 net.fabricmc.fabric.impl.client.rendering.hud.HudStatusBarHeightRegistryImpl 派发返回，未抛异常 |
| fabric-resource-conditions-api-v1 | 6.0.5+00a1fba64c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L62 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-resource-conditions-api-v1-6.0.5+00a1fba64c.jar；证据表：fabric-resource-conditions-api-v1 的 main 入口点 net.fabricmc.fabric.impl.resource.conditions.ResourceConditionsImpl 派发返回，未抛异常 |
| fabric-tag-api-v1 | 2.0.9+11a26f314c | Fabric API | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L63 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: fabric-tag-api-v1-2.0.9+11a26f314c.jar；证据表：fabric-tag-api-v1 的 main 入口点 net.fabricmc.fabric.impl.tag.TagInit 派发返回，未抛异常 |
| forgeconfigapiport | 26.1.4 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L64 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: ForgeConfigAPIPort-v26.1.4-mc26.1.x-Fabric.jar；证据表：forgeconfigapiport 的 main 入口点 fuzs.forgeconfigapiport.fabric.impl.ForgeConfigAPIPortFabric 派发返回，未抛异常 |
| framework | 0.13.23 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L74 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：@RegistryContainer 扫描改写为构建期表；根 jar: framework-fabric-26.1.2-0.13.23.jar；证据表：framework 的 main 入口点 com.mrcrayfish.framework.FrameworkFabric 派发返回，未抛异常 |
| freecam | 1.4.0-alpha.3 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L137 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: freecam-fabric-1.4.0-alpha.3+mc26.1.2.jar；证据表：freecam 的 client 入口点 net.xolt.freecam.fabric.FreecamFabric 派发返回，未抛异常 |
| ftblibrary | 26.1.2.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L77 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: ftb-library-fabric-26.1.2.2.jar；证据表：ftblibrary 的 main 入口点 dev.ftb.mods.ftblibrary.fabric.FTBLibraryFabric 派发返回，未抛异常 |
| ftbultimine | 26.1.2.3 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L78 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: ftb-ultimine-fabric-26.1.2.3.jar；证据表：ftbultimine 的 main 入口点 dev.ftb.mods.ftbultimine.fabric.FTBUltimineFabric 派发返回，未抛异常 |
| glitchcore | 26.1.2.0.0 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L79 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：EventManager.addListenerResolved 事件类型构建期解析；根 jar: GlitchCore-fabric-26.1.2-26.1.2.0.0.jar；证据表：glitchcore 的 main 入口点 glitchcore.fabric.core.GlitchCoreFabric 派发返回，未抛异常 |
| ias | 9.0.6+26.1.2-fabric | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L84 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: IAS-9.0.6+26.1.2-fabric.jar；证据表：ias 在运行期打出初始化标记（token `ias`），入口点未抛异常 |
| immediatelyfast | 1.15.2+26.1.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L126 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：MixinConfigPlugin.onLoad 的 earlyInit 重放 / 版本查询折叠；根 jar: ImmediatelyFast-Fabric-1.15.2+26.1.2.jar；证据表：immediatelyfast 在运行期打出初始化标记（token `immediatelyfast`），入口点未抛异常 |
| inventoryprofilesnext | 2.3.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L158 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: InventoryProfilesNext-fabric-26.1-2.3.2.jar；证据表：inventoryprofilesnext 的 client 入口点 org.anti_ad.mc.ipnext.InventoryProfilesKt::init 派发返回，未抛异常 |
| kirin | 1.22.0-beta.1+26.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L156 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: kirin-1.22.0-beta.1+26.1.jar；证据表：kirin 的 client 入口点 com.minelittlepony.kirin.impl.Test 派发返回，未抛异常 |
| libipn | 6.7.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L157 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: libIPN-fabric-26.1-6.7.2.jar；证据表：libipn 的 client 入口点 org.anti_ad.mc.common.LibIPNKt::init 派发返回，未抛异常 |
| litematica | 0.27.3 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L83 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: litematica-fabric-26.1.2-0.27.3.jar；证据表：litematica 的 main 入口点 fi.dy.masa.litematica.Litematica 派发返回，未抛异常 |
| lithium | 0.24.2+mc26.1.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L81 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: lithium-fabric-0.24.2+mc26.1.2.jar；证据表：lithium 的 main 入口点 net.caffeinemc.mods.lithium.fabric.LithiumFabricMod 派发返回，未抛异常 |
| malilib | 0.28.3 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L82 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: malilib-fabric-26.1.2-0.28.3.jar；证据表：malilib 的 main 入口点 fi.dy.masa.malilib.MaLiLib 派发返回，未抛异常 |
| mcfao_fixture | 1.0.0 | 第一方验证夹具 | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L160 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: mcfao-fixture.jar；证据表：mcfao_fixture 的 client 入口点 mcfao.fixture.GameMod 派发返回，未抛异常 |
| minihud | 0.39.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L84 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: minihud-fabric-26.1.2-0.39.2.jar；证据表：minihud 的 main 入口点 fi.dy.masa.minihud.MiniHUD 派发返回，未抛异常 |
| modmenu | 18.0.0-alpha.8 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L162 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: modmenu-18.0.0-alpha.8.jar；证据表：modmenu 的 client 入口点 com.terraformersmc.modmenu.ModMenu 派发返回，未抛异常 |
| mousetweaks | 2.31 | 库 / 嵌套依赖 | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L165 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: MouseTweaks-fabric-mc26.1-2.31.jar；证据表：mousetweaks 的 client 入口点 yalter.mousetweaks.fabric.MouseTweaksFabric 派发返回，未抛异常 |
| nochatreports | 26.1-v2.19.0 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L85 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: NoChatReports-FABRIC-26.1-v2.19.0.jar；证据表：nochatreports 的 main 入口点 com.aizistral.nochatreports.fabric.NoChatReports 派发返回，未抛异常 |
| presencefootsteps | 1.13.0+26.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L191 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: PresenceFootsteps-1.13.0+26.1.jar；证据表：presencefootsteps 的 client 入口点 eu.ha3.presencefootsteps.PresenceFootsteps 派发返回，未抛异常 |
| sit | 1.5.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L86 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: sit-fabric-26.1.1-1.5.1.jar；证据表：sit 的 main 入口点 bl4ckscor3.mod.sit.FabricEntrypoint 派发返回，未抛异常 |
| skinlayers3d | 1.11.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L193 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: skinlayers3d-fabric-1.11.1-mc26.1.jar；证据表：skinlayers3d 的 client 入口点 dev.tr7zw.skinlayers.SkinLayersMod 派发返回，未抛异常 |
| sound_physics_remastered | 1.5.1+26.1.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L87 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: sound-physics-remastered-fabric-1.5.1+26.1.2.jar；证据表：sound_physics_remastered 的 main 入口点 com.sonicether.soundphysics.FabricSoundPhysicsMod 派发返回，未抛异常 |
| terrablender | 26.1.2.0.2 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-87-simulator/game.log#L577 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: TerraBlender-fabric-26.1.2-26.1.2.0.2.jar；证据表：terrablender 在运行期打出初始化标记（token `terrablender`），入口点未抛异常 |
| transition | 1.0.19 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L196 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: TRansition-1.0.17-26.1-fabric-SNAPSHOT.jar, TRansition-1.0.19-26.1-fabric-SNAPSHOT.jar；证据表：transition 的 client 入口点 dev.tr7zw.transition.ClientTRansitionMod 派发返回，未抛异常 |
| trender | 1.0.13 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L198 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 嵌套 jar: TRender-1.0.12-26.1-fabric-SNAPSHOT.jar, TRender-1.0.13-26.1-fabric-SNAPSHOT.jar；证据表：trender 的 client 入口点 dev.tr7zw.trender.gui.impl.client.LibGuiClient 派发返回，未抛异常 |
| yet_another_config_lib_v3 | 3.9.3+26.1-fabric | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L200 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 定向适配：YACL 配置根与 handler 字段注册；根 jar: yet_another_config_lib_v3-3.9.3+26.1-fabric.jar；证据表：yet_another_config_lib_v3 的 client 入口点 dev.isxander.yacl3.platform.PlatformEntrypoint 派发返回，未抛异常 |
| zoomify | 2.16.0+26.1 | 内容 / 客户端 Mod | `LOAD_PASS` | pack-92 | fabric-pack-88-simulator/game.log#L201 | tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py | 根 jar: zoomify-2.16.0+26.1.jar；证据表：zoomify 的 client 入口点 dev.isxander.zoomify.Zoomify 派发返回，未抛异常 |
| cloth-basic-math | 0.6.1 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: basic-math-0.6.1.jar |
| com_electronwill_night-config_core | 3.8.3 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: core-3.6.7.jar, core-3.8.3.jar |
| com_electronwill_night-config_toml | 3.8.3 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: toml-3.6.7.jar, toml-3.8.3.jar |
| com_google_code_findbugs_jsr305 | 3.0.2 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: jsr305-3.0.2.jar |
| com_twelvemonkeys_common_common-image | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: common-image-3.12.0.jar |
| com_twelvemonkeys_common_common-io | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: common-io-3.12.0.jar |
| com_twelvemonkeys_common_common-lang | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: common-lang-3.12.0.jar |
| com_twelvemonkeys_imageio_imageio-core | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: imageio-core-3.12.0.jar |
| com_twelvemonkeys_imageio_imageio-metadata | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: imageio-metadata-3.12.0.jar |
| com_twelvemonkeys_imageio_imageio-webp | 3.12.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: imageio-webp-3.12.0.jar |
| de_marhali_json5-java | 3.0.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: json5-java-3.0.0.jar |
| fabric-api | 0.148.0+26.1.2 | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 根 jar: fabric-api-0.148.0+26.1.2.jar |
| fabric-api-base | 2.0.3+ece063234c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | tests/test_runtime_lowering.py::test_fabric_api_interfaces_are_pinned_for_dual_initializers | 定向适配：移除未使用的动态代理工厂方法；嵌套 jar: fabric-api-base-2.0.3+ece063234c.jar, fabric-api-base-2.0.3+ece0632359.jar |
| fabric-biome-api-v1 | 18.0.4+35c80edc4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-biome-api-v1-18.0.4+35c80edc4c.jar |
| fabric-block-api-v1 | 3.0.2+ec56b6014c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-block-api-v1-3.0.2+ec56b6014c.jar |
| fabric-block-getter-api-v2 | 2.0.6+ec56b6014c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-block-getter-api-v2-2.0.6+ec56b6014c.jar |
| fabric-command-api-v2 | 3.0.5+e2bdee784c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-command-api-v2-3.0.5+e2bdee784c.jar |
| fabric-content-registries-v0 | 11.1.0+1a3b26974c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-content-registries-v0-11.1.0+1a3b26974c.jar |
| fabric-crash-report-info-v1 | 1.0.3+9f78a5a84c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-crash-report-info-v1-1.0.3+9f78a5a84c.jar |
| fabric-creative-tab-api-v1 | 5.0.10+d871b99e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-creative-tab-api-v1-5.0.10+d871b99e4c.jar |
| fabric-data-generation-api-v1 | 24.1.0+47b0d63c4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-data-generation-api-v1-24.1.0+47b0d63c4c.jar |
| fabric-debug-api-v1 | 1.0.1+c792624d4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-debug-api-v1-1.0.1+c792624d4c.jar |
| fabric-entity-events-v1 | 5.0.2+e2bdee784c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-entity-events-v1-5.0.2+e2bdee784c.jar |
| fabric-game-rule-api-v1 | 4.0.5+d871b99e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-game-rule-api-v1-4.0.5+d871b99e4c.jar |
| fabric-item-api-v1 | 14.1.1+73d134684c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-item-api-v1-14.1.1+73d134684c.jar |
| fabric-key-mapping-api-v1 | 2.0.4+e2bdee784c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-key-mapping-api-v1-2.0.4+e2bdee784c.jar, fabric-key-mapping-api-v1-2.0.4+e2bdee7859.jar |
| fabric-language-kotlin | 1.13.11+kotlin.2.3.21 | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 根 jar: fabric-language-kotlin-1.13.11+kotlin.2.3.21.jar |
| fabric-loot-api-v3 | 3.0.11+00a1fba64c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-loot-api-v3-3.0.11+00a1fba64c.jar |
| fabric-message-api-v1 | 7.0.5+dae8ce3e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-message-api-v1-7.0.5+dae8ce3e4c.jar |
| fabric-object-builder-api-v1 | 23.0.14+b95dd56e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-object-builder-api-v1-23.0.14+b95dd56e4c.jar |
| fabric-rendering-fluids-v1 | 6.0.1+d871b99e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-rendering-fluids-v1-6.0.1+d871b99e4c.jar |
| fabric-resource-loader-v0 | 3.3.16+4fc5413f4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-resource-loader-v0-3.3.16+4fc5413f4c.jar |
| fabric-resource-loader-v1 | 2.0.9+d871b99e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-resource-loader-v1-2.0.9+d871b99e4c.jar, fabric-resource-loader-v1-2.0.9+d871b99e59.jar |
| fabric-screen-api-v1 | 5.0.1+d871b99e4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-screen-api-v1-5.0.1+d871b99e4c.jar, fabric-screen-api-v1-5.0.1+d871b99e59.jar |
| fabric-serialization-api-v1 | 2.0.3+11a26f314c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-serialization-api-v1-2.0.3+11a26f314c.jar |
| fabric-sound-api-v1 | 2.0.4+11a26f314c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-sound-api-v1-2.0.4+11a26f314c.jar |
| fabric-transfer-api-v1 | 8.0.5+357ea7334c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-transfer-api-v1-8.0.5+357ea7334c.jar |
| fabric-transitive-access-wideners-v1 | 8.1.0+acd9108d4c | Fabric API | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: fabric-transitive-access-wideners-v1-8.1.0+acd9108d4c.jar |
| ferritecore | 9.0.0 | 内容 / 客户端 Mod | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 根 jar: ferritecore-9.0.0-fabric.jar |
| freecam_cloth-config_26_1 | cloth-config-1.4.0-alpha.3+mc26.1.2 | 内容 / 客户端 Mod | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: freecam-cloth-config-1.4.0-alpha.3+mc26.1.2.jar |
| net_jodah_typetools | 0.6.3 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: typetools-0.6.3.jar |
| org_jetbrains_kotlin_kotlin-stdlib | 2.3.21 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlin-stdlib-2.3.21.jar |
| org_jetbrains_kotlin_kotlin-stdlib-jdk7 | 2.3.21 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlin-stdlib-jdk7-2.3.21.jar |
| org_jetbrains_kotlin_kotlin-stdlib-jdk8 | 2.3.21 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlin-stdlib-jdk8-2.3.21.jar |
| org_jetbrains_kotlinx_atomicfu-jvm | 0.32.1 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: atomicfu-jvm-0.32.1.jar |
| org_jetbrains_kotlinx_kotlinx-coroutines-core-jvm | 1.10.2 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-coroutines-core-jvm-1.10.2.jar |
| org_jetbrains_kotlinx_kotlinx-coroutines-jdk8 | 1.10.2 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-coroutines-jdk8-1.10.2.jar |
| org_jetbrains_kotlinx_kotlinx-datetime-jvm | 0.7.1 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-datetime-jvm-0.7.1.jar |
| org_jetbrains_kotlinx_kotlinx-io-bytestring-jvm | 0.9.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-io-bytestring-jvm-0.9.0.jar |
| org_jetbrains_kotlinx_kotlinx-io-core-jvm | 0.9.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-io-core-jvm-0.9.0.jar |
| org_jetbrains_kotlinx_kotlinx-serialization-cbor-jvm | 1.11.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-serialization-cbor-jvm-1.11.0.jar |
| org_jetbrains_kotlinx_kotlinx-serialization-core-jvm | 1.11.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-serialization-core-jvm-1.11.0.jar |
| org_jetbrains_kotlinx_kotlinx-serialization-json-jvm | 1.11.0 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: kotlinx-serialization-json-jvm-1.11.0.jar |
| org_quiltmc_parsers_gson | 0.2.1 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: gson-0.2.1.jar |
| org_quiltmc_parsers_json | 0.2.1 | 库 / 嵌套依赖 | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 嵌套 jar: json-0.2.1.jar |
| placeholder-api | 3.0.0+26.1 | 内容 / 客户端 Mod | `BUILD_PASS` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/transform/resolvedMods | unittest + verify_aot_classpath.py + simulator smoke | 根 jar: placeholder-api-3.0.0+26.1.jar |
| dynamic_fps | 3.11.6+minecraft-26.1.0 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | 隔离判定见 pack-68 / pack-70 冒烟日志 | 隔离（platform）：bundled net.lostluma.battery 2.0.0 (JNI natives, no iOS build)；嵌套 jar |
| entity_model_features | 3.2.2 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/entity_model_features | — | 导出期排除：运行时生成类 / 动态代理；1 处；定向适配：ASMParser 运行时 defineClass（未适配，已排除）；根 jar: entity_model_features_26.1-fabric-3.2.2.jar |
| iris | 1.10.9+mc26.1.1 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | 隔离判定见 pack-68 / pack-70 冒烟日志 | 隔离（pair-level）：immediatelyfast 1.15.2+mc26.1.2；嵌套 jar |
| net_lenni0451_reflect | 1.6.2 | 库 / 嵌套依赖 | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/net_lenni0451_reflect | inspect_archives / transformation_checks | 导出期排除：运行时生成类 / 动态代理；4 处；嵌套 jar: Reflect-1.6.2.jar |
| net_neoforged_bus | 7.2.0 | 库 / 嵌套依赖 | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/net_neoforged_bus | inspect_archives / transformation_checks | 导出期排除：运行时生成类 / 动态代理；1 处；嵌套 jar: bus-7.2.0.jar |
| org_javassist_javassist | 3.30.2-GA | 库 / 嵌套依赖 | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/org_javassist_javassist | inspect_archives / transformation_checks | 导出期排除：运行时生成类 / 动态代理；7 处；嵌套 jar: javassist-3.30.2-GA.jar |
| org_jetbrains_kotlin_kotlin-reflect | 2.3.21 | 库 / 嵌套依赖 | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/org_jetbrains_kotlin_kotlin-reflect | inspect_archives / transformation_checks | 导出期排除：运行时生成类 / 动态代理；1 处；嵌套 jar: kotlin-reflect-2.3.21.jar |
| org_reflections_reflections | 0.10.2 | 库 / 嵌套依赖 | `BLOCKED` | pack-92 | artifacts/mcfao/fabric-pack-92/fabric/*/product/result.json#/excludedMods/org_reflections_reflections | inspect_archives / transformation_checks | 导出期排除：运行时生成类 / 动态代理；2 处；嵌套 jar: reflections-0.10.2.jar |
| reeses-sodium-options | 2.0.5+mc26.1.1 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | 隔离判定见 pack-68 / pack-70 冒烟日志 | 隔离（platform）：sodium (declared depends)；嵌套 jar |
| sodium | 0.8.11+mc26.1.2 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | tests/test_config_reflection.py::test_sodium_dependency_injection_implementations_are_registered | 隔离（platform）：Metal-only GPU backend (no OpenGL implementation on iOS)；定向适配：布局驱动的顶点序列化器替换运行时字节码生成；嵌套 jar |
| sodium-extra | 0.8.7+mc26.1.1 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | 隔离判定见 pack-68 / pack-70 冒烟日志 | 隔离（platform）：sodium (declared depends)；嵌套 jar |
| xaerominimap | 25.3.12 | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | tests/test_runtime_lowering.py::test_mods_asking_for_their_own_jar_get_a_nominal_path | 隔离（platform）：iOS native image has no AWT/ImageIO natives (System.loadLibrary("awt") fails)；定向适配：ModFiles.modFile / FabricPlatformHelper.getModFile；嵌套 jar |
| xaeroworldmap | 26.1.2_1.40.16_fabric | 内容 / 客户端 Mod | `BLOCKED` | pack-92 | artifacts/mcfao/incompatible-01/result.json#/mods | tests/test_runtime_lowering.py::test_mods_asking_for_their_own_jar_get_a_nominal_path | 隔离（platform）：Metal-only GPU backend (no OpenGL implementation on iOS)；定向适配：ModFiles.modFile / fetchModFile；嵌套 jar |

## 排除与隔离明细

### 导出期排除（闭世界静态检查拒绝）

| Mod ID | 类别 | 首个不可达点 |
| --- | --- | --- |
| `entity_model_features` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: entity_model_features traben/entity_model_features/models/animation/math/asm/ASMParser$1.define -> traben/entity_model_features/models/ani |
| `net_lenni0451_reflect` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: net_lenni0451_reflect net/lenni0451/reflect/Agents.getInstrumentation -> net/lenni0451/reflect/ClassLoaders.defineClass |
| `net_neoforged_bus` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: net_neoforged_bus net/neoforged/bus/EventListenerFactory.createWrapper0 -> java/lang/invoke/MethodHandles$Lookup.defineHiddenClassWithClas |
| `org_javassist_javassist` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: org_javassist_javassist javassist/Loader$Simple.invokeDefineClass -> javassist/Loader$Simple.defineClass |
| `org_jetbrains_kotlin_kotlin-reflect` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: org_jetbrains_kotlin_kotlin-reflect kotlin/reflect/jvm/internal/calls/AnnotationConstructorCallerKt.createAnnotationInstance -> java/lang/ |
| `org_reflections_reflections` | 运行时生成类 / 动态代理 | Unsupported runtime class/native loading: org_reflections_reflections org/reflections/ReflectionUtils.toAnnotation -> java/lang/reflect/Proxy.newProxyInstance |

### 预先隔离（离开验证包，jar 原样保留在 `incompatible-01/`）

| Mod ID | 版本 | 层级 | 阻塞原因 | 证据 |
| --- | --- | --- | --- | --- |
| `dynamic_fps` | 3.11.6+minecraft-26.1.0 | platform | bundled net.lostluma.battery 2.0.0 (JNI natives, no iOS build) | `artifacts/mcfao/fabric-pack-73-simulator/game.log` |
| `iris` | 1.10.9+mc26.1.1 | pair-level | immediatelyfast 1.15.2+mc26.1.2 | `artifacts/mcfao/fabric-pack-68-simulator/game.log` |
| `reeses-sodium-options` | 2.0.5+mc26.1.1 | platform | sodium (declared depends) | `—` |
| `sodium` | 0.8.11+mc26.1.2 | platform | Metal-only GPU backend (no OpenGL implementation on iOS) | `artifacts/mcfao/fabric-pack-70-simulator/game.log` |
| `sodium-extra` | 0.8.7+mc26.1.1 | platform | sodium (declared depends) | `—` |
| `xaerominimap` | 25.3.12 | platform | iOS native image has no AWT/ImageIO natives (System.loadLibrary("awt") fails) | `artifacts/mcfao/fabric-pack-86-simulator/game.log` |
| `xaeroworldmap` | 26.1.2_1.40.16_fabric | platform | Metal-only GPU backend (no OpenGL implementation on iOS) | `artifacts/mcfao/fabric-pack-84-simulator/game.log` |

Iris 保持隔离：其 `FieldAccessor.makeSetter` 需要运行时生成类，与闭世界冲突；待其余 Mod 稳定后再单独开工作线。

## 框架级适配与对应回归测试

| 适配点 | 作用域 | 回归测试 |
| --- | --- | --- |
| `RuntimeLowering.lowerVanillaPackBuilder` + 生成的 `mcfao.aot.ModNamespaces` | 所有 Mod 的 `assets/` / `data/`（取代闭世界缺失的 `ModResourcePackCreator`） | `tests/test_runtime_lowering.py::test_mod_resource_namespaces_reach_the_builtin_pack` |
| `tools/config_reflection.py` 序列化根 / 反射成员扫描 | 所有用 Gson 或反射查游戏成员的 Mod | `tests/test_config_reflection.py`（16 项） |
| `RuntimeLowering.lowerQueries` / 生成 `Entrypoints` | 所有查询 Loader 的 Mod | `tests/test_runtime_lowering.py`（8 项） |
| `tools/verify_aot_classpath.py` 默认 + `--verify-members` | 整个 AOT classpath | 构建后静态校验产物 `classpath-check.json` |

## 验证链（每个新包都要重跑）

```bash
python3 -m unittest discover -s tests -q
python3 -B tools/verify_aot_classpath.py --build artifacts/mcfao/fabric-pack-92
python3 -B tools/verify_aot_classpath.py --build artifacts/mcfao/fabric-pack-92 --verify-members
python3 -B tools/smoke_mcfao_simulator.py --expect fabric --build artifacts/mcfao/fabric-pack-92 \
  --runtime artifacts/graphics/runtime-sim-02 \
  --graphics artifacts/graphics/world-simulator-input-02 \
  --assets artifacts/graphics/game-assets-01/assets \
  --seed-world /tmp/c0seed/world \
  --simulator 8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3 \
  --output artifacts/mcfao/fabric-pack-92-simulator
python3 -B tools/generate_mod_matrix.py --build <新包目录>
```
