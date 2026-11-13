# 当前状态（2026-11-10）

**EXPERIMENTAL。A0/A1/B0/B1 PASS。原版单人玩法已在模拟器验证，正式真机 C0 仍为 BLOCKED。**

当前实现和复现见 [BUILDING](BUILDING.md)，工具链决策见 [ADR-001](evidence/ADR-001.md)，原始记录见 [证据索引](evidence/README.md)。

## iPad Pro PR #2 真机失败修复（2026-11-13）

PR #2 的真机失败不是“CI 没跑够”，而是最终安装包仍声明为 iPhone-only：

- 失败构建的实际 `TARGETED_DEVICE_FAMILY = 1`，最终 `.app/Info.plist` 为 `UIDeviceFamily = [1]`，所以 iPad 以 iPhone 兼容模式运行并显示系统放大按钮。
- 兼容模式/非全屏场景不满足 iPadOS 指针锁定前提，`prefersPointerLocked` 未被批准，原输入桥又只在 `captured && pointerIsLocked` 时转发 `GCMouse` 位移，触控板于是只能移动系统光标。

修复已在独立分支 `fix/ipados-mouse-trackpad-look` 完成，**没有合并 main**：

| 项目 | 状态 | 证据 |
|---|---|---|
| 最终包 `UIDeviceFamily=[1,2]` | PASS（构建阶段强制） | `embed_graphics_libraries.sh` → `verify_ipad_bundle.sh`；[构建日志](../artifacts/ipad-pr2-fix-01/build-3.log) |
| 独立包契约复核 | PASS | `python3 tools/verify_ipad_bundle.py --app ...`；[契约 JSON](../artifacts/ipad-pr2-fix-01/ipad-bundle-contract.json)（若已归档） |
| iPad 原生场景/Drawable | PASS（iPadOS 27.2 模拟器） | 场景 `1210x834 pt`、Drawable `2420x1668 px`、`sceneFullScreen=1`，原版主菜单铺满屏幕；[截图](../artifacts/evidence/ipad-pointer-pr2-20261113/ipad-simulator-native-menu.png) |
| 窗口/Drawable/锁状态日志 | PASS（模拟器） | `input-*.log`：`state ... scene=1210x834 screen=1210x834 drawable=2420x1668` |
| 触控板指针锁/视角 | **NOT RUN（真机）** | 2026-11-13 两次安装均因 iPad 锁屏被 CoreDevice 拒绝；待解锁后执行 [IPAD_INPUT](IPAD_INPUT.md) §4 |
| 菜单点击/滚动/键盘 | **NOT RUN（真机）** | 同上 |

模拟器证据不能替代真机。PR #2 在真实 iPad Pro 完成触控板双向视角、锁定/释放、菜单点击/滚动/键盘验证前继续保持未合并。手动安装包和回传清单已放在 `artifacts/evidence/ipad-pointer-pr2-20261113/manual-test/README.md`，等待真机结果。

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

客户端和实例均保持在用户原位置。53 个现有 Mod 未执行或转换，兼容性未知。AOT 原生库来自固定官方源码；数值 CAP 数据来源和版本记录于工具链锁定文件。未提供的 JVM 原生入口会明确终止，当前探针没有触发这些入口，不能据此承诺完整 Java/Mod 兼容性。

B1诊断包为 artifacts/b1/device-handoff/export/FabricAOT B1.ipa（build 4），用户已安装验证。它只包含预转换的第一方夹具，不包含Minecraft游戏代码。描述文件有效期至2026-11-15 09:53:47（北京时间）。[B0复现](B0_TEST_HANDOFF.md)、[B1证据](B1_DEVICE_HANDOFF.md)和[客户端诊断](evidence/ADR-003.md)分别记录验证边界。

已按门槛文档建立本地Git源代码记录；提交可用git log -1查看。当前源文件和证据指纹由 verify_evidence.py 保存。生成物通过唯一中央 AAR 实际登记，保留历史实验和设备状态，安全删除标志均为 false。

第13轮时的6个源文件及差异另存handoff-snapshot-20261108（不含第17–24轮新增工具）。接手状态、实验12–24及测量边界见[WORK_HANDOFF](WORK_HANDOFF.md)。

用户第46轮确认蓝屏后进入日志；设备日志为Metal诊断成功，未确认独立启动条件。Xcode工程已切到下一版四分屏资源探针，设备目标构建及输入核对通过，用户已在真机确认四色，GPU读回/呈现日志匹配；宿主返回记录受日志覆盖问题影响，已修复并另行验证。日志、输入与测试边界见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。

第47轮只使用模拟器：真实NativeImage的PNG写读/缩放/回调与Metal裁剪上传、GPU读回通过，见[图像AOT结果](../artifacts/graphics/images-simulator-evidence-02/result.json)。G4已完成60/60程序预编译，覆盖全部79个可执行着色器。87条原版管线的Metal状态创建及混合/裁剪/索引/实例/三角扇像素检查通过，见[绘制证据](../artifacts/graphics/draw-simulator-evidence-02/result.json)。后端数组注入仅修改Minecraft.class，正在验证真实Main。

真实Main的后端注入现已执行验证：窗口与Metal设备初始化成功；HTTP/HTTPS处理器、固定索引30和OpenJDK libextnet已补齐。固定OpenAL Soft1.25.2/CoreAudio已通过静音PCM实际播放验证，真实Main已进入首帧绘制；正在验证启动Logo的预加载修复。真实菜单和世界仍未验收。后续继续仅模拟器。

[模拟器真实菜单](../artifacts/graphics/main-simulator-run-08/result.json)已验证欢迎页→主菜单→单人游戏→新建世界。音频引擎启动，原版图集和全景加载；按钮背景仍有裁切/缺失。补齐 Netty 两个构造器后，[原版客户端已登录集成服务器](../artifacts/graphics/main-simulator-run-09/result.json)。地形初始化在 256 MiB 的图形资源总限额处停止；新模拟器配置把该限额提高至 768 MiB，待地形渲染复验。
