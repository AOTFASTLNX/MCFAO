# 真实客户端AOT分析诊断

Last reviewed: 2026-11-08。C0 BLOCKED，C1/C2 NOT RUN。本轮没有游戏启动、目标代码生成或手机执行。Mac脚本由助手操作，真机由用户负责。

## 有界对照结果

固定26.1.2客户端SHA256 b1b3158572666445eff01e82fad8c7de2e4953db6d354f311730d77a8359d0b0；同一Java25.0.2、classpath指纹、iOS静态库和CAP数据。四分析线程，墙钟600秒/CPU1800秒，日志16 MiB、单文件64 MiB、FD512，默认拒绝沙盒控制每轮先通过。主机约18 GiB物理内存；堆不超过45%，启动可用比例阈值为6 GiB时35%、8 GiB时45%，磁盘余量至少8 GiB。这是预检和Java堆上限，不是整个进程组RSS硬上限或完整D0认证。

| 轮次 | 构建堆/GC | 墙钟 | GC累计暂停 | Full GC | 最后GC后堆占用 | 结果 |
|---|---|---:|---:|---:|---:|---|
| 09 | 6 GiB / Parallel | 91.0s | 73.33s | 49 | 4.50 GiB | Java heap OOM，退出3 |
| 10 | 8 GiB / Parallel | 127.6s | 110.51s | 50 | 5.78 GiB | Java heap OOM，退出3 |
| 11 | 8 GiB / G1 | 119.4s | 95.04s | 22 | 7.99 GiB | Java heap OOM，退出3 |

以上均未超时或耗尽CPU预算。GC数值来自保留的HotSpot日志，带大小取整；暂停统计仅计算已结束事件，不包含全部并发GC工作。Native Image分析线程为4，构建HotSpot记录的Parallel GC Workers为9；不要把--parallelism误当作全部JVM线程数量。Safepoint采样最大线程数为17/18/18，不是完整线程峰值普查。

Darwin time报告的maximum resident set size分别为4548132864、4599791616、4770480128字节，另有CPU秒494.1/680.4/578.1；这与Java逻辑堆占用是不同指标。本轮不将它推导为iOS内存预算或整个进程树的持续监控。

完整分析统计均未生成，可达类型/方法数量保持UNKNOWN；build-output JSON也不存在，官方文档说明其成功构建生成条件。不能把缺失文件当作零可达对象。诊断target_info显示IOS_AARCH64，但clang版本/架构为空；关闭工具链探测的分析配置不能证明完整交叉编译链成立。

## 元数据与观察影响

各轮metadata-audit.json只读核查25个classpath内META-INF/native-image文件（124655字节）：542条反射声明（336条无条件）、26条JNI声明（1条无条件）、4条资源声明。216个反射批量成员标志是按类型声明的候选，不是成员总数或完整可达性覆盖；没有发现Preserve=all或全资源通配。SDK默认、Feature注册与推导反射尚未穷尽，不能排除元数据带来的闭包膨胀。

第08轮构建JFR自动开启目标JFR，因缺少LibMDependencies.cap提前失败，保留独立证据与当轮源快照。09至11使用GC日志、诊断模式、分析统计选项和外部time；不启用构建JFR，避免这一观察影响。不能伪造空CAP或用macOS库替代iOS库绕过该错误。

原始07未覆盖。09/10命令、classpath、CAP、沙盒策略和源码指纹对照通过；10/11只改变构建GC参数，新增参数分支造成构建器源码SHA不同，差异明确保留。两组主机负载/内存压力不是受控变量，所以不是严密性能基准。

## 复现与证据

使用未存在的新输出目录，顺序运行，不并行争用内存：

