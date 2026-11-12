# MCFAO 整合包闭世界适配 · 工作交接（第 54 轮）

**交接时间**：2026-11-12 06:35（北京时间）
**项目根**：`/Users/kexin/Documents/ChatGPT/MCFAO`
**本文定位**：当前唯一有效的工作交接入口。`WORK_HANDOFF.md` 与 `A*/B*_HANDOFF.md` 是 11-08 及更早的历史阶段台账（分析墙、图形引导、原版客户端），结论仍有效但**接手顺序已被本文取代**。逐关证据在 `docs/STATUS.md`（pack-87 在末尾），设计约束在 `docs/FABRIC_AOT.md`。

> **给新对话的第一条消息建议**：
> `读 docs/C0_FABRIC_HANDOFF.md，按 §9 继续推进。验证只用 iOS 模拟器，不要向我提问，自主往下做。`

---

## 0. 最新接手状态（2026-11-12 06:30 续接，pack-87 已通过模拟器冒烟）

> **2026-11-12 晚间更新（pack-92 + 未签名 IPA）**：pack-89/90 已把交互探针打通（新增 `glfwGetMouseButton` 轮询、
> Sponge Mixin 合成内部类随包出货），pack-91 的 Jade 修复有四处缺陷（哈希钉错导致 Jade 被静默排除、`ALOAD 1`、
> 缺 `optionalModName` 生成、错改 `maxStack`），已在 pack-92 全部修正并用真实字节码验证。最新构建
> `artifacts/mcfao/fabric-pack-92` → `SIGNED_DEVICE_APP`，模拟器冒烟 `SIMULATOR_WORLD_SMOKE_PASS`（F1 `:159` / joined `:1010` / F3 `:1014`，崩溃 0），功能探针 `SIMULATOR_FUNCTION_PROBE_PASS`（7 张截图；Jade 提示框在 `probe-aim-down` 与 `probe-inventory` 里可见，拿到第一条 `FUNCTION_PASS`）。
> 另有未签名 IPA：`artifacts/mcfao/fabric-pack-92-unsigned-ipa/C0Harness-unsigned.ipa`
> （sha256 `502c6b8c003b0542a6252d9e0ff5113a571f025098631659403d62c33a4b876d`，602,702,176 字节，无签名，
> `deviceRun = NOT RUN`）；生成工具 `tools/package_unsigned_ipa.py`。下一步仍是 pack-92 冒烟 → 功能探针 → 逐 Mod `FUNCTION_PASS`。

**整合包已在 iOS 模拟器完整进世界并通过冒烟**。最新一轮 `artifacts/mcfao/fabric-pack-88-simulator/result.json` → `SIMULATOR_WORLD_SMOKE_PASS`；`game.log` 里 F1 `:159`、`TEXTURE_FRAME_PRESENTED 2622x1206` `:637`、`Dev joined the game` `:763`、F3 `:767`，共 1354 行、崩溃报告命中 0；`world.png` 是真实地形帧（方块纹理、9 格物品栏、左右触屏控件、左上坐标覆盖层俱全）。判据 **F1 + F3 + `Dev joined the game` 三者同时出现**已经满足（pack-87 首次达成），整条阻塞链清空。

判据既已全中，后续工作从「找下一个崩溃」转为三件互不重叠的事：

1. **逐 Mod `FUNCTION_PASS`**：`docs/MOD_COMPATIBILITY_MATRIX.md` 当前 127 行 / 56 `BUILD_PASS` / 58 `LOAD_PASS` / 13 `BLOCKED`，`FUNCTION_PASS` 仍为 0。`LOAD_PASS` 已由 `[MCFAO_ENTRYPOINT]` 派发标记自动填满（83 条入口点全覆盖），剩下这一步必须靠**交互**：对准方块看 Jade 提示、开背包/配方、按键功能，然后截图或断言。
2. **13 个 `BLOCKED` 分类收敛**：导出期静态拒绝 6 个 + 平台级隔离 7 个（Sodium 家族 3、Iris、dynamic-fps、Xaero World Map 的 OpenGL、Xaero Minimap 的 AWT）。平台级那 7 个闭世界手段修不了，报告里保留 `level: platform` 与 `reconsiderWhen`，不要反复重试。
3. **真机仍未做**：`C1/C2` 与 Gate D 的 IPA/安装/存档保留证据都缺，`result.json` 里 `deviceRun = NOT RUN`。用户约定只用模拟器验证，所以不能据此宣称真机可玩。

### 0.1 最后一公里（pack-83 → 88）的阻塞点

每轮固定「新编号构建 → 静态校验 → 模拟器冒烟 → 记录新崩溃点」，逐关证据在 `docs/STATUS.md`：

| pack | 崩溃 / 阻塞 | 性质 | 处置 |
| --- | --- | --- | --- |
| 83 | `ETF.canDoCustomTextures` `NullPointerException`（GlowSquid tick） | 闭世界反射缺 Gson 配置类 | `tools/config_reflection.py` 按结构信号（`X::new` 工厂句柄 ∩ 类字面量、`TConfigHandler` 供应器）识别 13 个配置类并登记构造器 + 字段；顺带修掉常量池 tag 15 被跳过不存的静默缺陷 |
| 84 | `liblwjgl_opengl.dylib` 缺失（Xaero World Map `MapLimiter.determineDriverType`） | 平台级（无 GL） | jar 移入 `incompatible-01`，`level: platform` 记账 |
| 85 | `Close the existing render pass before creating a new one!`（`CommandEncoder.clearColorAndDepthTextures`） | Metal 后端通道槽位残留 | 门禁丢弃的管线仍被 Mod 绘制 → `setPipeline` 抛异常被吞、`close()` 没跑。改为「不支持就标记 `skipped`、draw 变空操作」，`close()` 无条件释放 `device.activePass` |
| 86 | `UnsatisfiedLinkError: awt`（Xaero Minimap `ImageIO → Toolkit.loadLibraries`） | 平台级（无 AWT） | 同上；验证包剩 41 个文件（40 个第三方 jar + `mcfao-fixture.jar`） |
| 87 | 无 | — | 41 文件复验，`SIMULATOR_WORLD_SMOKE_PASS`（首次达标） |
| 88 | 无（只补证据面） | — | 派发循环加 `[MCFAO_ENTRYPOINT]` 打印，83 条入口点全覆盖；矩阵 `LOAD_PASS` 0 → 58 |
| 89 | `glfwGetMouseButton` → `UnsupportedOperationException`（malilib `KeybindMulti.isKeyDown`，交互探针首次触发） | GLFW-lite 只有事件回调、没有轮询状态 | native 补 `mouseButtons[8]` 轮询状态表（与 `glfwGetKey` 对齐），重出 glfw-sim-10 / glfw-ios-05 → lwjgl-sim-14 / lwjgl-ios-world-02 → metal-sim-27 / metal-ios-world-07；staged 输入 `world-simulator-input-05` |

**Gate 口径（2026-11-12 修订）**：模拟器口径下判据已全中，但 Gate C 的「真实菜单 + 创建/游玩世界 + 音频/触摸/持久存档」与 Gate D 的 IPA/安装/存档保留仍缺真机证据，`C1/C2` 与 D 维持 `NOT RUN`——不要把模拟器通过写成 Gate 通过。矩阵工具的 Gate 行现已按标记自动切换，不再硬编码 `BLOCKED / NOT RUN`。

历史（第 53 轮 → pack-82）的逐关结论保留在 `docs/STATUS.md`；其间已修的框架级项包括配置反射（AppleSkin/NCR/Chat Heads/Entity Culling/ETF）、Indigo 插件查询、Jade 元数据构造器、Kotlin 自定义入口单例、普通入口延迟缓存、Mixin Args 完整生成与栈大小、`net/fabricmc/api` 全包出货。

