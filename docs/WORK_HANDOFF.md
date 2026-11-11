# FabricAOT 工作交接

交接日期：2026-11-08（北京时间）。第17–24轮更新于当日17:40，第37–43轮真机/模拟器引导于当日20:59，第44轮图形栈侦察于当日21:40。项目目录：`$HOME/Documents/ChatGPT/MCFAO`。

## 1. 接手者首先需要知道的结论

**项目处于研发阶段。A0/A1/B0/B1 已在各自限定范围内通过；C0 BLOCKED，C1 NOT RUN，C2 NOT RUN。尚无可玩 Minecraft iOS 客户端或游戏 IPA。**

### 1.1 已经走通的路（不要再重做）

三件原先被视为"最难门槛"的事都已拿到证据：

1. **分析墙已打通**。根因是单个巨型方法（`Blocks.<clinit>`，7,331 invoke / 12,966 指令）的类型流图构建代价随方法规模平方增长。构建期方法拆分器（`compiler/splitter`，ASM）把 18 个类的 28 个 `static ()V` 拆成 358 段后，真实客户端在 6 GiB 堆下 **34–40 秒完成完整分析**（32,531 类型 / 112,219 方法），注册表摘要 `4fce5dfeb9c2f39b` 与原版逐字节一致。详见 §6e。
2. **AOT 镜像能生成并被链成 iOS 动态库**。`--relocatable` 绕过 svm 自带的宿主链接，`tools/link_c0_ios.py` 用 B1 配方链出 `client-graph.dylib`（114 MB，`platform IOS, minos 17.0`）。详见 §6f。
3. **镜像在真机和模拟器上真的执行了**。`run_main` 进入 `net.minecraft.client.main.Main.main`，参数解析、log4j、`CrashReport.preload`、**291 项 Datafixer 优化**、JOML 的 Unsafe 路径全部通过，Java 异常能正常抛出。详见 §6i / §6j。

沿路修掉的问题都不是 AOT 问题，均已定位并留证：`code 801`（`run_main` 自建 isolate 时 `ReservedAddressSpaceSize=0` → 32 GiB 预留，真机 `Cannot allocate memory`）、joptsimple 的反射元数据缺失（`File`/`Integer` "is not a value type"）、log4j 的 `/logs` 只读（宿主 `chdir` 到 gameDir）、iOS 26 缺 `UIApplicationSceneManifest` 导致 `UIApplicationMain` trap。

### 1.2 当前图形边界

第45轮已有第一方 GLFW-lite、显式iOS JNI overlay和Metal bootstrap。真实26.1.2的 `Window` 与 `RenderSystem.initRenderer` 已经在模拟器AOT执行，Metal呈现1206×2622蓝色诊断帧，入口返回0。原始日志、截图、构建链与测试边界见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。

第46轮用户确认真机蓝屏与四分屏资源探针。后续仅用模拟器。原版 26.1.2 已通过横屏单人游玩，保存重入时准确读回玩家位置。图集、天空亮度、局部颜色/深度清除、87 条原版管线和 CoreAudio PCM 已分别通过专项测试。C0/C0a 维持 BLOCKED，正式 C1/C2 真机 NOT RUN。[横屏验收](../artifacts/graphics/landscape-acceptance-01/result.json)

Java25的LWJGL默认多版本实现走FFM；本轮改为构建期JNI overlay，17种回调ABI每种32个预编译槽。实际客户端C导出58个；59个glfw前缀方法名包含Java辅助函数glfwFreeCallbacks。LWJGL还会一次初始化125个函数入口，未实现包装方法必须具名失败，不能让Window.close通过空指针调用。

用户需要Xcode工程调试，已添加共享Scheme **MetalProbe** 和 **Graphics Debug** 配置：[工程](../ios/C0Harness/C0Harness.xcodeproj/)、[配置](../ios/C0Harness/GraphicsProbe.xcconfig)。直接引用已验证的iPhone AOT镜像及3个本地原生库；设备目标未签名构建已通过。用户手动选择手机后运行；调试会话和后续断线独立运行是不同验证条件。

### 1.3 接手顺序

1. 阅读根 `AGENTS.md`、`docs/.codex/` 和本交接；产品边界以 [TECHNICAL_GATES](TECHNICAL_GATES.md)、[ACCEPTANCE](ACCEPTANCE.md) 为准。
2. 执行 `git status --short`，保留本交接和最新未提交研究代码。不要重置或清理工作区。
3. 先读 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)、[GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md) 与 [ADR-008](evidence/ADR-008.md)——这是当前唯一未通过的前线；分析、AOT、链接、真机执行的历史不必重走。
4. 需要复核历史时按此顺序：[方法形状普查](../artifacts/c0/method-shape-census-26.1.2.json) → [拆分结果](../artifacts/c0/client-split-04/) → [注册表摘要](../artifacts/c0/init-digest/result.json) → [镜像与链接](../artifacts/c0/client-link-sim-02/) → [模拟器运行日志](../artifacts/c0/harness/)。
5. 只有分析器本身的行为需要改动时，才回到 §5/§6c 的 01–24 轮记录与 [CLIENT_GRAPH_DIAGNOSTICS](CLIENT_GRAPH_DIAGNOSTICS.md)；那部分已经收敛，不要重复已排除的方向（内联深度、构造器预算、并行度、predicates、单类构建期初始化、加堆）。
6. 不提前宣称 Metal、可玩性或性能；每个工作包按 [GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md) §4 的验收条件单独记 PASS/BLOCKED，子门槛按 §5 的 C0a/C0b/C0c。

## 2. 不能改变的目标及用户分工

目标为 Minecraft Java Edition **26.1.2 / Java 25 / Fabric Only**；在 macOS Apple Silicon 构建签名，在普通未越狱 iPhone 本机执行游戏逻辑、渲染和存档。iPhone运行不能以 Java JIT、附加调试器或后台电脑服务为前提。

用户本地合法导入客户端及资源；不向仓库、公开 IPA 或外部服务上传游戏本体、凭据、令牌、私人存档或未获授权的 Mod。不得通过降低游戏/Java版本、串流、UI图片或解释器替换目标。

用户已明确授权：**助手执行 Mac 脚本和隔离测试，用户负责真机安装与运行**。已有 A1/B1 真机测试足够，不需要用户重复。不要因为早期“测试暂时交给我”停止后续已授权的 Mac 验证；也不要自动安装或启动手机 App。

第三方 Mod/Gradle/Mixin 插件和构建期初始化不得直接在个人主环境运行。现有实验仅使用固定依赖及审读过的第一方夹具，执行位于默认拒绝沙盒中；未执行原有53个Mod。

## 3. Gate 状态与主要证据

| Gate | 当前结论 | 已验证范围 / 证据 |
|---|---|---|
| A0 | PASS | 用户Mac真实26.1.2主菜单；关联同一进程Java25.0.1/Fabric0.19.3，125个实际打开JAR指纹。[记录](../artifacts/evidence/a0-desktop-reference/result.json) |
| A1 | PASS | 第一方Java25语义探针经iOS ARM64 AOT/签名后独立运行；用户确认退出Xcode、断开USB后重新启动。[记录](../artifacts/evidence/a1-user-device-run-03/result.json) |
| B0 | PASS | 真实Knot/Mixin、ClassTweaker访问修改、嵌套JAR、Entrypoint；转换后重放与JVM一致，原始未转换类精确失败。[run-04](../artifacts/b0/run-04/result.json)；run-05为修订运行器复验 |
| B1 | PASS | 同一B0转换输入在iOS AOT执行；build4两次真机PASS，用户称一次连接Xcode、一次未连接。[记录](../artifacts/evidence/b1-user-device-run-01/result.json) |
| C0 | BLOCKED | 模拟器原版 Main 与 Metal 图形已执行，设备仅验证诊断探针。见 [图形记录](GRAPHICS_BOOTSTRAP.md)。 |
| C0a | BLOCKED | 真机诊断清屏和资源探针通过，独立启动未确认。 |
| C0b | 模拟器 PASS | 原版主菜单与点击响应。 |
| C0c | 模拟器原版 PASS | 实际单人世界、移动、取放和破坏方块、保存退出、横屏读档。 |
| C1 / C2 | 真机 NOT RUN | 继续仅用模拟器。 |
| D0 | PARTIAL | 文件读/写与本地socket拒绝控制通过；恶意Gradle/Mod、IPC、完整配额和下载链未全面验收 |
| D1 / D2 / E | NOT RUN | 未验证整合包、游戏IPA更新/世界保留、持续游玩、FPS/温度等 |

B0/B1只覆盖第一方夹具，入口按固定列表重放；不能视作通用Fabric静态编译器或Fabric API/53个用户Mod兼容认证。ClassTweaker仅覆盖访问修改子集。

## 4. 环境、输入与构建链

### 工具链

- 当前实验主机约18 GiB物理内存，macOS27.2 arm64；Xcode及iPhoneOS SDK27.2。
- GraalVM CE **25.0.2+10.1**，Java25；路径：
  `.cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home`。
- 固定Graal提交：`6589574a0c5561605d619d2a5aa0d9ad11c61efa`；OpenJDK提交：`3bdcc4536ac3ee02420bcfbfa6fdd3f4bc7d6831`。
- 版本、归档SHA与许可来源见 [toolchains.lock](../compiler/toolchains.lock.json)、[upstream.lock](../compiler/upstream.lock.json)、[fabric.lock](../compiler/fabric.lock.json)。
- iOS运行库由固定官方源码和第一方构建器编译，119翻译单元、6个archive；B1源码输入与已验证A1一致，archive字节不相同。
- 第三方候选 `ios-graal-jdk25.zip` 只静态审读并引用固定数值CAP；未使用其中预编译原生archive充当已验证运行库。许可状态及限制保持在锁定文件中。

### 本地Minecraft与启动器

Swift Craft Launcher 根：`$HOME/Library/Application Support/Swift Craft Launcher`。

- 客户端：`meta/versions/26.1.2/26.1.2.jar`，38113927字节。
- 客户端SHA256：`b1b3158572666445eff01e82fad8c7de2e4953db6d354f311730d77a8359d0b0`。
- 当前A0参考实例：`profiles/26.1.2-fabric-0.19.3-20260804-145519`；Fabric API0.155.2+26.1.2。
- 原始 `profiles/Recollection3` 的53个Mod和世界保留原位，其旧日志不能替代当前A0证据。
- 只读定位共享versions/libraries/assets/runtime；没有读取账户数据库或游戏原始启动参数/令牌。

### 已有App与签名