```bash
python3 -B tools/probe_client_graph.py --heap-gib 6 --output artifacts/c0/client-graph-new-6g
python3 -B tools/probe_client_graph.py --heap-gib 8 --output artifacts/c0/client-graph-new-8g
python3 -B tools/probe_client_graph.py --heap-gib 8 --builder-gc g1 --output artifacts/c0/client-graph-new-g1
python3 -B tools/compare_client_graph_runs.py --left artifacts/c0/client-graph-new-6g --right artifacts/c0/client-graph-new-8g --output artifacts/c0/heap-comparison-new.json
python3 -B tools/compare_client_graph_runs.py --left artifacts/c0/client-graph-new-8g --right artifacts/c0/client-graph-new-g1 --vary builder-gc --output artifacts/c0/gc-comparison-new.json
```

若主机余量不足，运行器保留BLOCKED并停止于分析前。每轮保存source/、policy.sb、metadata-audit.json、host-memory-before.log、analysis/{command.json,stdout.log,stderr.log}、work/gc.log、work/reports/和result.json。当前对照为artifacts/c0/heap-comparison-verified.json与gc-comparison-verified.json。比较脚本不会提升C0，即使未来分析完成，也必须另证目标对象、链接与真实引导。

第09–11轮当时没有对象分布或保留链。后续第13轮已取得分配采样、浅层统计并定位Blocks.<clinit>分析失败，14–16仍未解决；仍没有峰值保留链。最新实验和源码状态见[工作交接](WORK_HANDOFF.md)。全客户端Fabric静态转换、反射/资源/JNI闭包和真实iOS引导验收仍未完成。详见[ADR-003](evidence/ADR-003.md)。

## 第14–21轮：内存归属与已排除项

全部为同一固定客户端、同一Java 25.0.2与classpath、iOS静态库与CAP数据、六GiB堆（除注明）、默认拒绝沙盒、墙钟600秒/CPU 1800秒，单变量改变。没有一轮完成分析，C0仍BLOCKED。

| 轮次 | 单变量 | 墙钟 | Full GC | GC累计 | 失败时可达类型/方法 | 结果 |
|---|---|---:|---:|---:|---|---|
| 14 | 关闭TrackPrimitiveValues与UsePredicates | 51.0s | 49 | 33.5s | 未生成统计 | OOM，退出3 |
| 15 | 上述再设InlineBeforeAnalysisAllowedDepth=0 | 7.1s | 7 | 0.5s | 1305/1186 | 配置不可用：ImageSingletons缺MetadataTracer |
| 16 | 恢复默认，构造器内联节点预算0 | 49.2s | 33 | 30.5s | 未生成统计 | OOM，退出3 |
| 17 | InlineBeforeAnalysisAllowedDepth=2 | 162.8s | 96 | 142.0s | 10153/30063 | OOM，退出1 |
| 18 | --parallelism=2 | 98.5s | 56 | 74.0s | 9787/23447 | OOM，退出1 |
| 19 | 定时浅层快照10/16/22/30s | 207.1s | 89 | 167.0s | 12915/44814 | GC overhead limit，退出1 |
| 20 | --parallelism=1 | 56.4s | 48 | 36.1s | 7586/15040 | OOM，退出1 |
| 21 | Blocks改为构建期初始化 | 4.6s | 6 | 0.3s | 未进入分析 | 配置不可用：Not bootstrapped (registry minecraft:game_event) |

### 墙的形态

每轮都出现同一个签名：堆占用爬到约4.2–5.3 GiB（约为Xmx的88–92%）后，连续Full GC报告的前后占用完全相同（例如`4714M->4714M`，Eden也已满），一直持续数十秒，然后才抛出OOM。第13轮最后两次Full GC中出现`4714M->1264M`，即失败任务放弃后可达数据从约4.7 GiB降到约1.3 GiB；第17/19/20轮同样降到1.04/1.25/0.85 GiB。**这说明峰值主要是分析与解析过程中的在途状态，而不是分析宇宙本身的稳态持有量**，且放弃解析即可回收。

