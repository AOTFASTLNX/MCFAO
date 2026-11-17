# B1 · CI 迁移到 GitHub Actions（2026-11-17 上午）

## 为什么要换

CircleCI 的 macOS 作业连续在 8~9 分钟处被取消（`canceled`），判断是 macOS 分钟/额度耗尽。
仓库 `zhangrongxue/mc-aot-ios` 是**公开仓库**，GitHub Actions 对公开仓库的 macOS / Windows
runner **不计入免费额度**，于是把 B1 的构建迁到 Actions。

## 新流水线

`.github/workflows/b1-client-windows.yml`（触发：`workflow_dispatch` 或推送到 `build/b1-n0`）：

| 步骤 | 说明 |
|---|---|
| Install GraalVM 21 | 下载 GraalVM CE 21.0.2 Windows 版 |
| Fetch graph + overrides | 用仓库 secret `GH_PAT` 从私有 release 拉图谱与 overrides 层 |
| Build client image | `runs-on: windows-2022`（VS 2022），`vswhere` 定位 VC 工具链，12 GB 堆 + 2 线程 + `-Ob` |
| Upload | 产出 `b1client.exe`（394 MB）作为 artifact |

已跑通两次：**build 成功**（约 12 分钟），artifact 可下载。

### 踩过的坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `Failed to find 'vcvarsall.bat'` | `windows-latest` 现在是 Windows 2025 + **VS 2026**，GraalVM 21.0.2 只认 VS 2022 | 改用 `windows-2022` |
| 同上 | 把 VS 路径写死 | 用 `vswhere.exe` 动态取安装路径 |
| `OutOfMemoryError` | 10 GB 堆不够 | 12 GB + 2 线程 |
| 图谱里还带着旧的 Euphoria | overrides 只改在本地、没上传 | 上传 overrides（含 `EuphoriaPatcher` 空实现）后重编 |

## 当前阻塞：原生崩溃（未解决）

CI 产物在本机运行：

```
starting net.minecraft.client.main.Main with 22 args
→ 进程退出（0xc0000005 access violation，无 Java 异常、无 LWJGL 日志）
```

因为连 `-Dorg.lwjgl.util.Debug=true` 都没有任何输出，崩溃发生在 **LWJGL 加载之前**，
即 `Main.main` 早期的某条 native 路径（也可能是我们替换的 stub 与 native 交互）。

## 下一步定位

1. 用 Sysinternals **procdump** 抓 crash dump（不需要管理员），至少拿到 faulting 线程的栈；
2. 或逐个还原 overrides 里的 stub（ImmediateWindowHandler / BackgroundWaiter / NativeModuleLister / Euphoria / ModernFix 插件）二分定位；
3. 也可先做一个「不进入 Main、只到 Bootstrap.validate()」的入口，确认崩溃是否在客户端初始化路径。

## 关于「重新注册 CircleCI 账号」

技术上可以（需要另一个 GitHub 账号，免费额度按账号算），但没必要：

- 我们的仓库是公开的，**GitHub Actions 已经免费**且支持 macOS/Windows runner，已经跑通；
- CircleCI 免费额度里 macOS 分钟最贵，换号也只是再来一次额度枯竭；
- 新号还可能在合规上被视为规避额度。

建议就留在 GitHub Actions 上。
