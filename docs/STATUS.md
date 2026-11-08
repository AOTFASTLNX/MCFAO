# 当前状态（2026-11-08）

**EXPERIMENTAL：A0/A1/B0/B1 PASS；C0 BLOCKED。可玩产品尚未交付。**

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
| C0 | BLOCKED | 09/10轮6/8 GiB堆和11轮8 GiB G1对照均Java heap OOM；无完整分析统计。见CLIENT_GRAPH_DIAGNOSTICS.md；没有iOS客户端引导执行结果 |
| C1 / C2 | NOT RUN | 无真实Minecraft iOS渲染、菜单或世界行为 |
| D0 | PARTIAL | 离线元数据/研究工具负例已测试；默认拒绝沙盒读/写/本地连接控制通过；恶意Mod/Gradle、IPC、完整下载/依赖服务未验收 |
| D1 / D2 | NOT RUN | 无已验证整合包、签名游戏 IPA、安装更新/存档保留结果 |
| E | NOT RUN | 无真机游戏性能、温度或持续游玩数据 |

当前79项自动化回归全部PASS，结果见 artifacts/evidence/unit-tests-c0-diagnostics-verified/。新增元数据审计、GC日志指标和受控变量比较回归。根据用户最新分工，Mac脚本测试由助手执行，真机安装/运行由用户负责。

主机：macOS 27.2 arm64，Xcode/iPhoneOS SDK 27.2，GraalVM CE 25.0.2。用户 iPhone/iOS27.2 的 build 2 原生日志确认 Java25语义运行通过，退出Xcode/拔线/重新打开条件由用户确认。专用调试模拟器与用户原有设备分开。

客户端和实例均保持在用户原位置。53 个现有 Mod 未执行或转换，兼容性未知。AOT 原生库来自固定官方源码；数值 CAP 数据来源和版本记录于工具链锁定文件。未提供的 JVM 原生入口会明确终止，当前探针没有触发这些入口，不能据此承诺完整 Java/Mod 兼容性。

最新诊断包为 artifacts/b1/device-handoff/export/FabricAOT B1.ipa（build 4），用户已安装验证。它只包含预转换的第一方夹具，不包含Minecraft游戏代码。描述文件有效期至2026-11-15 09:53:47（北京时间）。[B0复现](B0_TEST_HANDOFF.md)、[B1证据](B1_DEVICE_HANDOFF.md)和[客户端诊断](evidence/ADR-003.md)分别记录验证边界。

已按门槛文档建立本地Git源代码记录；提交可用git log -1查看。当前源文件和证据指纹由 verify_evidence.py 保存。生成物通过唯一中央 AAR 实际登记，保留历史实验和设备状态，安全删除标志均为 false。
