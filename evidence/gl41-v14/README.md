# GL41 v14 证据包

对应版本记录：`docs/GL41_V14_OPERATIONS_2026-11-14.md`

- **版本**：v14（帧时间诊断版），MCFAO `bb65fee`，CircleCI 作业 119
- **设备**：iPhone 16 Pro，应用 `app.perseus4004.sunset349`，Bundle 版本 7
- **结论**：稳定游玩约 71 FPS；分辨率减半不改善，瓶颈在每帧提交+同步。

## 目录

| 路径 | 内容 |
|---|---|
| `FabricAOT-GL41-v14-README.txt` | v14 发布说明（原始交付件） |
| `perf-v14.md` | 实测表、日志字段说明、测量方法 |
| `logs/*-build.log` | 各版本 CircleCI 构建日志（v1、v7–v13） |
| `logs/*-full.json` | 作业完整 JSON（步骤耗时、源码 SHA） |
| `logs/gl41-jobs.json` | 作业 101–120 的提交/状态/时间 |
| `logs/run-*.log` | 真机 `c0-logs` 运行日志（含 `[GL41] perf` 采样） |
| `device/run-*.log` | 设备容器内抓取的启动日志 |
| `configs/options-*.txt` | 游戏内 `options.txt` 快照（比例、限帧、渲染距离） |
| `configs/watcher-status.txt` | 日志监听器状态（USB 连接异常记录） |
| `scripts/bench*.{ps1,py}` | 基准测试与统计脚本 |
| `scripts/steady_run.py` | 稳态复测脚本 |
| `scripts/install-frame-diag.ps1` | 签名 + 安装 + 启动 + 版本校验 |
| `scripts/circle-*.js` | CircleCI 产物地址/下载/修复脚本 |
| `scripts/gl41-audit-*.py` | IPA 审计脚本（校验源码 SHA、渲染器配置） |
| `scripts/ls3.py`、`ls_cache.py`、`mk.py` | 通过 house_arrest 访问应用 Documents 的小工具 |
| `screenshots/diag-screen.png` | v14 真机画面 |
| `device-2026-11-15/` | 2026-11-15 凌晨真机复核：冷/热启动日志、Mesa 缓存目录实际结构（`cache-tree.txt`） |

## 未包含

- **IPA 二进制**：单文件 466 MB / 483 MB，超过 GitHub 100 MB 限制，且含授权游戏资源，不入库。
  版本由 SHA-256 锁定（见 `FabricAOT-GL41-v14-README.txt`）。
- **CircleCI 令牌 / 证书口令 / 签名 p12**：一律不入库。
- 原始 `artifact-url.txt`（含 S3 预签名 URL 与会话令牌）已剔除。