**输入必须使用** `artifacts/mcfao/curated-verification-mods-01`（40 个第三方根 JAR + 第一方 `mcfao-fixture.jar`；Iris、Sodium 家族、dynamic-fps、两个 Xaero 共 7 个 JAR 已按不兼容处置移至 `artifacts/mcfao/incompatible-01/`）。原目录不改。原包没有 F1/F3 夹具，默认冒烟现会启动前拒绝；显式 marker 诊断只出 DIAGNOSTIC_PASS。

保留已有配置复跑；新编号构建、静态核验、模拟器冒烟并持续记录实际阻塞，不宣称整个包或真机可玩。每轮冒烟后 `xcrun simctl shutdown all`，否则下一轮会因 free% < 45 被 AOT 预检拒绝。

---

## 1. 目标与不可改变的前提

| 项 | 内容 |
| --- | --- |
| 最终目标 | Minecraft Java Edition **26.1.2 / Java 25 / Fabric Only** 在**普通未越狱 iPhone 本机**执行游戏逻辑、渲染与存档；macOS Apple Silicon 上构建签名 |
| 硬约束 | **无 JIT、无附加调试器、无后台电脑服务、运行期不能生成新类**（闭世界 AOT）。不得擅自降低需求、不得改成 JS 版 Minecraft、不得用 SwiftUI 空壳或渲染 demo 顶替 |
| 当前战线 | 把**已策划的 Fabric 整合包**（`artifacts/mcfao/curated-verification-mods-01`，40 个第三方 JAR + `mcfao-fixture.jar`；Iris、Sodium 家族、dynamic-fps、两个 Xaero 已隔离）在 AOT 镜像里跑到真实进世界——**pack-87 已在模拟器达成** |
| Gate 定义 | `AGENTS.md` §27–35、`docs/TECHNICAL_GATES.md`。C = 原版真实菜单 + 创建/游玩世界 + 音频/触摸/持久存档；D0/D1/D2 = 隔离不可信 mod 构建 → 导入经测试的整合包 → 报告不兼容 mod、本地签名/IPA/安装/存档保留、真实进世界；E = 性能与稳定性 |
| 状态口径 | 原版 26.1.2 **在模拟器**已通过菜单/创建世界/移动/取放破坏/保存重进（`TECHNICAL_GATES.md` §22），但**这不等价于整合包可玩**；正式 `C0/C0a` 仍标 BLOCKED，真机 `C1/C2`、整合包与性能均 NOT RUN |
| 用户约定 | ① **后续所有验证只用 iOS 模拟器**（`tools/smoke_mcfao_simulator.py` + Xcode `WorldSimulator` scheme），不用真机；② **不要向用户提问**，自主推进；③ 长任务不要主动汇报进度，用户会自己查；④ 每次对工程做实质改动后**实时同步文档**（`docs/STATUS.md`、`docs/FABRIC_AOT.md` 等） |

---

## 2. 当前状态（精确到本次交接）

| 项 | 值 |
| --- | --- |
| 最新构建 | `artifacts/mcfao/fabric-pack-88/result.json` → `SIGNED_DEVICE_APP`（41 个文件 = 40 第三方 jar + fixture；`deviceRun = NOT RUN`） |
| 最新冒烟 | `artifacts/mcfao/fabric-pack-88-simulator/result.json` → **`SIMULATOR_WORLD_SMOKE_PASS`**；`game.log` 1354 行、崩溃报告命中 0；83 条 `[MCFAO_ENTRYPOINT]` 覆盖 56 个 Mod；`world.png` 为真实地形帧 |
| 判据 | F1 `:159` / `TEXTURE_FRAME_PRESENTED 2622x1206` `:637` / `Dev joined the game` `:763` / F3 `:767` —— **三者同时出现，已达成** |
| Gate C / D | 模拟器口径判据已全中；真机 `C1/C2` 与 Gate D 的 IPA/安装/存档保留仍未做 → `NOT RUN`（不写成通过） |
| classpath 可加载性 | pack-87 默认 82/52,725 不可加载、成员级 206/52,725；核心类 0 失败 |
| 已知不兼容（配对级） | `incompatible-01`：Iris（`FieldAccessor.makeSetter` 运行期造类）+ ImmediatelyFast 的 `net.lenni0451.reflect` 路径 |
| 已知不兼容（平台级） | `incompatible-01`：Sodium 0.8.11 + sodium-extra + reeses-sodium-options（无 GL）、dynamic-fps、Xaero World Map（`org.lwjgl.opengl.GL`）、Xaero Minimap（`java.awt`/`ImageIO`）。本工程唯一 GPU 后端是 `fabricaot.metal.MetalBackend`，lwjgl-lite 只为 GLFW/STB/OpenAL 生成 JNI，iOS 也不提供桌面 GL / AWT |
| 已知潜伏项 | ImmediatelyFast `SignAtlasRenderTarget` 引用 `org/lwjgl/opengl/GL`（告示牌文本图集）——只有渲染告示牌才会走到，出现该路径崩溃先查这里 |
| 非致命噪声 | 离线账户 401 用户属性、`oshi` 的 `Operating system not supported: Unknown`、freecam/PresenceFootsteps 配置降级。矩阵工具已把前者从「首个崩溃」里过滤掉 |
| 下一步 | 逐 Mod `FUNCTION_PASS` 证据（当前 56 `BUILD_PASS` / 58 `LOAD_PASS` / 13 `BLOCKED` / 0 `FUNCTION_PASS`） |

**阶段流水线**（`artifacts/mcfao/fabric-pack-N/` 下）：`fabric` → `split` → `metal-injection` → `aot` → `link` → `runtime` → `stage` → `package` → `verify`。每阶段有 `*/product/result.json`、`*/command/{stdout,stderr}.log`、`*/command/command.json`（可复现 argv）。

---

## 3. 环境与路径速查

```bash
ROOT=/Users/kexin/Documents/ChatGPT/MCFAO
JH=$ROOT/.cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home
JAVA=$JH/bin/java          # Java 25
JAVAP=$JH/bin/javap
NI=$JH/lib/svm/bin/native-image
MODS=$ROOT/artifacts/mcfao/curated-verification-mods-01 # 40 个第三方 jar + mcfao-fixture.jar（Iris / Sodium 家族 / dynamic-fps / 两个 Xaero 见 incompatible-01）
ORIGINAL_MODS=/private/tmp/mcfao-curated/mods          # 原始策划目录，保留
SIM=8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3             # 一次性模拟器 UDID（"FabricAOT World 26.1.2"；旧 F3EC958F 已被模拟器重置清掉）
SEED=/tmp/c0seed/world                               # 冒烟种子世界
APPDIR="$HOME/Library/Developer/CoreSimulator/Devices/$SIM/data/Containers/Data/Application"
```

`artifacts/mcfao-local.json`（构建输入，**不要随手改**）当前指向：

| 键 | 值 |
| --- | --- |
| `prepared` | `artifacts/b0/prepared-04` |
| `caps` | `artifacts/b1/ios-probe-03/work/caps` |
| `bootstrapRuntime` | `artifacts/b1/runtime-ios` |
| **`splitter`** | **`artifacts/compiler/method-splitter-03`**（哈希固定输入，见 §8） |
| `versionMetadata` | `~/Library/Application Support/minecraft/versions/26.1.2/26.1.2.json` |
| `assets` / `glfw` / `lwjgl` / `metal` / `openal` / `shaders` | 均在 `artifacts/graphics/` 下，是**构建输入**，清理 artifacts 前必读 `.workbuddy/memory/MEMORY.md` |
| `b1Evidence` | `artifacts/evidence/b1-user-device-run-01/result.json` |

