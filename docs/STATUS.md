# 当前状态（2026-11-15）

> 2026-11-15：GL41、v21、MDAF 和通用 P0 已集成。干净提交 70d5cbe 已生成 ARM64 macOS GUI、真实 Vanilla GL41 AOT IPA 和开发签名包；Tauri 命令到完整 AOT/IPA 的实际工作流通过，独立测试应用安装成功。Mac 和测试设备锁屏阻断原生 GUI 交互与独立游戏启动，C0/世界/存档/30分钟及 Fabric 真机门槛保持 BLOCKED，不继承历史 PASS。详见 [交付记录](integration/GL41_DELIVERY.md)。以下早期实验记录保留原日期与验证范围。


2026-11-12 末地修复：pack-92 真机日志在创建龙时因 `DragonHoverPhase(EnderDragon)` 反射查询失败退出。现已补齐 11 个阶段的精确构造注册，pack-93 最终 AOT 配置为 149 条、阶段覆盖 11/11；构建为 `SIGNED_DEVICE_APP`，签名导出为 `DEVELOPMENT_IPA_VERIFIED`。IPA：`artifacts/mcfao/fabric-pack-93-end-fix-signed-ipa/export/FabricAOT World.ipa`。助手按用户要求未运行测试、模拟器或手机；用户于 2026-11-12 安装复测后明确确认“确实修好了”，本次末地加载闪退按用户真机反馈记为已修复。完整战斗、复活及长时稳定性不由此推定通过。新复测日志确认末地已就绪并可见，随后出现后台 GPU 提交被拒绝的独立崩溃，前后台渲染生命周期问题仍 OPEN。调查与后续加固见 [末地加载崩溃](END_DIMENSION_CRASH_PLAN.md)。

**EXPERIMENTAL。A0/A1/B0/B1 PASS。原版单人玩法已在模拟器验证，正式真机 C0 仍为 BLOCKED。**

当前实现和复现见 [BUILDING](BUILDING.md)，工具链决策见 [ADR-001](evidence/ADR-001.md)，原始记录见 [证据索引](evidence/README.md)。

## 统一 AOT 构建与 Fabric 夹具

原版基线取自 Git `1d9af2d`，当时无 tracked 改动。原编译参数、真机链接及签名分别保存在 [Native Image 命令](../artifacts/graphics/main-aot-15/analysis/command.json)、[链接报告](../artifacts/graphics/main-link-ios-world-01/result.json)、[WorldDevice 命令](../artifacts/graphics/world-device-signed-02/command.json)。本轮主机为 macOS 27.2，GraalVM CE 25.0.2+10.1，Xcode 27.2（27B52），Apple Clang 21.0.0，iPhoneOS SDK 27.2。 [Doctor 记录](../artifacts/mcfao/doctor-01/stdout.log)

| 本轮验收 | 状态 | 证据 |
|---|---|---|
| P0 统一 CLI | PASS（构建与静态验证） | 从本地 26.1.2 JAR 重做拆分、Metal 注入、`--no-fallback` 对象、120 个 iOS Java/SVM 翻译单元、ARM64 链接和开发签名。新原版输入 JAR 的 29,433 个非目录条目逐项与既有 Metal 客户端相同。 [条目对照](../artifacts/mcfao/vanilla-bytecode-baseline.json) · [签名 App 清单](../artifacts/mcfao/vanilla-01/result.json) |
| 原版运行回归 | PASS（模拟器世界烟测） | 新对象另行链接为 IOSSIMULATOR，游戏成功进入复制的单人存档，渲染地形和触摸控件。现有横屏 UI 回归用新镜像通过，覆盖方块操作、移动、物品栏和保存退出。 [UI 测试](../artifacts/mcfao/vanilla-ui-01/stdout.log) · [世界日志](../artifacts/mcfao/vanilla-simulator-02/game.log) · [截图](../artifacts/mcfao/vanilla-simulator-02/world.png) |
| 原版 iPhone 包 | PASS（静态验签） | 嵌套签名、设备描述文件覆盖、无动态代码 entitlement。开发 IPA 已导出并完成解包复验。独立启动、交互、保存重进仍待上机。 [IPA 清单](../artifacts/mcfao/vanilla-ipa-01/result.json) · [设备覆盖报告](../artifacts/mcfao/vanilla-device-profile-01/stdout.log) |
| P1 真实 Loader 输入 | PASS（构建期） | Fabric Loader 0.19.3 解析根和嵌套元数据，实际 Knot 解析测试 Mod、执行 Mixin、导出游戏类及静态入口。 [嵌套元数据](../artifacts/mcfao/nested-metadata-01/fabric/f106f2b6c2e6450ba43b6d93800e7abd/product/result.json) · [字节码核验](../artifacts/mcfao/fabric-bytecode-02/stdout.log) |
| P1 F1 入口与资源 | PASS（模拟器） | 实际 Minecraft AOT 进程调用第一方 Mod 的 client 入口并读回内嵌资源。首轮随后因 Fabric 品牌调用残留退出，修复后重新编译并复测通过。 [首轮失败](../artifacts/mcfao/fabric-simulator-01/game.log) · [复测日志](../artifacts/mcfao/fabric-simulator-02/game.log) |
| P1 F2 Mixin 与 F3 游戏回调 | PASS（模拟器） | `Minecraft#setLevel` 的注入在进入实际单人世界时触发 Mod 回调。集成服务器登录、回调标记和横屏地形均有证据。`getVersionType` 只做了静态字节码核对。 [字节码](../artifacts/mcfao/fabric-bytecode-02/stdout.log) · [运行结果](../artifacts/mcfao/fabric-simulator-02/result.json) · [截图](../artifacts/mcfao/fabric-simulator-02/world.png) |
| Fabric iPhone 包 | PASS（构建与静态验签） | 修复版对象经 iPhoneOS 链接和开发签名，导出的 IPA 已解包核对原生镜像、资源、签名和指定 iPhone 描述文件覆盖。设备运行待验。 [IPA 清单](../artifacts/mcfao/fabric-ipa-02/result.json) |
| P2 / P3 | 部分实现 | 已转换 JAR 是 Loader 与原生后端的边界。当前版本选择仅 26.1.2，命名空间为 official。Forge、NeoForge 和旧版混淆映射尚未实现。 [适配说明](FABRIC_AOT.md) |

本轮 Python 回归为 182 项全通过。 [测试日志](../artifacts/mcfao/regression-03/stderr.log)

## Recollection3 整合包试导入

用户报告此前 IPA 已通过真机验证。此次记录未附该包的构建号和逐项验收日志。Recollection3 的结果单列如下。

- CurseForge ZIP 声明 Minecraft 26.1.2 和 Fabric Loader 0.19.2。已校验 ZIP 目录并暂存 6 个随包 JAR，全部通过 MCFAO 的 Fabric 元数据预检。6 个 JAR 与同名本地实例中的文件逐一匹配 SHA-256。清单另列 53 条 CurseForge 文件引用，尚未按文件 ID 核验完整输入集。 [归档清单](../artifacts/mcfao/recollection3-import-01/import.json)
- 初次整组预检被两个 Mod 描述字段中的未转义换行拦住。修复后，`--prepare-only` 以锁定的 Fabric Loader 0.19.3 一次解析本地实例的 53 个根 JAR 和 168 个嵌套 JAR。49 个根 JAR 或其子包触发现有 AOT 元数据限制，报告列出 178 条归档诊断，并标记两份 Fabric API。Fabric API 子模块、Sodium 的 `preLaunch` 和 Kotlin 语言适配器仍需单独支持。 [初次诊断](../artifacts/mcfao/recollection3-import-01/full-preflight-diagnostic/stderr.log) · [修复后报告](../artifacts/mcfao/recollection3-import-02/local-instance-preflight/fabric/67dce38cff064c7881fe4aef2ef2401a/product/result.json) · [187 项回归](../artifacts/mcfao/recollection3-import-02/regression/stderr.log)
- Recollection3 整包 AOT 为 BLOCKED，真机测试为 NOT RUN。此次只处理清单与 Mod 元数据，未运行第三方 Mod 或应用 overrides。 已审计的第一方夹具通过构建期转换复测。 [夹具报告](../artifacts/mcfao/recollection3-import-02/first-party-transform/fabric/3ff3e2e6604741bda8412f22fd9c8dac/product/result.json)
- 第 48 轮兼容性扩展：`Class::method` 入口改为构建期静态解析（生成 `invokestatic`/`invokevirtual`，运行时不经过 `MethodHandle`），`modmenu` 与提供者缺失的 `jei_mod_plugin` 入口记录为不可达并跳过，转换归档预算由 128 提高到 256 以覆盖整包 221 个归档，`MixinConfigPlugin` 由拒绝项改为构建期钩子，非字面量的 `isModLoaded` 查询改写成生成式成员测试。同一实例的预检降到 54 条诊断 / 31 组阻塞根。`fabric-networking-api-v1-6.3.0`、`fabric-api-base` 和 `chat_heads-1.2.2` 通过隔离转换，后者 18 个客户端类被 Mixin 实际改写。整包 AOT 仍为 BLOCKED，阻塞主因是 `META-INF/versions`/`services`、保留依赖 id 和 Kotlin 语言适配器。 [预检](../artifacts/mcfao/recollection3-import-07/)

## 整包 AOT 的四个静默失败（2026-11-10 第 52 轮）

47 个 JAR 的整合包此前卡在两个 `NoSuchMethodError`（`ETF.config()`、`Minecraft.fillReport`）。四个根因都不在死代码消除上，且都不会让构建失败——它们在运行期表现为「看起来无关的方法不存在」或「无关的类转换失败」：

1. **Mixin 类被按注解筛掉，导致引用它的类无法加载**。合并后的目标类会在 `interfaces` 表、`checkcast` 或签名里提到 Mixin 类型（`BlockStateModel implements ...BlockStateModelMixin`）。旧实现只保留带 `@Accessor`/`@Invoker` 的接口，其余整包丢弃（含 ETF 依赖的 TRender **嵌套 JAR** 里的 `ScreenAccessor`）。**一个引用了 classpath 上不存在的类型的类，根本不能被加载**，而 Native Image 不报错：它把对该类的每次调用换成一个抛 `NoSuchMethodError` 的 stub。`tools/verify_aot_classpath.py` 把这个静默失败变成清单——修复前 718 个类不可加载，修复后 112 个（全部是镜像本就不含的可选依赖叶子类，`net.minecraft` 与 Loader 类为 0）。
2. **按原样导出的 Mixin 接口保留了包私有访问**。Mixin 合并时会把非 public 的 Mixin 接口提成 public，照抄的副本没有，于是 30 个类（含 `BlockStateModel`、`SubmitNodeCollector`）加载期抛 `IllegalAccessError`。
3. **分段方法名不含方法身份**。分割器给分段和 spill 字段只用序号命名，`BlockStateData` 一个类里 10 个 `bootstrapX` 方法全部挤进 `fabricaot$part$1..N`，加载期抛 `Duplicate method name "fabricaot$part$1"`。
4. **瞄准库类的 Mixin 从未被应用**。Fabric API 的 dimension 模块让 datafixerupper 的 `TaggedChoice` 实现扩展接口，并由注入到 `V2832` 的 redirect 去转型；库 JAR 不参与合并，于是 `DataFixers.<clinit>` 抛 `ClassCastException`。导出器现在读取每个 Mixin 声明的 target，对不在游戏 JAR 里的目标执行同一套 Knot 变换后写进 overlay；同时把 client jar 提到镜像 classpath 首位，让它遮蔽库原件（改动前 client jar 与 78 个库的 `.class` 重叠为 0，因此提位本身语义中性）。

配套修复：`MixinConfigPlugin` 是构建期钩子，22 个 plugin 类不再随镜像出厂；`getConfigDir()` 在 `startClient` 之前被调用时（ETF 在 `DataFixers.<clinit>` 阶段读配置）回退到 `user.dir`，此前直接 NPE。

验证口径按用户要求改为 **iOS 模拟器**：`tools/smoke_mcfao_simulator.py` + `WorldSimulator` scheme。



## 多人联机根因（2026-11-10）

用户报告的 `Loading terrain` 已在模拟器定位到 Native Image 配置缺口：Netty 4.2.7 在 Java 25 下用 `Arena.ofShared` 管理 direct buffer，而 Native Image 默认不支持共享 arena，释放初始区块缓冲时抛出 `UnsupportedFeatureError` 并关闭连接。AOT 命令现已加入 `-H:+SharedArenaSupport`；构建期注入的 `PlayDiagnostics` 记录 Configuration→Play、区块批次、解码、位置包、`LevelLoadTracker` 状态和线程心跳。修复后模拟器联机进入 `ClientLevelReady`、出现真实地形，UI 测试完成前进/跳跃/破坏；单人 `testLandscapeInventory` 回归通过。**真机 NOT RUN，不能据此报告联机已修复。** 根因、日志开关、复现和待验项见 [MULTIPLAYER_DIAGNOSTICS](MULTIPLAYER_DIAGNOSTICS.md)。

## 历史门槛与实测

