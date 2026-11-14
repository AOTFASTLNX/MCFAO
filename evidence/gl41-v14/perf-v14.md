# GL41 v14 真机实测记录

- 设备：iPhone 16 Pro（未越狱，USB 连接）
- 应用：`app.perseus4004.sunset349`，`CFBundleVersion 7`（zsign `-r 7`）
- 版本：v14 = MCFAO `bb65fee`（帧时间诊断）/ CircleCI 作业 119
- 存档：沿用设备上的「新的世界」
- 方法：地形加载稳定后，取 80 秒窗口，每 5 秒一条 `[GL41] perf` 采样，统计中位/最低与 p95

## 一、主对比（同一存档、同一场景）

| 配置 | 中位 FPS | 最低 FPS | finishP95 | outsideSwapP95 |
|---|---|---|---|---|
| **80% 内部比例，120 档（最终保留）** | **71.3** | **44.2** | **13 ms** | **7 ms** |
| 内部比例 50% | 65.0 | 41.6 | 13 ms | 19 ms |
| 游戏内限 60 FPS | 49.8 | 34.8 | 15 ms | 15 ms |
| `ZINK_DESCRIPTORS=lazy` | 36.9 | 18.8 | 17 ms | 45 ms |
| zink 提交参数 db | 51.4 | 34.8 | 14 ms | 21 ms |
| MVK 异步提交 | 45.2 | 34.1 | 17 ms | 26 ms |
| MVK MPS 深度模板 | 47.0 | 29.1 | 15 ms | 25 ms |
| GL 线程化 | 46.2 | 28.5 | 15 ms | 25 ms |

结论：

1. 分辨率减半后 `finishP95` 不变（13 ms），说明瓶颈是每帧固定的提交+同步，不是像素填充。
2. 所有候选调参均更慢，已回滚；最终保留 80% 比例 + 120 档 + 现有等待策略。
3. 呈现层 `drops=0`，三重缓冲未成为瓶颈。
4. 刚进世界约 1 分钟内仍会掉到 40 FPS 左右，长帧集中在「提交前」阶段（区块网格上传与绘制提交）。

## 二、日志采样格式

```
[GL41] first render size 2098x965
[GL41] perf fps=71.2 finish=9.7ms present=1.1ms finishP95=13ms outsideSwapP95=7ms
[GL41] display fps=71.6 p95=21ms long34=0 drops=0
```

字段含义：

| 字段 | 含义 |
|---|---|
| `finish` | 本窗口平均「提交 → glFinish 完成」耗时（GPU + 回读） |
| `present` | 本窗口平均 CPU 写入 Metal 中转纹理并提交呈现的耗时 |
| `finishP95` | 上述 finish 的 95% 分位 |
| `outsideSwapP95` | 上一帧呈现完成 → 进入本帧 swap 的 95% 分位 |
| `display.p95` | 呈现层帧间隔 95% 分位 |
| `drops` | 3 个中转纹理都在途而丢弃的帧数（正常为 0） |

## 三、测量脚本

见 `scripts/`：

- `bench.ps1` / `bench_run.py`：按参数组合跑一轮并拉日志
- `bench_stats.py`：从 `c0-logs` 解析 `[GL41] perf` 行，输出中位/最低/p95
- `steady_run.py`：固定配置的稳态复测
- `install-frame-diag.ps1`：签名 + 安装 + 启动 + 校验版本的一体化脚本

> 注意：短窗口（< 60 秒）受区块加载波动影响很大，同一配置两次结果可差 10 FPS 以上，
> 因此结论一律以 80 秒稳定窗口为准。