运行时/图形输入：`artifacts/graphics/runtime-sim-02`、`world-simulator-input-02`、`game-assets-01/assets`。
状态与记忆：`docs/STATUS.md`（逐关台账，pack-87 在末尾）、`.workbuddy/memory/2026-11-12.md`（本轮方法论）、`.workbuddy/memory/MEMORY.md`（长期项目约定，含 artifacts 清理规则）。

---

## 4. 标准流程（命令可直接复制）

### 4.1 完整构建（N 取新编号，见 §8「输出目录必须递增」）

```bash
cd /Users/kexin/Documents/ChatGPT/MCFAO
N=60
nohup ./mcfao build --version 26.1.2 --loader fabric \
  --config artifacts/mcfao-local.json --mods artifacts/mcfao/curated-verification-mods-01 \
  --audited-mods --target ios-arm64 \
  --output artifacts/mcfao/fabric-pack-$N > /tmp/pack$N-build.log 2>&1 &
tail -3 /tmp/pack$N-build.log
python3 -c "import json;print(json.load(open('artifacts/mcfao/fabric-pack-$N/result.json')).get('status'))"
```

耗时：CAP 缓存命中时整条链约 **4–8 分钟**（AOT 阶段短至 ~96 秒）；缓存失效时单次 native-image 8–16 分钟（41 文件包实测 ~9–11 分钟）。构建预检要求：堆 ≤ 0.50×物理内存、free ≥35%（仅 8GiB 档位要求 45%）、`df` 空闲 ≥8GiB；**当前 `tools/mcfao.py` 传 `--heap-gib 9`**，`tools/probe_client_graph.py` 允许 6/7/8/9。pack-60 在 7GiB 下因恢复 Sodium 真实注册链而 AOT OOM，pack-69 在 8GiB 下 Full GC 零回收（`analysis/stderr.log` + `work/gc.log`），不要退回 7/8；更不要重新 stub 真实代码来省内存。

### 4.2 构建后静态校验（**先做，省一轮冒烟**）

```bash
N=48
python3 -B tools/verify_aot_classpath.py --build artifacts/mcfao/fabric-pack-$N
python3 -c "
import json,collections
d=json.load(open('artifacts/mcfao/fabric-pack-$N/classpath-check.json'))
f=d['failures']; print('总数',len(f),collections.Counter(x['cause'].split(':')[0] for x in f))
print('核心类失败:',[x['class'] for x in f if x['class'].startswith(('net.minecraft','net.fabricmc.loader'))])
"
A=$(ls artifacts/mcfao/fabric-pack-$N/aot/*/product/analysis/command.json | head -1)
M=$(ls artifacts/mcfao/fabric-pack-$N/metal-injection/*/product/client-26.1.2-metal.jar | head -1)
python3 -B tools/verify_shipped_closure.py --jar "$M" --image-cp "$A" \
  --output artifacts/mcfao/fabric-pack-$N/closure-check.json | tail -20
```

正常基线：`verify_aot_classpath.py` 的 `net.minecraft` / `net.fabricmc.loader` 失败数 = **0**；`closure-check` 的 200+ 缺失类型绝大多数是 mod 可选依赖（`iris`→DH API 等，方法体内惰性解析，无害），重点看 `org/spongepowered`、`mcfao/aot` 等会被真正链接的类型。

### 4.3 模拟器冒烟（**必须先清残留**，见 §8）

```bash
cd /Users/kexin/Documents/ChatGPT/MCFAO
N=48
SIM=8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3
APPDIR="$HOME/Library/Developer/CoreSimulator/Devices/$SIM/data/Containers/Data/Application"
/usr/bin/trash artifacts/mcfao/fabric-pack-$N-simulator 2>/dev/null
find "$APPDIR" -maxdepth 6 -path "*saves/MCFAO Smoke*" -type d 2>/dev/null | while read w; do /usr/bin/trash "$w"; done


python3 -B tools/smoke_mcfao_simulator.py --expect fabric \
  --build artifacts/mcfao/fabric-pack-$N \
  --runtime artifacts/graphics/runtime-sim-02 \
  --graphics artifacts/graphics/world-simulator-input-02 \
  --assets artifacts/graphics/game-assets-01/assets \
  --seed-world /tmp/c0seed/world \
  --simulator $SIM \
  --output artifacts/mcfao/fabric-pack-$N-simulator > /tmp/sim$N.log 2>&1
echo "exit=$?"; tail -5 /tmp/sim$N.log

L=$(grep -n "STDERR\]:" artifacts/mcfao/fabric-pack-$N-simulator/game.log | head -1 | cut -d: -f1)
[ -n "$L" ] && sed -n "$((L-2)),$((L+14))p" artifacts/mcfao/fabric-pack-$N-simulator/game.log
grep -n "MCFAO_F\|joined the game\|Loading terrain" artifacts/mcfao/fabric-pack-$N-simulator/game.log | tail -8
```

冒烟跑完立刻把逐 Mod 证据刷进表里，否则下一轮的 `LOAD_PASS` 永远是 0：

```bash
python3 -B tools/scan_mod_evidence.py --build artifacts/mcfao/fabric-pack-$N --emit-evidence
python3 -B tools/generate_mod_matrix.py --build artifacts/mcfao/fabric-pack-$N
```

前者只补空位（不覆盖 `FUNCTION_PASS`），后者重生成 `docs/MOD_COMPATIBILITY_MATRIX.md`；两条命令都不碰构建产物，可以随时重跑。

### 4.4 诊断工具箱（按成本从低到高）

| 手段 | 用途 / 命令 |
| --- | --- |
| `javap` 反编译出货 jar | 看某个崩溃方法被改写成什么样：`unzip -o -q <metal.jar> 'pkg/Class.class' -d /tmp/x && $JAVAP -c -p -cp /tmp/x pkg.Class`。注意用**类名**而非 `.class` 路径，否则常失败 |
| 常量池引用扫描 | 找谁引用了某字段/方法（`python3` 解析 CONSTANT_Fieldref/Methodref），比字节串搜索可靠（常量池 name/descriptor 是分开的条目） |
| JVM 初始化探针 | `/tmp/initprobe/InitProbe.java`（`--bootstrap` 先跑 `Bootstrap.bootStrap()`，再 `Class.forName(name,true,loader)`）用完整 AOT classpath 复现 `<clinit>` 异常链；classpath 从 `aot/*/product/analysis/command.json` 的 `-cp` 取，并把 `client-26.1.2-metal.jar` 替换为对应 pack 的 metal jar。**探针 classpath 太小会误报 NCDFE** |
| 调用树诊断 | `python3 -B tools/diagnose_call_tree.py artifacts/mcfao/fabric-pack-N/aot/<hash>/product`（约 10 分钟，后台跑）。输出到 `<product>/work/diag/reports/diagnostics_*/`。本轮交接时从 `/tmp/run_calltree.py` 固化入库，避免临时文件丢失 |
| 调用树读法 | `call_tree_methods_*.csv` 里某类 0 个方法可达 ⇒ 整类被丢弃；`call_tree_invokes_*.csv` 里目标解析成 `ImplicitExceptions.throwNoSuchMethodError` ⇒ 该类不可链接、所有调用被静默 stub |
| 迷你 Native Image | 用 `--shared -O1` 加最小 Main 复现 SVM 行为，classpath 顺序要把 Mini 的 classes 放最前（metal jar 里有 `module-info` 干扰） |

---

## 5. 成功判据与状态机

