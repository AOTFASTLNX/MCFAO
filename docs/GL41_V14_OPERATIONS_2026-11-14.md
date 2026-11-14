# GL41 v14 版本与操作全记录（2026-11-14）

> 本文把 2026-11-14 一整天在 GL41 渲染线上做过的全部操作、版本、构建、真机实测与结论固化到仓库里。
> 目标版本：**v14（帧时间诊断版）**。源码提交 `bb65fee`，CircleCI 作业 **119**，真机已签名安装。
> 更早的阶段（AOT 工具链、启动器 UI、World v21 线）见文末第 7 节与 `docs/` 下既有文档。

---

## 1. 目标与架构

- 目标：在**未越狱 iPhone** 上本地运行 **Minecraft Java Edition 26.1.2（原版）+ Fabric**，不依赖 JIT、调试器或远程串流；画面、逻辑、存档全部在手机上执行。
- GL41 是本轮引入的渲染路径，用来替换原来的 Metal 直连后端：

```
Minecraft (Java) → LWJGL-lite GlBackend
   → libOSMesa（Mesa OSMesa 8.x，GL 4.1）
      → zink（Gallium 的 Vulkan 驱动）
         → MoltenVK（Vulkan → Metal）
            → CAMetalLayer（三重缓冲）
```

- 呈现路径：OSMesa 渲染到 BGRA 缓冲 → `faot_surface_present_bgra` 回读 → 写入 3 个中转 Metal 纹理（带信号量）→ `CAMetalLayer` 上屏。
- 关键环境变量（`ios/glfw-lite/osmesa_gl.c` 的 `load_api()` 设置）：
  `GALLIUM_DRIVER=zink`、`MESA_GL_VERSION_OVERRIDE=4.1`、`MESA_GLSL_VERSION_OVERRIDE=410`、
  `MESA_EXTENSION_OVERRIDE=-GL_ARB_direct_state_access`、`mesa_glthread=false`、
  `MVK_CONFIG_FAST_MATH_ENABLED=2`、`MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=1`。

---

## 2. 版本演进一览（GL41 线，2026-11-14）

全部构建在 CircleCI `zhangrongxue/mc-aot-ios` 项目、macOS `m4pro.medium` 执行器（Xcode 27.1.0）上完成，
每次构建固定 `UPSTREAM=https://github.com/AOTFASTLNX/MCFAO` 的 `SOURCE_SHA`，产物为未签名 IPA，
下载后本地用 zsign + 个人证书签名再 USB 安装。

| 作业 | CI 提交 | 时间(北京) | MCFAO 源码 | 变更 | 结果 |
|---|---|---|---|---|---|
| 102 | `b1418d0` | 11-14 10:23 | `5eebefc3` | Build vanilla client with OpenGL 4.1 renderer | failed |
| 103 | `8f83627` | 11-14 10:33 | `9606ef1a` | Pin OpenGL 4.1 build to GLFW fixture fix | canceled |
| 104 | `b9b1bd2` | 11-14 10:34 | `79f3032b` | Pin OpenGL 4.1 build to shim warning fix | success |
| 105 | `01fdd0c` | 11-14 10:53 | `0d9fe55d` | Pin GL41 build to context fallback | success |
| 106 | `f85290c` | 11-14 11:26 | `d91dc4f0` | Pin GL41 build to context discovery fix | success |
| 107 | `a7fdb5e` | 11-14 12:11 | `045685fc` | Pin GL41 build to static JNI dispatch fix | success |
| 108 | `794bf11` | 11-14 12:46 | `e7182bc7` | Pin GL41 build to load-wait bypass | success |
| 109 | `aa092b0` | 11-14 13:40 | `a716aa4b` | Pin GL41 performance build | failed |
| 110 | `dea0cc7` | 11-14 13:40 | `75245a9c` | Pin GL41 performance build to warning fix | success |
| 111 | `215ffef` | 11-14 14:10 | `85f09322` | Pin GL41 native-resolution build（v7） | success |
| 112 | `0e1b661` | 11-14 14:44 | `93bac372` | Pin GL41 chunk-wait bypass build | success |
| 113 | `e03479f` | 11-14 15:08 | `9a759269` | Build the GL41 world-join fix with diagnostics | success |
| 114 | `46fbfdd` | 11-14 16:28 | `bacc9962` | Build GL41 asynchronous presentation test IPA | success |
| 115 | `3faee08` | 11-14 17:32 | `eabc5064` | Build GL41 120 Hz pacing profile | success |
| 116 | `52b5f34` | 11-14 18:39 | `bf999cd6` | Build GL41 80% scale steady-60 profile | failed |
| 117 | `f2c9fb0` | 11-14 18:50 | `affd1c16` | Rebuild after scaled-size fixture fix | success |
| 118 | `3c45456` | 11-14 19:49 | `8637ce3d` | Build GL41 v13 uncapped scaled profile | success |
| **119** | **`abc084a`** | **11-14 20:47** | **`bb65fee8`** | **Build GL41 frame timing diagnostic IPA（v14）** | **success** |
| 120 | `b913a75` | 11-14 22:10 | `17fc8b6a` | Build GL41 shader cache profile（v15） | success |

