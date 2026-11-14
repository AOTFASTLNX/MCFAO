# FabricAOT Desktop（实验版）

Tauri 2 + React + TypeScript 的本地工作台，面向 macOS、Windows 和 Linux。当前已在 macOS Apple Silicon 构建与测试；Windows / Linux 原生包仍需在对应系统验证。

## 启动

需要 Node.js 22.12+（或 24+）与 npm。桌面模式另需 Rust stable、对应系统的 Tauri 2 开发依赖以及 Python 3。

在本目录执行：

~~~sh
npm ci
npm run dev
~~~

浏览器打开 `http://127.0.0.1:1420`。预览模式支持报告导入、实例管理、筛选、导出、本地设置与准备命令生成。

桌面模式：

~~~sh
npm run tauri dev
~~~

若浏览器预览服务已启动，先停止它，再启动桌面开发模式，避免端口冲突。

## 当前能力

- 中文工作台、实例库、兼容性报告、构建准备、会话任务日志、工作环境和设置。
- 桌面应用通过文件选择器或拖放导入 `.mrpack` / Prism 实例，实际调用仓库 `tools/preflight.py`。
- Python 脚本随桌面应用打包；用户仍需本机安装 Python 3，可在设置中指定解释器。导入不依赖项目目录配置。
- 浏览器与桌面均可导入静态预检 JSON；报告最多 8 MiB。JSON 字段经过校验，错误与警告分开显示。
- 实例、报告和设置保存在当前 WebView / 浏览器的本地存储。两种模式的存储彼此独立，任务日志仅保留当前会话。
- 导出 JSON 报告、预检日志和构建准备说明。桌面导出使用系统保存对话框。
- 本机 Python / Java 25 / Xcode 检测，明确显示缺失和平台限制。

完整 AOT 编译、签名与 IPA 导出仍使用 [构建文档](../docs/BUILDING.md)。界面生成的命令固定为 `--prepare-only`；不会自动授予第三方 Mod 审计许可或执行完整构建。远程 Mac 调度尚未接入。

静态报告始终保留未测试状态；导入报告中的兼容性或真机验证宣称不会被当作实际验收证据。游戏与 Mod 行为按 [验收标准](../docs/ACCEPTANCE.md) 独立验证。

## 测试与打包

~~~sh
npm test
npx playwright install chromium
npm run test:e2e
cargo test --manifest-path src-tauri/Cargo.toml --lib
npm run build
npm run tauri build
~~~

仅构建本地 macOS 开发包（不需要分发证书）：

~~~sh
npm run tauri build -- --debug --bundles app
~~~

输出位于 `src-tauri/target/debug/bundle/macos/FabricAOT.app`。正式分发的签名与公证尚未配置。Windows / Linux 安装包应在各自系统构建与验收。

本轮本机 Rust 为 x86_64 工具链，已验证的开发包为 Intel / Rosetta 版本；Apple Silicon 原生桌面包尚未构建验收。验证结果与本地工件记录见 [DESKTOP.md](../docs/DESKTOP.md)。

测试夹具由 `tests/make_fixture.py` 生成，只有第一方元数据，不含 Minecraft、第三方 Mod 代码、账户或存档。首页方块山林插画和标记为本项目原创 SVG，不是游戏截图。

## 实现入口

- `src/App.tsx`：页面、工作流与本地状态。
- `src/model.ts`：报告校验、实例去重、持久化格式、命令参数引用。
- `src/bridge.ts`：浏览器 / Tauri 能力边界。
- `src-tauri/src/lib.rs`：固定预检命令、超时与输出限制、环境检测、文件导出。
- `src-tauri/capabilities/default.json`：仅开放所需本地对话框；没有 shell 插件。

npm 的可选开发工具 peer 解析在当前环境触发了安装器错误，项目 `.npmrc` 固定 `legacy-peer-deps=true`；提交的锁文件记录实际依赖版本。