- **冒烟 PASS 的唯一判据**（`tools/smoke_mcfao_simulator.py` 硬编码）：新日志同时出现 `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS`、`MCFAO_F3_CLIENT_WORLD_JOIN_PASS`、`Dev joined the game`，且 result.json 为 `SIMULATOR_WORLD_SMOKE_PASS`。**pack-87 首次满足**（`:88` / `:635` / `:634`），pack-88 复现（`:159` / `:767` / `:763`）；此后任何一轮冒烟只要三者仍在就说明没有功能性回归。
- `fabric/*/product/result.json` 的 `transform` 字段是本阶段的核心报告：`mixinClasses`、`mixinAccessorsApplied/Refused`、`libraryTransforms`、`argumentHolders`、`extrasShipped/Absent`、`syntheticShipped/Absent`、`stubbedMethods`、`staticAdaptations`、`adaptations`、`entrypoints`、`mergedResources`、`mixinTargetsAbsent`。**排查任何导出问题先看这里**，比反编译快得多。
- 常见 `status` 值：`ANALYZED` / `LINKED_WITH_UNSUPPORTED_ENTRYPOINTS` / `SIGNED_DEVICE_APP` / `SIMULATOR_WORLD_SMOKE_PASS`；`artifacts/graphics/` 里另有 `METAL_BOOTSTRAP_BUILT` 等历史状态机值。
- 构建失败先看 `fabric/*/product/compile/stderr.log`（javac）、`knot-2/stderr.log`（重复条目/导出失败）、`aot/*/product/analysis/{stdout,stderr}.log`（OOM / NativeImageError）。

---

## 6. 已知根因台账（pack-06 → 48，**不要重走**）