各版本解决的核心问题（按源码提交）：

| 版本 | 源码提交 | 解决的问题 | 真机现象 |
|---|---|---|---|
| v1–v2 | `5eebefc`→`0d9fe55` | 引入 OpenGL 4.1 渲染路径、最小 OSMesa 上下文回退 | 首个能出画面的 GL41 包 |
| v3 | `d91dc4f` | 修正 LWJGL 上下文发现、关闭 4.5 DSA 扩展 | 不再因缺少 4.5 入口闪退 |
| v4 | `045685f` | 允许 GL 初始化期间使用静态 JNI 派发 | 修掉 JNI 表崩溃 |
| v5 | `e7182bc` | 绕过客户端卡死的加载等待、接受非活跃启动场景 | 能通过加载界面 |
| v6 | `a716aa4`/`75245a9` | 三重缓冲 + 缩放呈现、性能优化 | 帧率从 31 提升 |
| v7 | `85f0932` | 恢复原生 2622×1206 渲染、关闭 Mesa GL 线程队列 | 修复界面被裁切 |
| v8 | `93bac37` | 进世界后绕过区块可见性门 | 村庄/地形能加载出来 |
| v9 | `9a75926` | 保留世界就绪状态并诊断 join 卡顿 | 减少进世界卡死 |
| v10 | `bacc996` | 把 drawable 等待移出游戏线程 | 提升呈现稳定性 |
| v11 | `eabc506` | 解锁 120 Hz 节拍、预分配 GL uniform | 高刷机型跑满 |
| v12 | `bf999cd` | 内部渲染缩到 80%、稳定阶段 60 FPS 上限 | 出现「更卡」，故 v13 回调 |
| v13 | `8637ce3` | 去掉帧率上限、修正 park 超调 | 放开限帧后回到 70 FPS 级 |
| **v14** | **`bb65fee`** | **增加 `finishP95` / `outsideSwapP95` 每帧分段统计** | 定位瓶颈：提交前 vs GPU 同步 |
| v15 | `17fc8b6` | 把 Mesa 着色器/管线缓存持久化到 Documents | 未完成验证（见第 8 节） |

---

## 3. v14 版本内容

### 3.1 改动

`bb65fee` 只加统计、不改画面与等待策略：

- `ios/glfw-lite/osmesa_gl.c` 新增两组 1 ms 直方图：
  - `finishP95`：渲染提交 → `glFinish` 完成（GPU + 回读）的 95% 分位；
  - `outsideSwapP95`：上一帧呈现完成 → 进入本帧 swap 的 95% 分位。
- 每 5 秒汇总输出一行：
  `[GL41] perf fps=71.2 finish=9.7ms present=1.1ms finishP95=13ms outsideSwapP95=7ms`
- 另有 `[GL41] display fps=71.6 p95=21ms long34=0 drops=0` 呈现层统计。
- 统计本身不引入额外 GPU 等待，因此不会影响帧率。

### 3.2 产物与校验

| 文件 | 大小（字节） | SHA-256 |
|---|---|---|
| `FabricAOT-GL41-v14-unsigned.ipa` | 466,753,894 | `e408dce1ddfa21d15891602314f5dc47acf7c0a57d0d986df707f9a79ed7f9ce` |
| `FabricAOT-GL41-v14-signed.ipa` | 483,562,228 | `df79bfafd6fdd09d4fcc8ef03d8995ad67dea5835ae1b01864692b1df46b4aa7` |

- Bundle：`app.perseus4004.sunset349`，`CFBundleVersion = 7`（zsign `-r 7`）。
- 安装方式：`python -m pymobiledevice3 apps install <signed.ipa>`，随后 `developer dvt launch --userspace`。
- 启动日志关键行：`[GL41] first render size 2098x965`。

### 3.3 真机数据（iPhone 16 Pro，同一存档，地形加载稳定后 80 秒窗口）