可编辑工程为 [A1Harness](../ios/A1Harness/A1Harness.xcodeproj) 与 [B1Harness](../ios/B1Harness/B1Harness.xcodeproj)。B1 build4复用研究Bundle ID `org.fabricaot.research.a1probe.kexin`，Team `YOUR_TEAM_ID`，保留该研究App旧A1 Documents。

C0 宿主是第三个工程 [C0Harness](../ios/C0Harness/C0Harness.xcodeproj)：Bundle ID `org.fabricaot.research.c0.kexin`，同 Team，`dlopen` 加载 `Frameworks/client-graph.dylib` 后调 `run_main`，日志逐行 `fflush` 到 `Documents/c0-logs/run-*.log`。它同时支持真机与模拟器两条通道（`tools/build_c0_harness.py --device` / `--simulator`），模拟器通道不需要解锁设备，是当前默认的迭代方式。`CFBundleVersion` 已迭代到 5：build 2 补 `UIApplicationSceneManifest`（修 iOS 26 的 `UIApplicationMain` trap），build 3/4 修 801 与逐行日志，build 5 修 joptsimple 反射。

诊断IPA在 `artifacts/b1/device-handoff/export/FabricAOT B1.ipa`；SHA256：`df588c3fd34c67dd1a52857226f3a39f03cf105e5607e827818b91d9c1df31ff`。它不含Minecraft游戏代码。包记录中的描述文件到期时间为2026-11-15 09:53:47（北京时间）；重新安装/签名前刷新实际有效性。

A1早期createIsolate=801为地址预留失败；通过公开version-1参数把预留限制为256 MiB解决，禁止填写内部保留字段。build3/4每个进程只执行一次，界面显示当前runID、时间、耗时和日志名；划掉后台再打开才会产生新运行。

## 5. 真实客户端分析实验：01–24（25 轮之后见索引与 §6e–§6k）

所有有效C0实验先通过第一方沙盒拒绝控制。分析入口是 `net.minecraft.client.main.Main`，但**不执行该Main**；仅尝试 `ExitAfterAnalysis`，不完成全客户端Fabric转换。

| 轮次 | 条件 / 观察 | 结果与解释 |
|---|---|---|
| 01–03 | clang/静态库定位 | 初始化阶段失败，后续明确指定实际iOS运行库和clang路径 |
| 04/05 | CPU预算 | 05约602.8秒子进程CPU、退出152；不能当不兼容证明 |
| 06 | 外层EPERM | 未执行分析 |
| 07 | 6 GiB | Java heap OOM；原记录保持不变 |
| 08 | 构建JFR | 自动开启目标JFR后缺LibMDependencies.cap，不能作为内存对照 |
| 09 | 6 GiB / Parallel | 91.0s，49次Full GC，暂停73.33s，OOM退出3 |
| 10 | 8 GiB / Parallel | 127.6s，50次Full GC，暂停110.51s，OOM退出3 |
| 11 | 8 GiB / G1 | 119.4s，22次Full GC，暂停95.04s，OOM退出3 |
| 12 | 6 GiB，关闭首次OOM立即退出 | 248.3s，CPU约1816.2s，退出152，未取得可用异常栈；不是正常完成 |
| 13 | 6 GiB，第一方JVMTI代理及OOM栈 | 108.8s，退出1；取得分配采样、浅层对象统计、部分分析计数及Blocks.<clinit>失败报告 |
| 14 | 关闭TrackPrimitiveValues/UsePredicates | 51.0s，OOM退出3；单独关闭这组优化未解决 |
| 15 | 上述配置再把普通分析前内联深度设0 | 7.1s，退出1；Graal内部MetadataTracer单例缺失，配置不能采用 |
| 16 | 恢复默认分析，只将构造器内联节点预算设0 | 49.2s，OOM退出3；这一限制也未解决 |
| 17 | 分析前内联深度 20→2 | 162.8s，96次Full GC，OOM退出1；10153类型/30063方法；与13轮同一堵墙，且更慢 |
| 18 | --parallelism=4→2 | 98.5s，OOM退出1；9787类型/23447方法；首个失败也是Blocks的lambda |
| 19 | 首次启用定时浅层快照10/16/22/30s | 207.1s，OOM（GC overhead limit）退出1；12915类型/44814方法；取得墙前类别分布 |
| 20 | --parallelism=4→1 | 56.4s，OOM退出1；7586类型/15040方法；单线程同样占满堆 |
| 21 | --initialize-at-build-time=...Blocks | 4.6s；Not bootstrapped (registry minecraft:game_event)，配置不可用 |
| 22 | 6 GiB，墙前定时线程栈14/18/22/26/30s | 77.0s，OOM退出1；主线程栈与OOM栈同一位置：`addRootMethod`→`createTypeFlow`→`nextQueuedNode`→`TypeFlowsOfNodesWithPredicates.clone` |
| 23 | 方法句柄分析前内联收紧到200节点/8层/50次 | 324.0s被CPU预算152终止（CPU 1848.7s）；487次Full GC，堆长期4510M→4510M，无完成迹象；该方向不解决 |
| 24 | 6 GiB，快照另记最大个体数组18/22/26s | 见§6b；判定不存在“少数巨型映射” |

09/10对照已核对classpath、CAP、策略和除堆/输出路径外的命令一致。10/11只改构建GC参数，增加GC参数分支导致构建器源码SHA不同，已单独记录；主机负载并非受控变量。这些是诊断实验，不是真机游戏性能测试。

资源边界为6/8 GiB堆、4分析线程、墙钟600秒、CPU1800秒、合计输出16 MiB、单文件64 MiB、FD512；先做主机内存/磁盘预检。HotSpot的GC工作线程可为9，`--parallelism=4`不限制整个构建JVM所有线程。进程组RSS没有硬限制，D0仍PARTIAL。

详细既有诊断见 [CLIENT_GRAPH_DIAGNOSTICS](CLIENT_GRAPH_DIAGNOSTICS.md)；最新12–24轮结论以本交接及各轮原始记录为准。第19轮启用了定时浅层快照，会停顿世界并扰动被测运行，因此它的可达类型数（12915）与其他轮不可直接比较。

**第 25 轮之后不再属于"分析墙"阶段**，索引如下（细节在对应小节，不重复列在本表）：

| 轮次 | 主题 | 小节 |
|---|---|---|
| 25–29 | 构建期方法拆分器、语义等价、完整分析通过 | §6e |
| 30–36 | 代码生成、jspawnhelper/sysroot 环境陷阱、可重定位镜像、iOS 链接 | §6f |
| 37–38 | iOS 宿主 App、签名装机、scene 清单崩溃 | §6g / §6h |
| 39 | 801 真因、镜像首次真正执行、joptssimple 反射 | §6i |
| 40–43 | 模拟器通道、反射修复、跑到 Datafixer 之后、LWJGL 阻断 | §6j |
| 44 | 图形栈侦察与方案 | §6k |
| 45 | GLFW/JNI/Metal启动实现、真实Window/RenderSystem模拟器AOT、Xcode调试Scheme | §6l |
| 46 | 用户真机蓝屏成功；纹理/传输/清除/fence及预编译四分屏呈现 | §6m |

## 6. 第13轮的新证据：能说明什么，不能说明什么

[原始构建输出](../artifacts/c0/client-graph-13/analysis/stdout.log)报告：

```text
Error encountered while parsing net.minecraft.world.level.block.Blocks.<clinit>(Blocks.java:54)
Caused by: java.lang.OutOfMemoryError: Java heap space: failed reallocation of scalar replaced objects
```

[诊断摘要](../artifacts/c0/census-summary-13.json)包含1152条分配样本。按每个样本的首个points-to栈帧统计，246条位于`TypeFlowsOfNodes.<init>`，129条位于`TypeFlowsOfNodesWithPredicates.<init>`；原始栈显示`HashMap`构造/扩容及`clone`。这是定位热点的证据，**样本数不能换算为所占堆字节或保留比例**。

OOM回调完成了浅层heap iteration：计数22375778个对象、1354443096字节，2个对象未识别到类。该遍历同时包含可达及不可达对象，且可能发生在其他线程已释放大图之后；其中还有JDK内部FillerElement等对象。因此它不是峰值保留堆、支配树或GC根路径。回调中的第一条失败线程栈也不一定等同于导致最大占用的分析线程，需结合构建器异常及分配采样判断。

本轮还有**失败时部分分析统计**：14112个类型、49919个方法、21294个字段。`analysisCompleted=false`，这些数不能称完整闭包。15轮因内部错误产生的1305类型等计数同样是失败快照。

### 诊断代理的实现与限制

- 第一方C源码：[oom_census.c](../interop/diagnostics/oom_census.c)；Java夹具：[CensusFixture.java](../interop/diagnostics/CensusFixture.java)。
- [prepare_census_agent.py](../tools/prepare_census_agent.py)编译Mac dylib，并在默认拒绝沙盒内用24 MiB第一方程序验证OOM栈和字节数组统计；[v2验证记录](../artifacts/c0/census-agent-v2/result.json)为VERIFIED，仅指代理自测。
- 采样使用公开JVMTI API，间隔16 MiB，最多4096条样本，采样日志约8 MiB上限，单个栈最多12帧；只记录类/方法/大小，不读取对象字段值。OOM浅层统计通过类标签和`IterateThroughHeap`完成。
- 初版夹具启用`ExitOnOutOfMemoryError`时只有AGENT_READY；关闭后才交付回调。固定HotSpot源码显示立即退出路径不执行正常清理。不要把代理加载成功当作统计已经取得。
- 代理仅加载到Mac构建JVM。它没有被加入iOS运行库/IPA，也不是iPhone运行前提。代理会影响测量，后续修复必须再做无代理对照。
- [summarize_census.py](../tools/summarize_census.py)明确区分采样与浅层计数，遇到部分文件不伪造完整统计。[test_census.py](../tests/test_census.py)有4项回归。

