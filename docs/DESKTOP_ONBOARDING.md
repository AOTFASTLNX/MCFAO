# 桌面首次引导与账号

Last reviewed: 2026-11-18

## 使用流程

macOS 桌面应用初次启动显示四步引导，顶部进度条随步骤推进：使用须知 → 正版登录 → 储存目录 → 完成配置。使用须知说明独立第三方身份、游戏文件本地获取及个人 IPA 分发边界。完成页可启动「一键下载并准备」或选择「稍后下载」。稍后可从「环境与资源」继续准备。

`DesktopSession.tsx` 位于工作台外层。工作台在首次引导结束后打开。准备任务由用户点击启动，离开引导后仍可在工作台看到进度。`ncl.onboarding.v1` 只保存须知确认、目录选择及完成标记；账号资格由原生服务读取。点击「开始使用」或「稍后下载」后记录引导完成。已完成引导但账号需要重新验证时，显示账号恢复页面，保留配置。

目录只选择一个总目录，复用 `unifiedStoragePaths`、`storage-change-plan` / `storage-change-apply` 与 `StorageChangeDialog`。自动配置 `cache`、`builds`、`jobs`、`rust`；存在旧文件时由用户选择保留、迁移或删除，删除需原有二次确认。取消不提交配置。表单路径重映射由 `storageFormPatch` 与设置共用。

设置首组为「账号管理」，显示 Minecraft 档案名、档案 ID、最近验证时间和资格状态，可重新验证或切换账号。有构建任务或其他工作台操作进行时暂停切换。旧的「我合法拥有」勾选声明由实际验证状态替代。

动效复用 `useStepContent` / `StepBody` 和全局时间、缓动、主题及强调色变量；前进/后退具有方向连续性，减少动态效果偏好下取消位移和进度插值。新页面在步骤切换后将焦点放到标题。

## 账号与凭证边界

`tools/account_service.py` 是独立第一方服务，由 Rust `account_action` 调用，与用户可选择的工作空间 / Python 配置分开。应用只打开固定的 Microsoft 登录网址，使用 OAuth device code：Microsoft → Xbox 用户认证 → XSTS → Minecraft 服务 → 正版 entitlement 与有效 Java 档案。

HTTP 限于四个固定官方 HTTPS 主机，拒绝重定向，响应大小与请求时间受限。错误不回传提供方原始响应。刷新令牌、设备令牌及待切换会话通过 Security.framework 保存在 macOS 登录钥匙串的 `org.fabricaot.desktop.microsoft` 服务中；不写入 localStorage、构建缓存、任务请求、日志或 IPA。UI 仅接收档案、验证时间与短期用户验证码。不会把桌面账号令牌注入游戏或 IPA。

验证结果最长缓存一小时，应用重开时重新验证；到期前尝试刷新。网络失败或授权撤销使权限失效，但保留可供重新验证的账号身份。刷新令牌轮换在后续验证前保存。新账号完整验证后先保存在待提交会话中，UI `commit` 后才替换当前账号；取消或失败保留原有效账号。

Rust 在 `start`、`retry`、`setup-start` 前调用原生 `require`，不信任前端完成标记或 `{owned:true}`。这是桌面构建入口的门禁，不改变研发 CLI 的使用方式，也不是本地开源程序的防篡改机制。

## App ID 审核期间的本地测试包

在 `desktop` 目录运行 `npm run build:mac -- --local-testing` 可构建标有「本地测试版」的免登录包。它跳过引导中的账号步骤，并允许直接准备环境、生成配置与构建 IPA。这个开关在编译时由 Rust 功能标记决定。发布时使用默认的 `npm run build:mac` 打包，构建入口会要求正版验证。

## 申请和配置自己的 Client ID