| 配置 | 中位 FPS | 最低 FPS | 渲染同步 p95 | 提交前耗时 p95 |
|---|---|---|---|---|
| **当前配置（80% 内部比例，120 档）** | **71.3** | **44.2** | **13 ms** | **7 ms** |
| 内部比例降到 50% | 65.0 | 41.6 | 13 ms | 19 ms |
| 游戏内限 60 FPS | 49.8 | 34.8 | 15 ms | 15 ms |
| `ZINK_DESCRIPTORS=lazy` | 36.9 | 18.8 | 17 ms | 45 ms |
| `zink` 提交参数 db | 51.4 | 34.8 | 14 ms | 21 ms |
| MVK 异步提交 | 45.2 | 34.1 | 17 ms | 26 ms |
| MVK MPS 深度模板 | 47.0 | 29.1 | 15 ms | 25 ms |
| GL 线程化（`mesa_glthread`） | 46.2 | 28.5 | 15 ms | 25 ms |

### 3.4 结论

1. **瓶颈不是像素填充**：分辨率砍一半（80%→50%）后 `finishP95` 仍是 13 ms，帧数反而略降。
2. **瓶颈是每帧固定的提交 + 同步开销**：整帧 GPU→CPU 回读，再 CPU 写入 Metal 中转纹理。
3. **限帧反而更慢**：60 FPS 限帧把中位帧数压到 49.8，因为限帧等待本身计入每帧成本。
4. **候选的 Mesa/MVK 调参全部更慢**（见 3.3 后六行），已全部放弃，保留默认参数。
5. 刚进世界的第一分钟，长帧主要落在「提交前」阶段，即区块网格上传与绘制提交，而不是 GPU 同步。

---

## 4. 复现步骤

### 4.1 触发云端构建（v14 配置）

CI 仓库：`https://github.com/zhangrongxue/mc-aot-ios`，分支 `build/gl41-renderer-2026-11-14`，提交 `abc084a`。
其 `.circleci/config.yml` 关键部分（完整快照见 `ci/snapshots/circleci-v14.yml`）：

```yaml
environment:
  UPSTREAM: https://github.com/AOTFASTLNX/MCFAO
  SOURCE_REF: fix/recollection3-fabric-pipeline
  MCFAO_OPT_LEVEL: -O3
steps:
  - run:
      command: |
        set -euo pipefail
        mkdir -p ~/build && cd ~/build
        curl -fsSL -o build_mac.sh https://raw.githubusercontent.com/AOTFASTLNX/MCFAO/bb65fee877fdcc339f588100c28299022e56c0c2/ci/build_mac.sh
        MCFAO_TOKEN="$MCFAO_TOKEN" FAOT_RENDERER=gl41 FAOT_BUILD_LOADER=vanilla HEAP_GIB=9 JOBS=6 AOT_PAR=4 SLIM_ASSETS=0 \
          UPSTREAM="$UPSTREAM" SOURCE_REF="$SOURCE_REF" SOURCE_SHA=bb65fee877fdcc339f588100c28299022e56c0c2 bash build_mac.sh
```

- 执行器：`macos` / `xcode: 27.1.0` / `resource_class: m4pro.medium`。
- 构建脚本：仓库内 `ci/build_mac.sh`（同一 `SOURCE_SHA`）。
- 单次构建耗时约 17 分钟（作业 119：20:47 → 21:04 北京时间）。
- 产物：`~/mcfao-build/FabricAOT-game.ipa` + `build.log`，通过 CircleCI artifacts 取出。

### 4.2 取产物

```bash
# 列 artifacts（需要 Circle-Token）
curl -H "Circle-Token: $CIRCLE_TOKEN" \
  https://circleci.com/api/v1.1/project/github/zhangrongxue/mc-aot-ios/119/artifacts
# 下载（单连接 + 断点续传，避免并发分块产生空洞）
curl -L -C - -o FabricAOT-GL41-v14-unsigned.ipa <artifact-url>
```

> 教训：并发分块下载一旦中断会留下**零填充空洞**，zip 中央目录随之损坏。
> 归档时本机一份 v15 未签名包就因此损坏（112 个 4 MiB 块中 73 块全零、找不到 EOCD）。
> 下载后务必 `zipfile.testzip()` 或对比 `Content-Range` 总长度再使用。

### 4.3 本地签名 + 安装

```powershell
zsign.exe -q -z 1 -k identity.p12 -p <p12密码> -m device.mobileprovision \
  -b app.perseus4004.sunset349 -r 7 -o FabricAOT-GL41-v14-signed.ipa FabricAOT-GL41-v14-unsigned.ipa
python -m pymobiledevice3 apps install FabricAOT-GL41-v14-signed.ipa
python -m pymobiledevice3 apps query app.perseus4004.sunset349   # 核对 CFBundleVersion=7
python -m pymobiledevice3 developer dvt launch --userspace app.perseus4004.sunset349
```

### 4.4 抓日志与性能数据

```bash
# 应用容器路径：Documents/c0-logs/*.log，Documents 即 HOME
python -m pymobiledevice3 apps afc app.perseus4004.sunset349 ls /Documents/c0-logs
```