官方参考：[JVMTI 25](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html#ResourceExhausted)、[IterateThroughHeap](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html#IterateThroughHeap)。

## 6b. 第19轮的定时快照：墙前类别归属

代理新增第二个模式：系统属性 `fabricaot.census.at=10,16,22,30` 在VMInit后启动独立线程，于指定秒数执行 `IterateThroughHeap` 并写出 `SNAPSHOT_*` 记录；原有的OOM记录保持字节级兼容。用法由 `tools/probe_client_graph.py --census-at` 记录进命令行，可直接从 command.json 复核。快照停世界、本身耗内存，会改变被测运行的走向（第19轮比第13轮多活了99秒并改变了OOM类型），因此**只能用于类别归属，不能当作保留量或跨轮性能比较**。

| 快照 | 对象数 | 浅层字节 | 主导类别 |
|---|---:|---:|---|
| T10 | 9,765,688 | 486 MiB | `[B` 91.1 MiB、`reflect.Method` 76.7 MiB |
| T16 | 16,941,913 | 851 MiB | `[B` 144.2 MiB、`reflect.Method` 79.4 MiB |
| T22 | 75,834,935 | 3,134 MiB | `HashMap$Node` 1612.6 MiB / 52,840,900个 |
| T30 | 60,076,756 | 2,669 MiB | `HashMap$Node` 1183.1 MiB / 38,766,196个 |

T16→T22的9.4秒新增58,893,022个对象、2,282 MiB，其中`HashMap$Node`+1594.6 MiB、`[Ljava/util/HashMap$Node;`+378.8 MiB（127,096个表数组、100,876,926个槽位）；T22→T30反而少465 MiB，符合在途复制而非单调持有。同一时刻Graal图对象约260万个，flow对象约100万个（`MethodTypeFlow` 9.8万）。当时的"约20份状态引用同一批节点"是比例推断，**第24轮已把它修正为快照计数推断，见§6c**：条目并非集中在少数巨型映射里。

源码（固定提交6589574）确认：`TypeFlowsOfNodes` 每份状态一个 `HashMap<Node,TypeFlowBuilder<?>>`，`clone()` 全量复制；启用predicates时还多复制一份 `invokes`。常规非构造器方法的分析前内联预算只有1节点/1次调用，所以第17轮把深度从20降到2几乎无变化；真正宽松的是构造器（200/50）与方法句柄内建（10000节点、1000深度、10000次内联）。

## 6c. 第22–24轮：失败点定位与方法形状普查

第22轮在墙前14/18/22/26/30秒各发一次 `SIGQUIT`，取得5份线程转储（记录在 `artifacts/c0/client-graph-22-supervisor.json`）。其中3份（22/26/30秒）主线程停在**同一处**，且与第22轮OOM栈完全一致：

```
NativeImageGenerator.runPointsToAnalysis → PointsToAnalysis.doTypeflow → addRootMethod
→ DefaultAnalysisPolicy.staticRootMethodGraph → MethodTypeFlow.getOrCreateMethodFlowsGraphInfo
→ createFlowsGraph → MethodTypeFlowBuilder.apply → createTypeFlow → PostOrderNodeIterator.nextQueuedNode
→ TypeFlowsOfNodesWithPredicates.clone → new TypeFlowsOfNodes(HashMap copy)   [Blocks.java:54]
```

结论：墙在**单个方法的类型流图构建**阶段，不在收尾、不在可达性迭代、不在编译。注意第22轮主线程CPU在22→30秒只前进1.35秒（15.98s→17.33s），说明那段时间主要被GC占用，不能把"卡在clone"读成"一次复制耗时8秒"。

固定提交6589574的 `PostOrderNodeIterator` 说明代价结构：每遇到控制分割或带异常边的invoke都会执行 `nodeStates.put(x, state)`，而 `state` 是整份 `flows` 映射的全量 `clone()`。因此单个方法的峰值 ≈ **快照数 × 平均映射条目数**，两者都随方法规模增长，合起来是平方级。

新工具 `tools/scan_method_shape.py`（只读反汇编，不执行）给出客户端jar的方法形状普查（`artifacts/c0/method-shape-census-26.1.2.json`，6882类/68956方法）：

| 排名 | 方法 | 指令 | invoke | 条件分支 | 快照位点 | 代价代理 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `Blocks.<clinit>` | 12,966 | 7,331 | 2 | 7,333 | 47.5M |
| 2 | `BlockStateData.bootstrap3_2` | 22,001 | 2,868 | 0 | 2,868 | 31.5M |
| 3 | `VanillaRecipeProvider.buildRecipes` | 10,498 | 3,457 | 0 | 3,457 | 18.1M |
| 4 | `CopperGolemAnimation.<clinit>` | 11,947 | 2,048 | 0 | 2,048 | 12.2M |
| 5 | `Items.<clinit>` | 7,802 | 2,986 | 0 | 2,986 | 11.6M |

第1名的代价代理 47.5M 与第19轮实测的 52.8M 条目同量级（差9%），这是当前最强的定量一致证据；但它只是代理，不是内存测量。

第24轮给代理加了"最大个体数组"记录（`SNAPSHOT_LARGE`），用来判定条目到底是"少数巨型映射"还是"大量中等映射"：

| 快照 | `HashMap$Node` | 总表槽位 | `TypeFlowsOfNodesWithPredicates` 实例数 | 最大单个节点表 |
|---|---:|---:|---:|---:|
| T18 | 52,229,436 | 100,205,670 | 38,550 | 未进入前12大数组 |
| T22 | 51,892,642 | 99,123,186 | 18,917 | 未进入前12大数组 |
| T26 | 51,974,096 | 99,367,306 | 23,036 | 未进入前12大数组 |

全堆前12大数组都是 `[B`（最大4,194,304字节），唯一上榜的节点数组是 `ConcurrentHashMap$Node` 1,048,576槽。**因此不存在千万级条目的flows映射**，"少数巨型映射被复制"被排除。按99M槽位/14.4万张表、52M条目/12万张表计算，条目分布在平均约400–690槽的映射中；其中约7,331张8K槽级的表即可容纳约37M条目，与"Blocks.<clinit>按invoke逐个快照一个数千条目映射"相容。

## 6d. 第一方夹具：形状复现与拆分验证

为把"平方级"和"拆分可行"从推断变成实验，新增 `tools/probe_shaped_methods.py`：生成**完全第一方**的 `Shaped` 类（不含任何Minecraft内容），静态初始化器执行 N 次 `keep(i, make(i))`，可指定拆成 K 个方法由 `<clinit>` 串起来，然后用 `-H:+ExitAfterAnalysis` 只做分析阶段，记录退出码、墙钟、GC汇总与失败首行。

实验记录（均为Mac构建JVM，`-O1 --parallelism=4`，非Gate证据）：

| 记录 | N | parts | 堆 | 结果 |
|---|---:|---:|---:|---|
| `shaped-01-single-n4000` | 4000 | 1 | 512 MiB | 31.5s，OOM退出3，598次GC暂停共18.9s |
| `shaped-02-split16-n4000` | 4000 | 16 | 512 MiB | **14.1s，退出0，分析阶段完成** |
| `shaped-03-single-n4000-h2g` | 4000 | 1 | 2048 MiB | 122.6s被CPU预算152终止；1489M→1489M钉住，1063次GC暂停共111.6s；加堆也不通过 |

同样的4000次调用：512 MiB下单个方法OOM，2048 MiB下仍钉死在1.49 GiB不动；而拆成16个方法后512 MiB、14.1秒完成（GC暂停仅0.74s）。**这是"峰值由单方法规模决定、拆分可以消除"的受控证据**，也说明"加大堆"不是解决办法——2 GiB版本并没有更接近完成，只是更慢地耗尽。

这仍**没有**证明真实客户端被拆开后能通过：客户端叠加了1.0万类型/3.0万方法的宇宙、资源扫描、反射闭包和多个同类巨型方法（§6c第2–5名）。它证明的是修复方向的必要性，不是充分性。

注意：该夹具工具默认不套 `sandbox-exec`（Native Image的工具链检查需要执行 `cc`，B0策略拒绝），这一点已写进每份 `result.json` 的 `sandbox` 字段；被沙盒化的仍是真实客户端实验。

## 6e. 第25–29轮：构建期方法拆分器

第22–24轮证明"单方法规模决定峰值"，本轮把它落成一个可运行的**构建期字节码转换器**：`compiler/splitter/src/fabricaot/split/MethodSplitter.java`（ASM tree + Analyzer，唯一第三方依赖是 ASM，未入库，按 SHA-256 记录在构建回执里）。

### 转换规则（每条都能被静态判定）

方法成为候选的条件：`static`、描述符 `()V`、非 `abstract/native/synchronized`、`sites ≥ --min-sites` 且 `sites × instructions ≥ --trigger-cost`。

切点在满足以下全部条件的指令边界：

1. 操作数栈为空（避免跨段搬栈）；
2. 没有任何 jump/switch 跨过切点（任一方向的跨越都会让目标标签落到另一段）；
3. 没有异常表条目跨过切点——`start`/`end`/`handler` 必须落在同一段内，否则异常会跳到另一段的方法里；
4. 下一段读取的局部变量可搬运：按帧类型生成类型精确的合成静态字段（`fabricaot$spill$<切点>$<槽位>`），`null` 类型用 `aconst_null` 重建；未初始化槽位不搬运。

若用 `BasicVerifier` 拿不到精确引用类型，则只在"下一段不读取任何已初始化槽位"的边界切割，绝不猜类型。

输出约束：段之间**链式调用**（`<clinit>` 只进第 1 段，第 k 段末尾调用第 k+1 段）；被方法体赋值的同类 `static final` 字段会**清除 `ACC_FINAL`**（JVMS 6.5 规定 final 字段只能在自身 `<clinit>` 里写，否则运行期 `IllegalAccessError`）；jar 的签名条目（`META-INF/*.SF|*.RSA|…`）会被剥离，因为改动任何类都会让原签名摘要失效；每个改写过的类都用 `CheckClassAdapter` 复查，结构性错误则整类回退为原始字节并标记 `REJECTED`。

### 两个只有真实客户端才能暴露的缺陷

| 版本 | 现象 | 根因 | 修复 |
|---|---|---|---|
| split-02 | JVM 引导 `IllegalAccessError: Update to static final field SoundEvents.ARMADILLO_PEEK attempted from a different method (fabricaot$init$1)` | `static final` 只能由 `<clinit>` 写 | 清除被赋值字段的 `ACC_FINAL`（这些字段没有 `ConstantValue`，调用点仍用 `getstatic`，链接不变） |
| split-03 | `IllegalStateException: Adding duplicate key '...block.bamboo_wood.place'` | `<clinit>` 调用每一段、每段末尾又调用下一段 → 每个方法体执行两遍 | 只保留链式调用 |

第一版夹具之所以两个缺陷都测不出来：它的 `keep()` 是幂等的（覆盖同一数组槽），重复执行看不出来。夹具现已加入 `RUNS` 计数，重复执行会立刻显形；真正抓住问题的是真实客户端的注册表摘要。

### 夹具验证（第一方，不含任何 Minecraft 内容）

| 记录 | 形状 | 堆 | 结果 |
|---|---|---:|---|
| `split-fixture-01`（未拆分） | 4000 次调用 / 单个 `<clinit>` | 512 MiB | 31.5s，OOM 退出 3 |
| `split-fixture-01`（拆分后） | 64 段，最大 126 sites | 512 MiB | **14.3s，退出 0，分析阶段完成** |

拆分前后 `Harness` 的 64 个槽位输出逐字节相同（`diff` 为空）。

### 真实客户端转换结果（`artifacts/c0/client-split-04/`）

| 项 | 数值 |
|---|---|
| 扫描类 | 10,682 |
| 改写类 | 18（0 拒绝） |
| 拆分方法 | 28 |
| 生成段 | 358 |
| 局部变量搬运字段 | 0（这些方法都不用局部变量） |
| 清除 `ACC_FINAL` | `Blocks` 1,149、`Items` 1,485、`SoundEvents` 1,814、`BlockStateData` 397、`EntityType` 161、`RenderPipelines` 113，其余合计 47 |

拆分前形状普查最大 `snapshotSites` 7,333（`Blocks.<clinit>`）；拆分后最大 3,457，是 `VanillaRecipeProvider.buildRecipes`——它**不是** `static ()V`（实例方法、带参数），当前版本不处理，见§10。

### 语义等价证据：真实注册表摘要

`interop/diagnostics/ClientInitDigest.java` 在普通 JVM 上执行 `SharedConstants.tryDetectVersion()` + `Bootstrap.bootStrap()`，然后把 `Blocks` 的每个静态 `Block` 字段与它在 `BuiltInRegistries.BLOCK` 里的 id 拼成一行，排序后取 FNV-1a 摘要：

| 输入 | blockFields | registryEntries | digest |
|---|---:|---:|---|
| 原版 `26.1.2.jar` | 1,144 | 1,168 | `4fce5dfeb9c2f39b` |
| `client-split-04` | 1,144 | 1,168 | `4fce5dfeb9c2f39b` |

两者逐字节相同，记录在 [init-digest](../artifacts/c0/init-digest/result.json)。这说明拆分没有改变 `Blocks`/`Items`/`SoundEvents`/`EntityType`/`RenderPipelines` 等 18 个类的初始化顺序与产出值。它是 JVM 层证据，不覆盖渲染、不覆盖 Native Image、不覆盖 iOS。

### 分析结果

| 轮 | 输入 | 堆 | 结果 |
|---|---|---:|---|
| 25 | split-01（带签名） | 6 GiB | 14.2s，`SecurityException: SHA-384 digest error`（签名未剥） |
| 26 | split-02 | 6 GiB | **分析 34.2s 完成**（30,642 类型 / 108,256 方法），随后在 `NativeLibraries` 列目录被沙盒拒绝 |
| 27 | split-02 + 策略修复 | 6 GiB | `analysisCompleted=true`，38.9s，峰值 RSS 3.49 GB |
| 28 | split-04（链式修正） | 6 GiB | `analysisCompleted=true`，39.7s，**32,531 类型 / 112,219 方法** |
| 29 | split-04，`--full-build` | 6 GiB | 见下节 |

第 28 轮比第 27 轮多出的约 1,900 个类型就是 358 个生成段自身及其引用。

对比第 13–24 轮：同样的客户端、同样的 6 GiB 堆，此前最多到 10,153 类型就 OOM，现在完整分析通过。

## 6f. 第30–36轮：分析之后——代码生成、链接与 iOS 镜像

分析墙打通后，`--full-build` 让 Native Image 继续执行代码生成与链接。第 30–34 轮全部停在链接，原因逐层剥开，**都不是 Minecraft 的问题，而是构建环境与目标平台**：

| 轮 | 现象 | 结论 |
|---|---|---|
| 30 | `posix_spawn failed, error: 0` | 只给 clang 一个字面量 exec 许可不够 |
| 31 | 同上（仍失败） | 见下条：**根因是 JDK 的 `lib/jspawnhelper` 没有 exec 许可**，构建 JVM 的任何 `ProcessBuilder` 都会失败 |
| 32 | `ld: library 'dl' not found` | 直接调用工具链内部 clang 时它不生成 `-syslibroot`（`/usr/bin/clang` 那个壳会先问 xcrun），系统库全部解析不到 |
| 33 | 同上 | `SDKROOT` 已进入构建进程环境（`command.json` 的 `environmentKeys` 有记录）却没有到达链接子进程 |
| 34 | `building for 'macOS', but linking in object file ... built for 'iOS'` | `-H:NativeLinkerOption=-isysroot` 解决了系统库，却暴露出真问题：svm 自带的链接目标是宿主，它会拉入 macOS 的 `libdarwin.a` 与 macOS 平台标记 |

两个环境陷阱都用第一方夹具定位并留证，不靠猜测：

- `artifacts/c0/spawn-probe/`（`result.json`）：同一策略下四变体对比，`01-round31-policy` 无法派生任何子进程，`02-plus-jspawnhelper-exec`、`03-plus-fork-launch-mechanism`、`04-...+POSIX_SPAWN` 三者都成功。修复取最小改动——只给 `lib/jspawnhelper` 一条 exec 许可（与 `bin/java` 同级信任），写在 `tools/probe_client_graph.py`，并附注释说明证据位置。
- `artifacts/c0/spawn-probe/sdk-result.json`：`SDKROOT` 在沙盒内让 clang 产出 `-isysroot` 并链接成功，未设时 `ld: library 'dl' not found`。据此第 34 轮改为把 sysroot 写在链接命令行上（`-H:NativeLinkerOption`），因为它同时会出现在 `command.json` 里，可复现。

### 正确的 iOS 链接路径：复用 B1 配方

svm 自己的链接无法产出 iOS 产物，因此按 `tools/build_b1_probe.py` 已验证的做法，第 35 轮加 `--relocatable`，用 `-H:+ExitAfterRelocatableImageWrite` 让它只写出可重定位镜像对象：

| 项 | 数值 |
|---|---|
| 输入 | `client-split-04`（18 类 / 28 方法拆成 358 段） |
| 堆 / 并行 | 6 GiB / 4 |
| 结果 | **exit 0，`Finished generating 'client-graph'`，1m22s，峰值 RSS 4.0 GiB** |
| 对象 | `client-graph.o`，115,623,411 字节，SHA-256 `4a384f1589e8c25870c3ae3ec7ef853898f70ec0d148e008036b83525a5f651a` |
| 平台标记 | 无 `LC_BUILD_VERSION`（这正是第 34 轮 ld 把它当成 macOS 的原因） |

新增第一方工具 `tools/link_c0_ios.py`（结构对齐 `tools/link_a1_ios.py`）：校验运行库 `status=COMPILED` 且 `target=arm64-apple-ios17.0`（拒绝把模拟器归档改名顶替）、逐个校验六个归档的 SHA-256、用 `xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -dynamiclib` 链接。

第 36 轮（`artifacts/c0/client-link-02/`）第一次链接只差 13 个符号，全部是 iOS 运行库**按设计不实现**的 JVM/JNI 原生入口：

```
JNI_OnLoad_extnet
Java_com_sun_management_internal_OperatingSystemImpl_initialize0
Java_jdk_net_MacOSXSocketOptions_{getIpDontFragment0,getSoPeerCred0,getTcpKeepAliveIntvl0,
  getTcpKeepAliveProbes0,getTcpKeepAliveTime0,ipDontFragmentSupported0,keepAliveOptionsSupported0,
  setIpDontFragment0,setTcpKeepAliveIntvl0,setTcpKeepAliveProbes0,setTcpKeepAliveTime0}
```

按 AGENTS.md「未提供的 JVM 原生入口会明确终止」，工具只为 `_Java_*`/`_JNI_*` 生成第一方 C 桩（写 `stderr` 报符号名后 `abort()`），**其他任何未解析符号仍然让链接失败**——这条判定有单元测试覆盖。重链结果：

| 项 | 数值 |
|---|---|
| 状态 | `LINKED_WITH_UNSUPPORTED_ENTRYPOINTS`（不写成 LINKED，也不写成可玩） |
| 产物 | `client-graph.dylib`，114,187,752 字节，SHA-256 `a19c949c2faee9a7a311440a092990763a4a94005e1f56b00af48fa14d3f875e` |
| 平台 | `LC_BUILD_VERSION platform IOS, minos 17.0, sdk 27.2`，arm64 单架构 |
| 依赖 | 仅 iOS 框架与 `/usr/lib` 系统库，无 macOS 专属依赖 |
| 真机 | **NOT RUN** |

这证明的是「真实客户端的 AOT 代码可以被链接成 iOS 动态库」，不证明它在 iPhone 上能启动、能渲染、能进菜单。C0 仍为 BLOCKED。下一步是把该 dylib 装进最简单的主机 App（`graal_create_isolate` + 头文件里的 `run_main(argc, argv)`），交给用户真机安装，观察它在哪一阶段终止；届时第一个真正的 Minecraft 侧障碍才会出现（当前预期是 LWJGL/GLFW 的窗口与 OpenGL 绑定）。

## 6g. 第37轮：把镜像装进 iOS 宿主

目标从「产出 dylib」改为「用户能用手边的 Xcode 把它装到设备上并看到第一次真实错误」。新增两样东西：

| 新增 | 作用 |
|---|---|
| `ios/C0Harness/` | 最小 iOS App：`dlopen(client-graph.dylib)` → `graal_create_isolate` → `run_main(argc, argv)`，日志写 `Documents/c0-logs/` |
| `tools/build_c0_harness.py` | 校验 dylib 是 `platform IOS`+`arm64` → `xcodebuild archive` → `-exportArchive` → 可选 `devicectl install/launch/copy`，把每一步的真实返回码写进 `artifacts/c0/harness/result.json` |

宿主用 `dlopen` 而不是链接，是为了避开 `tools/link_c0_ios.py` 写入的 install name `@rpath/FabricAOTClient.dylib` 与嵌入文件名 `client-graph.dylib` 不一致的问题；`graal_create_isolate_params_t` 只按公开的 version-1 前缀手写结构体，不依赖头文件版本。预留地址空间默认 4 GiB（Graal 默认申请 ≥32 GiB 会被 iOS 拒绝），`TMPDIR`/`HOME` 指到沙盒，`run_main` 收到 `--username Dev --version 26.1.2 --gameDir/--assetsDir`（沙盒内空目录）等最小参数集。

结果：

| 项 | 数值 |
|---|---|
| 未签名编译 | BUILD SUCCEEDED（`CODE_SIGNING_ALLOWED=NO`） |
| 签名构建 | BUILD SUCCEEDED，`Apple Development: [LOCAL_SIGNING_IDENTITY]`，Profile `iOS Team Provisioning Profile: org.fabricaot.research.c0.kexin`（`ab354b01-…`） |
| 归档 / 导出 | ARCHIVE SUCCEEDED / EXPORT SUCCEEDED |
| IPA | `artifacts/c0/harness/export/FabricAOT C0.ipa`，39,117,679 字节，SHA-256 `e7d99f2c298a98a4212066107d3d2181abf3bf6057d16b5b445823e6d5748e71` |
| 嵌入 dylib | 114,187,752 字节，SHA-256 `a19c949c…f875e`，Xcode 的 `strip -D -S` 已作用其上 |
| 描述文件设备 | `ProvisionedDevices` **为空** |
| 真机 | **NOT RUN** |

`ProvisionedDevices` 为空不是签名失败：该 App ID 的 Team Profile 是新生成的，而账号下没有已注册的设备槽。要把 IPA 装上去，必须先让某台设备出现在描述文件里，而唯一途径是**连接并解锁设备后重新构建**（Xcode 会自动注册）。当次环境里：

- `Kexin的iPhone`（`YOUR_DEVICE_UDID`）、`Y·H`、`iPhone Lily` 全部 `unavailable`（未连接）；
- 唯一 `available (paired)` 的 `iPad Pro`（`YOUR_DEVICE_UDID`）处于锁屏，`xcodebuild -destination 'platform=iOS,id=…'` 直接报 `iPad Pro needs to be unlocked to enable development services`。

因此本轮交付到「可安装的签名 App + 一键脚本」为止，不宣称任何真机行为。用户解锁设备后执行 `python3 -B tools/build_c0_harness.py --device <UDID> --install --launch`，或直接在 Xcode 里 ⌘R；随后 `--pull-logs` 取回 `Documents/c0-logs/run-*.log`。

**预期在真机上先撞到的墙**（未验证，仅登记假设）：`Main.main` → 资源索引读取 → `System.loadLibrary("lwjgl")`（iOS 上没有对应 dylib）或 GLFW 的 `glfwInit`。第 36 轮那 13 个 abort 桩也在同一路径上，命中时会打印符号名。

## 6h. 第38轮：真机首启崩溃——缺 scene 清单

用户在 Xcode 里选了自己的 iPhone（`YOUR_DEVICE_UDID`）直接 ⌘R，停在 `main()`：

```
Thread 1: EXC_BREAKPOINT (code=1, subcode=0x188cfcdc)
  main.m:394  return UIApplicationMain(argc, argv, nil, NSStringFromClass(FAOTAppDelegate.class));
```

崩点在 `UIApplicationMain` 内部、**任何第一方代码执行之前**，subcode 落在系统库地址段。成因是 iOS 26 起强制要求 UIScene 生命周期：Info.plist 里没有 `UIApplicationSceneManifest`、AppDelegate 又没有 `configurationForConnectingSceneSession` 时，系统直接 trap，而不是给出可读异常。第 37 轮的宿主漏抄了 A1/B1 工程里的这两项（`ios/B1Harness/Info.plist` 有 `UIApplicationSceneManifest`，`main.m` 有 scene delegate）。

修复（build 2）：

- `Info.plist` 增加 `UIApplicationSceneManifest = {UIApplicationSupportsMultipleScenes: NO}`；
- `main.m` 改为 `FAOTSceneDelegate`（`UIWindowSceneDelegate`）在 `scene:willConnectToSession:` 里建 window，`FAOTAppDelegate` 只实现 `configurationForConnectingSceneSession:options:` 返回带 `delegateClass` 的配置。

装到真机：设备此时已连接，Xcode 的首次 Run 已把 `YOUR_DEVICE_UDID` 注册进 Team Profile，`ProvisionedDevices` 变成 `[YOUR_DEVICE_UDID, YOUR_DEVICE_UDID]`。

| 项 | 数值 |
|---|---|
| 命令 | `python3 -B tools/build_c0_harness.py --device YOUR_DEVICE_UDID --install --launch` |
| 构建/导出 | ARCHIVE + EXPORT 成功，IPA 39,118,501 字节，SHA-256 `10dfe0f4a7cf8ba1400f5a29ad6bc9df1a3b441b1933d4cc33167cdca7c63a14` |
| 安装 | `installed: true`；`devicectl device info apps` 列出 `FAOT C0  org.fabricaot.research.c0.kexin  0.1  2` |
| 启动 | `devicectl process launch` 等待 60 s 超时；无崩溃报告、无进程、`Documents` 为空 |

启动超时但没有崩溃日志，说明是**设备锁屏**导致前台启动被拦住（devicectl 可以在锁屏时安装，不能锁屏启动 App），不是又一次崩溃。scene 修复是否生效仍**未验证**——需要用户解锁后手动点开 `FAOT C0`，或再按一次 ⌘R。修好后的日志应出现在 `Documents/c0-logs/run-*.log`。

## 6i. 第39轮：镜像第一次真正执行——801 的真因与 joptsimple

scene 修复（build 2/3）之后 App 不再闪退，`Documents/c0-logs/` 出现 9 份日志，每一份都只有一行：

```
Fatal error: Failed to create the main Isolate. (code 801)
```

**801 = `CEntryPointErrors.RESERVE_ADDRESS_SPACE_FAILED`**（`substratevm/.../c/function/CEntryPointErrors.java:96`），不是"iOS 不支持"，也不是签名或 dlopen 问题。

两处关键定位：

1. 这句话出自 `JavaMainWrapper.java:447` 的 `EnterCreateIsolateWithCArgumentsPrologue`，也就是 **`run_main` 内部自己创建 isolate** 时说的，不是宿主调用 `graal_create_isolate` 的结果。镜像只允许一个 isolate，宿主预先建好那个并不能被 `run_main` 复用。
2. 该 prologue 走 `MAIN_ISOLATE_PARAMETERS`，其中 `reservedSpaceSize` 恒为 0；`AddressRangeCommittedMemoryProvider.java:148-155` 对 0 的处理是 `max(maxHeapSize, MIN_RESERVED_ADDRESS_SPACE_SIZE)`，而后者是 **32 GiB**。

真机 mmap 探测（宿主在 `dlopen` 后、`run_main` 前直接测）证实了这一点：

| PROT_NONE 预留 | 结果 |
|---|---|
| 1024 MiB | OK（mprotect → RW 也 OK）|
| 2048 MiB | OK |
| 4096 MiB | OK |
| **32768 MiB** | **`Cannot allocate memory`** |

修复（build 4）：

- 宿主不再预建 isolate，改由 `run_main` 创建；
- 预留上限通过 **argv 的 `-XX:ReservedAddressSpaceSize=<字节>`** 传入（该选项注册在 `IsolateArgumentParser`，会被消费掉，不会出现在 Minecraft 的参数里）。走这条而不是 `graal_create_isolate_params_t`，是因为后者填的值到不了 `run_main` 那次创建；
- 日志改为**逐行 `fflush`**：上一版把内容攒在 `NSMutableString` 里，`failFatally` 一 abort 就全丢了，只剩最后一行；
- 默认预留从 4 GiB 降到 1 GiB（一次运行只能建一个 isolate，先确保能建起来）。

**结果：镜像真的执行了。**

```
[FAOT] run_main argc=20 argv=fabricaot-c0 -XX:ReservedAddressSpaceSize=1073741824 --username Dev ...
[FAOT] run_main returned 1
Exception in thread "main" java.lang.IllegalArgumentException: class java.io.File is not a value type
	at joptsimple.internal.Reflection.findConverter(Reflection.java:66)
	at joptsimple.ArgumentAcceptingOptionSpec.ofType(ArgumentAcceptingOptionSpec.java:106)
	at net.minecraft.client.main.Main.main(Main.java:77)
```

堆栈证明 `net.minecraft.client.main.Main.main` 已被调用，Java 异常能正常抛出、被 `ThreadGroup` 捕获并打印——AOT 镜像在 iPhone 上是活的。

下一个障碍是 `joptsimple`：`Reflection.CONVERTERS` 是 `HashMap<Class<?>, ValueConverter<?>>`，原构建里它属于 build-time 初始化（`--initialize-at-run-time` 只列了 `net.minecraft,com.mojang,org.lwjgl,com.microsoft,io.netty`），这张表被序列化进 image heap 后运行时按 `File.class` 查不到。修法是把 `joptsimple` 也加进 `--initialize-at-run-time`，让表在运行时重建（本轮正在重建镜像验证）。

## 6j. 第40–43轮：模拟器通道、反射修复，直到 LWJGL

**先解决"每次都要解锁手机"这个循环。** 真机 `devicectl` 拒绝在锁屏状态拉起前台 App，而迭代一轮要 3 分钟，人工守着的代价太高。`artifacts/a1/runtime-simulator/`（`target=arm64-apple-ios17.0-simulator`，status `COMPILED`）本来就在，于是补了模拟器通道：

- `tools/link_c0_ios.py --sdk iphonesimulator --runtime artifacts/a1/runtime-simulator` 用同一个镜像对象链出 `platform IOSSIMULATOR` 的 dylib；
- `tools/build_c0_harness.py --simulator <UDID>` 走 `-sdk iphonesimulator`、不签名、`simctl install/launch`，并从 `simctl get_app_container` 直接读宿主文件系统上的 `Documents/c0-logs/`。

模拟器里 `probe reserve 32768 MiB -> OK`（macOS 进程地址空间宽松），真机同一项是 `Cannot allocate memory` —— 这条差异正好复证了 §6i 对 801 的判断。

**反射才是 `joptsimple` 的真因。** `Reflection.findConverter` 的两条路都靠反射：`valueOfConverter` 调 `Class.getMethod("valueOf", String.class)`，`constructorConverter` 调 `Class.getConstructor(String.class)`，两条都吞掉 `NoSuchMethodException` 后抛 `"<type> is not a value type"`。Native Image 默认不带构造器/方法元数据，所以先报 `File`（`gameDir`/`assetsDir`），注册 `java.io.File` 的构造器后立刻变成 `Integer`（`width`/`height`/`fullscreen`），再注册 `Integer.valueOf(String)` 才过。`compiler/reflection-config.json` 里只有这两个类型，是 `javap net.minecraft.client.main.Main` 把全部 `ofType` 调用点列出来之后按证据加的，不是猜的。

**结果：客户端跑到了 Datafixer 之后。**

```
[20:54:07] [Datafixer Bootstrap/INFO]: 291 Datafixer optimizations took 260 milliseconds
WARNING: sun.misc.Unsafe::objectFieldOffset has been called by org.joml.MemUtil$MemUtilUnsafe
```

参数解析、log4j 初始化、`CrashReport.preload`、291 项 Datafixer 优化、JOML 的 Unsafe 路径全部正常。`java.lang.NoSuchMethodException: RuntimeMXBean.getStartTime()` 与 `oshi ... Operating system not supported: Unknown` 都是非致命告警（log4j 与硬件信息采集降级）。

顺带修掉 `Could not create directory /logs`：log4j 把 `logs/latest.log` 解析成相对路径，而 iOS 的工作目录是只读的 `/`；宿主现在先 `chdir` 到 `--gameDir`，日志落在 `Documents/game/logs/`。

**阻断点（Gate C 的真实边界）：**

```
java.lang.LinkageError: Unknown platform: iOS
	at org.lwjgl.system.Platform.<clinit>(Platform.java:128)
	at org.lwjgl.glfw.GLFW.<clinit>(GLFW.java:24)
```

LWJGL 3.4.1 的 `Platform` 静态初始化只认 `Windows` / `FreeBSD` / `Linux` / `SunOS` / `macOS`（`javap` 确认是 `os.name` 的 `startsWith` 链），其余一律 `LinkageError`。用 `-Dos.name=Mac OS X` 绕过只把失败推后了一步，并暴露出真正的墙：

```
[LWJGL] Platform/architecture mismatch detected for module: org.lwjgl
java.lang.UnsatisfiedLinkError: Failed to locate library: liblwjgl.dylib
	at org.lwjgl.system.Library.loadSystem(Library.java:177)
	at org.lwjgl.glfw.GLFW.<clinit>(GLFW.java:24)
```

也就是说：**iOS 上没有 LWJGL 的原生库，GLFW 也没有 iOS 后端**。这才是"C0 不能算通过"的实质原因——不是 AOT、不是签名、不是内存，而是图形与窗口层在 iOS 上不存在。`-Dos.name` 仅用于诊断，宿主里的注释已写明它不会让渲染工作。

## 6k. 第44轮：图形栈侦察——后端是接口化的，方案换成"三层替换"

本轮不写图形代码，只做只读核实，把"图形层要补什么"从模糊的"移植 LWJGL"收敛成可验收的工作包。完整方案见 [GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md)，决策与否证的备选见 [ADR-008](evidence/ADR-008.md)。以下为四项决定性事实。

### 后端本来就可插拔

`com.mojang.blaze3d.systems.GpuBackend` 只有 4 个方法：`getName()`、`setWindowHints()`、`handleWindowCreationErrors(GLFWErrorCapture$Error)`、`createDevice(long, ShaderSource, GpuDebugOptions)`。配套的 `GpuDeviceBackend`（26）、`CommandEncoderBackend`（19）、`RenderPassBackend`（14）也全是接口，而 `GpuDevice`/`CommandEncoder`/`RenderPass` 是转发用的普通类——参数校验与生命周期官方已写好。

`Minecraft` 构造函数里不是硬编码 GL，而是一个回退循环（字节码偏移 803–1017）：

```
803: anewarray GpuBackend            → new GpuBackend[1]
809: new GlBackend() + aastore       → backends[0] = new GlBackend()
863: new Window(..., backend)
928: backend.createDevice(window.handle(), shaderSource, debugOptions)
937: RenderSystem.initRenderer(device)
943: catch BackendCreationException → LOGGER.error("Failed to create backend {}")
                                    → 累加 "No supported graphics backend was found.\n- Tried <name>: <msg>"
1017: window == null → MessageBox.error(...) + throw WindowInitFailed
```

**Metal 后端的注入点就是这个数组**：构建期把 `iconst_1` 改成 `iconst_2` 并在 `aastore` 后追加 `new MetalBackend()`，客户端自己按"先 Metal、失败退 GL"尝试，失败路径复用官方异常与用户可读汇总。

### OpenGL 引用零泄漏

124 个 `org/lwjgl/opengl/*` 引用只出现在 13 个类里，且全部位于 `com.mojang.blaze3d.opengl` 包内（`GlStateManager` 63、`GlCommandEncoder` 15、`DirectStateAccess$Core` 13、`GlDebug` 9、`GlDevice` 5，其余 8 个类 1–4）。筛选"引用方不在该包内"的结果是**空集**。所以不走 `GlBackend` 就完全不需要 GL 兼容层——这条排除了 GL→Metal 逐调用转译的必要性。

### GLFW 是唯一横跨全局的本机依赖

85 个引用 / 74 个唯一符号，其中 59 个 `glfw*` 函数、15 个 LWJGL 结构体访问器。使用方集中在 `blaze3d/platform`：`Window` 29、`GLX` 13、`InputConstants` 12、`VideoMode`/`Monitor`/`ScreenManager`/`GlDevice` 5–6、`GLFWErrorScope`/`TextInputManager`/`CursorType`/`ClipboardManager` 2–4。

4 个**非上游 GLFW** 的符号必须在替身库里显式实现（3 个 Mojang 定制分支的 IME 支持 + 1 个 LWJGL 的 macOS 访问器）：`glfwSetIMEStatusCallback`、`glfwSetPreeditCallback`、`glfwSetPreeditCursorRectangle`、`glfwGetCocoaWindow`（iOS 上返回 0 让上层降级）。

### 着色器语料小且版本统一

jar 内 `assets/minecraft/shaders/`：88 个 GLSL 文件（`.vsh` 35 / `.fsh` 44 / `.glsl` include 9），**全部 `#version 330`**，总计 54,213 字节，最大 `core/terrain.fsh` 3,374 字节；`core/` 69、`post/` 10、`include/` 9。`ShaderSource` 是单方法接口 `String get(Identifier, ShaderType)`，后端可以忽略传入的 GLSL、改按 id 查预编译 MSL。

### 结论与工作包

三层替换，**不是**移植 LWJGL 的 GL 绑定，**不是** GL→Metal 转译层：

| 工作包 | 内容 | 验收 |
|---|---|---|
| G1 | `libglfw.dylib` 替身：UIKit + `CAMetalLayer`，74 个符号（59 个 `glfw*` + 15 个结构体访问器，含 4 个非上游扩展） | `GLX._initGlfw` 通过、`Window` 构造成功、事件通路可派发 |
| G2 | `liblwjgl.dylib` 替身：`system`/`util`/`stb`（68 个引用） | 越过 `Platform.<clinit>`，STB 能解 PNG |
| G3 | Metal 后端（`GpuBackend` + 三个 `*Backend`，Java ~25 类 + ObjC++ 桥） | C0a：真机出现 Metal 渲染的首帧 |
| G4 | 构建期 GLSL 330 → SPIR-V → MSL（88/88，`xcrun metal` 编译通过） | C0b 的前置 |
| G5 | 触摸 → GLFW 回调 | C0b：主菜单可点 |
| G6 | OpenAL 35 个符号 → AVAudioEngine（或先静音设备） | C1 |

最大风险按严重度：render pipeline state 缓存键（漏一个 state 就出现错管线复用）、UBO/UTB 偏移与 4 KB 限制、纹理格式映射、GLSL 精度与 `discard` 语义。**预设否证点**：某个 shader 翻译语义不符时记为 `UNSUPPORTED` 并明确报错，不手改 MSL、不静默出黑图。

本轮数据来自一次性只读检查（`javap` + jar 内统计 + 既有 `client-native-call-inventory.json`），未固化为工具；复现命令见方案文档 §7。**没有任何图形代码被编写，C0 未变化。**

## 6l. 第45轮：窗口、固定JNI回调与Metal启动实现

实现/命令/已验证行为和已知局限以 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md) 为准。新增代码在 `ios/glfw-lite`、`ios/lwjgl-lite`、`ios/metal-bridge`、`compiler/lwjgl-lite`、`compiler/metal-backend`、`interop/graphics`；构建/采集入口是 `build_glfw_lite`、`build_lwjgl_lite`、`build_metal_backend`、`collect_graphics_probe`。`probe_client_graph`增加指纹校验的overlay及window/metal探针模式。`build_c0_harness`显式验证/嵌入原生库并支持独立输出目录，已有归档不自动删除。

