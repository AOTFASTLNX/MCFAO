# GL41 v14 真机复核（2026-11-15 凌晨）

> 对 `docs/GL41_V14_OPERATIONS_2026-11-14.md` 第 8 节「未完成项」的现场核对。
> 结论：**v15 的着色器缓存“修复”建立在一个错误的诊断上，v14 的缓存本来就在工作。**

## 环境

| 项 | 值 |
|---|---|
| 设备 | iPhone（`iPhone17,1`），iOS 27.3，USB 连接 |
| 应用 | `app.perseus4004.sunset349`，`CFBundleVersion 7`（= v14 已签名包） |
| 连接方式 | `pymobiledevice3` house_arrest + `developer dvt launch --userspace` |
| 网络 | 校园 Wi-Fi（`DLOU`）+ USB 共享（`172.20.10.x`） |

## 发现 1：v14 的 Mesa 磁盘缓存已经落盘

`/Documents/Documents/.mesa_shader_cache/mesa_shader_cache_db`：

| 项 | 值 |
|---|---|
| `index` | 1,310,728 字节 |
| 分片目录 | `part0` … `part49`（50 个） |
| 缓存条目文件 | 100 个（每分片 `mesa_cache.db` + `mesa_cache.idx`） |
| 有效数据 | 约 156 KB（集中在 `part0`：`mesa_cache.db` 156,143 B） |

v14 的代码路径是 `$HOME/Documents/.mesa_shader_cache`，其中 `HOME` 已经是应用的 `Documents`，
所以实际目录是 `/Documents/Documents/.mesa_shader_cache`。**`mkdir` 成功了，Mesa 也写入了缓存。**

此前 ChatGPT 侧的判断（“单层 `mkdir` 失败，着色器与管线缓存从未落盘，每次启动都要重新编译”）不成立，
因此 v15（`17fc8b6`）把路径改成 `$HOME/.mesa_shader_cache` 只是**换了个位置**，不构成性能修复。

## 发现 2：冷 / 热启动没有可测差异

方法：把缓存目录改名（`mv .mesa_shader_cache .mesa_shader_cache.bak`）后启动 = 冷；恢复后启动 = 热。
每次运行约 110 秒，取 `[GL41] perf` 每 5 秒采样。

| 运行 | 采样数 | 中位 FPS | 平均 FPS | 最低 | finish 中位 | finishP95 中位 | drops |
|---|---|---|---|---|---|---|---|
| 冷（无缓存） | 22 | 56.5 | 57.3 | 40.8 | 10.07 ms | 14 ms | 0 |
| 热（有缓存） | 18 | 58.7 | 57.1 | 28.9 | 8.79 ms | 11 ms | 0 |

平均帧率 57.3 vs 57.1，差异在噪声范围内。缓存对稳定游玩阶段的帧率没有可测贡献，
这与 v14 已经测出的结论一致：**瓶颈是每帧的提交与 GPU→CPU 回读，不是着色器编译**。

## 发现 3：帧限速器与实际帧率、`maxFps` 不一致（待查）

- 设备上的 `Documents/game/options.txt`：`maxFps:120`、`enableVsync:true`。
- 启动日志：`[GL41] refresh request=80-120 preferred=120 maximum=120 drawables=3`。
- 但同一份日志里有：`[GL41] frame limiter=fixed-timeline fps=60 intervalNs=16666666`。
- 实测帧率却是 65–76 FPS。

即 `FramePacing.limitDisplayFPS` 收到了 `60`，却没把帧率压到 60。三种可能：

1. 补丁替换的调用点不是每一帧都会走到的位置（Minecraft 26.1.2 的调用链变化）；
2. 传进来的 `60` 是 iOS 报告的显示刷新率，而不是 `maxFps`；
3. 固定截止时间的“迟到即重置”分支（`FramePacing.java:31`）在帧时间 < 16.6 ms 时被反复触发，导致限速形同虚设。

需要一次带额外日志的构建来定位（记录调用次数与传入值来源）。

## 结论与下一步

1. **v15 不用下载验证**：缓存已在工作，且对帧率无贡献。v15 的产物（466 MB）在当前网络下不值得再花一小时下载。
2. 真正的提升仍来自渲染管线：把「整帧 GPU→CPU 回读 + CPU 写 Metal 中转纹理」换成 MoltenVK 交换链直出。
3. 另一条低风险线索是发现 3 的限速器异常：如果 iOS 的 ProMotion 实际按 60 Hz 节拍在跑，
   那么即使渲染出 75 帧，呈现仍是 60 Hz 节奏，表现为 `long34` 与不均匀帧间隔。
   可以先加日志定位，再决定是否改成按 `CADisplayLink` 的 `targetTimestamp` 对齐。
4. 新构建的下载是当前最大瓶颈：校园 Wi-Fi 到 CircleCI 产物主机约 1 KB/s；
   USB 共享（蜂窝）单连接约 10 KB/s、8 并发约 79 KB/s，466 MB 需要 30–100 分钟。

## 证据

| 文件 | 内容 |
|---|---|
| `device-2026-11-15/run-1794675623231.log` | 热启动运行日志（01:00） |
| `device-2026-11-15/run-1794675796046.log` | 冷启动运行日志（01:03） |
| `device-2026-11-15/run-1794673898510.log`、`run-1794673966600.log` | 复核前的两次运行（00:31 / 00:32） |
| `device-2026-11-15/cache-tree.txt` | 缓存目录结构与大小 |
