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

## 发现 3：限速器先按 60 起跑、选项加载后切到 120（不是缺陷）

- 设备上的 `Documents/game/options.txt`：`maxFps:120`、`enableVsync:true`。
- 启动日志：`[GL41] refresh request=80-120 preferred=120 maximum=120 drawables=3`。
- 同一次运行里限速器有两行：

```
[17:00:25] [GL41] frame limiter=fixed-timeline fps=60 intervalNs=16666666
[17:00:54] [GL41] frame limiter=fixed-timeline fps=120 intervalNs=8333333
```

即应用启动时先按默认 60 起跑，约 29 秒后（选项加载完成）切到 120。四个日志文件的规律一致
（`run-1794673898510` 只跑到加载阶段，故只有 60 那行）。

结论：不是限速器缺陷，但**进世界前的加载窗口是按 60 Hz 节拍跑的**，如果后续要优化「进世界第一分钟」，
这一段值得单独处理（例如在 `FramePacing` 里对加载期按 120 节拍，或直接跳过限速）。

## 结论与下一步

1. **v15 不用下载验证**：缓存已在工作，且对帧率无贡献。v15 的产物（466 MB）在当前网络下不值得再花一小时下载。
2. 真正的提升仍来自渲染管线：把「整帧 GPU→CPU 回读 + CPU 写 Metal 中转纹理」换成 MoltenVK 交换链直出。
3. 另一条低风险线索是加载窗口：进世界前的约 30 秒仍按 60 Hz 节拍限速（发现 3），
   这一段恰好也是 `long34` 最密集的阶段；可以先让 `FramePacing` 在加载期按 120 节拍走，成本很小。
4. 新构建的下载是当前最大瓶颈：校园 Wi-Fi 到 CircleCI 产物主机约 1 KB/s（且 GitHub 已出现连接重置）；
   USB 共享（蜂窝）单连接约 10 KB/s、8 并发约 79 KB/s，466 MB 需要 30–100 分钟。

## 证据

| 文件 | 内容 |
|---|---|
| `device-2026-11-15/run-1794675623231.log` | 热启动运行日志（01:00） |
| `device-2026-11-15/run-1794675796046.log` | 冷启动运行日志（01:03） |
| `device-2026-11-15/run-1794673898510.log`、`run-1794673966600.log` | 复核前的两次运行（00:31 / 00:32） |
| `device-2026-11-15/cache-tree.txt` | 缓存目录结构与大小 |