第10轮（8 GiB）墙前占用5.78 GiB、第11轮（8 GiB，G1）7.99 GiB、第13轮（6 GiB）4.71 GiB：墙的绝对位置随Xmx移动，因此"墙前占用"不能当作真实需求量的下界。第20轮单线程同样在23秒、4.22 GiB处撞墙，说明这不是四线程并行工作集之和。

### 第19轮的定时快照（首次取得墙前的类别分布）

`interop/diagnostics/oom_census.c`新增定时浅层快照（系统属性`fabricaot.census.at`，VMInit后用独立线程在指定秒数做`IterateThroughHeap`）。快照会停顿世界并扰动被测运行，因此计数只能用于类别归属，不能当作保留量。原始记录[census.tsv](../artifacts/c0/client-graph-19/work/census.tsv)，摘要[census-summary-19.json](../artifacts/c0/census-summary-19.json)，派生增量[census-snapshot-deltas-19.json](../artifacts/c0/census-snapshot-deltas-19.json)。

| 快照 | 对象数 | 浅层字节 | 最大类别 |
|---|---:|---:|---|
| T10 | 9,765,688 | 486 MiB | `[B` 91.1 MiB，`java.lang.reflect.Method` 76.7 MiB |
| T16 | 16,941,913 | 851 MiB | `[B` 144.2 MiB，`reflect.Method` 79.4 MiB |
| T22 | 75,834,935 | 3,134 MiB | `java.util.HashMap$Node` **1,612.6 MiB / 52,840,900个** |
| T30 | 60,076,756 | 2,669 MiB | `HashMap$Node` 1,183.1 MiB / 38,766,196个 |

T16→T22的9.4秒内新增58,893,022个对象、2,282 MiB，其中`HashMap$Node`单项+1,594.6 MiB、`[Ljava/util/HashMap$Node;`+378.8 MiB（127,096个表数组，共100,876,926个槽位）。T22→T30反而减少465 MiB，符合"在途复制"而非单调持有。

同一时刻Graal图对象合计约260万个（`Node`126万、`nodes.*`135万，另有`FrameState`20.9万、`NodeInputList`30.0万、`NodeSourcePosition`76.1万），而flow对象约100万个（`MethodTypeFlow`9.8万）。**52.8M个映射条目远多于260万个图节点，说明同一批节点被约20份状态复制同时引用**，这与分配采样的栈一致：`MethodTypeFlowBuilder$TypeFlowsOfNodes.<init>`→`new HashMap<>(copyFrom.flows)`→`putMapEntries`→`resize`。

### 源码阅读结论（固定提交6589574）

- `MethodTypeFlowBuilder.TypeFlowsOfNodes`只用一个`HashMap<Node,TypeFlowBuilder<?>>`保存"方法图中每个节点对应的流"，`clone()`就是`new TypeFlowsOfNodes(this)`→`new HashMap<>(copyFrom.flows)`全量复制；启用predicates时`TypeFlowsOfNodesWithPredicates`还额外保存`invokes`映射，即每次状态复制复制两份映射。
- 因此单个方法的状态复制成本是`O(图节点数 × 同时存活的状态副本数)`。方法图越大、合并点越多，成本按乘法增长。这是[交接](WORK_HANDOFF.md)里"瞬时复制量"的具体形式，也是第13轮采样把32%落在该类构造器上的原因。
- 分析前内联的常规预算很小：非构造器、非作用域方法的`InlineBeforeAnalysisAllowedNodes/Invokes`默认都是**1**，每个被调用者单独计数，非平凡方法基本不会被内联。这解释了第17轮把`AllowedDepth`从20降到2几乎无变化：深度不是限制因素。真正宽松的是构造器（200节点/50次调用）与方法句柄内建（10000节点/1000调用次数深度/10000次内联）。

### 已排除的方向

