# A1 真机测试交接

日期：2026-11-08。用户负责设备安装与运行测试。**A0/A1均已通过**，A1的独立运行证据明确来自build 2；下一阶段见[B0测试交接](B0_TEST_HANDOFF.md)。

## 本次交付

- [最新build 3 开发签名 IPA](<../artifacts/a1/device-handoff-v3/export/FabricAOT A1.ipa>)，4,970,738 字节。
- [同一 IPA 解出的安装 App](../artifacts/a1/device-handoff-v3/ipa-inspection/Payload/A1Harness.app)。
- [Xcode 归档](../artifacts/a1/device-handoff-v3/A1Harness.xcarchive)及[可编辑工程](../ios/A1Harness/A1Harness.xcodeproj)。
- [包记录](../artifacts/a1/device-handoff-v3/result.json)：哈希、ARM64/iPhoneOS 平台、签名权限、描述文件期限和设备覆盖。
- [已通过独立运行的build 2 IPA](<../artifacts/a1/device-handoff-v2/export/FabricAOT A1.ipa>)和[对应真机证据](../artifacts/evidence/a1-user-device-run-03/result.json)。

最新IPA SHA-256：`8aac4715dfc8801831bf7159128a4130bfeaeaa7b548604383df0f79f025712f`。

本次归档、Xcode 本地导出和解包后的嵌套代码签名检查均退出0。Bundle ID 为 `org.fabricaot.research.a1probe.kexin`，最低 iOS17.0。描述文件包含此前已配对的用户 iPhone，签名有效期至 **2026-11-15 09:53:47（北京时间）**。安装是否成功仍由设备验证。

用户通过 Xcode 安装的 build 1 曾返回 `createIsolate=801`；[原始记录](../artifacts/evidence/a1-user-device-run-01/result.json)保留。build 2 通过公开参数将预留空间限制为256 MiB，已解决该失败：用户独立重新启动后，日志从 `a1-1794103907099.log` 变为 `a1-1794104082625.log`，原生三个返回值全为0，Java全部断言通过。用户明确确认退出Xcode、拔线，并确认日志名变化；[本次证据](../artifacts/evidence/a1-user-device-run-03/result.json)同时记录了该确认。

build 3 补充 RUNNING 状态、本次开始时间、耗时、runID/processID与日志名；UI只读取本进程的报告。后台恢复会展示本进程结果，后台划掉后重开才创建新报告，不人为延长运行。用户已提供build 3 PASS截图（开始10:24:55.778，显示0.022秒，日志 `a1-1794104695778.log`）；对应日志见 artifacts/evidence/a1-user-device-run-04/。这一运行段耗时不代表游戏启动或性能。

这是 Java25 原生语义探针；其通过只能提供 A1 的部分证据。Minecraft/Fabric 的 Mac 参考启动、游戏引导、图形和世界验收另行进行。App 不含游戏客户端或用户整合包。

## 安装与独立启动

可直接在现有 Xcode 工程重新构建并覆盖安装，确认界面显示 **build 3**，随后按下述方式独立启动。也可在项目根目录操作，连接并解锁目标 iPhone，在 Xcode 的 Devices and Simulators 选中该手机，通过 Installed Apps 加号选取上面的 `.app`。保留当前 App 及 Documents。

下列命令限定此前已配对的用户 iPhone，只安装、不自动启动；由用户自行执行：

```bash
xcrun devicectl device install app --device 00008160-001A78620A600036 artifacts/a1/device-handoff-v3/ipa-inspection/Payload/A1Harness.app
```

随后退出 Xcode、断开 USB，从 iPhone 主屏幕点开 **FabricAOT A1**。测试时不附加调试器，不开启 Java JIT。App 会自动执行一次探针，并显示 PASS 或 FAIL。若持续停在 STARTED/Starting、闪退或无法安装，保留当时错误和日志。

## 需要记录的结果

1. 手机型号、iOS 版本、安装是否成功，以及独立启动后的画面。
2. `latest.json` 中 `harnessBuild=3`、`reservedAddressSpaceBytes=268435456`、`status=PASS`，且 `createIsolate`、`runResult`、`tearDownIsolate` 均为0。build 3另有runID/processID，时间与日志名应对应本次启动。
3. 该 JSON 的 `log` 字段指向的同一次日志，包含 `A1_SEMANTICS_PASS` 和 `A1_NATIVE_FINISH create=0 run=0 teardown=0`。日志另有线程、ScopedValue、GC、资源、JNI、文件原子写入/读取断言。
4. 手动结束 App 后再次从主屏幕打开，保存第二次结果与日志。结果文件按启动时间保留；文件断言只覆盖探针自身的读写行为。

App 已开放 Documents 文件共享。可在“文件”→“我的 iPhone”→“FabricAOT A1”导出 `latest.json` 及对应 `.log`；也可在 Xcode Devices and Simulators 下载该 App 的容器。失败时同时保留该 App 的崩溃报告。

若使用命令行复制，下面命令只读取该测试 App 的 Documents，目标目录使用新的名称，避免覆盖既有记录：

```bash
xcrun devicectl device copy from --device 00008160-001A78620A600036 --domain-type appDataContainer --domain-identifier org.fabricaot.research.a1probe.kexin --source Documents --destination artifacts/evidence/a1-user-device-run-05
```

反馈时提供上述画面、设备/iOS 信息和同一次的 JSON/日志即可。若还测试了 Swift Craft Launcher 的 Java25 + Fabric26.1.2 桌面基线，请一并记录实际使用的 Java、Loader 版本和启动结果。

## 后续处理

本轮所有真机安装/运行由用户执行，Agent只读采集报告并检查日志。早期46项自动化测试及模拟器结果保留为历史证据；后续Mac脚本由助手负责，当前回归结果见STATUS。A1独立运行的通过结论来自build 2原始断言与用户确认；build 3截图/日志另行保留。签名权限只有 application identifier、team identifier 和标准开发签名的 get-task-allow；没有 JIT 权限。小屏/横屏、最大文字、VoiceOver与暗色模式等UI扩展验证仍交由用户，未宣称全部完成。

到期后用相同 Team/Bundle ID 重新签名并覆盖安装；保留现有 App 和 Documents。安装更新与数据保留尚待验证。生成的新设备记录需要后续核验并登记中央 AAR。
