# Gate / 验收清单

> 2026-11-15 集成决策：C0a：真实 Minecraft 26.1.2 经 GL41 渲染首帧；C0b：真实主菜单及输入，均要求物理 iPhone/iPad、源码 SHA、IPA SHA-256、日志和截图/视频。C2 另须移动/视角、破坏/放置、背包、保存退出、重启重进；E 须至少 30 分钟及实测性能/内存/热状态，缺失记 NOT MEASURED。GUI 须 Apple Silicon .app 启动、真实完整 AOT、渲染器选择、日志/取消/失败重试/产物管理及自动化验证。Fabric Loader、Fabric API 和轻量 Mod 的 FUNCTION_PASS 必须有实际游戏证据。


原则：**所有证据必须来自真实执行，未执行的测试只能写 NOT RUN。** 不以模拟器结果替代真机结果。

| Gate | 验收最低标准 | 必须保存的证据 |
|---|---|---|
| A | A0 Mac Java25 Fabric 参考基线通过；A1 Java25 小程序 AOT 为 iOS ARM64，在普通 iPhone 无 JIT 独立启动 | compiler version, commands, codesign entitlements, device logs |
| B | Fabric + 真实 Mixin、Class Tweaker、Entrypoint、嵌套 JAR fixture 预编译后先通过桌面 JVM 行为对照，再通过 iOS 运行时行为测试 | original/transformed bytecode hash, test logs |
| C1 | 实际 26.1.2 显示主菜单，并能响应输入 | screenshot/video, logs, commit hash |
| C2 | 创建世界，放/破坏方块，移动，保存退出并正确重入 | world checksums, test case, logs |
| D | 安全构建/下载哈希验真，一份指定、兼容的 Fabric 整合包导入后，诊断、编译、签名、IPA 导出、实际设备安装且可玩 | pack manifest hash, mod compatibility matrix, build/install logs |
| E | 真实设备性能/稳定性测试，无伪造数值 | FPS & frame-time data, memory, thermal state, 30min run, crash logs |

详细子门槛与停止条件请先执行 `TECHNICAL_GATES.md`。静态预检成功永远不等于 Mod VERIFIED；必须在真机实际执行 Mod 行为。

## 测试矩阵

- 单人：新世界、既有世界、保存/加载、应用被系统中断、资源包、输入、音频。
- 联机：v1 不宣称支持，仅在正式支持后独立验收，断线重连、版本协议、服务器资源包。
- Mod：纯资源 Mod、Mixin 改方块行为的 Mod、Fabric API 基础组件、服务端专用 Mod、动态 defineClass Mod（应报告不支持）。
- 整合包：合法 `.mrpack` / Prism，Mod 依赖缺失、不同版本、Forge/NeoForge 伪装包、损坏压缩包、路径穿越、下载 hash 错误。
- 签名：Personal Team 7 天到期场景、真机安装、IPA 导出分别验收；重签名、同 BundleID 的世界数据保留。
- 发布：所有游戏本体文件由最终用户合法自行获取，发布仓库不含 Mojang 客户端文件。

## 发布门槛

全部 Gates A–E 通过后才可打 `v1.0`；且应公开兼容范围和不兼容清单。A–E 任一缺失则标记 `experimental`，不得把壳 App、菜单演示或单一方块画面称为 Minecraft Java 可玩终版。