| 类别 | 根因与修法 | 首次修掉 |
| --- | --- | --- |
| **静默 stub（最高频）** | 类引用了 classpath 不存在的类型 ⇒ JVM/NI 无法加载该类，GraalVM **不会让构建失败**，而是把对该类的每次调用替换成运行期抛 `NoSuchMethodError` 的桩。用 `verify_aot_classpath.py` 量化（pack-06 有 718 个不可加载类） | pack-08~11 |
| Mixin 类缺失 | 旧逻辑只保留带 `@Accessor` 的接口，把 Mixin 包其余类全丢；TRender 嵌套 jar 的 `dev/tr7zw/trender/.../ScreenAccessor` 从未展开，导致 `Minecraft`、`ETF` 不可加载。改为**保留全部 Mixin 包类**（剥离注解、提升为 public），并把构建期 `plugin` 类排除 | pack-08/09 |
| 瞄准库类的 Mixin 未应用 | `TaggedChoice`（datafixerupper）、`YggdrasilUserApiService`、`ContextChain` 等不在游戏 jar 里，Mixin 从未作用。读取 `@Mixin` 的 visible+invisible 注解收集 targets，向 Knot `transform()` 索取改写后的字节，并把合并 jar 提到 AOT classpath 首位（已验证 class 重叠为 0，语义中性） | pack-13~15 |
| 运行期类生成 | `Args$N`（`@ModifyArgs`）、MixinExtras `*RefImpl`（sugar）、Mixin 匿名 helper、静态 `@Accessor` 方法体，全都只在 Knot 内存里。改为构建期按真实调用点生成等价字节码，或向 Knot 索取；`MixinException` + `IActivityContext` + `IActivity` 三件套加入 pinned 出货清单 | pack-17/22/30/31/32 |
| 闭世界反射 | ferritecore 的 `getDeclaredField("cache")`、nightconfig `TomlFormat` 的 `Class.forName`、AppleSkin 配置类构造器 —— 都需在 `compiler/reflection-config.json` 显式注册 | pack-29/43/48 |
| 字节码缺陷 | ① 方法分割的 `fabricaot$part$N` / `$spill$` 不含方法身份 ⇒ 同类多方法撞名 `ClassFormatError`（`BlockStateData` 有 10 个方法撞车）；② `List.of` 用 `Methodref` 而非 `InterfaceMethodref` ⇒ SVM NSME；③ `getModContainer(query)` 折叠多一个 `SWAP` ⇒ `VerifyError: Bad type on operand stack`；④ residue stub 只写 `stubbed` 列表不加 `adaptations`，出货条件只看后者 ⇒ stub 全丢 | pack-11/24/33/35 |
| VerifyError 静默丢类 | 生成的 `Entrypoints.mappingNamespaces` 少压两个字符串就 `invokestatic List.of` ⇒ 操作数栈下溢 ⇒ 整类不可加载 ⇒ `configDir` 变 NSME。修法：补参数 + 给生成类加构建期 `verify()` 自检 | pack-28 |
| 私有字段跨类访问 | 生成的 `GETSTATIC` 指向 private 字段（`Network.CONFIGURATION_CHANNEL`、`Entrypoints.GAME_DIR`）⇒ SVM 解析失败 stub 成 `NoSuchFieldError`。修法：private 走同类 public getter；自生成字段改 `public` | pack-41/42 |
| Loader 查询 | `MappingResolver.mapFieldName/mapClassName/unmapClassName` 在 official 命名空间是恒等映射；`isModLoaded`、`getModContainer`、`getAllMods`、`getConfigDir` 折叠到 `mcfao.aot.Entrypoints` 钩子。**注意栈布局**：参数在 receiver 之后压栈，从调用点回退要先按描述符跳过 N 个参数再走一步到 `getMappingResolver` | pack-25~27 |
| framework 注册扫描 | `FabricRegistrationHelper.getRegistryObjects` 原靠 reflections 运行期扫描（该库已被排除）。改为构建期收集 `@RegistryContainer` 的 static final 字段表 + 生成 `GETSTATIC` 分派；**三个坑**：分派必须用字段声明类型而非容器类、private 字段走 getter、方法体开头要 `Class.forName(name,true,loader)` 强制初始化所有容器（原扫描顺带完成了注册） | pack-34/36/40/41 |
| mod 派发顺序 | `Entrypoints.startClient` 原按字母序派发，导致 `Backpacked.onInitialize` 早于 `FrameworkFabric`，注册表未初始化。改为按 `ModDependency.Kind.DEPENDS` 做 Kahn 拓扑排序（**必须过滤依赖类型**，把 recommends/breaks/conflicts 也当约束会造出假环并静默回退字母序） | pack-37/38 |
| 资源 | 根 `*.toml`（`forgeconfigapiport.toml`）默认配置需进 jar + 进 `game-resources.json` 的 IncludeResources 模式。**但资源合并过宽会把 2173 条 `resourcepacks/` 垃圾灌进 metal jar，AOT 分析早期 old gen 从 1.5GB 涨到 4.8GB，`-Xmx8g` 也 OOM**；只保留 `assets/`、`data/` + 根目录 `.toml`/`.json`/`pack.mcmeta` 即恢复 | pack-44~47 |
| 测试环境 | 模拟器 `NSUserDefaults` 残留 `--quickPlayMultiplayer` 与 smoke 的 singleplayer 冲突 ⇒ 显式传空 `SIMCTL_CHILD_FABRICAOT_SIMULATOR_EXTRA_ARGS`；容器残留测试世界/`NCR-*.json` 改变代码分支 | pack-32/43 |
| **闭世界泛型反射** | GlitchCore `EventManager` 靠 TypeResolver 从隐藏 lambda 反推 `Consumer<T>` ⇒ `Failed to resolve consumer event type`。修法：从 LambdaMetafactory 的 instantiatedMethodType / 类 Signature 解析事件类，调用点压 `LDC Class` 并改调克隆出来的 `addListenerResolved(Consumer, Class)`（原 slot 1 即 eventClass）；指纹限定 + `maxStack +1` | pack-61/62 |
| **构建机堆预算** | 恢复真实 Mod 代码会让可达图像堆单调增长；pack-60 在 7GiB 老年代 5117M/5438M 全满 OOM ⇒ `--heap-gib 8`。不要通过重新 stub 真实入口来省内存 | pack-60/61 |
| **克隆方法的相对栈帧** | 复用原方法体但参数个数变了 ⇒ `Stack map does not match the one at exception handler`。只对被改写类用 `ClassWriter(COMPUTE_FRAMES\|COMPUTE_MAXS)` 输出，其余类保持 `ClassWriter(0)`；`--verify-members` 是唯一会抓到它的检查 | pack-63/64 |
| **字符串类发现** | Sodium `DependencyInjection.load` 用 `Class.forName("...Impl")` + `getConstructor().newInstance()`；类在 classpath ≠ 类在镜像。四个实现类需在 `compiler/reflection-config.json` 注册 `allDeclaredConstructors`，保留真实反射语义 | pack-64/65 |
| **被排除的嵌套库拖垮宿主 Mod** | `AotExport` 按 mod id 排除整库，而宿主 Mod 的类仍留在镜像里：dynamic-fps 内嵌 `battery-2.0.0.jar`（声明 JNI native，无 iOS 构建）→ `BatteryTracker` 的字段类型全部消失 → 该类不可链接 → Native Image 把对它的每次调用替换成抛 `NoSuchMethodError` 的桩，而**方法本身就在出货类里**。关键：宿主 Mod 的 `fabric.mod.json` 并不声明对嵌套库的 `depends`，所以依赖级联抓不到；默认 `verify_aot_classpath.py` 也看不到（宿主类本身能加载），只有 `--verify-members` 报 `BatteryTracker -> ClassNotFoundException: net.lostluma.battery.api.exception.LibraryLoadError`。**结论：看到 `NoSuchMethodError` 指向一个确实存在的 Mod 方法时，先查该类有没有引用被排除的嵌套库** | pack-73 |
| **缺失的 API 接口声明** | Mod 入口类实现了镜像里不存在的接口就整体不可链接，Native Image 只在运行期入口派发处抛 `NoClassDefFoundError`。Xaero 三个 client 入口都额外实现 `DedicatedServerModInitializer`，而手工白名单漏了它。改为从固定 Loader jar 枚举出货整个 `net/fabricmc/api/` 包；构建后把 `classpath-check.json` 的 failures 与 `transform.entrypoints` 交叉核对，不可加载入口点必须为 0 | pack-65/66 |
| **配置框架的反射元数据** | YACL v2 `ConfigClassHandlerImpl` 在配置类 `<clinit>` 里用 `getDeclaredConstructor()` + `getDeclaredFields()` + `Field` 读写；类有构造器但闭世界未登记元数据 ⇒ `NoSuchMethodException` → `ExceptionInInitializerError`。按框架特征（`<clinit>` + `ConfigClassHandler` 字段）在 `tools/config_reflection.py` 自动识别全部配置类并注册，别逐个补类名 | pack-66/67 |
| **Mixin 插件的 onLoad 副作用** | 插件类只在构建期 Knot 里跑、不进镜像。若 Mod 没有 entrypoint、全靠 `onLoad` 初始化静态状态（ImmediatelyFast `earlyInit()` 装载 config/runtimeConfig/VERSION），运行期就是 null ⇒ `Config not loaded yet`。修法：按 SHA-256 审计 `onLoad` 恰好含一次 `earlyInit()`，登记到 `transform.earlyInitializers` 并在 `startClient` 设置 `GAME_DIR` 后重放；同时把被 residue 压成 `Optional.empty()` 的 `getModVersion` 改接 `Entrypoints.optionalModVersion` 构建快照（**改写必须先于 `lowerQueries`**） | pack-67/68 |
| **运行期造类的第三方库** | `net.lenni0451.reflect` 的 `FieldAccessor` 用 `BytecodeBuilder` 拼字节码再 `defineMetafactory`，同库还调 `Unsafe.defineClass` ⇒ `validateModCode` 排除整个库。ImmediatelyFast 的 `IrisCompat` 恰恰用它读写 Iris 私有字段，`NoClassDefFoundError` 后 `System.exit(-1)`。闭世界无解，按 pair 级不兼容登记（`artifacts/mcfao/incompatible-01/`），不要 stub `System.exit` 或伪造 `IRIS_LOADED` | pack-68 |
| **排除 Mod 的连带引用** | 排除某个库之后必须回扫还有谁静态引用它：本次靠扫描出货 jar 常量池字符串（`lenni0451`）找到 4 处，其中 2 处是 Mixin 合并进原版类（`MapTextureManager$MapInstance.<clinit>`），读 transform 报告看不出来 | pack-68 |
| **签名团队不是构建输入** | 工程 `DEVELOPMENT_TEAM = ""`，Xcode 隐式账户解析时好时坏（同参数两次构建一次成功一次 `requires a development team`）。`tools/mcfao.py` 现从 `MCFAO_DEVELOPMENT_TEAM` 或覆盖 bundle id 的已安装描述文件解析，命令行覆盖；argv 变了只会让 `package` 重跑，前面阶段仍复用检查点 | pack-68 |
| **Mod 资源不在 ResourceManager** | `ModResourcePackCreator` 在闭世界产出空集（没有 Mod jar），`MultiPackResourceManager` 只按 `getNamespaces()` 建索引，于是全部 Mod `assets/`/`data/` 不可见（546 条 Missing model 全是 Mod 命名空间）。修法：`RuntimeLowering.lowerVanillaPackBuilder` 在 `VanillaPackResourcesBuilder.build()` 单点把 `Set.copyOf(namespaces)` 改写为生成的 `mcfao.aot.ModNamespaces.withVanilla(...)`（95 命名空间，构建期常量表），客户端/服务端一次覆盖 | pack-76 → 77 |
| **`Class.forName` 的拼接类名** | mrcrayfish framework 用 `X.class.getName() + "$Deserializer"`（`makeConcatWithConstants`）拿嵌套类名再 `Class.forName`——字节码里既无完整字符串常量也无嵌套类字面量，常量扫描全盲。类在 jar 里没用，闭世界只对注册进反射配置的类回答按名查找。修法：`tools/config_reflection.py` 新增 `forname_sites()` + `bootstrap_recipes()`（解析 BootstrapMethods 配方常量配对 `ldc class` → `getName` → `invokedynamic` → `forName`；同时覆盖字面量形态），命中目标登记 `allDeclaredConstructors`。真实 jar 新增 17 条注册 | pack-77 → 78 |
| **Mod 自带着色器管线** | `ShaderManager.apply` 在资源重载时对 `getStaticPipelines()` **全量**预编译，任一失败即再清缓存并抛异常；Metal bundle 只含构建期翻译的原版源，于是 `malilib:pipeline/legacy/wireframe` 的 `UnsupportedOperationException` 把整次重载打空，下一帧 GUI 绘制崩溃。修法：在唯一漏斗 `RenderPipelines.register` 装门禁，`BundledPipelines.register(Map, pipeline)` 查 `ShaderIndex.key` 是否在 `fabricaot-shaders/index.json`，不支持则不注册并打 `[MCFAO_SHADER] dropped pipeline`；`RuntimeLowering.lowerRenderPipelineRegister` 改写方法体，`AotExport` 加 `pipelines` 触发位。**fail-open**：`org.lwjgl.librarypath` 未设或 index 不可读时放行全部，避免丢掉原版管线 | pack-79 → 80 |
| **类分析型库的「无元数据」** | Lithium `ReflectionUtil.hasMethodOverride` 用 `Class.getDeclaredMethod` + `catch NoSuchMethodException` 判断某个类是否覆盖了 `canCollideWith` 等 7 个方法；闭世界对所有未注册方法都抛 NSME，于是全判「没覆盖」，`EntityClassGroup.<clinit>` 的自检 `AssertionError` 直接把登录打死。修法：`tools/config_reflection.py` 新增 `override_entries()` 按字节码登记**真正声明**这些名字的类（`methods: [{"name": …}]`，不带 parameterTypes 等于登记全部重载）；未声明的类继续抛真实 NSME，语义不变。真实 jar：32 类 / 58 条 | pack-80 → 81 |
| **配置发现依赖 Mod 元数据** | mrcrayfish framework 从 `FabricLoader.getAllMods()` + `fabric.mod.json` 的 `framework.configs` 枚举配置类，再 `Class.forName` + `getDeclaredFields` 找 `@FrameworkConfig` 字段。闭世界把 `getAllMods()` 折叠成空集合，于是所有 `AbstractProperty` 都没被链接，`get()` 抛 `Config property is not linked yet` 打死玩家 tick。修法：导出期枚举出货字节里的 `@FrameworkConfig` 静态字段（含注解 id/name/readOnly/type/separator），生成 `mcfao.aot.FrameworkConfigs`（`Pair.of(注解实现, GETSTATIC 字段)`）+ `FrameworkConfigAnnotation`，改写 `FabricConfigHelper.getAllFrameworkConfigs()` 为表查询；`framework-config-roots.json` 驱动 `allDeclaredFields` 让 `ConfigScanData.scan` 保持原逻辑 | pack-81 → 82 |
| **Gson 配置类的构造器与字段** | Gson 写配置靠 `getDeclaredFields()`、读配置靠 `getDeclaredConstructor()`（拿不到就 `Unsafe.allocateInstance` 绕过构造器）。闭世界两边都不应答，于是落盘成 `{}`（2 字节）而读回一个全 null 实例：ETF 的 `ETFConfig.canDoCustomTextures` 第一次 `entityRandomOverrides.isEmpty()` 就 NPE，打死实体 tick。`collectSerializationRoots`（`fromJson` + 尾参 `Class`）抓不到「handler + supplier」和「`loadConfig(Class, Supplier, String)`」两种形状。修法：`tools/config_reflection.py` 新增 `json_config_roots()`，(a) 同类里 `X.class` 字面量与 `X::new` 工厂句柄同时出现，(b) 声明 `TConfigHandler` 字段的类所造的工厂目标；命中根走 `config_entries()` 闭包登记 `allDeclaredConstructors` + `allDeclaredFields`。顺带修掉常量池 tag 15（`CONSTANT_MethodHandle`）只跳过不保存的缺陷，否则工厂句柄对扫描器不可见 | pack-83 → 84 |

