# 可以直接发送给 Codex Agent 的总任务

你是拥有 macOS/Xcode/Java/GraalVM 编译环境、可写当前工作区的高级工程 Agent。请阅读仓库 `AGENTS.md`、`docs/REVIEW_REPORT.md`、`docs/TECHNICAL_GATES.md`、`docs/SECURITY_AND_DISTRIBUTION.md`、`docs/PRODUCT.md`、`docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md` 并直接着手开发 FabricAOT 的最终可玩产品：Minecraft Java 26.1.2、Fabric Only、Mac 导入 Fabric 整合包并 AOT 生成签名 IPA、iPhone 本地运行且不需要 Java JIT/越狱/远程串流。

不要停留在需求讨论或只做空白 SwiftUI 界面。优先执行 Gate A0/A1/B0/B1/C0/C1/C2 的真实实验，得到可复现命令、日志、源码和测试；Gate 失败则分析根因、尝试技术上可信的修复，在不违背产品硬条件的前提下继续推进。不得谎报兼容性、真机测试、可玩性或生成 IPA。用户没有付费 Apple Developer Program，优先考虑 Xcode Personal Team 本机签名。在需要用户本人完成 Microsoft 登录、Apple 证书/签名、连接设备等动作时，准确注明如何操作，不要索要凭据。

每次完成有意义的改动：执行测试、记录结果、提交有说明的 commit（如在 Git 仓库），更新 `docs/STATUS.md`（当前 Gate、通过/阻断、验证设备、准确命令、风险、下一步）。不要为完成而更换 Minecraft 版本、切换到 Forge/Quilt、使用浏览器版或伪装 JIT 为 AOT。最终以 `docs/ACCEPTANCE.md` 的真实验收门槛判断是否可发布。

**第一条具体任务**：无需用户再次确认，检查本机 Java25、Xcode、可用的 iOS GraalVM native-image fork，输出 `docs/evidence/ADR-001.md`，用真机执行 A1 小程序，明确每个子检查的 PASS/BLOCKED/NOT RUN 与日志。不可把 Python preflight 的 PASS 当成 AOT PASS。只有 Gate A1 完成，才执行 Fabric 静态化；任何不可信 Mod 代码在隔离完成前不得执行。