1. 降低分析前内联深度：第17轮与第13轮同处撞墙，且更慢。深度0不是可用配置。
2. 缩小构造器内联预算：第16轮仍撞墙。
3. 关闭primitive跟踪与predicates：第14轮仍撞墙（虽更快），说明不是predicates专有开销。
4. 减少并行度：第18、20轮在更少的可达方法下更早撞墙，单线程也能占满堆。
5. 让Blocks在构建期初始化以绕开该巨型`<clinit>`：第21轮在3.8秒内因Minecraft注册表未bootstrap而失败，需要先执行`Bootstrap.bootStrap`，不属于单类开关。

### 仍缺的证据与下一步

- 仍未取得对象保留链或支配树；快照是按类浅层计数，且停顿世界会扰动运行。没有峰值RSS的进程组硬限制，D0仍PARTIAL。
- 第22–24轮已把上面两条补上，见下一节。

## 第22–24轮：墙的位置、代价结构与第一方夹具

### 墙在单方法的类型流图构建

第22轮在14/18/22/26/30秒各发一次`SIGQUIT`（`tools/probe_thread_samples.py`，只观察）。5份转储中3份的主线程栈与当轮OOM栈完全一致：

```
PointsToAnalysis.addRootMethod → DefaultAnalysisPolicy.staticRootMethodGraph
→ MethodTypeFlow.createFlowsGraph → MethodTypeFlowBuilder.apply → createTypeFlow
→ PostOrderNodeIterator.nextQueuedNode → TypeFlowsOfNodesWithPredicates.clone
→ new TypeFlowsOfNodes(HashMap copy)                        [Blocks.java:54]
```

`PostOrderNodeIterator`对每个控制分割/带异常边的invoke执行`nodeStates.put(x, state)`，而`state`是整份flows映射的全量clone。因此单方法峰值≈快照数×平均映射条目数，两者都随方法规模增长。主线程CPU在22→30秒只前进1.35秒，说明那段时间是GC在占时间，不能把"停在clone"读成"一次复制耗时8秒"。

### 巨型方法清单（`tools/scan_method_shape.py`）

`artifacts/c0/method-shape-census-26.1.2.json`扫描6882类/68956方法，只反汇编不执行。前5名：`Blocks.<clinit>`（12,966指令/7,331 invoke/代价代理4,750万）、`BlockStateData.bootstrap3_2`（22,001/2,868/3,155万）、`VanillaRecipeProvider.buildRecipes`（10,498/3,457/1,815万）、`CopperGolemAnimation.<clinit>`（11,947/2,048/1,223万）、`Items.<clinit>`（7,802/2,986/1,165万）。第1名的代理值与实测52.8M条目同量级（差9%），但代理不是内存测量。

### 条目不是集中在少数巨型映射里

第24轮给JVMTI代理加了`SNAPSHOT_LARGE`（每快照记录最大12个个体数组）。三个快照中`HashMap$Node`稳定在5,200万左右、总表槽位约9,900万，而**前12大数组全是`[B`（最大4 MiB）**，唯一上榜的节点数组是`ConcurrentHashMap$Node` 1,048,576槽。因此不存在千万级条目的flows映射：条目分布在约12万张平均400–690槽的表中，其中数千张8K槽级表即可容纳约3,700万条目。这与"按invoke逐个快照一个数千条目映射"相容。

### 第一方夹具（`tools/probe_shaped_methods.py`）

生成不含任何Minecraft内容的`Shaped`类，静态初始化器执行N次`keep(i, make(i))`，可拆成K个方法由`<clinit>`串联，用`-H:+ExitAfterAnalysis`只跑分析阶段。

| 记录 | N | parts | 堆 | 结果 |
|---|---:|---:|---:|---|
| shaped-01-single-n4000 | 4000 | 1 | 512 MiB | 31.5s，OOM退出3，598次暂停共18.9s |
| shaped-02-split16-n4000 | 4000 | 16 | 512 MiB | 14.1s，退出0，分析完成 |
| shaped-03-single-n4000-h2g | 4000 | 1 | 2048 MiB | 122.6s被CPU预算终止，1489M→1489M钉住 |

