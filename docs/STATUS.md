# 当前状态（2026-11-10）

**EXPERIMENTAL。A0/A1/B0/B1 PASS。原版单人玩法已在模拟器验证，正式真机 C0 仍为 BLOCKED。**

当前实现和复现见 [BUILDING](BUILDING.md)，工具链决策见 [ADR-001](evidence/ADR-001.md)，原始记录见 [证据索引](evidence/README.md)。

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
| D1 / D2 | NOT RUN | 无已验证整合包、签名游戏 IPA、安装更新/存档保留结果 |
| E | NOT RUN | 无真机游戏性能、温度或持续游玩数据 |

当前 **170 项 Python 自动化回归全部 PASS**。GLFW 与像素转换 C 夹具通过 ASan/UBSan，真实 Metal 像素测试通过。原版单人运行证据来自模拟器，iPhone 游戏包等待用户安装运行。[回归日志](../artifacts/graphics/regression-18/stderr.log) · [GPU 记录](../artifacts/graphics/draw-simulator-evidence-05/result.json)

主机：macOS 27.2 arm64，Xcode/iPhoneOS SDK 27.2，GraalVM CE 25.0.2。用户 iPhone/iOS27.2 的 build 2 原生日志确认 Java25语义运行通过，退出Xcode/拔线/重新打开条件由用户确认。专用调试模拟器与用户原有设备分开。

客户端和实例均保持在用户原位置。53 个现有 Mod 未执行或转换，兼容性未知。AOT 原生库来自固定官方源码；数值 CAP 数据来源和版本记录于工具链锁定文件。未提供的 JVM 原生入口会明确终止，当前探针没有触发这些入口，不能据此承诺完整 Java/Mod 兼容性。

B1诊断包为 artifacts/b1/device-handoff/export/FabricAOT B1.ipa（build 4），用户已安装验证。它只包含预转换的第一方夹具，不包含Minecraft游戏代码。描述文件有效期至2026-11-15 09:53:47（北京时间）。[B0复现](B0_TEST_HANDOFF.md)、[B1证据](B1_DEVICE_HANDOFF.md)和[客户端诊断](evidence/ADR-003.md)分别记录验证边界。

已按门槛文档建立本地Git源代码记录；提交可用git log -1查看。当前源文件和证据指纹由 verify_evidence.py 保存。生成物通过唯一中央 AAR 实际登记，保留历史实验和设备状态，安全删除标志均为 false。

最新研发变更尚未提交；第13轮时的6个源文件及差异另存handoff-snapshot-20261108（不含第17–24轮新增工具）。接手状态、实验12–24及测量边界见[WORK_HANDOFF](WORK_HANDOFF.md)。

用户第46轮确认蓝屏后进入日志；设备日志为Metal诊断成功，未确认独立启动条件。Xcode工程已切到下一版四分屏资源探针，设备目标构建及输入核对通过，用户已在真机确认四色，GPU读回/呈现日志匹配；宿主返回记录受日志覆盖问题影响，已修复并另行验证。日志、输入与测试边界见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。

第47轮只使用模拟器：真实NativeImage的PNG写读/缩放/回调与Metal裁剪上传、GPU读回通过，见[图像AOT结果](../artifacts/graphics/images-simulator-evidence-02/result.json)。G4已完成60/60程序预编译，覆盖全部79个可执行着色器。87条原版管线的Metal状态创建及混合/裁剪/索引/实例/三角扇像素检查通过，见[绘制证据](../artifacts/graphics/draw-simulator-evidence-02/result.json)。后端数组注入仅修改Minecraft.class，正在验证真实Main。

真实Main的后端注入现已执行验证：窗口与Metal设备初始化成功；HTTP/HTTPS处理器、固定索引30和OpenJDK libextnet已补齐。固定OpenAL Soft1.25.2/CoreAudio已通过静音PCM实际播放验证，真实Main已进入首帧绘制；正在验证启动Logo的预加载修复。真实菜单和世界仍未验收。后续继续仅模拟器。

[模拟器真实菜单](../artifacts/graphics/main-simulator-run-08/result.json)已验证欢迎页→主菜单→单人游戏→新建世界。音频引擎启动，原版图集和全景加载；按钮背景仍有裁切/缺失。补齐 Netty 两个构造器后，[原版客户端已登录集成服务器](../artifacts/graphics/main-simulator-run-09/result.json)。地形初始化在 256 MiB 的图形资源总限额处停止；新模拟器配置把该限额提高至 768 MiB，待地形渲染复验。