**方法论总结（本轮最大价值）**：在闭世界 AOT 里，「运行期 `NoSuchMethodError` / `NoSuchFieldError` / 整类不可达」几乎都不是链接器死代码消除，而是**类不可链接**或**元素未注册**。定位顺序固定为：`fabric` 报告 → `verify_aot_classpath.py` → `javap` 出货字节 → 调用树 CSV → 迷你 JVM/NI 复现。

---

## 7. 关键实现地图（改哪里）

| 文件 | 作用 | 注意事项 |
| --- | --- | --- |
| `interop/fabric/tool/mcfao/build/AotExport.java` | 导出器主循环：合并 mod jar、Mixin 保留/剥离、库类改写、运行期类生成、`mcfao.aot.Entrypoints` 生成（`startClient` 派发 / `configDir` / `stage` / 恒等钩子 / **每条入口点派发后的 `[MCFAO_ENTRYPOINT] mod=…` 打印**）、资源合并、生成 `mcfao.aot.ModNamespaces`、`verify()` | 本轮改动最集中。`put()` 走流式 `ZipOutputStream`，**不能回头改已写条目**，需要全局信息（容器表、命名空间表）必须先预扫描；命名空间表在资源写完之后才生成，并断言 `gameTransforms` 里已有 builder 改写 |
| `interop/fabric/tool/mcfao/build/RuntimeLowering.java` | Loader 查询折叠、residue stub、生成序列化器替换、`VanillaPackResourcesBuilder.build` 命名空间扩表、生成 `ModNamespaces` 常量类 | `lowerQueries` 签名第 4 参是 `List`、第 5 参是 `Set`；改内联栈指令后务必跑 SimpleVerifier。`previousReal(x)` **自己会回退一步**，传 `x` 而不是 `x.getPrevious()` |
| `compiler/splitter/src/fabricaot/split/MethodSplitter.java` | 巨型方法分割；分段/spill 命名带方法身份 + 撞名自检 | **源改了必须重固化**，见 §8 |
| `compiler/reflection-config.json` | 闭世界反射注册（构造器/字段/方法/`Class.forName`） | 每加一条都让 AOT 可达集微增，注意堆余量 |
| `tools/prepare_fabric_aot.py` | fabric 阶段编排；不兼容 mod 排除重试 | `incompatible.json` 按轮次**归档改名**（`incompatible-1.json`），不要 `unlink()` —— 批量删除保护钩子会拦 |
| `tools/probe_client_graph.py` | AOT 分析命令组装、堆/磁盘预检、`game-resources.json` 与 JNI/reflection 配置生成 | **`--heap-gib` 当前 9**（允许 6/7/8/9）；预检 `heap > 0.50*物理内存` 或 free% < 35（仅 8g 档要求 45）即 BLOCKED，另需 ≥8GiB 空闲磁盘；资源模式见 §6 |
| `tools/generate_mod_matrix.py` | 从验证包 `result.json` 生成 `docs/MOD_COMPATIBILITY_MATRIX.md` | 只按证据推导到 `BUILD_PASS`；`LOAD_PASS`/`FUNCTION_PASS`/`DEVICE_PASS` 必须经 `docs/MOD_MATRIX_EVIDENCE.json` 人工升级，且 `BLOCKED` 不可被证据表升级。**冒烟通过时不要「取第一条 Exception 当崩溃」**——离线认证/Realms/`oshi` 都是良性噪声，`BENIGN_NOISE` 与 `_PASS` 短路就是为此 |
| `tools/scan_mod_evidence.py` | 从冒烟日志挖逐 Mod 的 `LOAD_PASS` 证据：入口点派发标记 `[MCFAO_ENTRYPOINT]` + Mod 自称的初始化行，按「类名/显示名/命名空间/裸 id」分级，只认 INFO 级 | `--emit-evidence` 会写入证据表且**不覆盖**已有人工判定；裸 id 命中（`Builtin shader registered`）不算证据 |
| `interop/diagnostics/ModNamespacesProbe.java` | 对合成与**真实** `26.1.2.jar` 的 builder 做命名空间扩表改写 + 字节码校验 + 反射加载生成类 | 上游改 `build()` 形状时在这里 1 秒失败，别等 AOT 跑完 |
| `tools/mcfao.py` | 顶层 `mcfao build` 阶段编排与输入哈希校验 | 输入清单里含 splitter 目录，源改了会报 "Input hash changed" |
| `tools/smoke_mcfao_simulator.py` | 模拟器重链接 + xcodebuild + 安装 + Quick Play 冒烟 | 已内置清空 `EXTRA_ARGS`；输出目录已存在会失败，先 `/usr/bin/trash` |
| `tools/verify_aot_classpath.py` / `verify_shipped_closure.py` | 静态可加载性 / 出货闭包检查 | 后者需传 `--image-cp` 指向 `analysis/command.json` |
| `tools/diagnose_call_tree.py` | 调用树诊断（本次交接时从 `/tmp/run_calltree.py` 固化） | 输出到 `<product>/work/diag/`，不动原产物 |
| `ios/C0Harness/main.m` + `WorldSimulator.xcscheme` | iOS 宿主 argv 组装、Quick Play 参数持久化 | 改宿主需重新 xcodebuild |

---