| 检查 | 状态 | 证据 / 阻断 |
|---|---|---|
| A0 客户端输入 | FOUND / HASH MATCH | Swift Craft Launcher 的 meta/versions/26.1.2/26.1.2.jar，38113927 字节，SHA-1 与版本元数据一致；主类存在 |
| A0 Mac Java25 + Fabric 实际参考启动 | PASS（用户执行） | 真实主菜单截图；同一进程已映射Java25.0.1，打开新实例日志；Fabric0.19.3，125个实际打开JAR指纹和复现步骤在artifacts/evidence/a0-desktop-reference/ |
| A1 JVM / 桌面 AOT 语义 | PASS（辅助检查） | 第一方全部断言通过 |
| A1 自建 iOS 静态运行库 / Framework 链接 | PASS（编译检查） | 固定官方源码，119 个翻译单元，iPhoneOS 与 Simulator 分别编译 |
| A1 iPhoneOS 开发签名归档 / IPA 导出 | PASS（构建检查） | 最新build 3：artifacts/evidence/a1-ios-archive-run-state-v3/、a1-ios-export-run-state-v3/；包记录 artifacts/a1/device-handoff-v3/result.json |
| A1 iOS ARM64 模拟器执行 | PASS（调试检查） | 创建/销毁 isolate、线程、ScopedValue、GC、资源、JNI、文件断言全部通过 |
| A1 IPA 嵌套签名 / ARM64 平台 | PASS（静态检查） | artifacts/evidence/a1-ios-ipa-signature-run-state-v3/；无 JIT 权限，描述文件包含此前配对的用户 iPhone |
| A1 build 2 真机 Java语义 / 独立启动 | PASS（用户执行） | artifacts/evidence/a1-user-device-run-03/result.json；新日志、全部Java断言和原生三个0；用户明确确认退出Xcode、拔线后重新打开 |
| A1 build 3 运行状态显示 | PASS（用户截图/运行） | 显示本次开始时间、0.022秒耗时和新日志名；原始记录 artifacts/evidence/a1-user-device-run-04/。build 3这一次的独立启动条件未单独询证，A1独立运行结论来自build 2 |
| B0真实构建期转换 | PASS（助手Mac隔离执行） | artifacts/b0/run-04/；真实Knot/Mixin、ClassTweaker访问修改、嵌套JAR和Entrypoint，导出重放一致，未转换负例准确失败 |
| B1 iOS AOT行为 | PASS（用户真机执行） | artifacts/evidence/b1-user-device-run-01/；build 4两次原生返回全0，行为与B0一致；用户确认一次连接Xcode、一次未连接 |
| C0 | BLOCKED | 真实 Main 的既有 Datafixer/JOML 证据保留。第46轮用户真机蓝屏日志匹配；模拟器资源读回与四分屏通过。STB、原版着色器与实际Metal绘制已在模拟器验证；真实Main已创建UIKit窗口与Metal设备，现已越过音频初始化，进入游戏首帧绘制。 |
| C0 图形层实现 | PARTIAL | 已有 UIKit GLFW-lite、iOS JNI overlay、固定回调、Metal 纹理/视图/传输/清除/fence、原版87条PSO及绘制/绑定/裁剪。真机蓝屏1398×2034与模拟器资源测试见 [图形启动结果](GRAPHICS_BOOTSTRAP.md)。 |
| C0a | BLOCKED | 真机诊断清屏 PASS，资源探针模拟器 PASS；后端数组改写已静态验证，原版着色器绘制已在模拟器验证；真实Main已初始化Metal；菜单加载和真机独立运行未验证。 |
| C0b / C0c | 模拟器原版单人 PASS | 实测横屏 2622×1206。菜单、转视角、移动、取放和破坏方块、物品栏、保存退出及独立重开通过。见[横屏记录](../artifacts/graphics/landscape-acceptance-01/result.json)和[新建世界与跳跃记录](../artifacts/graphics/simulator-recovery-01/result.json)。 |
| 原版单人真机测试包 | PASS（构建与签名检查） | WorldDevice 已更新 Metal 库，原版 GUI 文字使用的 Fog 缓冲区物理分配由 40 字节对齐至 48 字节。设备构建与嵌套签名校验通过，修复后真机待复测。见[构建日志](../artifacts/graphics/world-device-signed-02/stdout.log)、[签名校验](../artifacts/graphics/world-device-signature-02/command.json)和[测试步骤](BUILDING.md#iphone-原版单人测试)。 |
| C1 / C2 | 真机 NOT RUN | 模拟器记录单独保留。 |
| D0 | PARTIAL | 离线元数据/研究工具负例已测试；默认拒绝沙盒读/写/本地连接控制通过；恶意Mod/Gradle、IPC、完整下载/依赖服务未验收 |
| D1 / D2 | NOT RUN | 已有原版与第一方夹具的开发签名 IPA。尚无通过验收的整合包、真机安装更新或存档保留证据 |
| E | NOT RUN | 无真机游戏性能、温度或持续游玩数据 |

此前图形栈阶段的 **170 项 Python 自动化回归全部 PASS**。GLFW 与像素转换 C 夹具通过 ASan/UBSan，真实 Metal 像素测试通过。原版单人运行证据来自模拟器，iPhone 游戏包等待用户安装运行。[回归日志](../artifacts/graphics/regression-18/stderr.log) · [GPU 记录](../artifacts/graphics/draw-simulator-evidence-05/result.json)

主机：macOS 27.2 arm64，Xcode/iPhoneOS SDK 27.2，GraalVM CE 25.0.2。用户 iPhone/iOS27.2 的 build 2 原生日志确认 Java25语义运行通过，退出Xcode/拔线/重新打开条件由用户确认。专用调试模拟器与用户原有设备分开。

客户端和实例均保持在用户原位置。第 50 轮用本地 47 个根 JAR（154 MB）跑通了整包转换，并走完 `split → metal-injection → aot → runtime → link → stage → package`，产出 `SIGNED_DEVICE_APP`（689 MB，`client-graph.dylib` 238 MB），已装进 iPhone 19,4。第 51 轮把剪枝集合从 11 个降到 7 个：Sodium 的顶点序列化器改为 `mcfao.aot.GenericVertexSerializer`（布局驱动的等价复制计划，与 Sodium 生成器在 92 个兼容格式对上逐字节相同），`iris`/`sodium-extra`/`reeses-sodium-options` 随之回到闭世界，`resolvedMods` 125 个。见 [FABRIC_AOT](FABRIC_AOT.md#第-51-轮sodium-恢复剪枝一致性与真机首跑)。

**真机首跑结果：启动链路通，游戏未起来。** `dlopen`、内存预留探测、GraalVM 入口都成功，日志显示执行进入 `net.minecraft.client.main.Main.main`，随后退出码 1。唯一异常是 `NoClassDefFoundError: net.irisshaders.iris.Iris`，位置在 `SystemReport.handler$cfc001$iris$fillSystemDetails`——上一轮剪掉了 Iris 的类但它的 jar 仍在 mods 目录，Knot 照常注入 Mixin，构成「注入存在、类不存在」的矛盾。已修：剪枝现在整体退场 jar，且 `SystemReport` 的 `handler$` 注入方法无条件 stub。**修复后的镜像尚未在真机复跑，D1 仍然是 NOT RUN。** AOT 原生库来自固定官方源码；数值 CAP 数据来源和版本记录于工具链锁定文件。

B1诊断包为 artifacts/b1/device-handoff/export/FabricAOT B1.ipa（build 4），用户已安装验证。它只包含预转换的第一方夹具，不包含Minecraft游戏代码。描述文件有效期至2026-11-15 09:53:47（北京时间）。[B0复现](B0_TEST_HANDOFF.md)、[B1证据](B1_DEVICE_HANDOFF.md)和[客户端诊断](evidence/ADR-003.md)分别记录验证边界。

已按门槛文档建立本地Git源代码记录；提交可用git log -1查看。当前源文件和证据指纹由 verify_evidence.py 保存。生成物通过唯一中央 AAR 实际登记，保留历史实验和设备状态，安全删除标志均为 false。

第13轮时的6个源文件及差异另存handoff-snapshot-20261108（不含第17–24轮新增工具）。接手状态、实验12–24及测量边界见[WORK_HANDOFF](WORK_HANDOFF.md)。

用户第46轮确认蓝屏后进入日志；设备日志为Metal诊断成功，未确认独立启动条件。Xcode工程已切到下一版四分屏资源探针，设备目标构建及输入核对通过，用户已在真机确认四色，GPU读回/呈现日志匹配；宿主返回记录受日志覆盖问题影响，已修复并另行验证。日志、输入与测试边界见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。

第47轮只使用模拟器：真实NativeImage的PNG写读/缩放/回调与Metal裁剪上传、GPU读回通过，见[图像AOT结果](../artifacts/graphics/images-simulator-evidence-02/result.json)。G4已完成60/60程序预编译，覆盖全部79个可执行着色器。87条原版管线的Metal状态创建及混合/裁剪/索引/实例/三角扇像素检查通过，见[绘制证据](../artifacts/graphics/draw-simulator-evidence-02/result.json)。后端数组注入仅修改Minecraft.class，正在验证真实Main。

真实Main的后端注入现已执行验证：窗口与Metal设备初始化成功；HTTP/HTTPS处理器、固定索引30和OpenJDK libextnet已补齐。固定OpenAL Soft1.25.2/CoreAudio已通过静音PCM实际播放验证，真实Main已进入首帧绘制；正在验证启动Logo的预加载修复。真实菜单和世界仍未验收。后续继续仅模拟器。

[模拟器真实菜单](../artifacts/graphics/main-simulator-run-08/result.json)已验证欢迎页→主菜单→单人游戏→新建世界。音频引擎启动，原版图集和全景加载；按钮背景仍有裁切/缺失。补齐 Netty 两个构造器后，[原版客户端已登录集成服务器](../artifacts/graphics/main-simulator-run-09/result.json)。地形初始化在 256 MiB 的图形资源总限额处停止；新模拟器配置把该限额提高至 768 MiB，待地形渲染复验。

## 整合包模拟器逐关推进（2026-11-11，第 53 轮）

用户约定：后续验证一律用 iOS 模拟器（`tools/smoke_mcfao_simulator.py` + WorldSimulator scheme），不再使用真机，全程自主推进不打断。成功判据为新日志同时出现 `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS`、`MCFAO_F3_CLIENT_WORLD_JOIN_PASS` 与 `Dev joined the game`。**截至 fabric-pack-48 仍未达成，游戏不可玩。**

`builds` 从 pack-06 推进到 pack-48，每轮在模拟器暴露并修掉一个闭世界缺口。已固化的修复：

| 缺口 | 处理 |
| --- | --- |
| 类引用 classpath 上不存在的类型 → Native Image 静默把调用 stub 成 `NoSuchMethodError` | 新增 `tools/verify_aot_classpath.py`（`Class.forName(name,false,loader)` 全量解析）；718 个不可加载类降至 0 个核心类 |
| Mixin 包类被「只留 accessor」过滤丢弃，含嵌套 jar 的 `ScreenAccessor` | 保留全部 Mixin 包类并提升为 public；构建期 plugin 类不随镜像出厂 |
| 瞄准库类的 Mixin 从未应用（`TaggedChoice` 等） | 从 visible/invisible 注解提取 target，向 Knot 索取改写后的库类放入 client jar 首位遮蔽 |
| 运行期生成类（`Args$N`、MixinExtras `*RefImpl`、Mixin 匿名 helper、静态 accessor 方法体） | 按真实调用点生成等价字节码 / 向 Knot 索取；`MixinException` 三件套加入 pinned 清单 |
| 方法分割命名撞名（`fabricaot$part$1` 重复 → `ClassFormatError`） | 分段名与 spill 字段名带上原方法身份，并加构建期自检 |
| Loader 查询与反射扫描（`getConfigDir`、`mapFieldName`、`getModContainer`、framework `getRegistryObjects`） | 恒等折叠 / 构建期字段表 GETSTATIC；private 字段改走 public getter；`Entrypoints.GAME_DIR` 改 public |
| 入口派发按字母序，违反 mod 依赖序（Backpacked 早于 Framework） | 按 `ModDependency.Kind.DEPENDS` 做 Kahn 拓扑排序 |
| 更改写但不落盘（residue stub 未计入变更检测）、`List.of` 误用 `Methodref`、SWAP/POP 栈序错 | 修复并在 `verify()` 中对被改写方法追加 `SimpleVerifier` 精确校验 |
| 资源：根目录 `*.toml` 默认配置缺失；过宽合并把 2173 条 `resourcepacks/` 垃圾灌进 jar 导致 AOT 早期 OOM | 合并收窄为 `assets/`、`data/` + 根目录声明性文件；`game-resources.json` 增加 `[^/]+\.toml` 模式 |
| nightconfig TOML 格式注册、AppleSkin 配置类构造 | 追加 `compiler/reflection-config.json` 条目 |

**当前阻塞（pack-48）**：入口派发已走到 AppleSkin，`AutoConfigIntegration.lambda$init$1` 抛 `NullPointerException`（`ConfigManager.load:95` → `ModConfig.init:36` → `AppleSkin.onInitializeClient:22`），客户端在 `Minecraft.<init>` 阶段崩溃，尚未进入主循环，更未加载世界。清理模拟器容器残留（各版 `MCFAO Smoke*` 测试世界、`NCR-*.json`）是复跑前置，已由冒烟脚本与手工步骤处理。

**未验收**：Gate C（进世界）、Gate D（触摸/音频/存档/真机性能）全部 NOT RUN。后续仍需逐个适配剩余 mod 入口的闭世界行为。


## AppleSkin 配置闭包修复（2026-11-11，pack-49 验证中）

出货字节码确认 `ModConfig.init` 先创建 INSTANCE，随后 `load` 在已有 appleskin.json5 时用 Jankson.fromJson 覆盖 INSTANCE。此前仅注册 GUI 配置类，缺少实际 ModConfig 的反射构造器与字段；增加该类注册以保留配置持久化语义。构建与模拟器回归待运行，门槛状态不变。

pack-49 在宿主执行权限检查处失败，未执行转换；pack-50 使用相同源码在允许的本机构建环境重跑。209 项既有 Python 回归通过（`/tmp/mcfao-tests-20261111.log`）。另确认原 61 个根 JAR 不含 `mcfao_fixture`，交接默认 F1/F3 判据对该输入不可达；已构建仓库自有验证夹具，并复制原包至 `artifacts/mcfao/curated-verification-mods-01`（61 个原 JAR + 1 个夹具，原输入不改）。冒烟增加启动前夹具检查及测试；后续完整判据使用带夹具的包，诊断运行必须显式给出 marker。

pack-50 已完成构建；classpath 56,700 类中 112 个不可加载，核心游戏/Loader 0 个失败；AppleSkin JVM 与桌面 AOT 配置值往返回归均 PASS（`artifacts/mcfao/appleskin-config-aot-01/result.json`）。模拟器保留已有配置运行，先撞上 NoChatReports `JSONConfig.writeFile` 的空 fileName（`fabric-pack-50-simulator/game.log`）；不再靠删除 NCR 配置绕过。出货字节确认三个 NCR 配置类各有 protected 无参构造器初始化 fileName/filePath，缺反射导致 Gson 走无构造器分配。追加三个配置类构造器/字段、基类字段及 SigningMode 枚举字段注册，pack-51 连同验证夹具复验；AppleSkin iOS 路径仍待越过 NCR 后确认。

冒烟脚本现对新日志中的原生返回或 Minecraft 崩溃报告立即失败；测试覆盖部分标记不能通过、先入世界后崩溃不能通过、原版不能混入 Fabric 夹具标记。该检查避免每轮崩溃后仍空等 160 秒。

pack-51 核心类可加载性仍 0 失败；保留配置的模拟器已越过 NCR 与 AppleSkin，接着在 Chat Heads `ChatHeadsConfigData.<init>()` 缺反射构造器处失败。新增只读 classfile 结构扫描 `tools/config_reflection.py`：根据 ConfigData 继承链生成构造器/字段元数据，覆盖同配置包内的字段类型（含数组/泛型枚举）及继承字段；不加载、不初始化 Mod，不遍历 Minecraft 字段图。与手动反射配置合并，并记录 autoConfigReflection 与构建输入指纹。真实出货 JAR 扫描得到 12 个类型，含 ChatHeadsConfigData/RenderPosition/SenderDetection；五项扫描/继承/边界/截断负例回归通过。pack-52 完整复验中。

pack-52 模拟器已越过 Chat Heads，下一处为 Indigo.onInitializeClient 引用被排除的 IndigoMixinConfigPlugin。已审计插件原字节：shouldApplyIndigo 仅扫描所有 Mod 的 `fabric-renderer-api-v1:contains_renderer` 自定义键；生成同一布尔决定替换该调用，不在运行期加载插件。改写受原插件 SHA-256 934ac8f2002a53fcf5a095d44cfd1ce97625ff362058b2556b5d4f59941f0d47 限定，改版插件精确拒绝。第一方 JVM 字节码回归在插件不存在的 classpath 上分别执行 true/false 路径，并验证指纹不符拒绝和无关方法不变，PASS（`artifacts/mcfao/indigo-gate-regression-01/`）。pack-53 完整复验中。

pack-53 已消除 Indigo 插件缺失引用，核心类可加载性 0 失败；模拟器下一处是 Entity Culling ConfigUpgrader 的空 blockEntityWhitelist。字节码显示其 Gson.fromJson 使用 Config.class 字面量；缺构造器注册导致已有 JSON 分支的字段为 null。导出器现从 Gson/Jankson 的静态 Class 字面量反序列化调用收集实际 Mod 类型，写入本地出货 JAR 的 serialization-roots.json（不收游戏/库外部类型），配置扫描器据此合并构造器/字段和同包字段类型注册。动态 Class/TypeToken 不猜测；报告字段 serializationRoots / configurationReflection 可审计。新增非 AutoConfig 根及调用点收集回归通过。pack-54 验证中；保留已有配置，不以清配置绕过。

pack-54 模拟器已越过 Entity Culling，随后 Jade ClientProxy.<clinit> 抛 VerifyError。不执行初始化的 JVM 成员解析定位到 FabricJadeMetadata.<init> 被 residue stub 改成单独 RETURN，未调用 super。已审计并按原构造器语义生成构建期 Jade 元数据表：保留父类状态、OR 三个布尔标志、记录禁用物品 Mod 名提示的 id 列表；仅接受原类 SHA-256 0893768a286b48ac48e75ab7b8d7ecf2da3321d8743fbba0366abd0c42aa2184。其它未适配构造器改为合法 ATHROW 明确失败，避免 VerifyError；同批修正 residue stub 中 List/Set/Map.of 的接口调用标志。第一方 JVM 回归实际加载生成类、构造 Jade 数据并校验父类状态/列表/指纹负例，且验证未支持构造器可校验但明确抛错、集合返回可调用，PASS。原始定位证据 `artifacts/mcfao/jade-verify-01/`。pack-55 完整复验中。

223 项 Python/第一方 JVM 回归全通过（`artifacts/mcfao/regression-20261111-jade-01/`）。`verify_aot_classpath.py --verify-members` 提供不初始化的成员解析补充检查，单独输出 classpath-members-check.json；它比默认类加载更严格，可报告私有死方法签名里的可选类型，不直接替代运行结论。探针子进程失败/缺 SUMMARY/计数不全现在精确失败，防止把无输出当 0 个失败。

pack-55 模拟器首次出现 MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS，尚未进世界；下一处是 ModMenu 自定义阶段 NEW Zoomify Kotlin object 的 private 构造器而抛 IllegalAccessError。自定义阶段现按不初始化的类结构识别 INSTANCE，普通 provider 延迟创建并缓存（每项同步工厂），复现 Loader 的单次实例语义；第一方 JVM 回归验证 private 构造器单例、延迟创建及跨查询身份 PASS。

同轮成员校验主动找到 5 个合成 Args$N 的 VerifyError：手写 getter 从 Object 返回具体引用缺 CHECKCAST；原承载类还未实现 Args 的抽象 set/setAll。现从同一构建期 Mixin transformer 的 ArgsClassGenerator 注册表导出上游完整结果，校验所有真实调用成员匹配，运行期只用预生成字节。新增 ArgsBehaviorProbe 覆盖全部出货承载类的 typed getter、set/setAll、索引/数量/原始类型 null/引用类型负例，待 pack-56 产物执行。原始定位在 `artifacts/mcfao/args-verify-01/`。pack-56 完整复验中。

pack-56 在构建期检查到 AppleSkin 元数据声明的 rei_client 提供者 `squeek.appleskin.client.REITooltipPlugin` 本就不在 JAR 内，未进入 AOT。现在从实际保留下来的 Entrypoints.stage 调用收集 queriedEntrypointStages，只为有调用点的阶段生成派发；其余全部原始声明保留在 unqueriedEntrypointStages，不按消费者名字猜测或删除 Mod。对活跃阶段继续验证 public 构造器或 INSTANCE；静态阶段收集、单例及延迟身份回归通过。pack-57 复验中。

pack-57 已成功导出上游 Args 与 Kotlin 单例，实际保留的查询阶段为 appleskin / frex_flawless_frames / glitchcore / jade / modmenu / terrablender；其余阶段声明有独立台账。ArgsBehaviorProbe 在进入模拟器前发现生成器原始 maxStack 不含 long/double 的完整槽位（上游要求最终 writer 计算最大栈）；主动停止该轮 AOT，未作为有效模拟器构建。导出序列化现用 COMPUTE_MAXS，并追加实际 JVM 运行宽类型栈夹具（故意提供不足 maxStack，验证重算后可执行）的回归，PASS。pack-58 复验中；Args 完整行为仍待新产物执行。

pack-58 的 8 个真实出货 Args 已通过独立 JVM 行为回归（typed getter、set/setAll、索引/数量/原始类型 null/引用类型负例），`artifacts/mcfao/args-behavior-58-01/result.json` 记录输入指纹。此为构建期字节码行为辅助证据，模拟器进世界仍待验。

pack-58 核心类可加载性 0 失败，成员校验 VerifyError 0；模拟器越过 Zoomify/Mod Menu，F1 再次出现，随后 Presence Footsteps 的 TargettedVersion.getVersion 因 Optional 方法引用仍提到未出货 ModMetadata 而失败。已对原类 SHA-256 354dc01c8aff54e3b4543f1d441fcbbbefa32ee15ccc5041aad895a44196aa1b 的 getVersion(String) 改写为构建快照版本查询；保留并出货固定 Loader 的 8 类纯 Version/SemanticVersion/解析与异常闭包，经常量池/调用审计仅依赖 JDK 值操作，无 Loader 生命周期/类发现/IO。Residue 与代码审核仅豁免这 8 个固定值类型，仍拒绝其它运行时 Loader 行为。第一方 JVM 回归确认快照文本/比较、纯解析不被 stub、缺失 id 明确失败，PASS。pack-59 完整复验中。

pack-59 版本查询已越过，F1 出现；下一处 Sodium `ConfigManager.registerConfigs` 报核心配置未找到，根因是 collectConfigEntryPoints 因 getProvider→metadata→id 被 residue 清空。现在容器保存声明者 id，将该只读链折叠为 providerModId；保留 getEntrypoint/getDefinition 两个已实现的只读接口调用。按固定 Sodium ConfigLoaderFabric 指纹 13cb0cc07040be08158ab8cd53992f519d1430bcd40574bd651c93362efa2cfd，将 getModMetadata(String) 接到真实 name/version 快照，原核心与第三方配置注册代码继续执行，不跳过 Sodium。

已核对 Loader 0.19.3 EntrypointContainerImpl 的延迟创建：容器查询仅记录索引/定义/id，实际 getEntrypoint 时才调用预编译的缓存工厂；Kotlin INSTANCE 同样延迟读取。第一方 JVM 回归验证查询不初始化、实例身份、真实 owner id 和 Sodium 元数据值 PASS。日志中的非致命 HashedFingerprint record Gson getter 缺失由配置扫描器对 Record 类型补 allDeclaredMethods 解决，新增回归通过。尚不提供完整运行时 ModContainer/文件系统 API。pack-60 完整复验中。

**pack-60 未产出镜像：AOT 分析 OOM。** `fabric-pack-60/aot/a3845ea9.../product/analysis/stderr.log` 记录 `-Xmx7g` 下 `Terminating due to java.lang.OutOfMemoryError: Java heap space`，`work/gc.log` 的 GC(1055) 已是 5117M→5117M / 5438M 老年代满，进程 RSS 6.50GB，耗时 71.9s。这不是环境抖动：与 pack-59（成功，Full GC 后 4.05GB live，1m42s）对比，本次恢复 Sodium 真实配置注册路径后 `transform.stubbedMethods` 97→88、`staticAdaptations` 208→212、`queriedEntrypointStages` 6→7，metal jar 只增 5,122 字节，反射配置只多 `HashedFingerprint` 一个 record 的 `allDeclaredMethods`（64 条不变）。可达图像堆的真实增长来自 9 个不再 stub 的方法重新链接到原配置注册代码，**这是修复本身，不应通过重新 stub 来省内存**。处置：`tools/mcfao.py` 的 `--heap-gib` 由 7 提到 8（`tools/probe_client_graph.py` 允许 6/7/8，预检仍要求堆 ≤ 0.50×物理内存、free ≥45%、磁盘 ≥8GiB）；本轮 18GiB 主机 free 67%。225 项 Python/第一方 JVM 回归 PASS。pack-61 以 8GiB 堆重跑，Gate 状态不变，整合包仍未进世界。

**pack-61：AOT 通过、Sodium 越过，新阻塞为 GlitchCore 事件总线。** 8GiB 堆完整构建成功（5m17s，`result.json` → `SIGNED_DEVICE_APP`，AOT `heapGiB=8`、峰值堆 6.78GB / Full GC 后 5.82GB live，印证 7GiB 不够）。静态校验：默认 112/56,710 不可加载、核心游戏/Loader 类 0 失败、VerifyError 0；`--verify-members` 259 条多为可选依赖签名（含 1 条 `net.fabricmc.loader.api.ModContainer`），VerifyError 仍 0。保留已有配置的模拟器冒烟 38 秒即崩：`glitchcore.event.EventManager.getEventClass:62` 抛 `IllegalStateException: Failed to resolve consumer event type: biomesoplenty.init.ModClient$$Lambda/0xb2f5...`，链路为 `ModClient.addClientHandlers` → `BiomesOPlenty.init` → `GlitchCoreFabric.onInitialize` → `Entrypoints.startClient`。上一轮的 `Sodium mod config not found` 与 `HashedFingerprint.version()` 报错均未再出现，**Sodium 修复已生效**；本轮日志未出现 F1（崩在更早的入口派发阶段）。判据仍未达成，游戏不可玩。

根因是 `getEventClass` 用 typetools `TypeResolver.resolveRawArgument(Consumer.class, consumer.getClass())` 从隐藏 lambda 类反推 `Consumer<T>`；Native Image 里既没有泛型签名也没有可反射的常量池，事件总线**所有**监听器注册都会失败。出货 jar 里共 5 个 `addListener` 调用点：BiomesOPlenty `ModClient` 的 4 个 `invokedynamic`，以及 `glitchcore.util.RegistryHelper` 构造里传入的具名 `Consumer<RegistryEvent>`。修法（`RuntimeLowering.lowerGlitchCoreEvents`）：从 LambdaMetafactory 的 `instantiatedMethodType` 或类 Signature 在构建期读出事件类，为每个调用点压入 `LDC Class`，改调新增的 `EventManager.addListenerResolved(Consumer, Class)`；该方法克隆原 `addListener` 方法体、仅删掉 `getEventClass` 三步，因为原 slot 1 正好存放解析出的 `Class`，监听器、事件与注册顺序一律不跳过。改写受原始类 SHA-256 限定（EventManager `dafe0c0a…`、RegistryHelper `d2e5f55d…`），无法识别的 consumer 形状精确报错，并为方法 `maxStack` 补 1 槽防止 VerifyError。第一方 JVM 回归 `interop/diagnostics/GlitchCoreEventProbe.java` 实际定义改写后的类、注册 lambda 与具名 Consumer、执行一次回调、断言反射路径从未进入，并验证指纹不符/未知形状拒绝；226 项全量回归 PASS。

pack-62 **未进入 AOT**：预检 `memory free percentage: 34%` 低于 8GiB 堆要求的 45%（`aot/*/product/result.json` → `Host memory headroom below bounded experiment threshold`），原因是上一轮冒烟后模拟器仍 Booted、SpringBoard/SimMetalHost 占内存，不是源码问题。`xcrun simctl shutdown all` 后 free 回到 58%，用新编号 pack-63 重跑；该环境陷阱已写进 `docs/C0_FABRIC_HANDOFF.md` §8。Gate C/D 口径不变。

**pack-63：改写生效，但严格成员校验抓到栈帧缺陷。** 出货字节确认 4 个 BOP `invokedynamic` 与 `RegistryHelper.<init>` 全部变成 `LDC Class` + `EventManager.addListenerResolved(Consumer, Class)`，`transform.staticAdaptations` 218 条含 5 条 `GlitchCore event=...`；默认 classpath 校验仍是 112/56,710、核心类 0 失败。但 `--verify-members` 首次报出 1 个 `VerifyError: glitchcore.event.EventManager: Stack map does not match the one at exception handler 87`（pack-61 为 0）。根因不是指令错误，而是**克隆方法沿用了相对栈帧**：StackMapTable 的相对帧以方法入口 implicit frame 为基准，原 `addListener` 入口是 `(Consumer)` 一个参数，生成的 `addListenerResolved` 是 `(Consumer, Class)` 两个，异常处理器处的 frame 语义整体偏移。修法：只对 EventManager 类改用 `ClassWriter(COMPUTE_FRAMES|COMPUTE_MAXS)` 重算全类帧（`AotExport.recomputedClassBytes`），其余类继续用原 `classBytes` 保持字节稳定；`GlitchCoreEventProbe` 新增 javac 编译、带真实 synchronized 栈帧的 `RealManager`，在 JVM 上定义重算后的类并实际反射调用 `addListenerResolved`，把这次失败固化成可重现回归。226 项回归 PASS，pack-64 完整复验中。

构建前空间处置：`df` 空闲降到 8.9GiB，AOT 预检要求 ≥8GiB 已临界。先跑 `tools/dedup_artifacts.py`（54 组 / 130 个 `.dylib`/`.jar` 已是 APFS clone，`df` 无变化，印证「逻辑重复 ≠ 物理可回收」），再按强制校验流程确认 `git ls-files artifacts/mcfao` 为空、无 `.ipa/.xcarchive/.p12/.mobileprovision`、docs 未引用编号后，把 `fabric-pack-36/38/39/40/42/45/46` 移入废纸篓并定向清空 fabric-pack 项，`df` 空闲 8.9GiB → 18GiB；文档引用过的编号与 `artifacts/evidence/` 一律保留。

**pack-64：GlitchCore 越过、栈帧缺陷修好，新阻塞为 Sodium 的字符串类发现。** 构建成功，`--verify-members` 的 VerifyError 回到 0（259 条仍是可选依赖签名），出货字节保留 5 条事件类改写且 EventManager 帧由 `COMPUTE_FRAMES` 重算。保留配置的模拟器冒烟 35 秒崩溃于 `com.mojang.blaze3d.vertex.VertexFormat.handler$djc000$sodium$afterInit` → `DefaultVertexFormat.<clinit>` → `RenderPipelines.<clinit>` → `Sheets.<clinit>` → BiomesOPlenty `ModClient.registerWoodTypes`：`VertexFormatRegistry.<clinit>` 用 `DependencyInjection.load(Class, String)` 做 `Class.forName("net.caffeinemc.mods.sodium.client.render.vertex.VertexFormatRegistryImpl")` + `getConstructor().newInstance()`，闭世界里该实现类虽在 metal jar 却未注册，抛 `ClassNotFoundException`。日志中 F1 仍未出现，判据未达成。

出货 jar 里共有 4 处同构 `<clinit>`：`BlockEntityRenderHandlerImpl`、`SpriteUtilImpl`、`VertexFormatRegistryImpl`、`VertexSerializerRegistryImpl`，四个实现类都在原始 Sodium jar 与 metal jar 中、都有 public 无参构造器，默认 classpath 校验也显示它们可加载。修法沿用项目既有的闭世界反射注册路线：在 `compiler/reflection-config.json` 为四个类补 `allDeclaredConstructors: true`，保留 `Class.forName` / `isAssignableFrom` / 反射构造的真实语义，不 stub、不跳过 Sodium。新增 `tests/test_config_reflection.py::test_sodium_dependency_injection_implementations_are_registered` 校验条目与原 jar 中的类一一对应；227 项回归 PASS。pack-65 完整复验中，Gate C/D 口径不变。

**pack-65：Sodium 字符串类发现已越过，F1 首次在本轮链条中出现；新阻塞为 XaeroLib 入口类不可链接。** 8GiB 堆构建成功（5m6s，`result.json` → `SIGNED_DEVICE_APP`）；静态校验默认 112/56,710 不可加载、核心游戏/Loader 类 0 失败、VerifyError 0，`aot/*/product/work/reflection-config.json` 含四个 Sodium 实现类条目。保留配置的模拟器冒烟在 `Minecraft.<init>` 崩溃，但 `fabric-pack-65-simulator/game.log:80` 出现 `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS`（pack-61 以来第一次），证明 GlitchCore 事件总线、Sodium 配置与 `DependencyInjection` 三条链都已越过。随后 `Entrypoints.startClient` 抛 `java.lang.NoClassDefFoundError: xaero.lib.XaeroLibFabric`。同轮另有两处非致命降级：freecam `ModConfigDTO.<init>()` 反射未命中 → `Using Cloth Config Freecam GUI`；PresenceFootsteps 配置 JSON 第 81 行损坏 → `Failed to load config, using defaults`，二者均未终止启动，单独留台账。

定位：`classpath-check.json` 的 112 个不可加载类中，只有 3 个是 `transform.entrypoints` 里的真实入口点，且三者同因 —— `xaero/lib/XaeroLibFabric`、`xaero/minimap/XaeroMinimapFabric`、`xaero/map/WorldMapFabric` 都 `ClassNotFoundException: net.fabricmc.api.DedicatedServerModInitializer`。metal jar 里 `xaero/lib/**` 共 352 个类随嵌套 jar 正常出货，三个入口类都在其中；`javap` 确认 `XaeroLibFabric` 同时 `implements ClientModInitializer, DedicatedServerModInitializer`。`AotExport` 原先只把 `ModInitializer` / `ClientModInitializer` / `EnvType` 三个 Fabric API 类写进出货白名单，漏掉的第四个接口让三个类在闭世界里全部无法链接，而 Native Image 不把这当构建错误，只在运行期入口派发处抛 NCDFE。

修法不采用「再补一个类名」：`AotExport.fabricApiTypes()` 从固定 Fabric Loader 0.19.3 jar 的 code source 枚举**整个 `net/fabricmc/api/` 包**（jar 与展开目录两种形态都支持，条目名与 classfile 内部名逐一自检），导出时把未在 `names` 里的声明全部出货，并把新增条目写进 `transform.pinnedFabricApi` 供审计。这些都是无状态接口/注解，不含 Loader 生命周期、类发现或 IO；不改 Mod 字节、不跳过 Xaero 初始化。新增第一方 JVM 回归 `interop/diagnostics/FabricApiClosureProbe.java`：在无 Fabric Loader jar 可见的自定义 ClassLoader 里，仅用导出的 API 字节定义一个同时实现 client/server 初始化接口的 `probe/DualInitializer`，断言两个接口都可赋值且都来自该闭世界加载器；`tests/test_runtime_lowering.py` 新增同名用例。**228 项 Python/第一方 JVM 回归 PASS**，pack-66 完整复验中，Gate C/D 口径不变。

**pack-66：Xaero 入口派发越过，新阻塞为 YetAnotherConfigLib 配置反射。** 完整构建成功（9m23s，`SIGNED_DEVICE_APP`）；`transform.pinnedFabricApi` 列出 4 个新增声明（`DedicatedServerModInitializer` / `Environment` / `EnvironmentInterface` / `EnvironmentInterfaces`），metal jar 里 `net/fabricmc/api/` 由 3 个类补齐到 7 个。静态校验：默认 **109**/56,714 不可加载（pack-65 是 112）、核心类 0 失败、VerifyError 0；严格成员校验 256 条、VerifyError 0；**89 个真实入口点不可加载数 0**（pack-65 是 3），Xaero 相关失败全清。

模拟器冒烟 49 秒崩溃：`game.log:80` 仍出现 F1，随后 `dev.isxander.yacl3.platform.PlatformEntrypoint.onInitializeClient` → `YACLConfig.<clinit>` → `ConfigClassHandlerImpl.<init>` 抛 `ExceptionInInitializerError`，根因 `NoSuchMethodException: dev.isxander.yacl3.platform.YACLConfig.<init>()`。出货字节确认该类有 public 无参构造器，但 `ConfigClassHandlerImpl` 用 `Class.getDeclaredConstructor()` + `getDeclaredFields()` + `Field` 读写访问配置，闭世界未登记这些元数据；`getDeclaredMethods` 未被使用。两处非致命配置降级（freecam / PresenceFootsteps）与上一轮相同，未终止启动。

修法沿用可复用的配置扫描器，而不是把类名硬塞进 `compiler/reflection-config.json`：`tools/config_reflection.py` 的 `class_shape` 现解析方法表与全部（含 static）字段描述符，`yacl_config_roots()` 以「同时具备 `<clinit>` 与 `ConfigClassHandler` 类型字段」识别所有 YACL v2 配置类（真实 metal jar 上精确命中 `dev.isxander.yacl3.platform.YACLConfig` 一个类，无误报），再复用 `config_entries` 的同包字段闭包生成 `allDeclaredConstructors` + `allDeclaredFields`。这样以后其它 Mod 的 YACL 配置类进入包时不会再逐个爆一次。新增 3 项回归：根识别正/负例、真实 metal jar 出货注册、以及既有夹具的方法表解析不变；**230 项 Python/第一方 JVM 回归 PASS**。

构建前磁盘降到 7.4GiB（低于预检 8GiB）：按强制校验流程确认候选目录无文档精确路径引用、无 xcconfig/pbxproj 硬编码、无 git 跟踪后，只对**失败构建**（49/56/57/60/62/44）与**已被取代的模拟器输出**（50/51/52/53/61/64/65 的 `-simulator`）执行 `/usr/bin/trash` + 定向清空废纸篓，`df` 7.4GiB → 15GiB。所有 `SIGNED_DEVICE_APP` 且含 `embedded.mobileprovision` 的签名证据包一律保留。pack-67 完整复验中，Gate C/D 口径不变。

**pack-67：YACL 越过，客户端推进到 `RenderSystem.initRenderer`；新阻塞为 Mixin 插件的构建期副作用未带进镜像。** 完整构建成功（11m19s，`SIGNED_DEVICE_APP`）；`aot/*/product/work/reflection-config.json` 69 条中确认 `dev.isxander.yacl3.platform.YACLConfig` 带 `allDeclaredConstructors` / `allDeclaredFields`，`configurationReflection` 51 条含该类。静态校验默认 109/56,714 不可加载、核心类 0 失败、VerifyError 0、严格成员校验 VerifyError 0、89 个入口点不可加载 0 个。模拟器日志确认 YACL 配置文件被真实创建（`yacl.json5` 序列化成功）、Xaero 三个 Mod 的配置与 Stage 1/3 全部加载、GLFW/Metal 设备初始化完成，F1 仍在；随后 `ImmediatelyFast.onRenderSystemInit` 抛 `NullPointerException: Config not loaded yet`。另有 401 用户属性拉取失败（离线账户，非致命）。

定位：`ImmediatelyFast.config` 与 `VERSION` 同时为 null，说明 `earlyInit()` 从未运行。该 Mod 的 `fabric.mod.json` **没有任何 entrypoint**；`earlyInit()` 只由 `ImmediatelyFastMixinPlugin.onLoad()` 调用，而该插件在 `transform.droppedEntries` 里明确标为 `(MixinConfigPlugin)`、不随镜像出厂 —— Knot 只在构建期应用 Mixin 时执行了它，副作用留在构建 JVM 的静态字段里。这是 Indigo 插件之后第三例同类问题。此外 `PlatformCodeImpl.getModVersion(String)` 被 residue 折叠成 `Optional.empty()`，即便重放 `earlyInit()` 也会在 `orElseThrow` 处立刻失败。

修法（两部分，都保留真实 Mod 代码）：
1. `RuntimeLowering.lowerImmediatelyFastVersion`：按原类 SHA-256 `c8beac00…` 限定，把 `getModVersion` 方法体改为调用新生成的 `Entrypoints.optionalModVersion(String)`；该钩子用构建期版本快照回答「Mod 存在则给真实版本、不存在则 `Optional.empty`」，与 Loader 语义一致，且因为改写先于 `lowerQueries`，通用 residue stub 不再把它压成空值。
2. `RuntimeLowering.collectMixinPluginEarlyInit`：在插件被丢弃的分支按 SHA-256 `10f0fa06…` 审计其 `onLoad` 必须恰好含一次 `ImmediatelyFast.earlyInit()V`，把这条副作用登记到 `transform.earlyInitializers`；`AotExport.staticHooks` 在 `startClient` 设置完 `GAME_DIR` 后、所有入口派发之前重放它（对应 Fabric 在 entrypoint 之前应用 Mixin 的时序）。配置文件读写、runtime config 构造、兼容性检查全部继续执行，未 stub、未跳过。

新增第一方 JVM 回归 `interop/diagnostics/ImmediatelyFastInitProbe.java`：审计正例/缺调用/错指纹三个边界，检查生成的 `startClient` 确实含 `earlyInit` 调用，把生成的 `Entrypoints`、改写后的 `PlatformCodeImpl` 与桩 `ImmediatelyFast` 放进同一个闭世界 ClassLoader，实际调用 `optionalModVersion`（存在/不存在两种）、`getModVersion`（确认没被 residue stub 吃掉）以及 `startClient(null,null)`（确认 `earlyInit` 真的执行）。`ExportGenerationProbe` 的 `staticHooks` 反射签名同步更新。**231 项回归 PASS**，pack-68 完整复验中，Gate C/D 口径不变。

**pack-68：`earlyInit` 重放生效，ImmediatelyFast 在本机 GPU 上真实初始化；新阻塞是 Iris 兼容层必须运行期生成字节码。** 首次构建在 `package` 阶段失败（`Signing for "C0Harness" requires a development team`），与代码无关：工程里 `DEVELOPMENT_TEAM = ""`，此前 Team 由 Xcode 隐式账号状态解析，两次参数完全相同的构建一次解析到、一次没有。已改为由 `tools/mcfao.py` 显式解析（`MCFAO_DEVELOPMENT_TEAM` 环境变量优先，否则在已安装且覆盖 `org.fabricaot.research.c0.kexin` 的 `.mobileprovision` 里取到期最晚的团队）并以 `DEVELOPMENT_TEAM=P57SZ9Z7G2` 加到 `xcodebuild` 命令行；无可用描述文件时直接报错而不是让 Xcode 抛模糊信息。续跑复用前七个阶段的检查点，只重做 `package`，`result.json` → `SIGNED_DEVICE_APP`，签名身份 `Apple Development: <redacted-email> (<redacted-cert-id>)`、描述文件 `iOS Team Provisioning Profile: org.fabricaot.research.c0.kexin`。新增 3 项回归（团队选择、环境变量覆盖与格式校验、命令行只出现一次 `DEVELOPMENT_TEAM`），**234 项 PASS**。

静态校验：默认 109/56,714 不可加载、核心类 0 失败、VerifyError 0；严格成员校验 256 条、VerifyError 0；89 个真实入口点不可加载 0 个；`transform.earlyInitializers` 记录 `net/raphimc/immediatelyfast/ImmediatelyFast#earlyInit`。

模拟器冒烟在 `RenderSystem.initRenderer` 之后走到 `ImmediatelyFast.onRenderSystemInit`，日志打印 `Initializing ImmediatelyFast 1.15.2+26.1.2 on Apple iOS simulator GPU` —— 说明 early 初始化重放、`optionalModVersion` 版本查询、Gson 配置装载三条链都已跑通，`Config not loaded yet` 不再出现，F1 继续出现（`game.log:80`）。随后 `IrisCompat.init` 抛 `NoClassDefFoundError: net.lenni0451.reflect.accessor.FieldAccessor`，被 catch 后调用 `System.exit(-1)`，客户端在 `Minecraft.<init>` 终止。

定位：ImmediatelyFast 检测到 Iris（`isModLoaded("iris")`）后进入兼容路径，用 `FieldAccessor.makeGetter/makeSetter` 与 `RStream` 读写 Iris 的私有字段；`FieldAccessor` 的内部实现是 `BytecodeBuilder → BuiltClass.defineMetafactory`，**运行期生成并定义类**，同库还有 `Unsafe.defineClass` / `ClassLoader.defineClass`，因此整个 `net_lenni0451_reflect` 被 `validateModCode` 排除。这不是某一行代码缺失，而是闭世界与「运行期代码生成」的根本冲突，且 ImmediatelyFast 把该失败当作不可恢复（`System.exit`）。处置：把 Iris 从验证整合包移入 `artifacts/mcfao/incompatible-01/`（jar 原样保留并带指纹），`result.json` 记录 `EXCLUDED_INCOMPATIBLE`、完整证据路径、以及「Iris 自身渲染路径未被验证，这是 pair 级不兼容」的边界说明。同一份记录还标出 ImmediatelyFast 的 `map_atlas_generation` mixin 会把 `net.lenni0451.reflect.Objects.allocate` 合进 `MapTextureManager$MapInstance.<clinit>`，地图渲染预期仍会 `NoClassDefFoundError`，但不影响进世界，单独留台账。pack-69 正在完整构建，Gate C/D 口径不变。

**pack-69：Iris 移出后 AOT 在 8GiB 堆下 GC 死亡螺旋，堆上限抬到 9GiB（= 18GiB 机器的 50% 硬上限），改在 pack-70 复跑。** 去 Iris 后的 `fabric` 阶段正常（47 个根 mod / 161 个含嵌套，`excludedMods` 不再含 iris，`earlyInitializers` 仍登记 ImmediatelyFast）。AOT 分析在 8GiB 下停在 `Pause Full 7087M->7087M(7337M)`：每次 Full GC 回收 0，单次 safepoint 停顿 8~15 秒，40 分钟无进展，`client-graph` 从未生成。按 Full GC 的 live 序列（5711M → 5963M → 7087M 后饱和）判定为可达集真实增长而非泄漏——Iris 不在场时 Sodium/ImmediatelyFast 的 `--initialize-at-run-time` 之外的静态初始化走另一条分支，构建期实打实构造了更多对象。处置：`--heap-gib` 8 → 9、`probe_client_graph.py` 的 choices 增加 9（50% 物理内存硬上限，9GiB 恰好等于该上限，10GiB 会被预检拒绝）。因 `probe_client_graph.py` 属于 `BACKEND_TOOLS` 指纹集合，pack-69 目录已不可续跑（`Build inputs changed`），改在 pack-70 全量构建。

**pack-70：9GiB 堆构出 `SIGNED_DEVICE_APP`，新阻塞是 Sodium 要 OpenGL，而设备只有 Metal —— 判为平台级不兼容。** AOT 分析 580 秒收尾（42 次 Full GC，live 未到容量），`link → runtime → stage → package` 全部通过，`package` 阶段按 `MCFAO_DEVELOPMENT_TEAM`/已安装描述文件解出团队 `P57SZ9Z7G2` 签名成功。模拟器冒烟（新 UDID `8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3`，旧的 `F3EC958F` 已被模拟器重置清掉）在 `Minecraft.<init>` 内、`RenderSystem.initRenderer` 之后崩：

```
UnsatisfiedLinkError: Can't load library: .../Frameworks/liblwjgl_opengl.dylib
  at org.lwjgl.opengl.GL.<clinit>(GL.java:74)
  at org.lwjgl.opengl.GL11C.<clinit>(GL11C.java:23)
  at net.caffeinemc.mods.sodium.client.compatibility.environment.GlContextInfo.create(GlContextInfo.java:10)
  at RenderSystem.handler$dfb000$sodium$postContextReady(RenderSystem.java:1544)
```

判据：这不是「少打包了一个 dylib」。`GlContextInfo.create()` 就是三句 `GL11C.glGetString(0x1F00/0x1F01/0x1F02)`；`net.caffeinemc.mods.sodium.client.gl.device.RenderDevice.<clinit>` 无条件 `INSTANCE = new GLRenderDevice()`，`RenderDevice.getCapabilities()` 的返回类型是 `org.lwjgl.opengl.GLCapabilities`，而 `SodiumWorldRenderer` 每帧经 `LevelRenderer` mixin 走 `RenderDevice.INSTANCE.createCommandList()`。本工程没有任何 GL 实现：唯一 GPU 后端是 `fabricaot.metal.MetalBackend`（`GpuBackend`/`GpuDevice` on Metal），`lwjgl-lite` 只为 GLFW/STB/OpenAL 生成 JNI（`graphics-jni.json` 21 条，无 `GL11C`/`glGetString`），stage 也只铺 `libglfw/liblwjgl/libfaot_metal/libopenal`。iOS 不提供桌面 GL，所以 Sodium 的渲染路径**无法用闭世界手段修复**：类都在镜像里、也都能加载，缺的是一整个 OpenGL 实现。处置：Sodium 连同声明硬依赖它的 `sodium-extra`、`reeses-sodium-options` 一并移入 `artifacts/mcfao/incompatible-01/`，`result.json` 新增 `level: "platform"` 条目（含字节码证据、当前后端、native 清单、以及「重新考虑的触发条件：GL-on-Metal 翻译层」）。验证整合包根 JAR 47 → 44。

连带改动：`PrepareFabricAot` 的 run-time overlay 现在按 Mod 是否存在来编译——`mcfao/aot/GenericVertexSerializer.java` 实现的是 Sodium 自己的 `VertexSerializer`，Sodium 不在包里时 javac 会因缺包直接失败。新增 `RUNTIME_OVERLAY_MODS` 映射与 `runtime_overlay_sources()`，跳过项写进 `result.json` 的 `runtimeOverlays.skipped`，配 3 条回归（`tests/test_mcfao.py::RuntimeOverlayTests`）。`RuntimeLowering.replaceGeneratedSerializer` 本身按类名匹配，Sodium 不在场时自然不触发。

**pack-72：Sodium 移出后构建干净通过，F1 稳定复现，新阻塞是 Gson 配置的闭世界反射。** 44 个根 mod / 158 个含嵌套，`runtimeOverlays` 正确记录「skipped: GenericVertexSerializer.java」。AOT 580 秒、`SIGNED_DEVICE_APP`。静态校验：默认 88/54,189 不可加载、核心类 0 失败；严格成员校验 229 条、**VerifyError 0**；87 个入口点不可加载 0 个；`earlyInitializers` 仍含 ImmediatelyFast。模拟器冒烟 `game.log:80` 出现 `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS`，`RenderSystem.initRenderer` 与 Sodium 的 GL 探测都不再出现，新崩溃点是：

```
ExceptionInInitializerError at dynamic_fps.impl.feature.volume.SmoothVolumeHandler.init(SmoothVolumeHandler.java:21)
  ... dynamic_fps.impl.config.DynamicFPSConfig.<clinit> -> Serialization.loadDefault
Caused by: IllegalArgumentException: Type dynamic_fps.impl.config.DynamicFPSConfig is instantiated
  reflectively but was never registered. Register the type by adding "unsafeAllocated" ...
```

定位：`Serialization.loadDefault()` 是 `ldc class DynamicFPSConfig` + `invokestatic JsonUtil.fromJson(String, Class)`，`JsonUtil` 再把 `Class` 原样转给 `Gson.fromJson`。既有的 `collectSerializationRoots` 只认 `owner == com/google/gson/Gson|Jankson`，于是**类字面量在包装器调用点上、Gson 调用点上只有 `aload`**，`DynamicFPSConfig` 从未成为序列化根，也就从未进反射配置。Gson 找不到已注册的无参构造器后退到 `Unsafe.allocateInstance`，闭世界直接拒绝。

修法（两处都是框架级，不是给这个 Mod 打补丁）：① `RuntimeLowering.collectSerializationRoots` 改按「方法名 `fromJson`/`fromJsonCarefully` + 最后一个参数是 `Class`」判定，不再要求 owner 是 Gson 本体——Mod 包裹 Gson 是普遍写法；实测该放宽只为整包新增 **1** 个根（就是 `DynamicFPSConfig`），没有过注册。② `config_reflection.class_shape` 记录 `<init>` 描述符，`config_entries` 对**没有 `()V` 构造器**的类型补 `unsafeAllocated`（`Config` 只有 6 参构造、`VolumeTransitionConfig` 只有 protected `(FF)`，Gson 必然走 Unsafe）。回归：新增 `interop/diagnostics/SerializationRootProbe.java`（直接 Gson / 包装器 / `fromJsonCarefully` 三个正例，非 `fromJson` 名与非 `Class` 尾参两个反例）与 `tests/test_config_reflection.py::test_types_without_a_no_arg_constructor_get_unsafe_allocation`。pack-73 用这两处修法完整复验。

**pack-73：`NoSuchMethodError` 指向一个确实存在的 Mod 方法 —— 被按 id 排除的嵌套库把宿主类拖成了桩。** 43 个根 mod 的包（dynamic-fps 已移出时点为 44，本轮处置后 43），构建 `SIGNED_DEVICE_APP`；静态校验默认 88/54,189 不可加载、核心类 0 失败、87 个入口点 0 不可加载。冒烟 F1 稳定复现（`game.log:80`），新崩溃点在 `Description: Initializing game`：

```
NoSuchMethodError: dynamic_fps.impl.feature.battery.BatteryTracker.isFeatureEnabled()
```

`BatteryTracker` 就在出货类里，方法也确实存在——这正是误导点。真实原因是 dynamic-fps 内嵌 `battery-2.0.0.jar`（`fabric.mod.json` 声明 JNI native，无 iOS 构建），`AotExport` 按**整库 mod id** 排除它，但宿主 Mod 的类留在镜像里，于是 `BatteryTracker` 的字段类型全部消失、类不可链接，Native Image 把对它的每次调用替换成抛 `NoSuchMethodError` 的桩。宿主 Mod 的元数据并不声明对嵌套库的 `depends`，依赖级联抓不到；默认 `verify_aot_classpath.py` 也看不到，只有 `--verify-members` 报 `BatteryTracker -> ClassNotFoundException: net.lostluma.battery.api.exception.LibraryLoadError`。处置：dynamic-fps 移入 `artifacts/mcfao/incompatible-01/`，`level: "platform"`、`blockedBy: "bundled net.lostluma.battery 2.0.0 (JNI natives, no iOS build)"`。

**pack-74：Xaero 取自身 jar 路径走 `ModContainer.getOrigin`，闭世界里它是桩 → `fetchModFile()` 返回 null。** 构建 `SIGNED_DEVICE_APP`，静态校验同为 88 不可加载、核心类 0 失败。冒烟 F1 在 `game.log:80`，崩溃提前到 `Minecraft.<init>` 阶段（`Entrypoints.startClient` → `WorldMapFabric.onInitializeClient`）：

```
Caused by: java.lang.NullPointerException
	at xaero.map.WorldMap.loadClient(WorldMap.java:152)
	at xaero.map.WorldMapFabric.loadClient(WorldMapFabric.java:86)
	at xaero.map.WorldMapFabric.onInitializeClient(WorldMapFabric.java:45)
	at mcfao.aot.Entrypoints.startClient(Unknown Source)
	at net.minecraft.client.Minecraft.<init>(Minecraft.java:477)
```

`WorldMapFabric.fetchModFile()` 原来是 `ModContainer.getOrigin().getPaths()` → `ContainerMetadata`，闭世界缺这条链时被整体替换成返回 null 的桩，`WorldMap.loadClient` 解引用 null `File`。修法（框架级）：`RuntimeLowering.lowerModFile` 把 `fetchModFile()` 与 `FabricPlatformHelper.getModFile(String)` 改写为 `ModFiles.modFile(GAME_DIR, id)`——按**名义路径** `<gameDir>/mods/<id>.jar` 返回，不依赖 Loader 元数据；新增 `interop/fabric/tool/mcfao/aot/ModFiles.java`（无 Mod 依赖，故始终参与 overlay 编译），`RuntimeOverlayTests` 相应拆开 `ModFiles.java` 与 `GenericVertexSerializer.java` 的编译条件。出货字节码已核对：`fetchModFile` = `getstatic Entrypoints.GAME_DIR; ldc "xaeroworldmap"; invokestatic ModFiles.modFile; areturn`。

**pack-75：Mod 用反射查游戏成员（Xaero 的 `RenderType.create`），闭世界没有这条元数据 —— 新增反射成员扫描器。** 构建仍是 `SIGNED_DEVICE_APP`，静态校验 88/54,125 不可加载、核心类 0 失败、入口点 0 不可加载；F1 在 `game.log:80`，Xaero 的 `loadLaterClientRender` 阶段崩：

```
java.lang.RuntimeException: Xaero's World Map (26.1.2_1.40.16_fabric) has crashed!
  at xaero.map.CrashHandler.checkForCrashes(CrashHandler.java:15)
Caused by: java.lang.ExceptionInInitializerError at xaero.map.graphics.CustomRenderTypes.<clinit>
Caused by: java.lang.NoSuchMethodException:
  net.minecraft.client.renderer.rendertype.RenderType.create(java.lang.String, RenderSetup)
  at xaero.lib.common.reflection.util.ObfuscatedReflectionFabric.getMethodReflection(...)
  at xaero.lib.client.graphics.XaeroRenderType.<clinit>(XaeroRenderType.java:112)
```

`RenderType.create(String, RenderSetup)` 在出货类里是 `public static`（javap 已核对）。Mod 用反射取它是因为同一个 jar 要跨映射集工作；闭世界默认不导出任何成员元数据，`getDeclaredMethod` 于是抛 `NoSuchMethodException`，报错形态与「方法真的不存在」完全一致。修法不是给 Xaero 打补丁，而是补一类普遍缺口：`tools/config_reflection.py` 新增 `member_sites()` + `member_entries()`，扫出货 jar 的字节码，把「class 字面量 + 字符串常量 → 返回 Method/Field 的调用（含 Mod 自己的包装器）」配对成成员元数据；实际只扫 80 / 26,919 个类（先用 `getDeclaredMethod` 等字符串做预筛），在真实 43-mod 包上产出 14 个目标、共 18 条成员，其中就有 `RenderType.create`。pack-76 用它复验。

**pack-76：反射成员元数据生效（`RenderType.create` 不再是阻塞），Xaero 前进到 `loadLaterClientRender`，新阻塞是 Mod 的 `assets/` 从未进入 ResourceManager。** 构建 `SIGNED_DEVICE_APP`（AOT ~11 分钟，`runtimeOverlays.compiled = [ModFiles.java]`、`skipped = [GenericVertexSerializer.java ← sodium]`、`transformed.entrypoints 86`）；静态校验默认 88/54,125 不可加载、核心类 0 失败、**VerifyError 0**、严格成员校验 225 条、入口点 86 个不可加载 0 个；`reflection-config.json` 65 条里含 `net.minecraft.client.renderer.rendertype.RenderType: methods=[create]`。冒烟 F1 在 `game.log:80`，pack-75 的 `NoSuchMethodException` 不再出现，崩溃变成：

```
java.lang.RuntimeException: Xaero's World Map (26.1.2_1.40.16_fabric) has crashed!
Caused by: java.util.NoSuchElementException: No value present
	at java.base@25.0.2/java.util.Optional.get(Optional.java:143)
	at xaero.map.file.OldFormatSupport.loadVanillaStates(OldFormatSupport.java:262)
	at xaero.map.file.OldFormatSupport.loadStates(OldFormatSupport.java:368)
	at xaero.map.WorldMapClientOnly.loadLaterClientRender(WorldMapClientOnly.java:30)
```

字节码显示那一行是 `ResourceManager.getResource(Identifier).get()`，Identifier 是 `xaeroworldmap:vanilla_states.dat`。该文件在出货 jar 里确实存在（`assets/xaeroworldmap/vanilla_states.dat`，144 KB），`-H:ResourceConfigurationFiles` 的 `assets/.*` 也已把它注册进镜像，但**运行期的资源包只有 vanilla 一个**（崩溃报告 `Packs: vanilla`）。同一现象在整份日志里还有旁证：546 条 `Missing model for variant` 全部是 Mod 命名空间（biomesoplenty 等），vanilla 模型正常——即 Mod 的 `assets/`/`data/` 从未作为资源包出现在 `ResourceManager` 里。Fabric 正常是从每个 Mod 的 jar 根建 `ModResourcePack` 并挂进 `PackRepository`；AOT 运行期没有 Mod jar，`ModResourcePackCreator` 也就产出空集。这一条是产品级缺口（不只是 Xaero），下一轮处理。

**pack-77：资源包命名空间修复生效——Mod 模型 JSON 进入反序列化管线，546 条 Missing model 时代结束；新阻塞是运行期 `Class.forName` 的拼接类名。** 构建 `SIGNED_DEVICE_APP`（AOT ~11 分钟）。框架级修复（`RuntimeLowering.lowerVanillaPackBuilder` + 生成 `mcfao/aot.ModNamespaces` 常量类 + `AotExport` 把 95 个 `assets/<ns>/`/`data/<ns>/` 命名空间并进 `VanillaPackResourcesBuilder.build` 的 `Set.copyOf` 处）：出货 jar 里 `build()` 已改写为 `ModNamespaces.withVanilla(...)`，`MultiPackResourceManager` 的 namespaced 索引因此包含全部 Mod 命名空间。静态校验与 pack-76 基线完全一致（默认 88/54,126 不可加载、核心类 0 失败、成员级 225 条、入口点 86 个不可加载 0 个、ImmediatelyFast 早初始化保留、iris 未被排除）。冒烟 F1 在 `game.log:80`，**Xaero 的 `Optional.get` 崩溃与 546 条 `Missing model for variant` 均不再出现**——资源重载真正开始解析 Mod 模型（`ModelManager.loadBlockModels` → Fabric model loading API → mrcrayfish `OpenBlockModel` 反序列化）。新崩溃点在资源重载的 CompletableFuture 里：

```
Caused by: java.util.ServiceConfigurationError: com.mrcrayfish.framework.platform.services.IClientHelper:
    Provider com.mrcrayfish.framework.platform.FabricClientHelper could not be instantiated
Caused by: java.lang.ExceptionInInitializerError
    at com.mrcrayfish.framework.platform.FabricClientHelper.<clinit>(FabricClientHelper.java:22)
Caused by: java.lang.ClassNotFoundException: net.minecraft.client.resources.model.cuboid.CuboidModelElement$Deserializer
    at java.base/java.lang.Class.forName(Class.java:1641)
    at com.mrcrayfish.framework.platform.FabricClientHelper.createBlockElementDeserializerInstance(FabricClientHelper.java:53)
```

`CuboidModelElement$Deserializer.class` 就在出货 jar 里；`Class.forName` 失败是因为闭世界只对注册进反射配置的类回答按名查找。mrcrayfish framework 用 `X.class.getName() + "$Deserializer"`（`makeConcatWithConstants` 拼接）拿到嵌套类名——**字节码里既没有这个字符串常量也没有嵌套类的字面量**，pack-75/76 的成员扫描器看不见这类调用点。修法仍是框架级扫描器：`tools/config_reflection.py` 新增 `forname_sites()`（配 `bootstrap_recipes()` 解析 `makeConcatWithConstants` 配方常量，`class_shape` 延迟 Code 扫描到类级 BootstrapMethods 解析之后），把「类字面量 `getName` + 单占位符配方 → `Class.forName`」「字符串字面量 → `Class.forName`」两种形态都登记为 `allDeclaredConstructors` 反射条目。在真实 43-mod jar 上新增 17 条注册（`CuboidModelElement$Deserializer`、Xaero 会话类、ambientsounds、clothconfig、ferritecore、kotlin 协程内部类、twelvemonkeys webp 等）。顺带修掉 `_instruction_length` 对 `tableswitch` 头部长度少算 4 字节的潜伏 bug（此前只扫含成员反射提示词的类，litematica 的 `forName` 提示词首次触发它）。回归：`tests/test_config_reflection.py` 新增 `ForNameScanTests` 6 项。pack-78 复验。

**pack-78：`Class.forName` 拼接类名修复生效——mrcrayfish 服务实例化成功，游戏首次进入 GUI 渲染循环；新阻塞在 Metal 着色器预载契约。** 构建 `SIGNED_DEVICE_APP`；`reflection-config.json` 82 条（65 基线 + 17 条 `forName` 新增，`CuboidModelElement$Deserializer`、Xaero 会话类、clothconfig、ferritecore、kotlin 协程内部类等）。静态校验与基线一致（默认 88/54,126、成员级 225、核心 0 失败、入口点 86 个不可加载 0 个）。冒烟 F1 在 `game.log:80`，`FabricClientHelper` 的 CNFE 与 `ClientServices.<clinit>` 连锁消失；资源重载继续推进到**模型烘焙**（`Missing texture references in model backpacked:...` 等 Mod 模型警告），Xaero/Jade/ambientsounds 初始化完成，`[Metal] TEXTURE_FRAME_PRESENTED` 出现。新崩溃点在渲染循环：

```
java.lang.IllegalStateException: Shader source unavailable before preload: minecraft:pipeline/gui vertex
	at fabricaot.metal.ShaderIndex.verifyStage(ShaderIndex.java:72)
	at fabricaot.metal.ShaderIndex.program(ShaderIndex.java:51)
	at fabricaot.metal.MetalDevice.precompilePipeline(MetalDevice.java:85)
	at fabricaot.metal.MetalRenderPass.setPipeline(MetalRenderPass.java:27)
	at net.minecraft.client.gui.render.GuiRenderer.executeDraw(GuiRenderer.java:481)
```

判定要点：`MetalDevice.precompilePipeline:85` 是**缓存全 miss 后的全新编译路径**（`pipelineInstances` 按实例、`pipelines` 按 `MetalPipeline.Key`）；`ShaderIndex.program` 里 bundle 条目存在（否则抛 `Rebuild required`）、metallib 指纹匹配，但 `defaultShaderSource.get(vertexShader)` 返回 null 且 `verifiedSources` 不含该程序 key。`defaultShaderSource` 是 `Minecraft` 构造器里 `createDevice` 时传入的 `Minecraft::getShader`‑类委托，**首次重载完成前恒为 null**；唯一允许此时绘制的路径是 `GameRenderer.preloadUiShader(vanillaPackResources.asProvider())` 预编译并登记的 `GUI`/`GUI_TEXTURED`/`TRACY_BLIT`。因此触发条件是「缓存被 `GpuDevice.clearPipelineCache()` 清空（唯一调用方是 `ShaderManager.apply`）后，某个未在预载集合内的管线先被绘制」。`ShaderManager.apply` 的字节码顺序为：清缓存 → 用新 `CompilationCache` 预编译全部静态管线（失败收集 → 再清缓存并抛 `RuntimeException`）→ 换缓存。若该循环中途抛异常，缓存会停在空中状态，下一帧 GUI 绘制即命中本节崩溃。为拿到现场事实（而不是继续推演），pack-79 给 `MetalDevice`/`ShaderIndex` 加了 `[MCFAO_SHADER]` 诊断：清理点调用栈、全新编译的管线名与源类型、bundle 缺条目时的管线名、缺源时的 verified/allow 状态；同时把 `libfaot_metal.dylib` + `metal-backend.jar` 由 `metal-sim-24`/`metal-ios-world-04` 取代（`artifacts/mcfao-local.json` 的 `metal` 已指向后者，模拟器图形输入新建 `world-simulator-input-03`）。

**pack-80：管线 bundle 门禁生效——首次在同一轮里同时拿到 F1、`Dev joined the game` 与 F3；新阻塞是 Lithium 类分析反射。** 构建 `SIGNED_DEVICE_APP`（AOT ~14 分钟），`fabric` 报告的 `staticAdaptations` 里出现 `net/minecraft/client/renderer/RenderPipelines#register = BundledPipelines.register(byLocation, pipeline)`，即门禁确实进入了出货字节。静态校验：默认 88/54,127 不可加载（基线不变，新增 1 个类来自 `BundledPipelines`）、成员级 225/54,127、入口点 86 个不可加载 0 个。

模拟器冒烟（`artifacts/mcfao/fabric-pack-80-simulator/`，图形输入 `world-simulator-input-04` = `world-simulator-input-03` + `metal-sim-25/libfaot_metal.dylib`）里门禁按设计工作，8 条 malilib 管线被拒（`game.log:75-82`）：

```
[MCFAO_SHADER] dropped pipeline malilib:pipeline/legacy/solid vertex=malilib:legacy_terrain ...
[MCFAO_SHADER] dropped pipeline malilib:pipeline/legacy/wireframe ...
（其余 legacy/cutout、solid/masa/offset、wireframe/offset、cutout/offset、translucent、translucent/offset）
```

`ShaderManager.apply` 的预编译循环不再被它们炸掉，进度因此跨过了此前所有轮次的行数：

| 事实 | 位置 |
| --- | --- |
| `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS` | `game.log:88` |
| 首个 GUI 帧呈现 `[Metal] TEXTURE_FRAME_PRESENTED 2622x1206` | `game.log:645` |
| `Dev joined the game` | `game.log:758` |
| `MCFAO_F3_CLIENT_WORLD_JOIN_PASS` | `game.log:917` |

三个判据首次在同一轮里齐现，但**同一秒内**客户端崩溃，因此不构成 PASS：

```
java.lang.AssertionError
	at net.caffeinemc.mods.lithium.common.entity.EntityClassGroup.<clinit>(EntityClassGroup.java:41)
	at net.caffeinemc.mods.lithium.common.world.WorldHelper.getEntitiesForCollision(WorldHelper.java:45)
	at net.caffeinemc.mods.lithium.common.entity.LithiumEntityCollisions.doesBoxCollideWithHardEntities(...)
	at net.minecraft.world.level.Level.noCollision(Level.java:4575)
	at net.minecraft.client.player.LocalPlayer.resetPos(LocalPlayer.java:776)
	at net.minecraft.client.multiplayer.ClientPacketListener.handleLogin(ClientPacketListener.java:560)
```

根因在 `EntityClassGroup` 的类初始化自检：`CUSTOM_COLLIDE_LIKE_MINECART_BOAT_WINDCHARGE.contains(Minecart.class, EntityType.MINECART)` 必须为真，而求值器是 `ReflectionUtil.hasMethodOverride(clazz, Entity.class, true, "canCollideWith", Entity.class)` —— 它沿父类链调 `Class.getDeclaredMethod` 并捕获 `NoSuchMethodException` 当作「本类没有覆盖」。闭世界对**未注册**的方法一律抛 `NoSuchMethodException`，于是所有实体都被判成「没覆盖」，自检必然失败。同一处还有 `canHitEntity`/`canBeHitByProjectile`/`isPickable`/`isPushable`/`onClimbable`/`canBeCollidedWith` 六个查询名。修法与 pack-64/77 同源：`tools/config_reflection.py` 新增 `override_entries()`，按扫描到的字节码只登记**真正声明了这些方法**的类（本轮 32 个类 / 58 条方法，含 `AbstractMinecart#canCollideWith`、`AbstractBoat`、`AbstractWindCharge`、`Entity` 自身），其余类继续得到真实的 `NoSuchMethodException`，语义不变。pack-81 复验。

非致命遗留（本轮未处理，先记账）：`ServerPlayer` 保存时 mrcrayfish backpacked 的 `AbstractProperty.get` 抛 `IllegalStateException: Config property is not linked yet`（`game.log:830`），出现在崩溃后的 `stopServer` 存盘路径；以及离线账户 `401`、`oshi` 报 `Operating system not supported: Unknown` 的崩溃报告硬件段落。

**pack-81：Lithium 类分析反射修复生效——F1、`Dev joined the game`、F3 依次出现，崩溃推迟到玩家 tick 的框架配置。** 构建 `SIGNED_DEVICE_APP`（AOT ~11 分钟）；`configurationReflection` 96 条（pack-80 的 82 + `override_entries()` 新增 14 类 / 58 条方法，含 `net.minecraft.world.entity.vehicle.minecart.AbstractMinecart`）。静态校验与基线一致（默认 88/54,127、成员级 225/54,127、入口点 86 个不可加载 0 个）。

模拟器冒烟（`artifacts/mcfao/fabric-pack-81-simulator/`）：`game.log:88` 出 F1、`game.log:694` 出 `Dev joined the game`、`game.log:855` 出 F3——`EntityClassGroup.<clinit>` 的 `AssertionError` 消失。随后崩溃换成 `Description: Ticking player`：

```
java.lang.IllegalStateException: Config property is not linked yet
	at com.mrcrayfish.framework.api.config.AbstractProperty.get(AbstractProperty.java:100)
	at com.mrcrayfish.backpacked.inventory.ManagementInventory.getMaxEquipable(ManagementInventory.java:98)
	at net.minecraft.world.entity.player.Player.handler$zbp001$backpacked$TickHead(Player.java:3310)
	at net.minecraft.server.network.ServerGamePacketListenerImpl.tickPlayer(ServerGamePacketListenerImpl.java:330)
```

同一异常在 pack-80 的 `stopServer` 存盘路径里已出现过一次（当时按非致命遗留记账），现在证明它会打死整个 tick。根因链：`FabricConfigHelper.getAllFrameworkConfigs()` 遍历 `FabricLoader.getInstance().getAllMods()`，逐个读 `fabric.mod.json` 的 `framework.configs`（字符串类名）→ `Class.forName` → `getDeclaredFields()` 找 `@FrameworkConfig` 字段 → `field.get(null)`；闭世界把 `getAllMods()` 折叠成空集合（没有 Mod jar 可枚举），于是 `FrameworkConfigManager.configs` 为空，backpacked 的 5 个配置（`CLIENT`/`BACKPACK`/`PICKPOCKETING`/`WANDERING_TRADER`/`AUGMENTS`）一条都没登记，`AbstractProperty.proxy` 恒为 null。修法：在导出期枚举出货字节里所有 `@FrameworkConfig` 静态字段（标注 id/name/readOnly/type/separator 全部取自字段自身的 RuntimeVisibleAnnotations），生成 `mcfao.aot.FrameworkConfigs`（`Pair.of(注解实例, GETSTATIC 配置字段)` 常量表）+ `mcfao.aot.FrameworkConfigAnnotation`（普通类实现该注解接口），把 `getAllFrameworkConfigs()` 整体改写为表查询；反射侧由 `framework-config-roots.json` 驱动，为配置根类及其 `$` 嵌套组登记 `allDeclaredFields`，让框架自己的 `ConfigScanData.scan` 仍按原逻辑链接属性。pack-83 复验（pack-82 的改写挂错了类处理循环，见 `docs/FABRIC_AOT.md` 的「pack-82 的一次空转」）。

**pack-83：框架配置发现修复生效——backpacked 的 `Config property is not linked yet` 消失，崩溃换到 Gson 配置类。** 构建 `SIGNED_DEVICE_APP`（AOT ~18 分钟）；`fabric` 的 `staticAdaptations` 首次出现 `com/mrcrayfish/framework/platform/FabricConfigHelper#getAllFrameworkConfigs = FrameworkConfigs.all()`，`frameworkConfigs` 列出 `com/mrcrayfish/backpacked/Config` 的 `CLIENT`/`BACKPACK`/`PICKPOCKETING`/`WANDERING_TRADER`/`AUGMENTS` 五条。静态校验：默认 88/54,129 不可加载、成员级 225/54,129、入口点 0 个不可加载。

模拟器冒烟（`artifacts/mcfao/fabric-pack-83-simulator/`）三个判据齐全：

| 事实 | 位置 |
| --- | --- |
| `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS` | `game.log:88` |
| `[Metal] TEXTURE_FRAME_PRESENTED 2622x1206` | `game.log:612` |
| `Dev joined the game` | `game.log:694` |
| `MCFAO_F3_CLIENT_WORLD_JOIN_PASS` | `game.log:731` |

11 秒后崩在实体 tick：

```
java.lang.NullPointerException: Ticking entity
	at traben.entity_texture_features.config.ETFConfig.canDoCustomTextures(ETFConfig.java:98)
	at net.minecraft.world.entity.animal.squid.GlowSquid.modify$zen001$entity_texture_features$mixin(GlowSquid.java:528)
	at net.minecraft.world.entity.animal.squid.GlowSquid.aiStep(GlowSquid.java:90)
```

现场取证：模拟器容器里的 `config/entity_texture_features.json` 只有 **2 字节 `{}`**（`etf_warnings.json`、`modmenu.json`、`transition.json`、`trender.json` 同样是空的）。反汇编确认 `ETFConfig.canDoCustomTextures` 第 98 行是 `entityRandomOverrides.isEmpty()`，而该字段在构造器里 `new`；`new ETFConfig()` 却确实执行过（`TConfigHandler` 构造器调 `supplier.get().getClass()` 拿类型）。结论：**配置对象被 Gson 用 `sun.misc.Unsafe` 重新分配、绕过了构造器**，同时 `Gson.toJson` 也看不到字段（所以写出来是 `{}`）。闭世界里 `ETFConfig` 既没有构造器元数据也没有字段元数据，两个方向一起坏：第一次启动落盘空对象，第二次启动读回一个全 null 的实例。修法：`tools/config_reflection.py` 新增 `json_config_roots()`，按两种**结构信号**（不看类名清单）挑出 Gson 必须反序列化的配置类——(a) 同一个类里既出现 `X.class` 字面量又用 `X::new` 工厂句柄（NoChatReports 的 `loadConfig(Class, Supplier, String)`、CreativeCore 的包注册表）；(b) 声明了 `TConfigHandler` 字段（ETF 的两个配置都由 `ETF` 经 supplier 建出、由 handler 构造器反射取类型）。两处都走现成的 `config_entries()` 传递闭包，为种子类及其同包字段类型登记 `allDeclaredConstructors` + `allDeclaredFields`；本轮在 43-mod 包上新增 13 个根（ETF 2、NoChatReports 3、CreativeCore 8），反射条目 133 → 142。顺带修掉常量池解析把 `CONSTANT_MethodHandle`（tag 15）只跳过不保存的旧缺陷——不修则工厂句柄对扫描器完全不可见。pack-84 复验。

**pack-84：Gson 配置元数据修复生效——ETF 的 `canDoCustomTextures` NPE 消失，世界真正加载完成；新阻塞是 Xaero World Map 的 OpenGL 依赖。** 构建 `SIGNED_DEVICE_APP`；`reflection-config.json` 133 → 156 条（新增 ETF 两个配置、NoChatReports 三个配置、CreativeCore 八个包类，以及它们的同包传递闭包）。静态校验：默认 88/54,129、成员级 225/54,129（与基线一致）。

模拟器冒烟（`artifacts/mcfao/fabric-pack-84-simulator/`）：F1 `game.log:88`、`TEXTURE_FRAME_PRESENTED` `:612`、`Dev joined the game` `:693`、F3 `:700`，日志里不再出现 `Config property is not linked yet`，`EntityClassGroup` 与 `ETFConfig` 两处崩溃都消失。崩溃换到世界渲染的第一帧：

```
java.lang.RuntimeException: Xaero's World Map (26.1.2_1.40.16_fabric) has crashed!
	at xaero.map.CrashHandler.checkForCrashes(CrashHandler.java:15)
	at xaero.map.MapProcessor.onRenderProcess(MapProcessor.java:562)
Caused by: java.lang.UnsatisfiedLinkError: Can't load library: .../Frameworks/liblwjgl_opengl.dylib
	at org.lwjgl.opengl.GL.<clinit>(GL.java:74)
	at xaero.map.MapLimiter.determineDriverType(MapLimiter.java:38)
```

`MapLimiter.determineDriverType` 每帧调 `GL11C.glGetString` 估算 VRAM；jar 里 8 个类绑定 `org/lwjgl/opengl/GL`（`MapLimiter`、`OpenGlHelper`、`TextureUploader`、`PixelBuffers`、`PNGExporter`、`TextureUploadBenchmark`、`Misc`、`OpenGLException`），地图区域纹理本身就走 GL 对象。这与 Sodium 是同一堵墙（[FABRIC_AOT](FABRIC_AOT.md) 的「平台级不兼容」一节、`artifacts/mcfao/incompatible-01/result.json` 的 `sodium` 条目），不是缺元数据也不是可达性问题。处置：jar 原样移入 `artifacts/mcfao/incompatible-01/`，在 `result.json` 里按 `level: platform` 记账（`blockedBy`、字节码证据、`reconsiderWhen` 与 Sodium 条目同格式）。Xaero 的小地图不依赖 world map 的 mod id，继续留在验证包里。

**pack-85：移除 Xaero World Map 后世界首次完整加载（`ClientLevelReady`），阻塞推进到 Metal 渲染通道生命周期。** 构建 `SIGNED_DEVICE_APP`（42 个 mod）；静态校验默认 86/53,742、成员级 219/53,742（比 pack-84 各少 2 是因为少了一个 mod，不是回归）。同一轮还把 JSON 配置的传递闭包从「同包」放宽到「Mod 自己的命名空间」：`serialization_roots` 与 `json_config_roots` 都按开放根处理，`PLATFORM_PREFIXES` 之外的字段类型全部跟进（43-mod 包上反射条目 142 → 150），AmbientSounds 的 `environment/pocket/AirPocketGroup` 因此拿到 `allDeclaredFields`/构造器。

模拟器冒烟（`artifacts/mcfao/fabric-pack-85-simulator/`）：F1 `:88`、帧呈现 `:599`、`Dev joined the game` `:680`、F3 `:717`；心跳显示 `tracker=ClientLevelReady`、`chunkDecoded=271`、`clientPositions=1`——**世界首次在客户端真正就绪**。11 秒后崩在 GUI 渲染：

```
java.lang.IllegalStateException: Close the existing render pass before creating a new one!
	at com.mojang.blaze3d.systems.CommandEncoder.clearColorAndDepthTextures(CommandEncoder.java:77)
	at net.minecraft.client.gui.render.GuiItemAtlas.<init>(GuiItemAtlas.java:64)
	at net.minecraft.client.gui.render.GuiRenderer.prepareItemAtlas(GuiRenderer.java:396)
```

`CommandEncoder.clearColorAndDepthTextures` 的第一条指令就是 `backend.isInRenderPass()`，为真即抛。我们的 `MetalCommandEncoder.isInRenderPass()` 返回 `device.activePass != null`，所以是**通道槽位残留**。泄漏源在同一帧更早的位置：`renderBlockOutlineOverlapping(): Draw Exception; Rebuild required for shader variant: malilib:pipeline/debug_lines/masa_simple/lequal_depth`（`game.log` 大约 `816` 行）——门禁把 malilib 的 8 条管线挡在 `PIPELINES_BY_LOCATION` 外，但 Mod 自己持有 `RenderPipeline` 对象，仍会在自己的通道里 `setPipeline`，`MetalRenderPass.setPipeline` 于是抛 `UnsupportedOperationException`，异常被 malilib/vanilla 的绘制循环吞掉，`close()` 没跑到，`device.activePass` 留在原地。修法两条，都在 `compiler/metal-backend`：`setPipeline` 先问 `BundledPipelines.supports()`，不支持就把这条通道标记成 `skipped` 并让 `draw`/`drawIndexed` 直接返回（Mod 的绘制按设计被丢弃，不再抛）；`MetalRenderPass.close()` 改成无条件释放 `device.activePass`、收尾 debug group、`endPass`，即使设备此前已报错也不会把槽位钉死。`libfaot_metal.dylib` 的二进制哈希不变（改动全在 Java 侧），所以模拟器图形输入仍用 `world-simulator-input-04`；`artifacts/mcfao-local.json` 的 `metal` 指向新建的 `metal-ios-world-06`（`metal-sim-26` 供模拟器侧复现）。pack-86 复验。

**pack-86：通道槽位修复生效——不再有 `Draw Exception`，阻塞换成 Xaero 小地图的 AWT/ImageIO。** 构建 `SIGNED_DEVICE_APP`；AOT 输入确认指向 `metal-ios-world-06`。静态校验 86/53,742、成员级 219/53,742（与 pack-85 一致，说明后端 Java 改动没有改变链接面）。

模拟器冒烟（`artifacts/mcfao/fabric-pack-86-simulator/`）：F1 `:88`、帧呈现 `:568`、`Dev joined the game` `:649`、F3 `:654`。日志出现 `[MCFAO_SHADER] skipping draws for unsupported pipeline malilib:pipeline/debug_lines/masa_simple/lequal_depth`（`:834`）和 xaerolib 的 5 条管线（`:1363-1367`），`close` 之前那条 `renderBlockOutlineOverlapping(): Draw Exception` 与 `Close the existing render pass` 一起消失——说明「不支持就不画」这条路走通了。11 秒后新阻塞：

```
java.lang.RuntimeException: Xaero's Minimap has crashed!
	at xaero.hud.minimap.Minimap.checkCrashes(Minimap.java:73)
Caused by: java.lang.UnsatisfiedLinkError: Can't load library: awt | java.library.path = [.]
	at java.awt.Toolkit.loadLibraries(Toolkit.java:1293)
	at javax.imageio.spi.IIORegistry.getDefaultInstance(IIORegistry.java:121)
	at javax.imageio.ImageIO.<clinit>(ImageIO.java:61)
	at xaero.common.minimap.write.MinimapWriter.loadBlockColourFromTexture(MinimapWriter.java:1745)
```

`MinimapWriter` 靠 `ImageIO` 从 PNG 采样方块颜色来生成地图瓦片，`writeChunk → writeTile → loadBlockColor → calculateBlockColors → loadBlockColourFromTexture` 在每次接近新区块时都会跑。iOS native image 里 `java.desktop` 只有字节码、没有 `libawt`，`Toolkit.<clinit>` 的 `System.loadLibrary("awt")` 必然失败——与 Xaero World Map 的 OpenGL 一样是平台级不兼容，但撞的是另一堵墙（前者要 GL，后者要 AWT）。处置：jar 原样移入 `artifacts/mcfao/incompatible-01/`，按 `level: platform` 记账。验证包剩 41 个 mod。

顺带核对剩余 41 个包里的同类引用（避免一轮一轮撞墙）：`ftb-library`(awt 2/imageio 2)、`malilib`(awt 4)、`yacl`(awt 14/imageio 1)、`libIPN`(awt 1)、`minihud`(awt 1) 都只是引用、启动路径未触碰；`ImmediatelyFast` 的两处 `org/lwjgl/opengl/GL` 在 `SignAtlasRenderTarget`（告示牌文本图集），只有渲染告示牌时才会走到——本轮的测试存档里没有告示牌，属于**已知潜伏项**，一旦出现告示牌渲染崩溃先查这里。

**pack-87：整合包首次在模拟器完整进世界并通过冒烟（`SIMULATOR_WORLD_SMOKE_PASS`）——判据 F1 + F3 + `Dev joined the game` 全中，无任何新崩溃点。** 构建 `SIGNED_DEVICE_APP`（41 个文件 = 40 个第三方 jar + `mcfao-fixture.jar`，与 pack-86 同一输入集，属于「无新修复的一轮复验」）；静态校验默认 82/52,725、成员级 206/52,725，与 pack-86 完全一致，说明移除两个 Xaero 之外没有任何链接面变化。

模拟器冒烟（`artifacts/mcfao/fabric-pack-87-simulator/`，`result.json.status = SIMULATOR_WORLD_SMOKE_PASS`）：F1 `game.log:88`、`TEXTURE_FRAME_PRESENTED 2622x1206` `:553`、`Dev joined the game` `:634`、F3 `:635`；日志共 1290 行，`Minecraft Crash Report` / `Game crashed` / `has crashed` 命中数为 **0**。`world.png`（1.13 MB）显示真实地形帧：方块纹理与植被清晰、物品栏 9 格有物品、左右触屏控件（方向键 `Break`/`Place`/`Items`/`Jump`/`Pick`）与左上坐标覆盖层（`x 45.66 z -133`、`Facing: SOUTH`）都在正确位置，没有花屏或未初始化纹理。该帧天空为纯黑（服务器时间是夜间），天穹/云是否缺失尚不能从单帧判断，留作视觉待观察项。日志侧确认这是新建世界：`ServerLevel[New World]`、`Preparing spawn area: 100%`，三个维度都注册了 TerraBlender（`overworld`/`the_nether`/`the_end`）。

这意味着**闭世界适配在「整合包能跑到真实进世界且不崩」这条线上的阻塞已经清空**，剩下的都不是崩溃：
- 逐 Mod 的 `FUNCTION_PASS` 还没有功能证据（当前 114 个 `BUILD_PASS`、13 个 `BLOCKED`，`FUNCTION_PASS` 仍为 0）——需要按 Mod 造功能探针或截图断言，不能凭「整包进世界」升级状态。
- 13 个 `BLOCKED` 分三类：导出期静态拒绝 6 个、平台级隔离 7 个（Sodium 家族 3 + Iris + dynamic-fps + Xaero World Map + Xaero Minimap）。
- 真机 `C1/C2` 与 Gate D 的 IPA/安装/存档保留证据仍未做（`result.json` 里 `deviceRun = NOT RUN`），按用户约定只用模拟器验证，不越界宣称真机可玩。

同时修掉一处**矩阵工具的自欺**：`tools/generate_mod_matrix.py` 的 `smoke_evidence()` 在没有 fatal section 时会退化成「取日志里第一条 Exception」，于是在健康的 pack-87 日志上把启动期的 `oshi` 噪声（`java.lang.UnsupportedOperationException: Operating system not supported: Unknown`，日志第 20 行、每次启动都打印）写成了「首个崩溃」。现在两层收紧：`BENIGN_NOISE` 过滤 `oshi`/离线认证 401/Realms/`Missing model`；且当 `result.json.status` 以 `_PASS` 结尾时不再做退化取值——没崩就是没崩。渲染段里两处硬编码也随之改成按标记判定：判据全中时输出「未出现致命崩溃」与「Gate C / D（模拟器口径）：判据已全中」，未全中时才回到 `BLOCKED / NOT RUN`。新增回归 `test_a_passing_smoke_never_reports_startup_noise_as_a_crash`，`tests/test_mod_matrix.py` 5 项全绿。

`docs/MOD_COMPATIBILITY_MATRIX.md` 由 `python3 -B tools/generate_mod_matrix.py --build artifacts/mcfao/fabric-pack-87` 重新生成：127 行、114 `BUILD_PASS`、13 `BLOCKED`、41 个根 jar、91 个资源命名空间。


**pack-88：给派发循环加逐入口点打印，矩阵的 `LOAD_PASS` 从 0 变成 58。** 这一轮不改运行语义，只补证据面：`AotExport.emitEntrypointDispatched()` 在每条入口点回调**返回之后**打印 `[MCFAO_ENTRYPOINT] mod=<id> stage=<main|client> class=<definition>`。打印位置就是契约——抛异常的初始化器走不到这行，所以「有这行」等价于「该 Mod 的初始化跑完了」。

构建 `SIGNED_DEVICE_APP`；静态校验默认 82/52,725、成员级 206/52,725，与 pack-87 逐位相同（只多了日志，没有新的链接面）。模拟器冒烟（`artifacts/mcfao/fabric-pack-88-simulator/`）：`SIMULATOR_WORLD_SMOKE_PASS`，F1 `:159`、`TEXTURE_FRAME_PRESENTED 2622x1206` `:637`、`Dev joined the game` `:763`、F3 `:767`；日志 1354 行、崩溃报告 0；`world.png` 1.18 MB 仍是可用的地形帧。派发标记 83 行、覆盖 56 个 Mod，**与 `transform.entrypoints` 的 83 条逐条对齐、缺失 0**——说明派发覆盖是完整的，不必怀疑有 Mod 被悄悄跳过。

顺带把「为什么还有 62 个 Mod 静默」也查清了：它们没有 `main`/`client` 入口点（`ferritecore` 这类纯 Mixin 库，以及 `fabric-api` 的子模块、Kotlin 运行时），另有 43 条**自定义阶段**入口点被 `optionalEntrypointsSkipped` 记录在案——`biomesoplenty` 的 `glitchcore`/`terrablender` 两条由 provider Mod 自己派发，`creativecore` 的 `modmenu` 一条由 ModMenu 派发。这些走不进 `startClient`，所以永远不会有派发标记；`biomesoplenty` 之所以还能拿到 `LOAD_PASS`，靠的是它自己打的 `Registered region biomesoplenty:...`。

工具侧新增 `tools/scan_mod_evidence.py`（+`tests/test_scan_mod_evidence.py` 8 项）：按 `class`/`name`/`namespace`/`id` 四级取证据、只认 `INFO`/`STDOUT`，裸 id 命中不算（`Builtin shader registered` 会被 `shader` 这种短 id 命中）。`--emit-evidence` 只补空位不覆盖人工判定。矩阵由 107 `BUILD_PASS` / 7 `LOAD_PASS` 变成 **56 `BUILD_PASS` / 58 `LOAD_PASS` / 13 `BLOCKED`**（127 行不变）。全量测试 274 项 PASS。

`FUNCTION_PASS` 仍是 0，且这一轮的日志里也没有能升级它的东西：Jade 的方块提示要求准星对准方块（截图里没有提示框）、IPN/IAS 这类要开界面才能看到。下一步要给冒烟加交互脚本（对准方块、开背包、看配方），否则只能靠截图猜。

## pack-89 → 92：交互探针打通、Jade 元数据改写落地（2026-11-12 下午）

pack-88 之后工作重心从「找下一个崩溃」转成「让探针真正在游戏里交互」，因为 `FUNCTION_PASS` 必须靠交互证据。四轮构建各自清掉一个探针才会撞到的问题：

**pack-89：`glfwGetMouseButton` 只有回调、没有轮询状态。** `WorldUITests/testFabricModFunctions` 一旦按下前键，malilib 的 `KeybindMulti.isKeyDown` 就会每 tick 轮询 `glfwGetMouseButton`，而 GLFW-lite 只实现了事件回调，Overlay 把未实现的 API 换成 `UnsupportedOperationException`。修法是 native 侧补 `mouseButtons[8]` 轮询表（注意 `uikit_surface.m` 把 action 放在 `e.b`）、失焦清零，并让 supported 列表继续由 `nm -gUj` 自动派生。重建链 `glfw-sim-10`/`glfw-ios-05` → `lwjgl-sim-14`/`lwjgl-ios-world-02` → `metal-sim-27`/`metal-ios-world-07`，staged 输入为手工拼的 `world-simulator-input-05`（来源哈希写在其 `result.json`）。冒烟仍 `SIMULATOR_WORLD_SMOKE_PASS`。

**pack-90：Mixin 合成内部类没进镜像。** 探针第二次跑崩在 `NoClassDefFoundError: net/minecraft/world/item/CreativeModeTabs$1CreativeModeTabPosition$0e98f8…`（Sponge Mixin 的 `InnerClassGenerator` 用 `UUID.nameUUIDFromBytes` 生成 `target$1Inner$<32hex>`，惰性产出字节码）。`AotExport` 原来只认 `$Anonymous$<hex>` 形式，改为同时认 `$<32hex>` 后缀并随包出货，`syntheticShipped` 里能看到该类。冒烟 PASS。

**pack-91：Jade 修复的三个缺陷（该轮包无效）。** 为了让 Jade 的 tooltip 不再走 `FabricLoader → ModContainer → ModMetadata`，这一轮加了 `RuntimeLowering.lowerLoaderMetadata`，但：① 钉的 `JADE_CLIENT_PROXY_SHA256` 是错的，审计拒绝后 **Jade 整个 Mod 被排除出包**（`excludedMods.jade = Unaudited …`，镜像里少了 409 个 `snownee/` 类 + 53 个资源）；② 写的是 `ALOAD 1`，而 `getModName(String id, boolean modMenu)` 的局部变量 1 是 boolean，参数应是 `ALOAD 0`；③ 生成的 `Entrypoints` 类里根本没有 `optionalModName` 方法；④ 还把 `maxStack` 从 5 覆盖成 1（保留下来的 I18n 分支需要 5）。四个问题里前一个恰好把后三个挡住了——哈希不匹配让改写根本没执行。

**pack-92：四处修复 + 真实字节码验证。** 哈希改为真实值 `1e4f1456…`（`Jade-mc26.1-Fabric-26.1.0.jar` 里的 `snownee/jade/util/ClientProxy.class`）；`ALOAD 0`；`AotExport` 补生成 `optionalModName(String)Optional`（未知 id 返回 `Optional.empty()`，与 Loader 一致，Jade 自己会 filter 掉）；不再改 `maxStack/maxLocals`，只清掉以被删标签结尾的 `localVariables`。验证不是只看单测：用真实 `ClientProxy.class` 跑改写，输出 `MAXSTACK = 5`、无任何 `net/fabricmc/loader` 引用、表调用前是 `ALOAD 0`、可重新序列化。`LoaderMetadataProbe` 也补了「必须用局部变量 0」「不得改 frame size」「不得留悬空 local-variable 表」三条断言。

`artifacts/mcfao/fabric-pack-92/result.json` → `SIGNED_DEVICE_APP`，`staticAdaptations` 里能看到 `snownee/jade/util/ClientProxy#getModName(String,boolean) fallback = mcfao/aot/Entrypoints.optionalModName`，`excludedMods` 只剩 `entity_model_features` 与 `net_lenni0451_reflect`。

**pack-92 冒烟与功能探针均通过。** `artifacts/mcfao/fabric-pack-92-simulator/result.json` → `SIMULATOR_WORLD_SMOKE_PASS`：F1 `game.log:159`、`TEXTURE_FRAME_PRESENTED 2622x1206` `:377`、`Dev joined the game` `:1010`、F3 `:1014`，1787 行日志、崩溃报告 0、83 条 `[MCFAO_ENTRYPOINT]`（与 `transform.entrypoints` 逐条对齐）。Jade 两条入口点 `:80`/`:155` 派发完成，`:332-334` 加载 `CorePlugin`/`VanillaPlugin`/`UniversalPlugin`。随后功能探针 `SIMULATOR_FUNCTION_PROBE_PASS`（`fabric-pack-92-simulator/probe/result.json`，7 张截图）：对准沙地时 Jade 提示框显示 `Sand` + 蓝色 `Minecraft`（`probe-aim-down_0_….png`），创造物品栏悬停显示 `Service Door` + `Minecraft`（`probe-inventory_0_….png`）——这是 `FUNCTION_PASS` 的第一条，矩阵升到 56 `BUILD_PASS` / 57 `LOAD_PASS` / 1 `FUNCTION_PASS` / 13 `BLOCKED`。顺带修了探针工具的一处自欺：`xcresulttool` 把附件导出成 UUID 文件名，原来的「缺附件」检查拿 UUID 去匹配测试标签，7 张图全被判缺失；现在按 `suggestedHumanReadableName` 还原成 `probe-*` 名字（+2 项回归）。

**未签名 IPA（Gate D2 的导出半边）。** 新增 `tools/package_unsigned_ipa.py`（+4 项回归测试）：核对 `.app` 与 `appFilesSHA256` 逐字节一致后，删 `_CodeSignature`/`embedded.mobileprovision`/各 Mach-O 的 LC_CODE_SIGNATURE，按 `Payload/` 打包，并拒绝 `__MACOSX` 资源叉条目。产物 `artifacts/mcfao/fabric-pack-92-unsigned-ipa/C0Harness-unsigned.ipa`，602,702,176 字节，sha256 `502c6b8c…`，arm64 / iOS 17.0 / 无签名。**它没有在任何设备上运行过（`deviceRun = NOT RUN`），Gate D 的安装与存档保留仍为 NOT RUN**——导出一份 IPA 不等于 D2 通过。IPA 用的是 device 构建，而冒烟/探针跑的是同一 AOT 镜像的模拟器产物，两者不等价。

## 2026-11-12 TechReborn 模组查询接口修复

用户首包真机在 `RebornCoreClient:81` 因查询被置空失败。现用构建期 `ModCatalog` 快照返回真实存在的容器及名称/版本/资源根目录，保留 Fabric 内置包注册行为。285 项回归通过，`artifacts/mcfao/techreborn-interface-build-02` 为 `SIGNED_DEVICE_APP`，模组未被排除。模拟器 RebornCore/TechReborn client 入口返回，但随后在 MTLSimDriver/XPC 提交中 signal 6，世界烟测不通过；修复版真机 NOT RUN。通用能力缺口与实现顺序见 [玩法模组适配路线](MOD_ADAPTATION_PLAN.md)。

修复版签名 IPA 已导出并验签：`artifacts/mcfao/techreborn-interface-signed-ipa-01/export/FabricAOT World.ipa`（470,792,773 字节，SHA-256 `a27a4b43b3a081458f137a6e39ba51b100055772c7edae98f7af7a548d5cfb6e`）。该包供用户真机复验接口修复；不得据导出成功提升玩法兼容状态。

## 2026-11-13 内容样本集与 Loader 快照扩展

已生成 26.1.2 Fabric 内容样本 mrpack：TechReborn、BetterEnd、BetterNether、Biomes O’ Plenty、YUNG’s Better Dungeons，共 12 个根 JAR、80 个嵌套 JAR。真实 Loader 依赖 RESOLVED；整包 AOT/游戏 NOT RUN。AE2 目标发行版为 NeoForge，不混入 Fabric。通用元数据/模组枚举/provider 快照扩展经对照测试和 TechReborn 隔离转换验证，未做本轮完整 AOT。见 [样本包](CONTENT_SAMPLE_PACK.md) 和 [适配路线](MOD_ADAPTATION_PLAN.md)。

## 2026-11-13 内容样本 AOT 测试包

`content-samples-build-04` 完成 AOT（2m31s）、iPhoneOS 链接及签名。五个主模组全部保留；导出器排除了含运行时类生成/代理代码的嵌套 Javassist 和 Reflections 库，不能据此宣称完整功能兼容。修复新版 GlitchCore EventManager 的精确指纹（审阅字节码差异，RegistryHelper 与原版相同）及两处扫描器对生成资源副本的重复计数；资源 metadata 改用 assets/data 目录 glob。前序失败/被替代构建保留。用户要求仅交签名 IPA 自测，本轮未运行游戏或模拟器。

## 2026-11-13 World Weaver ModCore 构造器修复

用户真机日志 run-1794501579373.log 在 Bootstrap 阶段由 BetterEnd 的属性 Mixin 触发 ModCore(String,String)，构造器因未识别 getInstance→ALOAD/GETFIELD→getModContainer 查询而被 residue 替换为抛错。RuntimeLowering 现用 ASM SourceInterpreter 分析接收者栈来源，保留任意 ID 表达式求值并路由目录快照。复杂 Map 表达式查询执行断言及目录相关 3 项测试通过；实际转换中 ModCore 构造器不再 stub。content-samples-build-05 AOT（2m38s）、iPhoneOS 链接和签名通过。用户指定真机自行测试，本轮未运行游戏或模拟器；两项嵌套动态库排除仍保留，不宣称整包功能通过。

## 2026-11-13 自定义入口值/容器语义修复

用户日志 run-1794502414023.log 显示已越过 ModCore，随后 World Weaver DatapackRegistryBuilderImpl 将 Entrypoints$Container 强转 DatapackRegistryEntrypoint 失败。根因是 getEntrypoints 与 getEntrypointContainers 被统一改写到返回容器的 stage。现前者使用生成的 stageValues，解包真实实例并保留 provider 缓存身份；后者仍返回容器。11 项相关回归通过，涵盖实例列表、未知 stage 和实例缓存；content-samples-build-06 已完成 AOT、iOS 链接与签名。本轮按用户要求不运行游戏/模拟器，真机仍需复验。两项嵌套动态库排除限制仍在。

## 2026-11-13 Mixin 重定位 Guava 闭包修复

用户 run-1794503860221.log 显示 wover/bclib 主入口已返回，BetterEnd 在 SmithingTemplates.combine 初始化缺 org.spongepowered.include.com.google.common.collect.ImmutableList。AotExport 现从固定 Mixin JAR 打包完整重定位 Guava 值库命名空间，保留其 ABI，不引入运行时类加载器。11 项相关回归通过，含隔离类加载器从该闭包创建 ImmutableList 的断言。content-samples-build-07 AOT（2m18s）、iOS 链接与签名通过；本轮不运行游戏或模拟器，真机待用户复验，原两项嵌套库排除仍在。