同样4,000次调用：单方法在512 MiB OOM、2 GiB仍钉死；拆成16个方法后512 MiB通过。**峰值由单方法规模决定，拆分可以消除它，加堆不能。** 这没有证明真实客户端拆开后能通过（还叠加1.0万类型/3.0万方法、资源与反射闭包、以及第2–5名同类方法）。

该夹具工具默认不套`sandbox-exec`：Native Image的工具链检查需要执行`cc`，B0策略拒绝该exec，导致初始化阶段就报"cc not found"。每份`result.json`的`sandbox`字段记录了这一点；真实客户端实验仍然在沙盒内。


## 第25–29轮：拆分器落地，分析通过

拆分方向在第22–24轮只是推断，第25轮起变成可执行的构建期转换：`compiler/splitter/src/fabricaot/split/MethodSplitter.java`。它把 `static ()V` 巨型方法按"栈空 + 无跨段跳转 + 无跨段异常表 + 局部变量可搬运"的边界切成若干段，段之间链式调用，并把被方法体赋值的 `static final` 字段清除 `ACC_FINAL`（JVMS 6.5：final 字段只能在自身 `<clinit>` 写）。

**分析结果的变化**（同一客户端、同一 6 GiB 堆、同一并行度）：

| 轮 | 输入 | 结果 |
|---|---|---|
| 13–24 | 原版 jar | 最多 10,153 类型即 OOM，从未完成分析 |
| 26 | split-02 | 分析 34.2s 完成（30,642 类型 / 108,256 方法），随后 `NativeLibraries` 列目录被沙盒拒绝 |
| 27 | split-02 + 策略修复 | `analysisCompleted=true`，38.9s，峰值 RSS 3.49 GB |
| 28 | split-04（链式修正） | `analysisCompleted=true`，39.7s，32,531 类型 / 112,219 方法，峰值 RSS 3.29 GB |

**语义证据**：`interop/diagnostics/ClientInitDigest.java` 在 JVM 上执行真实 `Bootstrap.bootStrap()`，把 `Blocks` 的 1,144 个静态 Block 字段映射到 `BuiltInRegistries.BLOCK` 的 1,168 个 id，排序后取 FNV-1a 摘要。原版与拆分版都是 `4fce5dfeb9c2f39b`。

**两个只有真实客户端才暴露的缺陷**（夹具当时测不出，因为它的写入是幂等的）：

1. `IllegalAccessError: Update to static final field SoundEvents.ARMADILLO_PEEK ... from a different method` —— 拆分后写 final 字段的方法不再是 `<clinit>`。
2. `IllegalStateException: Adding duplicate key '...block.bamboo_wood.place'` —— `<clinit>` 与每段末尾都调用下一段，方法体执行了两遍。

修复后夹具的 `keep()` 增加 `RUNS` 计数，重复执行会立刻显形。

**仍未涉及**：代码生成之后的目标平台行为、渲染、真机。分析通过只说明可达性与类型流图能算出来，不代表 iOS 上能跑。

## 第30–36轮：代码生成与 iOS 链接

分析通过之后，`--full-build` 让 Native Image 继续走 [2/8]…[8/8]。[2/8]–[7/8]（分析→universe→内联→编译→布局）在第 30 轮就已全部通过，唯一失败点是 [8/8] 创建镜像时的链接。第 30–34 轮的错误逐层剥开，**没有一条来自 Minecraft**：

