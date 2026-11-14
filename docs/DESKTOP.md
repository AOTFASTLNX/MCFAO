# 跨平台桌面工作台

Last reviewed: 2026-11-14

状态：实验版前端与本地静态预检桥接。源码和使用说明见 [desktop/README.md](../desktop/README.md)。本次前端工作不提升游戏运行、Mod、签名或性能 Gate。

## 平台与功能

桌面管理界面采用 Tauri 2、React、TypeScript、Vite；面向 macOS、Windows、Linux。iOS AOT 工具链继续运行于 macOS Apple Silicon。桌面端调用随应用打包的第一方 `preflight.py`，仅读取本地元数据。Python 3 由本机提供；GUI 可配置解释器路径。浏览器模式通过 JSON 报告完成相同的查看、筛选、实例管理和导出工作。

支持 `.mrpack`、Prism 目录选择和原生拖放；阻断与预警按原始报告展示。首版构建页可生成元数据准备命令，实际编译、签名和导出仍使用现有 CLI。没有远程 Mac 服务。

## 边界

- 报告输入校验后统一为静态预检类型。所有 Mod 的 iOS / AOT 状态为未测试，不从 imported JSON 的 VERIFIED 字段推断真机证据。
- 不下载或执行 Mod。Rust 仅以参数数组启动第一方脚本，不借助 shell；预检 120 秒超时、stdout 8 MiB / stderr 64 KiB 上限。
- 环境检查只证明被调用工具的当前可用性，Java / Xcode 检测不证明完整 iOS GraalVM 工具链有效。
- 本地存储损坏时保留原始记录、暂停覆盖，提供导出和显式重置。工作台移除实例仅删除报告记录。
- 应用只包含前端、原创 SVG 和预检脚本，不包含游戏文件、Mod 二进制、账户、存档和签名材料。

## 验证入口

`desktop/src/model.test.ts` 验证报告输入、状态边界、跨系统路径、重复导入与命令参数；`desktop/tests/workspace.spec.ts` 使用真实第一方预检输出检查导入、持久化、筛选、导出、阻断、键盘和响应式布局。Rust 测试验证命令参数、超时、输出限额、无效源和错误报告传递。

本轮测试、截图和本地打包记录放在 `artifacts/desktop/`。Windows / Linux 的原生构建、文件对话框和运行验收尚未执行；当前 macOS 的结果不作为其他系统的验收证据。

## 2026-11-14 本轮结果

| 检查 | 结果 |
|---|---|
| TypeScript / Vite 生产构建 | PASS |
| 数据模型与命令参数自动化 | 19 PASS |
| 浏览器工作流与 375 / 768 / 1280 / 1440 布局 | 10 PASS |
| Rust 预检桥接、超时与输出上限 | 5 PASS |
| Rust Clippy（-D warnings） | PASS |
| macOS 桌面开发包 | PASS，约 30.54 MiB |
| 原生 .mrpack 选择、Python 预检、报告和任务日志 | PASS，第一方元数据夹具 |
| 原生系统保存对话框导出日志 | PASS |

本机 Rust 工具链默认 host 为 x86_64-apple-darwin，本轮开发包也为 x86_64，在 Apple Silicon 宿主通过 Rosetta 运行验证。aarch64 原生包、正式分发签名与公证尚未验证。原生 Prism 目录选择和拖放有实现，未在本轮逐项交互验收。

原始日志：`artifacts/desktop/unit-tests.log`、`browser-tests.log`、`native-tests.log`、`native-preflight-log.txt`。概要、工件与附带脚本指纹见同目录 `result.json`。本地测试包为 `FabricAOT-macos-x64-experimental.zip`；只包含工作台与预检工具。
