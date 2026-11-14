# FabricAOT — 编码 Agent 根指令

> 2026-11-15 集成决策：本次主要渲染路线按 docs/evidence/ADR-009.md：Blaze3D OpenGL → LWJGL JNI → OSMesa/Zink → MoltenVK → Metal/CAMetalLayer；保留 compiler/metal-backend 为可选 Metal 构建。所有开发位于 integration/gl41-gui-ipa-20261115 或子分支，禁止推送/合并 main 或删除备份分支。桌面构建器继续 desktop/ 的 Tauri 2 + React + TypeScript + Rust，仅验收 Apple Silicon macOS。


> 本仓库是 **Minecraft Java Edition 26.1.2 + Fabric Only** 的 iOS 无 Java JIT 原生运行工程。最终目标是 Mac 导入兼容整合包、编译签名 IPA、iPhone 本地真实游玩。**不是 UI mock，不是 Web 串流，不是解释器假装 AOT。**

## 不可更改的产品约束

1. Minecraft Java Edition **26.1.2**，Java **25**；仅支持 Fabric，不以旧版本替代目标。
2. 构建在 macOS Apple Silicon 上完成；运行在普通未越狱 iPhone/iOS 上，**不需要用户手动开启 JIT**。禁止使用动态代码生成、私有 JIT 权限、附加调试器作为运行前提。
3. iOS 在本机执行游戏逻辑、渲染画面、加载与保存世界。电脑只参与构建与签名，不能当远程游戏服务器。
4. 用户仅构建其合法拥有的 Minecraft 客户端，游戏本体、授权资源、第三方未授权 Mod 和专有库不可提交仓库或塞进预编译公开 IPA。采取用户本地获取/导入模式。
5. 支持 `.mrpack` 和 Prism Launcher 实例导入；按兼容性报告处理 Mod，不要宣传无条件支持所有 Fabric Mod。
6. 做到可玩版本的定义以 docs/ACCEPTANCE.md 为准，不准用“构建成功”代替真机可玩证据。

## 开发行为

- 先阅读 docs/REVIEW_REPORT.md、docs/TECHNICAL_GATES.md、docs/SECURITY_AND_DISTRIBUTION.md、docs/PRODUCT.md、docs/ARCHITECTURE.md、docs/ACCEPTANCE.md；持续更新状态和原始实验日志。
- **从真正最难的可行性门槛开始**：Java 25 AOT iOS arm64 的工具链能否成功、Fabric/Mixin 编译前静态转换能否成功、Minecraft 的桌面图形依赖能否适配 iOS。先用最小可复现测试证实，否则不得投入大量 UI 伪开发。
- AOT 必须生成预先签名的 ARM64 原生二进制。不得通过 DebugServer、JITServer、执行时 `mprotect` 修改为可执行、解释执行后宣称“高性能 AOT”等途径绕开指标。
- 研究 GraalVM Native Image 25 与 iOS toolchain 当前实际版本、补丁和许可证；**不要假设普通 GraalVM for macOS 可以直接交叉编译 iOS**。先核验官方文档，再用真机验证。
- Fabric Loader 的 Mixin/ASM 类转换要在构建时执行，记录每个 Mod 的转换覆盖和兼容性风险。若发生运行时动态类定义，必须精准报错，不能忽略。
- OpenGL 与 Metal 不是 drop-in 替换。渲染路径必须由真实 Minecraft 26.1.2 调用验证；不能用一个渲染立方体假装游戏已兼容。
- 每个里程碑保留可复现命令、日志、失败用例、真机验证记录以及已知局限。
- 错误处理优先于“全部支持”的产品宣称；无法完成要求时给出阻断证据和可行替代架构，不伪造 IPA、FPS 和测试。
- 不上传任何玩家的 Microsoft 登录凭证、访问令牌、个人存档或专有游戏文件。**绝对不要在用户个人主环境直接执行未经审计的第三方 Gradle 构建脚本/Mixin 插件或构建期类初始化**。
- 写单元测试、集成测试和清晰文档；新增代码需自动化测试。优先适配 ARM64 与合理内存预算。

## 工作顺序与停止条件

1. **Gate A0/A1:** Mac Java25+Fabric 参考基线先通过；随后 Java 25 的小型程序经 AOT + 代码签名，在普通 iPhone 上独立启动，无 JIT / 调试器依赖。
2. **Gate B0/B1:** Fabric 测试 Mod（包含真实 Mixin、Class Tweaker、嵌套 JAR 与 Entrypoint）完成构建期转换；先在 JVM 对照，再在 iOS AOT 的同一运行时证明行为正确。
3. **Gate C:** 原版 26.1.2 展示真实主菜单，随后创建和游玩一个世界，并实现音频、触摸、持久存档。
4. **Gate D0/D1/D2:** 首先隔离不可信 Mod 构建，再导入一个经过测试的 Fabric 整合包，报告不兼容 Mod，验证本地签名/IPA 导出/安装/存档保留，真实进入世界。
5. **Gate E:** 性能和稳定性，真机记录 FPS、帧时间 1% low、峰值内存、加载时间、温度/降频表现及崩溃日志。

任何 Gate 不成立则保持门槛状态为 BLOCKED。**不能将项目标记 FINAL、COMPLETE 或 RELEASE。** 不因遇到困难擅自降低需求或改为 JavaScript 版 Minecraft。可开发调试辅助工具，但要清楚标识它们不构成可玩产品。

## 代码结构建议

- `desktop/` Tauri 2 + React + TypeScript + Rust macOS 整合包导入、诊断、构建编排、日志与签名。
- `compiler/` Java 25、Fabric 加载图、构建期 Mixin、AOT、资源处理、可复现构建。
- `ios/` Swift/Objective-C++、触摸输入、Metal 图形适配、音频、文件/沙盒、日志。
- `interop/` Java 与 iOS 原生 API 之间的窄接口和测试夹具。
- `tools/` 预检与资产核验 CLI。
- `tests/` 真实 modpack fixtures（不包含专有游戏内容）。
- `docs/` ADR、兼容性矩阵、证据、构建说明、故障排查，尤其遵守 TECHNICAL_GATES 与 SECURITY_AND_DISTRIBUTION。

## 交付标准

最终交付：可编辑源代码、Xcode 工程、构建工具、测试、安装文档、经过验证的测试整合包兼容列表、可重现的构建步骤，以及依法通过用户本地资产生成的 IPA。若缺少真机运行证据，只能交付研发阶段成果，不能称最终版。