真实Window/RenderSystem的模拟器AOT已通过并截图；149项回归、C状态夹具ASan/UBSan、JVM原生/Unsafe内存一致性、回调容量负例、隔离Window构造/关闭已执行。模拟器结果见 `artifacts/graphics/metal-simulator-evidence-01`。`glfw-*-02`补充IME常量与尺寸加锁；MetalProbe工程引用最新iPhone窗口库。真机待用户在Xcode运行，不能提升C0/C0a。

## 6m. 第46轮：真机诊断确认与GPU资源通路

用户确认蓝色画面后进入日志；`artifacts/graphics/device-run-02`保存原始设备日志与逐项判断，Apple A20 Pro GPU、1398×2034、真实Window/RenderSystem与Metal清屏、入口返回0。未确认退出Xcode后独立启动。旧日志中的后台读取UIView.layer与present后读取drawable.texture均已修正；新模拟器运行请求Apple运行检查并确认Metal API validation启用，这两条警告未复现。

新增 `TextureSpec`、`MetalTexture`/`MetalTextureView`、`MetalCommandEncoder`和清除型`MetalRenderPass`；原生实现RGBA8/RED8/RED8I/DEPTH32、mip视图、上传/复制/读回、共享buffer切片映射、颜色/深度清除和fence。`present.metal`构建期生成平台专属metallib，运行时仅载入预编译资源。游戏pipeline、绘制与绑定仍明确失败。完整资源预算、同步策略和未覆盖API见[GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。

`resources-aot-04`用6 GiB/4线程在56.36秒生成镜像，Simulator与iPhoneOS分别链接。`resources-simulator-evidence-04`保留四格式GPU比对、三mip、非对齐行/切片、深度清除、fence成功及四分屏截图；早期两次夹具遗漏usage标志的失败日志保留，最终版补齐真实游戏API要求。Java边界契约与C像素转换ASan/UBSan通过；151项Python回归见`regression-06`。

同一Xcode工程默认配置与MetalProbe均已切到`resources-link-ios-04`及`xcode-device-input-02`；默认设备目标未签名构建通过，4库UUID与metallib核对通过，见`xcode-default-device-check-02`。助手未安装/启动实体手机；用户下一次⌘R预期红/绿/蓝/黄四分屏20秒后日志。C0/C0a仍BLOCKED，G4/G6仍NOT RUN。

用户随后确认四色，`device-run-03`保存四格式GPU比对/呈现与探针完成标记。此次宿主返回行缺失，定位到重定向FD无O_APPEND，延迟系统输出可覆盖宿主独立append流写入的记录。`log_file.h`统一打开O_APPEND，`C0LogAppendProbe.c`在ASan/UBSan下验证两路写入不覆盖；151项回归通过，设备目标重建见`xcode-default-device-check-03`。真机资源行为证据有效，正常入口返回与独立启动条件仍不得推断。

## 6n. 第47轮：原版着色器、绘制与真实Main（模拟器）

用户要求仅模拟器、不操作手机、不提问，自主推进到可玩。STB/NativeImage的PNG、缩放、裁剪GPU上传通过；固定回调18种×32槽。原版shader语料经实际RenderPipelines和GlslPreprocessor收集为60种程序，覆盖79入口+9include；glslang与SPIRV-Cross在隔离环境构建，60/60翻译和metallib通过。跨阶段varying位置按名称统一，绑定使用Cross真实分配值。

`draw-simulator-evidence-02`验证87条原版PSO及真实GUI shader的混合、纹理、归一化顶点、UBO、裁剪、索引偏移/baseVertex/实例和三角扇像素结果；截图已检查，正常返回0，无Metal/主线程验证警告。此结果使用第一方几何，尚非真实菜单。必须使用`client-split-04`；02旧包缺final字段修正，会在RenderPipelines初始化报END_PORTAL_SNIPPET。构建器已拒绝旧拆分报告。

`inject_metal_backend.py`只扩容候选数组并把Metal放在首位，保留原回退循环；移除已失效的逐文件签名清单、保留主属性。真实Main在模拟器已经运行至UIKit窗口和Metal设备初始化。先解决HTTPS处理器未启用，再编译OpenJDK的libextnet，13个缺失链接入口降为1个未触发的management入口。当前真实阻断是OpenAL模块的iOS加载；正在接入公开Apple OpenAL并验证实际PCM通路。

`stage_game_assets.py`验证26.1.2固定索引30和4,750项对象（457,972,321字节），本地缓存不匹配的145对象从固定官方源补齐；已复制到专用模拟器，原账户/存档/Mod保持原位。170项Python回归PASS（regression-13）。C0/C0a仍BLOCKED，真实菜单/世界未验收。

## 7. 当前代码、版本及可恢复快照

最近已提交版本：

- `fe15a74`：第08–11轮有界诊断、GC对照、元数据审计；该阶段79项测试。
- `51e6aea`：A0/A1/B0/B1相关第一方源代码、工程和证据工具。

**最新研究代码尚未提交，交接保留原工作区。** 下列分组记录第44轮的36项变更；第45–46轮新增图形代码与工具见§6l/§6m，当前完整清单以`git status --short`为准。

**构建期转换与镜像生成**

| 路径 | 状态 / 用途 |
|---|---|
| `compiler/splitter/src/fabricaot/split/MethodSplitter.java` | 新增；ASM tree + Analyzer 的构建期方法拆分器（切点条件、局部变量搬运、`ACC_FINAL` 清除、签名剥离） |
| `compiler/reflection-config.json` | 新增；`java.io.File` 构造器 + `Integer.valueOf(String)`（按 `Main` 全部 `ofType` 调用点取证） |
| `tools/split_methods.py`、`tools/build_method_splitter.py` | 新增；拆分器 CLI 与 Java 构建 |
| `tools/probe_client_graph.py` | 修改；`--full-build`、`--relocatable`、`--initialize-at-run-time`、`--census-at`、`--parallelism`、jspawnhelper exec 许可 |
| `tools/link_c0_ios.py` | 新增；`--sdk iphoneos/iphonesimulator`、`--runtime`、`--stub-unsupported-jni`，运行库 target 校验 |
| `tools/build_c0_harness.py` | 新增；dylib 平台校验 → `xcodebuild archive` → `-exportArchive` → `devicectl`/`simctl` install/launch/pull-logs |

**iOS 宿主**

| 路径 | 状态 / 用途 |
|---|---|
| `ios/C0Harness/main.m` | 新增；`dlopen` + `run_main`，`-XX:ReservedAddressSpaceSize` 注入，逐行 flush 日志，`FAOTSceneDelegate`，`chdir` 到 gameDir |
| `ios/C0Harness/Info.plist`、`C0Harness.xcodeproj`、`ExportOptions.plist` | 新增；`UIApplicationSceneManifest`、Bundle ID `org.fabricaot.research.c0.kexin`、Team `YOUR_TEAM_ID` |

**诊断工具（分析墙阶段，已收敛）**

| 路径 | 状态 / 用途 |
|---|---|
| `interop/diagnostics/oom_census.c`、`CensusFixture.java` | 新增；Mac 构建 JVM 的 OOM 栈/浅层/定时快照代理与第一方夹具 |
| `interop/diagnostics/ClientInitDigest.java` | 新增；真实注册表 FNV-1a 摘要（拆分语义等价证据） |
| `tools/prepare_census_agent.py`、`summarize_census.py`、`probe_thread_samples.py`、`scan_method_shape.py`、`probe_shaped_methods.py`、`await_c0_log.py` | 新增；代理编译自测、摘要、SIGQUIT 线程栈、方法形状普查、第一方拆分夹具、设备日志轮询 |

**测试**

`tests/test_c0_harness.py`、`test_census.py`、`test_link_c0_ios.py`、`test_method_shape.py`、`test_shaped_source.py`、`test_split_methods.py`、`test_thread_samples.py` 均为新增；`test_client_graph_comparison.py` 为修改（夹具写解析后路径，避开 `/var`→`/private/var` 误报）。

**文档**

`docs/WORK_HANDOFF.md`（本文件，尚未纳入 Git）、`docs/GRAPHICS_STACK_PLAN.md`、`docs/evidence/ADR-008.md` 为新增；`README.md`、`docs/STATUS.md`、`docs/BUILDING.md`、`docs/CLIENT_GRAPH_DIAGNOSTICS.md`、`docs/evidence/ADR-003.md`、`docs/.codex/{index,memory,project}.md` 为修改。

**可恢复快照**

`artifacts/evidence/handoff-snapshot-20261108/` 只含第 13 轮之前的 6 个研发源文件，**已严重过时**（不含拆分器、iOS 宿主、链接器与全部新测试）。恢复时以工作区为准，不要用该快照重建。`.workbuddy/`、`logs/`、`ios/C0Harness/build/` 是本地运行产物，不属于交付源码。

不要只 checkout `fe15a74` 或 `51e6aea` 便宣称已经拿到最新源码。

`.cache/`及`artifacts/`受Git忽略，克隆源码不会自带工具链、客户端、签名材料和实验日志；必须保留本机原始目录。没有设置远程或推送游戏内容。

## 8. 复现命令与输出约定

所有命令从项目根执行。输出目录/文件必须尚不存在；重试换新名称，不覆盖12–16及更早记录。先检查主机余量，不并行启动多个大堆分析。

```bash
cd $HOME/Documents/ChatGPT/MCFAO
python3 -B -m unittest discover -s tests -v
python3 -B tools/prepare_census_agent.py --output artifacts/c0/census-agent-new
python3 -B tools/probe_client_graph.py --heap-gib 6 --oom-stack --census-agent artifacts/c0/census-agent-new --census-at 10,16,22,30 --output artifacts/c0/client-graph-new
python3 -B tools/summarize_census.py --input artifacts/c0/client-graph-new/work/census.tsv --output artifacts/c0/census-summary-new.json
python3 -B tools/probe_client_graph.py --heap-gib 6 --oom-stack --parallelism 1 --analysis-inline-depth 2 --output artifacts/c0/client-graph-new-p1
python3 -B tools/probe_thread_samples.py --output artifacts/c0/client-graph-new-dump --at 18,22,26
python3 -B tools/scan_method_shape.py --jar "$CLIENT_JAR" --top 15 --output artifacts/c0/method-shape-census-new.json
python3 -B tools/probe_shaped_methods.py --output artifacts/c0/shaped-new-single --invokes 4000 --parts 1 --heap-mib 512
python3 -B tools/probe_shaped_methods.py --output artifacts/c0/shaped-new-split --invokes 4000 --parts 16 --heap-mib 512
python3 -B tools/verify_evidence.py --output artifacts/evidence/verification-new.json
```

第 25 轮之后新增的链路（**分析墙已不需要再逐轮重跑**，仅在输入或拆分器变更时执行）：

```bash
# 1) 构建拆分器 + 拆分真实客户端（--dry-run 先看报告，不写 jar）
python3 -B tools/build_method_splitter.py --output artifacts/c0/splitter-new
python3 -B tools/split_methods.py --jar "$CLIENT_JAR" \
  --output-jar artifacts/c0/client-split-new/client.jar \
  --report artifacts/c0/client-split-new/report.json \
  --classpath-file <该实例的 libraries 列表> --dry-run
# 2) 完整构建并只写出可重定位镜像对象（--relocatable 走 ExitAfterRelocatableImageWrite）
python3 -B tools/probe_client_graph.py --heap-gib 6 --full-build --relocatable \
  --output artifacts/c0/client-build-new
# 3) 链成 iOS 动态库（真机与模拟器各一份；运行库 target 必须匹配）
python3 -B tools/link_c0_ios.py \
  --image artifacts/c0/client-build-new/work/client-graph.o \
  --runtime artifacts/b1/runtime-ios --output artifacts/c0/client-link-new/client-graph.dylib \
  --stub-unsupported-jni
python3 -B tools/link_c0_ios.py \
  --image artifacts/c0/client-build-new/work/client-graph.o \
  --runtime artifacts/a1/runtime-simulator --output artifacts/c0/client-link-sim-new/client-graph.dylib \
  --sdk iphonesimulator --stub-unsupported-jni
# 4) 装进宿主 App（模拟器通道不需要解锁设备；真机通道需要设备已解锁并注册）
python3 -B tools/build_c0_harness.py --dylib artifacts/c0/client-link-sim-new/client-graph.dylib \
  --simulator <UDID> --install --launch --pull-logs artifacts/c0/harness/sim-run-new
python3 -B tools/build_c0_harness.py --dylib artifacts/c0/client-link-new/client-graph.dylib \
  --device <UDID> --install --launch --pull-logs artifacts/c0/harness/device-run-new
```

镜像对象名由 `--relocatable` 写出，位于该轮 `work/` 下（第 35 轮记录为 `client-graph.o`，115,623,411 字节，SHA-256 `4a384f15…651a`）；不要硬编码文件名，先看该轮 `result.json`/`work/`。模拟器中 `probe reserve 32768 MiB` 会成功而真机失败，这是 mprotect 预留探测的宿主差异，不能拿它证明真机能跑。

`python3` 必须是3.11或更新的解释器：本机的 `/usr/bin/python3` 是3.9.6，`tools/bootstrap_toolchain.py` 使用 `hashlib.file_digest`，在3.9下会有20项测试报错而看起来像回归。第17–44轮使用 `$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3`。`$CLIENT_JAR` 指启动器meta目录下的 `26.1.2.jar`（本机见§4）。

`probe_client_graph.py`在分析未完成时返回2；读取每轮result.json、analysis/command.json及原始stdout/stderr确认具体原因。当前参数中的conservative、内联深度0、构造器预算0均为**失败实验开关**，不是推荐的生产配置。直接关闭首次OOM退出也可能只换来长时间GC并最终耗尽CPU预算。

每轮源快照、参数、输入指纹、GC及诊断报告保存在各自目录；比对时区分构建JVM配置与目标iOS配置。`--shared`、`IOS_AARCH64`和实际iOS静态库路径不能证明交叉编译链所有阶段已通过。分析阶段禁用的工具链探测也不构成发布验证。

B0/B1重新构建见 [B0复现](B0_TEST_HANDOFF.md)、[B1记录](B1_DEVICE_HANDOFF.md)、[BUILDING](BUILDING.md)。改变B0源码/Java/依赖后必须重新prepare；B1历史输入固定来自run-04，不能用新一轮不同Target指纹覆盖既有链。

## 9. 验证、中央登记与数据保留

当前源码的Python回归：**170项PASS**，见 [原始日志](../artifacts/graphics/regression-13/stderr.log)。历史133/123/101项记录保留。图形集成的执行范围、截图和局限见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)，不替代真机或游戏验收。