## 8. 环境陷阱（**必须遵守，都是踩过的**）

1. **输出目录必须递增**：源码或输入变更后复用同一 `--output` 目录会被输入哈希校验/半成品状态卡住。一律用新 `fabric-pack-N`。
2. **分割器是哈希固定输入**：改 `MethodSplitter.java` 后必须
   `python3 -B tools/build_method_splitter.py --output artifacts/compiler/method-splitter-04`，再把 `artifacts/mcfao-local.json` 的 `splitter` 指向新目录（当前是 `-03`）。
3. **内存/堆**：18GB 机器，AOT 分析阶段是唯一吃内存大户。实测（`aot/*/product/result.json` 的 `gcSummary` / `maximumResidentSetBytes`）：pack-43 峰值堆 5.89GB、RSS 5.78GB、FullGC 13 次、112s；pack-47 5.80GB/6.25GB、12 次、96s；pack-48 6.46GB/5.34GB、12 次、110s —— 即**约 6GB 堆 + 5–6GB RSS，紧贴上限，几乎没有余量**。其余阶段（Knot / split / metal-injection / link / package）都是普通 JVM 或链接器，不单独吃 GB。AOT 期间先 `xcrun simctl shutdown all` 关掉模拟器；`purge` 可释放页缓存。**pack-60 起 7GiB 已不够**：恢复 Sodium 真实配置注册链（9 个方法从 stub 回到真实代码）后 pack-60 Full GC 后 live 5117M / 5438M 老年代全满、RSS 6.50GB、71.9s OOM，而 pack-59 同堆成功时 live 4.05GB。当前固定 **9GiB**（pack-61~68 用 8GiB 时 Full GC 后 live ≈4.96GB；pack-69 起 live 涨到 7087M / 7337M 容量，8GiB 直接进入零回收的 full-GC 螺旋。9GiB 是 18GiB 机器的 50% 硬上限，10GiB 会被预检拒绝；预检：堆 ≤0.50×物理内存、非 8GiB 档 free ≥35%，不以重新 stub 真实路径省内存）。GC 日志在 `aot/*/product/work/gc.log`，OOM 原文在 `analysis/stderr.log`，看 Full GC 后 live old-gen 判定是输入膨胀还是瞬时压力。**冒烟后必须 `xcrun simctl shutdown all`**：WorldSimulator 仍 Booted 时 SpringBoard / SimMetalHost 会吃掉十几个百分点 free%，8GiB 堆预检要求 free ≥45%，pack-62 就因 34% 在预检被拒（`Host memory headroom below bounded experiment threshold`），源码无问题；shutdown 后回到 58% 即可重跑。`purge` 在普通账户报 Operation not permitted，不用依赖它。
4. **磁盘**：单次 `mcfao build` 输出目录约 **2.5GB**（pack-48：package 757M / fabric 527M / aot 320M / stage 306M / link 302M / split 178M，其中 `client-graph.dylib` 302M 在多阶段重复，APFS clone 未必真占双份）；metal jar 177M；`.cache`（工具链 + CAP 缓存）3.4G 跨构建复用。累积 `artifacts/mcfao` 已达 88G，历史 pack 需定期清理；构建预检要求空闲磁盘 ≥8GiB。`/usr/bin/trash` 移入废纸篓**不释放同卷空间**；`~/.Trash` 受 TCC 保护 `rm -rf` 静默失败，要用
   `osascript -e 'tell application "Finder" to delete (every item of trash whose name starts with "fabric-pack")'` 定向清空。清理前先查 `du -sh artifacts/mcfao` 和 `df -h /`。
5. **模拟器容器数据跨 App 重装保留**：残留 `MCFAO Smoke*` 世界会让冒烟直接失败；残留 `NCR-*.json` 会让 NoChatReports 走 Gson 反序列化分支（绕过构造器 → `fileName=null` → `Path.resolve(null)` NPE），**这个分支本身是 mod 的真实缺陷，第二次启动也会崩**，但清残留可先验证主链路。
6. **批量删除保护钩子**：一次删 >50 个文件会触发 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 并静默中止脚本（曾把重试机制打断，误判成 AotExport 排除逻辑失败）。用归档改名代替删除。
7. **artifacts 不是纯输出目录**：里面混着 `docs/BUILDING.md` 声明的构建输入与文档证据引用。清理前按 `.workbuddy/memory/MEMORY.md` 的三步强制校验流程走；若要真省空间，`tools/dedup_artifacts.py` 只做 APFS clone（**绝不能硬链接**，`codesign --force` 会就地改写共享 inode）。`du` 看不见 clone 共享块，只有 `df` 准。
8. **CAP 缓存**：`-H:+UseCAPCache` 让重建快很多，但它只是汇编指令缓存，**不会缓存分析结果**，遇到「类可达性」问题不要怀疑缓存导致陈旧，直接跑调用树。
9. **Codex 智能体并发**：用户已授权暂时忽略其改动（对方撞额度墙）。工作区未提交的改动都是本轮有效成果，不要 `git checkout --` / `git reset`。
10. **证据脱敏**：`artifacts/evidence/` 里 4 个 archive stdout.log 含个人邮箱与证书名（历史提交里已存在），仓库转公开后更不应再新增副本。`.gitignore` 的 `/artifacts/*` + `!/artifacts/evidence/` 规则不能退回 `/artifacts/`。
11. **测试**：`python3 -m unittest discover -s tests -q`（当前 234 个用例）；**项目无 pytest 依赖，不要 pip install pytest**。
12. **zsh 不做未加引号变量的词分割**：写 `TARGETS="a b c"; for t in $TARGETS; do ...; done` 在 zsh 里只会循环一次，且 `$t` 是整串，配合 `[ -d ... ] || continue` 会**静默什么都不做**（曾误判成 `/usr/bin/trash` 失效）。清理脚本一律用数组 `targets=(a b c); for t in "${targets[@]}"`，或用 `${=TARGETS}` 显式分词。
13. **`BACKEND_TOOLS` 里的脚本是构建指纹**：改 `probe_client_graph.py` / `prepare_fabric_aot.py` / `link_c0_ios.py` 等会让 `inputs.json` 与已有输出目录不匹配，报 `Build inputs changed. Use a new output.`，**不能在同目录续跑**（pack-69 因此作废，改 pack-70）。只改 `tools/mcfao.py` 不受影响——它不在指纹集合里，所以签名团队那次能只重做 `package`。
15. **分割器的两个 ASM jar 原本寄生在 `~/.gradle/wrapper/dists/...`**：`artifacts/compiler/method-splitter-03/result.json` 记录的 `asmJars` 里有两条路径指向 Gradle 发行版的 `lib/asm-9.9.jar` 与 `lib/asm-tree-9.9.jar`。2026-11-11 23:36 该 `dists` 目录被外部清空（`~/.gradle/wrapper` 只剩一个空壳），`mcfao build` 立刻报 `[Errno 2] No such file or directory: '/Users/kexin/.gradle/wrapper/dists'`。恢复办法（已用完，指纹逐字节吻合）：从 Maven Central 取 `asm-9.9.jar`（sha256 `03d99a74ad1ee5c71334ef67437f4ef4fe3488caa7c96d8645abc73c8e2017d4`）与 `asm-tree-9.9.jar`（`42178f3775c9c63f9e5e1446747d29b4eca4d91bd6e75e5c43cfa372a47d38c6`），放回 result.json 里那条绝对路径即可，不要改路径或换版本——`inputs()` 会按记录的 sha256 校验。要根治应把这两个 jar 复制进 `~/.cache/libs/asm-9.9/` 并重建分割器（重建会改变构建指纹，等于一次全量 AOT）。
14. **签名证据不可删**：`SIGNED_DEVICE_APP` 的 pack 目录里含 `package/.../C0Harness.app/embedded.mobileprovision`。清理时只挑 `result.json` 缺失的失败构建与 `-simulator` 冒烟输出；含 `.mobileprovision`/`.p12`/`.ipa` 的目录一律 BLOCK。pack-67 前按此规则清了 13 个目录，`df` 7.4GiB → 15GiB。