| 轮 | 错误 | 真正的成因 | 修复 |
|---|---|---|---|
| 30–31 | `posix_spawn failed, error: 0` | 构建 JVM 通过 `lib/jspawnhelper` 派生所有子进程，而策略只允许 `bin/java` 与 clang | 给 `lib/jspawnhelper` 一条 exec 许可（`artifacts/c0/spawn-probe/result.json`） |
| 32–33 | `ld: library 'dl' not found` | 直接调用工具链内部 clang 时不生成 `-syslibroot`；`SDKROOT` 能被记录进 `command.json` 却没有到达链接子进程 | `-H:NativeLinkerOption=-isysroot <SDK>`，写在命令行里可复现 |
| 34 | `building for 'macOS', but linking in object file ... built for 'iOS'` | svm 自带链接的目标是宿主：拉入 macOS `libdarwin.a`，镜像对象也没有平台标记 | 放弃 svm 链接，改走 B1 配方 |

**第35轮：只产出可重定位镜像对象。** `-H:+ExitAfterRelocatableImageWrite` 让 Native Image 在写出 `client-graph.o` 后停止。结果 exit 0、`Finished generating 'client-graph'`、1m22s、峰值 RSS 4.0 GiB，对象 115,623,411 字节，`otool -l` 显示**没有** `LC_BUILD_VERSION`——这正是第 34 轮 ld 把它当成 macOS 的直接原因。

**第36轮：第一方 iOS 链接。** `tools/link_c0_ios.py` 先验运行库（`status=COMPILED`、`target=arm64-apple-ios17.0`、六个归档逐个比对 SHA-256），再 `xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -dynamiclib` 链接。首次只差 13 个符号，全部是 iOS 运行库按设计不实现的 JVM/JNI 入口（`JNI_OnLoad_extnet`、`MacOSXSocketOptions.*`、`OperatingSystemImpl_initialize0`）。工具只为 `_Java_*`/`_JNI_*` 生成报名字后 `abort()` 的 C 桩，其他任何未解析符号仍让链接失败（有单元测试）。产物 `client-graph.dylib`：114,187,752 字节，`platform IOS, minos 17.0`，arm64，仅依赖 iOS 框架。

**边界**：拿到的是"真实客户端的 AOT 代码可以链接成 iOS 动态库"，不是"能在 iPhone 上启动"。dylib 从未被装载，`run_main(argc, argv)` 从未被调用；引导、资源索引、类初始化、GLFW/OpenGL 全部无证据。C0 仍为 BLOCKED。

## 第40–43轮：模拟器通道与 LWJGL 边界

真机通道每轮都要人工解锁，因此补了模拟器通道：`artifacts/a1/runtime-simulator`（`arm64-apple-ios17.0-simulator`，COMPILED）与同一个镜像对象用 `-sdk iphonesimulator` 链接，`simctl` 安装启动，日志直接读宿主文件系统。

| 障碍 | 表现 | 真因 | 处置 |
|---|---|---|---|
| 参数解析 | `java.io.File is not a value type` | joptsimple `constructorConverter` → `Class.getConstructor(String.class)`，Native Image 无元数据 | 注册 `java.io.File` 构造器 |
| 参数解析 | `java.lang.Integer is not a value type` | 同上，`valueOfConverter` → `getMethod("valueOf", String.class)` | 注册 `Integer.valueOf(String)` |
| 日志 | `Could not create directory /logs` | log4j 用相对路径，iOS 工作目录是只读的 `/` | 宿主 `chdir` 到 `--gameDir` |
| 平台 | `LinkageError: Unknown platform: iOS` | LWJGL `Platform` 枚举只有 4 个桌面平台 | 诊断用 `-Dos.name=Mac OS X`，仅推后 |
| 原生库 | `UnsatisfiedLinkError: liblwjgl.dylib` | iOS 无 LWJGL natives，GLFW 无 iOS 后端 | **未解决，Gate C 真实阻断** |

跑到这里说明 AOT、链接、签名、堆预留都不是瓶颈：`[Datafixer Bootstrap/INFO]: 291 Datafixer optimizations took 260 milliseconds` 是 Minecraft 自己的代码在跑。真正缺的是图形与窗口层。