证据完整性复核见 [verification-c0-22-24.json](../artifacts/evidence/verification-c0-22-24.json)（976条命令/78个二进制/730份报告，PASS）；只核对已存日志/二进制/报告和当前源清单，不能替代Gate行为。

中央AAR唯一位置：`$HOME/Documents/Codex/monitor/registry.sqlite`，CLI：`$HOME/Documents/Codex/monitor/bin/aar`。不得设置AAR_HOME切换私有数据库。

新增12–16轮、代理构建、自测、源快照及交接核验的登记回执见 [registry-handoff-20261108.json](../artifacts/registry-handoff-20261108.json)；第17–21轮与定时快照工具的登记回执见 [registry-c0-17-21.json](../artifacts/registry-c0-17-21.json)；第22–24轮（线程转储、方法形状普查、第一方夹具）见 [registry-c0-22-24.json](../artifacts/registry-c0-22-24.json)。历史记录见`registry-c0-diagnostics.json`与`registry-b1-c0.json`。安全删除标志保持false，不执行清理；登记目录不授权递归删除。本文是项目源文档，按SOURCE保留。

可靠派生摘要的登记可以包含生成命令；历史运行结果与时间戳不能承诺精确再生成。若有登记失败必须明确报告，不以目录存在替代成功登记。Xcode构建树有符号链接，不能直接递归跟随，也不得为了登记删除链接。