---

## 9. 下一步待办（有序、可验证）

0. **判据已全中，不要在「找下一个崩溃」上继续投入**：pack-87 的 `SIMULATOR_WORLD_SMOKE_PASS` 已经把闭世界阻塞链清空。继续照着老套路刷包编号只会得到同一结果，除非同时改动输入（加 Mod、回填被隔离的 Mod、换维度/存档）。
1. **逐 Mod `FUNCTION_PASS`（当前最大的空白：114 个 `BUILD_PASS`，0 个功能证据）**
   - `LOAD_PASS` 已经用 `tools/scan_mod_evidence.py --emit-evidence` 刷完了（58 条，含 56 条派发 + 2 条自述），不要手工重写；要做的是 `FUNCTION_PASS`，证据格式在 `docs/MOD_MATRIX_EVIDENCE.json`（`note` / `evidence` 指 `pack-NN-simulator/game.log#L123` 或 `world.png`）/ `tests`。`BLOCKED` 不可升级。
   - 分批做法（从证据成本最低的批次开始）：① 只在日志里打初始化/HUD 标记的（如 Jade、AppleSkin、Entity Culling 的 debug 屏幕）；② 可以在 `world.png` 里直接看到的（hotbar 物品、HUD 元素、粒子/光效）；③ 需要交互才能证明的（配方查看 JEI 类、箱子界面、按键功能）——这一批要先确认触屏注入路径，别先写探针。
   - 升级完跑 `python3 -B tools/generate_mod_matrix.py --build artifacts/mcfao/fabric-pack-87` 重生成矩阵，汇总行必须与证据表一致。
2. **13 个 `BLOCKED` 收敛成报告**：导出期静态拒绝 6 个（`excludedMods`）+ 平台级 7 个（`incompatible-01`）。平台级 7 个不要再试——Sodium 家族要桌面 GL、Iris 要运行期造类、dynamic-fps 与两个 Xaero 分别撞 GL / AWT；报告里保留 `blockedBy`、字节码证据与 `reconsiderWhen`。
3. **真机 Gate C/D 仍 `NOT RUN`**：用户约定只用模拟器验证，所以 `C1/C2` 与 Gate D 的 IPA/安装/存档保留证据要等用户开口再做。届时用的是已经产出的 `SIGNED_DEVICE_APP`（pack-87），不需要重建。
4. **框架级待验证（不是阻塞，是覆盖面）**：① 换维度（下界/末地）各跑一次冒烟——本次只验证了主世界新建存档；② 长时间跑（10 分钟以上）看 tick 与内存是否稳定；③ ImmediatelyFast 的 `SignAtlasRenderTarget` 仍引用 `org/lwjgl/opengl/GL`，一旦渲染告示牌崩溃先查这里；④ 音频（OpenAL）与存档持久化（退出重进）尚无断言。
5. **每轮固定三步不变**：新编号构建 → `verify_aot_classpath.py` 核心类 0 失败 + 入口点 0 不可加载 → 保留配置跑模拟器冒烟 → 记录结果。每次实质改动后同步 `docs/STATUS.md`、`docs/FABRIC_AOT.md` 与 `.workbuddy/memory/YYYY-MM-DD.md`。
6. **已知但未推进**：2 个 Kotlin 语言适配器类不可加载（历史记录，非游戏核心类）；`VanillaTooltipProviderOrder` 的 `MixinService` 运行期字节码抓取（闭世界不可行，未触发）。

## 10. 交接时的工作区状态（`git status --porcelain`，均为有效未提交改动）

截至 2026-11-12 06:35，实质改动分四组：

- **metal 后端（pack-85/86 的通道槽位修复）**：`M MetalRenderPass.java`、`M MetalDevice.java`、`M ShaderIndex.java`、`?? BundledPipelines.java`（管线门禁）。
- **闭世界反射（pack-83/84）**：`?? tools/config_reflection.py`（Gson 配置类识别 + 常量池 tag 15 修复）、`M compiler/reflection-config.json`、`?? tests/test_config_reflection.py`。
- **矩阵工具**：`?? tools/generate_mod_matrix.py`、`?? tests/test_mod_matrix.py`、`?? docs/MOD_COMPATIBILITY_MATRIX.md`、`?? docs/MOD_MATRIX_EVIDENCE.json`。
- **文档**：`M docs/STATUS.md`、`M docs/FABRIC_AOT.md`、`M docs/GRAPHICS_BOOTSTRAP.md`、`?? docs/C0_FABRIC_HANDOFF.md`（本文）。

本地构建输入（`artifacts/` 已被 `.gitignore` 整体忽略，不在 `git status` 里）：`artifacts/mcfao-local.json` 的 `metal` 指向 `artifacts/graphics/metal-ios-world-06`；`artifacts/mcfao/incompatible-01/result.json` 新增 `xaeroworldmap` / `xaerominimap` 两条 `level: platform`。

`M logs/*` 是运行日志，可忽略；`?? config/`、`?? interop/fabric/tool/mcfao/aot/` 是既有生成物。

artifacts 占用：pack 目录只保留文档引用过的编号（87、87-simulator、incompatible-01、curated-verification-mods-01 等），其余按 §8 的校验流程清掉；磁盘 460GiB 中剩 11GiB 时优先删未引用 pack，不要动 `graphics/` 下的构建输入。

## 11. 文档索引（按接手顺序）

| 文档 | 读它做什么 |
| --- | --- |
| **本文** | 接手入口、流程、台账、陷阱 |
| `AGENTS.md` §27–35 | Gate 定义与「不得宣称完成」的硬规则 |
| `docs/STATUS.md` | 逐关证据链（pack 编号 → 崩溃点 → 修法），pack-87 通过记录在末尾 |
| `docs/MOD_COMPATIBILITY_MATRIX.md` | 逐 Mod 构建/功能状态（由工具生成，勿手改） |
| `docs/FABRIC_AOT.md` | Fabric AOT 的设计约束（Mixin/Loader 折叠/资源策略） |
| `docs/BUILDING.md` | 完整构建配方与 artifacts 输入依赖清单 |
| `docs/TECHNICAL_GATES.md` | Gate 通过标准、原版模拟器已通过项 |
| `docs/CLIENT_GRAPH_DIAGNOSTICS.md` | 分析墙历史（已收敛，不要重走） |
| `docs/GRAPHICS_BOOTSTRAP.md` / `GRAPHICS_STACK_PLAN.md` | 图形栈现状与证据 |
| `docs/WORK_HANDOFF.md` | 11-08 历史交接（历史价值，接手顺序已过期） |
| `.workbuddy/memory/MEMORY.md` | 长期项目约定（artifacts 清理、去重、GitHub 权限限制等） |

## 12. 术语

**闭世界 AOT** = GraalVM Native Image `--no-fallback --shared`，构建期决定全部可达类，运行期不能加载/生成新类；**Knot** = Fabric Loader 0.19.3 的类转换服务，构建期执行 Mixin 变换；**metal jar** = `client-26.1.2-metal.jar`，导出器合并产物，AOT 的实际输入；**CAP cache** = 汇编指令缓存；**residue stub** = `RuntimeLowering` 把无法折叠的 Loader 调用替换成安全默认值的兜底改写；**pinned** = 从工具 classpath 上固定的 Mixin jar 直接出货的少量类；**Gate C/D** 见 §1。
