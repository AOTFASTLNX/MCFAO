# BMC5 本地可玩验证（2026-11-16 凌晨）

## 结论

Better MC [NEOFORGE] BMC5 在本机（Windows + 15.3 GB RAM + RTX）**已经能进游戏并正常游玩**，
截图：`C:\Users\zrxma\Desktop\BMC5-可玩-证据.png`（第一人称、快捷栏、小地图、坐标 -46/89/71）。

## 进游戏前的三个拦路问题

| # | 现象 | 根因 | 处理 |
|---|---|---|---|
| 1 | 启动即崩：`ExceptionInInitializerError` → `NullPointerException` at `ScreenCustomization.isCustomizationEnabledForScreen` | FancyMenu 3.9.12 的属性容器未初始化，`LoadingOverlay.<clinit>` 时 NPE | 把 `fancymenu_neoforge_3.9.12_MC_1.21.1.jar` 改名为 `.disabled` |
| 2 | `Mod drippyloadingscreen requires fancymenu 3.9.9 or above` | Drippy Loading Screen 硬依赖 FancyMenu | 把 `drippyloadingscreen_neoforge_3.1.5_MC_1.21.1.jar` 改名为 `.disabled` |
| 3 | 窗口「未响应」，内存警告「3908 MB < 推荐 5907 MB」 | 默认堆只有系统内存的 1/4；本机 15.3 GB，堆 3.9 GB，物理内存只剩 0.3 GB | 启动加 `-Xmx6G`（实际占用 6.6 GB RSS） |

## 启动方式（不经过 PCL，可复现）

```powershell
$env:JAVA_HOME='C:\Users\zrxma\AppData\Roaming\.minecraft\runtime\java-runtime-delta'
$env:JAVA_TOOL_OPTIONS='-Xmx6G'
python D:\harness\work\b1-ci\launch_client.py `
  --root "C:\Users\zrxma\Desktop\我的世界\.minecraft" `
  --version-id "Better MC [NEOFORGE] BMC5" `
  --game-dir "C:\Users\zrxma\Desktop\我的世界\.minecraft\versions\Better MC [NEOFORGE] BMC5"
```

启动耗时约 143 秒（ModernFix 记录），进世界后再读一次资源。

## 用 PCL 玩的话

1. 版本设置 → 高级 → JVM 参数：加 `-Xmx6G`
2. 保持两个 mod 以 `.disabled` 结尾（FancyMenu / Drippy Loading Screen）
3. 不要用 `--demo` 启动（上面复现命令带了 demo，所以是试玩世界）

## 与 B1（iOS）的关系

- 这次验证证明了**整合包本身在本机是可玩的**，后续 iOS 端的对照基线就是它
- 客户端类图谱已在带 agent 的那次运行里落盘（37,403 个类、941 个 `net/minecraft/client/*`），
  但因 FancyMenu 崩溃，图谱不完整；现在崩溃原因已排除，可以再跑一次拿全量客户端图谱
- 全量图谱 → native-image（B1）→ 才是 iOS 可玩的下一关