第30–36轮的登记回执见 [registry-c0-30-36.json](../artifacts/registry-c0-30-36.json)：`artifacts/c0` 1,773 项（BUILD）、`artifacts/evidence` 497 项（GENERATED）、工具链缓存 4 项、上游源码缓存 3 项、Metal 组件 12 项，全部 `safeToDelete=false`。`tools/register_artifacts.py` 在这轮修了两处，否则本次证据根本登记不上：

1. **单个路径失败不再中止整轮**。此前 `artifacts/a1` 因符号链接抛错就整体退出，排在它后面的 `artifacts/evidence` 从未被登记。现在失败会收集进 `failures` 并在末尾以退出码 2 报告（`artifacts/a1` 仍失败，因为 AAR 自身拒绝含符号链接路径组件的登记；这符合§9上一条的既有规定，不是新问题）。
2. **只拒绝逃出证据树的符号链接**。Xcode 在自己构建产物里留了相对链接（`BuildProductsPath/.../A1Harness.app -> ../../InstallationBuildProductsLocation/...`），解析后仍在树内，此前被判为违规。

`.cache/upstream` 被 AAR 判为"内容已变"。核验后才接受：`graal-6589574…tar.gz` 的 SHA-256 是 `d88726885469868457898ee204673a4c849bc03f897d53120c46e6c4ffa27e0b`，与 `compiler/upstream.lock.json` 的 `archiveSHA256` 完全一致，即该目录是固定归档的解包产物；另外删掉了 Finder 生成的 `.cache/upstream/.DS_Store`（非证据文件）。没有任何第一方文件被改动。

