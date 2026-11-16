# B1 · Windows AOT 客户端：编译成功并启动，原生崩溃待定位（2026-11-17 凌晨）

## 成果

| 步骤 | 结果 |
|---|---|
| VS Build Tools（C++ 工作负载） | ✅ 装在 `C:\BuildTools`，`cl.exe` 可用 |
| GraalVM 架构探测 bug | ✅ `-H:-CheckToolchain` 绕过 |
| **Windows 客户端镜像** | ✅ **395 MB**，`Finished generating 'b1client-new' in 17m 15s`（11 GB 堆 + `-Ob`） |
| 启动 | ✅ 走完 `ClientMain` 的环境注入 → `Main.main`（22 个参数） |
| 进入游戏 | ❌ 原生崩溃 `0xc0000005`（APPCRASH，无 Java 异常） |

## 本轮修掉的问题

| 问题 | 处理 |
|---|---|
| EuphoriaPatcher 在游戏启动时调 OSHI/JNA，镜像里没有 JNA 本地库 | 用空实现替换 `EuphoriaPatcher`（光影已关，它无事可做） |
| 首次运行时 `NoClassDefFoundError: com.sun.jna.Platform` | 同上 |
| 13 GB 堆时 JVMCI 自身崩溃（`jvmciRuntime.cpp:1010`） | 降到 11 GB 堆 + 2 线程后构建稳定 |

## 构建耗时参考（本机 15.3 GB 内存）

| 堆 | 结果 |
|---|---|
| 6 GB | GC overhead limit exceeded |
| 10 GB | 内存抖动，40 分钟后失败 |
| 12 GB | 分析阶段后 JVMCI 崩溃 |
| **11 GB + `-Ob` + 2 线程** | ✅ 17 分 15 秒，395 MB |

## 当前的崩溃

```
事件名称: APPCRASH
异常代码: 0xc0000005 (access violation)
出错模块: b1client-new.exe
```

崩溃发生在 `Main.main` 刚进入、mod 初始化早期；日志停在 `starting net.minecraft.client.main.Main with 22 args` 之后。
没有 Java 层异常，也没有 crash-reports，说明是 native 层（最可能是 JNI/本地库调用，或某个被替换的 stub 与 native 路径交互）。

## 下一步定位手段（下一轮）

1. 用 WER LocalDumps 抓崩溃转储，配 `b1client-new.pdb`（native-image 可生成 `-H:+SourceLevelDebug`? 至少用 `dumpbin /disasm` 定位偏移）；
2. 缩小变量：临时把 `overrides` 里的 stub（ImmediateWindowHandler / BackgroundWaiter / NativeModuleLister / Euphoria）逐个还原，看哪个引入崩溃；
3. 或者先跑一个「只到 `Bootstrap.validate()`、不建窗口」的入口，确认崩溃是否发生在窗口/GL 路径。

## 状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM） | ✅ 448 mods、光影关、89.95 秒进主菜单 |
| 静态运行期（注册表） | ✅ 1,060 / 1,333 / 130 |
| AOT 客户端：CI macOS | ✅ 357 MB，跑到渲染初始化（无 GPU 提供不了上下文） |
| AOT 客户端：Windows 本机 | ✅ 395 MB，能启动，跑到 `Main.main` 后 native 崩溃 |
| iOS | ⏳ 需 A1 iOS 运行时 + headless glfw |

## 顺带

- CircleCI 的 macOS 作业连续被 cancel（8~9 分钟处），判断是免费额度/macOS 分钟耗尽，
  后续 CI 侧验证要等额度恢复或换执行环境。
- `ci/headless_glfw.c` 已写好（GLFW 子集 + OSMesa 上下文），等 CI 可用后即可验证无 GPU 渲染。