1. 打开 [Microsoft Entra 管理中心](https://entra.microsoft.com/)，进入 **Entra ID → 应用注册 → 新注册**。使用自己的租户及具备应用注册权限的账号。名称可填 `NCL Builder`，账号类型选 **仅个人 Microsoft 账号**（或包含个人账号的类型）。注册后在「概述」复制 **应用程序（客户端）ID / Application (client) ID**。官方步骤和前置条件见 [应用注册文档](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)。注册/租户条件以门户当前要求为准。
2. 在应用的 **身份验证 → 高级设置** 中将 **允许公共客户端流 / Allow public client flows** 设为 **是**并保存。本工程使用设备代码流，不需要回调地址或客户端密钥。见 [Microsoft 桌面公共客户端配置](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration#enable-public-client-flow) 及 [device code 协议](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code)。
3. 将公开的 UUID 写入 `compiler/microsoft-auth.json` 的 `clientId`，再重新打包桌面应用。开发调试也可通过 `NCL_MICROSOFT_CLIENT_ID` 环境变量覆盖；环境变量属于运行进程配置，Finder 启动的分发应用应使用包内配置。
4. 必须实际完成 Microsoft、Xbox、Minecraft 各阶段验证。取得 Entra ID 不代表 Minecraft 服务一定接受该应用；遇到 `403 / Invalid app registration` 或 Xbox 授权拒绝时，应向 Microsoft / Minecraft 官方支持确认当前第三方应用准入流程，并提交项目自己的 Client ID 处理。不要将普通 Microsoft Graph 权限当作游戏 API 授权，也不要承诺注册后立即可登录。

该配置只需要公开的 Client ID。当前 `clientId` 留空时 UI 显示「登录服务待配置」，允许用户点击「暂时跳过正版验证」完成引导并进入工作台。跳过标记只在未配置 Client ID 时生效；原生 require 在未配置时返回未验证的暂缓状态，允许本地输入构建与工具链准备。配置 Client ID 后自动恢复资格验证。官方游戏资源下载仍需要账号验证。

Xbox token 交换依据 [Microsoft Xbox 服务认证说明](https://learn.microsoft.com/en-us/gaming/gdk/docs/services/fundamentals/s2s-auth-calls/service-authentication/live-website-authentication)。Minecraft license / profile 的路径与字段交叉核对了 [Prism Launcher 的 entitlement 实现](https://github.com/PrismLauncher/PrismLauncher/blob/develop/launcher/minecraft/auth/steps/EntitlementsStep.cpp)、[解析器](https://github.com/PrismLauncher/PrismLauncher/blob/develop/launcher/minecraft/auth/Parsers.cpp)、[profile 请求](https://github.com/PrismLauncher/PrismLauncher/blob/develop/launcher/minecraft/auth/steps/MinecraftProfileStep.cpp)；服务实际是否接受本项目须等待自己的应用注册和真实账号验证。

## 验证

- `python3 -B -m unittest discover -s tests -p test_account_service.py -v`：官方响应夹具、无资格 / 错误身份拒绝、轮询间隔、取消 / 提交、刷新失败、凭证输出边界。
- `cd desktop && npm test && npm run build`：引导恢复、完成条件、路径映射及前端编译。
- `cd desktop && npx playwright test tests/onboarding.spec.ts`：四步流程、设置首行、未配置阻断、目录取消 / 已有文件、账号切换、深浅色、最小窗口 / 小预览及减少动态效果。
- `cd desktop && cargo test --manifest-path src-tauri/Cargo.toml --lib`：账号动作 allowlist 与构建入口分类。

浏览器默认仍用于工作台的静态预览；`?onboarding` 可预览引导首屏。自动化测试模拟原生 IPC 和官方响应，不是实际 Microsoft 登录。当前尚无 Client ID，真实登录、账号切换、Keychain 完整会话及真实所有权验收均 **NOT RUN**。游戏 AOT、IPA、真机和性能 Gate 不因本 UI 修改而提升。

2026-11-18 验证：前端构建通过，87 项前端单测、78 项浏览器交互（其中 10 项引导 / 账号）、15 项账号服务、32 项源码打包 / 桌面便携性、12 项 Rust 测试全部通过。浏览器最终使用已编译前端快照及独立端口，避免共享开发服务和热重载干扰。截图、原始 JSON 报告、构建日志与测试日志位于 `artifacts/desktop/onboarding/`，汇总为 `verification.json`；`tested-frontend.json` 记录受测静态文件哈希。