## 10. 后续优先级及验收条件

### P0（已完成，保留供复核）：按"单方法规模"修复分析内存

1. **已闭环**：墙的位置（第22轮线程栈）与代价结构（第22–24轮快照＋方法形状普查）定位到"单个巨型方法的类型流图构建"；修复落在 `compiler/splitter`，第 28 轮真实客户端完成分析。不要再重复已排除的方向：分析前内联深度（17轮）、构造器内联预算（16轮）、并行度1/2/4（18/20轮）、关闭primitive跟踪与predicates（14轮）、单类构建期初始化（21轮）、收紧方法句柄内联（23轮）、加堆（10/11/20轮与夹具第3组）。
2. **仍待补的两类方法**：`VanillaRecipeProvider.buildRecipes`（3,457 快照位点）、`BlockStateData.bootstrap3_2`（2,868）等**实例方法/带参方法**目前不在拆分范围内（拆分器只处理 `static ()V`）。第 28 轮已能在不拆它们的前提下完成分析，所以不阻塞；若后续某个 Mod 或版本升级再次顶到墙上，再扩展拆分器而不是先动 Graal。
3. **不要改 Graal**：修改 `TypeFlowsOfNodes` 表示（紧凑 map/写时复制）成本更高，需固定源码 SHA、独立工具链副本并先证明 Node 键等价性与 clone 隔离。仅在拆分路线被真实客户端否证后才考虑。