- 关注行：`[GL41] first render size`、`[GL41] perf fps=...`、`[GL41] display fps=...`。
- 基准脚本与统计脚本见 `evidence/gl41-v14/scripts/`（`bench.ps1`、`bench_run.py`、`bench_stats.py`、`steady_run.py`）。

---

## 5. 证据文件索引（`evidence/gl41-v14/`）

| 路径 | 内容 |
|---|---|
| `FabricAOT-GL41-v14-README.txt` | v14 发布说明（原始交付件） |
| `perf-v14.md` | 完整实测表、日志字段说明、测量方法与被否决的候选 |
| `logs/gl41-jobs.json` | 作业 101–120 的提交、状态、时间 |
| `logs/gl41-v1-build.log`、`gl41-v7-build.log` … `gl41-v13-build.log` | 各版本的 CircleCI 构建记录 |
| `logs/gl41-v10-build-full.json`、`gl41-v11-full.json`、`gl41-v12-full.json` | 作业完整 JSON（步骤耗时、源码 SHA） |
| `logs/run-*.log`、`device/run-*.log` | 真机 `c0-logs` 运行日志（含 `[GL41] perf` 采样） |
| `scripts/bench*.{ps1,py}`、`steady_run.py` | 真机基准、稳态测量脚本 |
| `scripts/install-frame-diag.ps1` | 签名 + 安装 + 启动 + 版本校验 |
| `scripts/circle-*.js`、`gl41-audit-*.py` | 取产物、审计 IPA 的脚本 |
| `scripts/ls3.py`、`ls_cache.py`、`mk.py` | 通过 house_arrest 访问应用 Documents 的工具 |
| `screenshots/diag-screen.png` | v14 真机画面（诊断版截图） |
| `configs/options-*.txt`、`watcher-status.txt` | 游戏内设置快照与日志监听状态 |

---

## 6. 约束与合规说明

- 仓库**不包含** IPA 二进制：GitHub 单文件上限 100 MB，且 IPA 内含 Minecraft 客户端与授权资源，
  按 `docs/SECURITY_AND_DISTRIBUTION.md` 不得进入公开仓库或公开 Release。
- IPA 只在本机保留，用 SHA-256 与源码提交锁定版本；需要分发时走私有渠道并自行承担授权责任。
- `MCFAO_TOKEN`、证书 `p12` 口令、CircleCI 令牌均不入库。

---

## 7. 更早的里程碑（11/10–11/13）

| 阶段 | 文档 | 要点 |
|---|---|---|
| AOT 工具链打通（Gate A0/A1） | `docs/BUILDING.md`、`docs/TECHNICAL_GATES.md` | Java 25 → GraalVM Native Image → iOS arm64 可执行文件，无 JIT |
| Fabric 编译期转换（Gate B） | `docs/FABRIC_AOT.md` | Mixin/ASM 在构建期完成，运行期禁止动态类定义 |
| 启动器 UI + 控制布局 | `docs/2026-11-12-ios-launcher-and-performance.md` | SwiftUI 启动器、可编辑控制布局、横屏 |
| World v21 线（进世界、维度、崩溃修复） | `docs/VERSION_SUMMARY_AND_NEXT_PLAN.md`、`docs/performance-2026-11-13.md` | 进入世界、存档、末地崩溃排查与 AOT 性能 |
| GL41 渲染线（本文件） | `docs/GL41_RENDERER.md` | OpenGL 4.1 → zink → MoltenVK → Metal 全链路 |

---

## 8. 未完成项与下一步

1. **v15 未验证**：`17fc8b6` 把着色器缓存目录从 `$HOME/Documents/...` 修正为 `$HOME/.mesa_shader_cache`
   并加了 `[GL41] shader cache ready:` 日志；构建（作业 120）成功，但产物下载在 23:14 中断，
   本机副本损坏，尚未在真机确认缓存是否真正落盘、冷/热启动差异多少。
   → **2026-11-15 凌晨已复核并推翻该前提**：v14 的缓存本来就在工作，冷/热无可测差异，
   详见 `docs/GL41_V14_DEVICE_RECHECK_2026-11-15.md`。v15 不必再下载验证。
2. **渲染管线改造**：当前每帧 GPU→CPU 回读再上传 Metal。要突破约 70 FPS，需要改成 Vulkan 交换链直出
   （MoltenVK 直接呈现，跳过 CPU 中转），属于结构性改动，需单独一轮设计 + 真机验证。
3. **进世界首分钟长帧**：区块网格上传与绘制提交仍在主线程，后续可考虑分帧上传或后台网格构建。
4. **Gate C 验收**：按 `docs/ACCEPTANCE.md`，真机可玩证据仍需补齐（长时间游玩、存档保留、音频、触摸）。