### P0（当前前线）：补全 iOS 图形栈

按 [GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md) 的 G1–G6 推进，决策理由与已否证的备选见 [ADR-008](evidence/ADR-008.md)。要点：

1. **当前开发顺序**：用户真机窗口/RenderSystem/蓝屏通路已验证；资源探针在模拟器验证通过，Xcode已备好四分屏版供用户运行。STB、原版pipeline/绑定/绘制与构建期shader变体已经模拟器验证；真实Main已初始化Metal，继续补音频和后续游戏引导缺口。
2. **注入点**：`Minecraft` 的 `GpuBackend[]`（字节码偏移 803–1017 的回退循环）。构建期 ASM 扩容数组并在首位插入 `MetalBackend`，不改控制流、不走 `-Dos.name` 伪装。
3. **验收按子门槛**：C0a（Metal 清屏首帧）→ C0b（真实主菜单 + 触摸）→ C0c（创建世界/存档）。任一未达成就记 BLOCKED，不用"构建成功"或渲染 demo 代替。
4. **着色器不手改**：G4 只在构建期做 GLSL 330 → SPIR-V → MSL；语义不符的 shader 记 `UNSUPPORTED` 并在启动时报错，不允许静默出黑图。
5. **风险最高处**：render pipeline state 缓存键（漏 state → 错管线复用）、UBO/UTB 偏移与 4 KB 上限、纹理格式映射、触摸→相对光标的映射。

### P1：完整 Fabric 静态化仍需实现

产品链应为本地资产/Mod解析及哈希核验→隔离的Mixin/ClassTweaker转换→最终类快照、覆盖报告与动态定义拒绝→AOT分析→iOS对象生成/链接/签名→用户真机引导。当前核心客户端诊断没有完成这条全链。

### P1：按阶段补齐闭包与目标验证

图形层通过后，再按明确缺失点补齐反射、资源、JNI和类初始化，建立精确错误及负例。当前 `compiler/reflection-config.json` 只声明参数转换及日志实际访问到的精确方法，是"跑到哪补到哪"的最小值，不是完整闭包。

当前319个LWJGL引用只是10,682个class的静态候选；GLFW的59个前缀名称含Java辅助函数，实际C导出58个，另有13个GL引用类与88个shader源文件（含9个include）。见[GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)与[GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md)。这仍不是完整动态依赖或逐调用验证结果；音频、世界保存和性能测试在后续Gate。

## 11. 关键入口速查

| 内容 | 入口 |
|---|---|
| 产品与验收约束 | AGENTS.md、docs/TECHNICAL_GATES.md、docs/ACCEPTANCE.md |
| 总体状态 / 项目记忆 | docs/STATUS.md、docs/.codex/ |
| **当前前线：图形栈实现与验证** | **docs/GRAPHICS_BOOTSTRAP.md、docs/GRAPHICS_STACK_PLAN.md、docs/evidence/ADR-008.md** |
| AOT源码运行库与链接 | tools/build_ios_runtime.py、tools/link_a1_ios.py、docs/evidence/ADR-001.md |
| Fabric转换与iOS夹具 | tools/prepare_b0.py、tools/run_b0_reference.py、tools/build_b1_probe.py、docs/evidence/ADR-002.md |
| 方法拆分（分析墙修复） | compiler/splitter/、tools/split_methods.py、tools/build_method_splitter.py、tests/test_split_methods.py |
| 真实客户端分析 | tools/probe_client_graph.py（`--full-build`/`--relocatable`）、artifacts/c0/client-graph-28/ |
| 拆分语义等价证据 | interop/diagnostics/ClientInitDigest.java、artifacts/c0/init-digest/result.json |
| iOS 镜像链接 | tools/link_c0_ios.py（`--sdk` 取 `iphoneos` 或 `iphonesimulator`）、artifacts/c0/client-link-sim-02/ |
| iOS 宿主与装机 | ios/C0Harness/、tools/build_c0_harness.py（`--device`/`--simulator`/`--pull-logs`） |
| 真机/模拟器运行日志 | artifacts/c0/harness/、tools/await_c0_log.py |
| Mac分配诊断（历史） | interop/diagnostics/、tools/prepare_census_agent.py、tools/summarize_census.py |
| 墙前定时快照 / 线程栈 | `--census-at`；tools/probe_thread_samples.py |
| 元数据/GC对照 | tools/client_graph_diagnostics.py、tools/compare_client_graph_runs.py |
| 图形面静态清单 | artifacts/evidence/client-native-call-inventory.json（319 引用，分组见 §6k） |
| 最有用的一条原始错误 | `LinkageError: Unknown platform: iOS`（§6j）⇒ 本文件 §10 P0 图形栈 |
| 生成物中央登记 | $HOME/Documents/Codex/monitor/registry.sqlite |

当前Xcode入口已切到四分屏资源探针，输入与构建核对见`xcode-default-device-check-02`；真机蓝屏诊断成功证据见§6m。后续用户运行新的资源探针后另存新设备证据，不改写历史包的运行状态。
