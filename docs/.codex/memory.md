# 持久决策

Last reviewed: 2026-11-10

- 根AGENTS/TECHNICAL_GATES是验收依据。A0/A1已通过：A0主菜单+同一进程Java25.0.1/Fabric0.19.3；A1为build 2独立运行。B0构建期转换/重放/负例及B1真机同等行为随后均已通过；C0仍BLOCKED。
- 官方桌面 GraalVM25.0.2直接 iOS 尝试报缺 java/nio/net。当前通过固定官方源码和第一方构建器编译目标库，数值 CAP 的版本契约固定25.0.2。
- static JNI 编译需要逐库设置 LIBRARY_NAME；A1 还需要实际 ZIP 原生函数和 JNI_OnLoad_zip。locale 要包含 java_props_macosx.h 的真实声明。
- 编译119单元；未提供 JVM 入口生成明确终止诊断。当前探针没有触发这些入口，不能推广为完整 Java/Mod 兼容。
- iPhoneOS 与 Simulator 原生库分开构建，link_a1_ios 拒绝目标不匹配。A1Harness 可通过 FAOT_FRAMEWORK_DIR / FAOT_JNI_LIBRARY 选择构建输入。
- JVM、桌面AOT、模拟器和用户真机build 2均通过Java25线程/ScopedValue/GC/资源/JNI/文件保存及isolate生命周期。a1-user-device-run-03原始日志与用户退出Xcode/拔线/重新打开确认共同支持A1 PASS；不会据此提升Minecraft/Fabric/性能Gate。
- 固定 Graal AddressRangeCommittedMemoryProvider 默认至少预留32 GiB，801=RESERVE_ADDRESS_SPACE_FAILED。build 2 使用 graal_create_isolate_params_t 的公开 version-1 reserved_address_space_size=256 MiB，已解决用户首轮801；不得填写内部保留字段。
- build 3以当前进程报告名显示结果，冷启动先显示RUNNING，STARTED/结束通知UI；报告有runID/processID，界面显示开始时间/耗时/日志名。每进程一次，后台恢复不重跑，划掉后启动生成新名。用户PASS截图/日志在a1-user-device-run-04；原生AOT输入未重建。
- Swift Craft 的 Recollection3 是实例目录；26.1.2.jar 在共享 meta/versions/26.1.2，大小/SHA1匹配。不得因标准 minecraft 目录缺 JAR 而断言本机没有客户端。
- A0使用新实例26.1.2-fabric-0.19.3-20260804-145519，Fabric API0.155.2+26.1.2。只读lsof关联进程所打开latest.log与映射libjvm，release确认25.0.1，依赖指纹与GUI复现步骤存a0-desktop-reference。未读取原始命令参数/令牌或启动游戏。Recollection3历史日志不用于当前A0结论。
- Loader0.19.3的getClassByteArray(true)是PreMixin，不能当最终导出；B0采用第一方Java agent只捕获Knot定义的第一方类。访问修改选择器只覆盖游戏命名空间，所以自写Target使用net.minecraft.fabricaot_fixture；元数据accessWidener由ClassTweaker读取，当前只测访问修改子集。
- interop/b0与prepare_b0已编译12类/3JAR，-proc:none。run_b0_reference必须先通过文件读写和本地连接拒绝控制，才初始化真实Knot；源码/Java/JAR指纹不符即停止。Mac脚本现由助手执行；B0真实参考/重放/负例和拒绝控制已通过，D0完整隔离未认证。不得跳过控制，不执行原有用户Mod/Gradle。
- 不执行既有整合包 Mod，不改账户/存档/原始客户端。已按TECHNICAL_GATES建立本地Git提交；不包含游戏资产/缓存/产物，不设置远程或推送。证据另外通过指纹记录。
- 所有持久生成物使用中央 AAR；可靠可重取缓存与历史证据分开标记，无自动清理。
- Xcode ArchiveIntermediates 的 BuildProductsPath 包含 App 符号链接；AAR 拒绝跟随，构建树只登记专用根，实际归档/解包文件另登记。不要删除链接迁就登记。
- 用户最新要求：继续自主推进到可玩；后续仅模拟器，不进行任何真机操作，不再提问。Mac构建/隔离测试与模拟器运行继续由助手执行。不要因早期“测试暂时交给我”停止已授权Mac验证，也不要自动安装/启动iPhone App。79项回归PASS，含关闭输出流后仍强制超时的进程控制回归。
- B0 run-04是B1输入，19个源码输入保留source-snapshot-04；运行器后续增加资源记录与关闭流超时修复，需重新prepare。run-05复验PASS，不以其不同Target指纹替换既有B1链。
- B1 build 4两份原始日志匹配B0_BEHAVIOR与B1_SEMANTICS_PASS，用户称一次连接Xcode、一次没连。设备结论存b1-user-device-run-01；包创建时的deviceRun NOT RUN保持历史，不回写。
- C0 client-graph-07先过拒绝控制，再分析真实Main。6 GiB Java堆OOM退出3，CPU约566秒，无游戏对象/执行；不是不兼容证明。319个LWJGL静态引用候选不是动态覆盖或iOS适配完成。
- C0后续09/10的6/8 GiB Parallel与11的8 GiB G1均OOM退出3，没有完整analysis_stats/build-output JSON；可达规模UNKNOWN。GC后堆约4.50/5.78/7.99 GiB，大量Full GC，无保留对象直方图/链，不能宣称已找到具体持有者。8 GiB是当前18 GiB主机受控上限，不盲增预算。
- 08中构建JFR自动开启目标JFR，触发LibMDependencies.cap缺失；固定Graal JfrFeature源码确认了测量影响，原记录与源快照保留。后续使用GC日志/time/诊断模式，无构建JFR。
- client_graph_diagnostics审计显式classpath的25个内置元数据文件：542反射、26 JNI、4资源声明；非唯一可达类数，SDK/Feature/推导未穷尽，未发现Preserve=all不等于已排除元数据膨胀。
- compare_client_graph_runs核对09/10除堆/输出目录外相同；10/11仅GC参数变化，但构建器增加GC参数分支，源码SHA不相同并如实记录。analysisCompleted与目标生成/执行分开，完整Fabric客户端转换仍NOT RUN，不推进C1/C2。
- 最新交接docs/WORK_HANDOFF.md覆盖12–16：12关闭ExitOnOOM耗尽CPU，13自写Mac JVMTI代理取得Blocks.<clinit>解析失败和1152采样；Map复制路径突出，但浅层统计发生于OOM交付时，不能当峰值保留链。部分统计14112类型/49919方法不构成分析完成。
- 14关闭TrackPrimitiveValues/UsePredicates仍OOM；15普通内联深度0触发MetadataTracer单例错误；16仅构造器预算0仍OOM。均保留，不作为生产配置。Graal/pointsto.jar映射补丁尚未实现；先验证键语义/clone/merge再研究紧凑映射。
- 83项Python回归及24MiB第一方代理自测通过。最新6个研发源文件未提交，副本与SHA在handoff-snapshot-20261108；保留工作区与研究记录，接手者不能只看fe15a74。
- 17–21轮都在真实客户端上撞同一堵墙：堆到约88–92%Xmx后连续Full GC前后占用完全相同（如4714M->4714M），失败任务放弃后回落到0.85–1.3GiB，说明峰值多为在途状态而非稳态宇宙；墙的绝对位置随Xmx移动，不能当需求下界。17内联深度2、18并行度2、20并行度1都仍OOM（单线程也能占满堆）；21把Blocks改构建期初始化3.8秒即被“Not bootstrapped (registry minecraft:game_event)”挡住。
- 19轮新增定时浅层快照（agent系统属性fabricaot.census.at，VMInit后独立pthread+AttachCurrentThreadAsDaemon，模式SNAPSHOT_*，旧OOM记录保持兼容）。T22取得HashMap$Node 5284万个/1612.6MiB，T16→T22 9.4秒新增5889万对象、2282MiB；同期Graal图对象约260万，即同一批节点被约20份状态复制引用，与TypeFlowsOfNodes.clone的全量HashMap复制一致。快照停世界并扰动运行，只作类别归属。
- 固定6589574源码确认常规非构造器方法的分析前内联预算只有1节点/1次调用（所以深度20→2几乎无变化），宽松的是构造器200/50和方法句柄内建10000/1000/1000/10000；未定的仍是“图为什么这么大”，下一步用tools/probe_thread_samples.py抓墙前线程栈再决定。
- macOS上/var→/private/var符号链接会让test_client_graph_comparison的sandbox策略比对误报；夹具已改为写解析后路径。python3必须是3.11+（/usr/bin/python3是3.9.6，缺hashlib.file_digest会报20项错）。当前89项回归PASS，证据unit-tests-20261108-pm。
- 22–24轮把C0的墙定死：第22轮墙前5次SIGQUIT里3次主线程在 `addRootMethod→staticRootMethodGraph→createFlowsGraph→apply→createTypeFlow→nextQueuedNode→TypeFlowsOfNodesWithPredicates.clone`，与OOM栈逐帧一致——所以墙是「单个方法的类型流图构建」，不是收尾/可达性/编译。主线程CPU 22→30秒只涨1.35秒，说明是GC在吃时间，别把栈顶读成「一次clone跑8秒」。
- 代价结构：`PostOrderNodeIterator` 在每个控制分割/带异常边的invoke上 `nodeStates.put(x,state)`，state 是整份 flows 映射的全量 clone → 单方法峰值 ≈ 快照数 × 平均条目数，平方级。新工具 `tools/scan_method_shape.py` 给形状普查：Blocks.<clinit> 12966指令/7331invoke/仅2条件分支，代价代理47.5M，与实测52.8M条目差9%；后面依次 BlockStateData.bootstrap3_2 31.5M、VanillaRecipeProvider.buildRecipes 18.1M、CopperGolemAnimation 12.2M、Items 11.6M。客户端只有24个方法超8KB字节码、2个超32KB——问题集中在这极少数方法上。
- 23轮把方法句柄分析前内联收紧到200节点/8层/50次：不再30秒OOM，而是324秒被CPU预算152终止、487次Full GC、堆长期4510M→4510M，仍不完成 → 这个方向作废（也修正了「巨型map来自MH内联放大」的猜测）。
- 24轮给JVMTI代理加 `SNAPSHOT_LARGE`（每快照前12大个体数组）：全堆前12大连数组全是 `[B`（最大4MiB），唯一上榜节点数组是 ConcurrentHashMap$Node 1,048,576槽 → **不存在千万级条目的flows映射**，条目分布在约12万张平均400–690槽的表里。所以「少数巨型映射被反复复制」的模型被否掉，「按invoke逐个快照一个数千条目映射」保留。
- 关键转折：新工具 `tools/probe_shaped_methods.py` 用完全第一方的 `Shaped` 类做受控对照。4000次调用的单个<clinit>：512MiB OOM(31.5s)、2048MiB 仍钉死在1489M不完成(122.6s)；同样4000次调用拆成16个方法：512MiB、14.1s、退出0。→ 修复方向定为「构建期拆分巨型方法」，不是加堆也不是调内联预算。
- 坑：native-image 在 sandbox-exec 里跑不起来（工具链检查要 exec `cc`，B0策略只允许 java/native-image；`-H:-CheckToolchain` 在沙箱内也不生效），另外要显式 `-J-Djava.io.tmpdir` + `-H:TempDirectory` 指到可写目录，否则报 /var/tmp Operation not permitted。夹具工具因此默认不套沙盒，并在 result.json 里写明 `sandbox` 字段。
- 现状：101项Python回归PASS（evidence/unit-tests-20261108-evening），完整性复核976命令/78二进制/730报告 PASS，登记回执 registry-c0-22-24.json。代码仍未提交，未改Graal源码/pointsto.jar/客户端类。
- 25–28轮把拆分从设想做成工具：`compiler/splitter/src/fabricaot/split/MethodSplitter.java`（ASM tree + Analyzer）。切点必须同时满足「栈空」「无 jump/switch 跨段」「异常表 start/end/handler 同段」「下一段的局部变量可搬运（类型精确的合成静态字段，null 用 aconst_null 重建）」。拿不到精确类型（只有 BasicVerifier）时只在“下一段不读已初始化槽”的边界切，绝不猜。
- 两个只有真实客户端能暴露的坑（夹具幂等，测不出来）：① `static final` 只能在自身 `<clinit>` 写，拆到子方法后运行期 `IllegalAccessError`（SoundEvents.ARMADILLO_PEEK）→ 对被方法体赋值的同类 final 字段清 `ACC_FINAL`（这些字段没有 ConstantValue，调用点仍 getstatic）；② `<clinit>` 调每一段、段尾又调下一段 → 方法体执行两遍，注册表 duplicate key → 改成只进第一段的链式调用。夹具的 keep() 现已加 RUNS 计数。
- 真实客户端 jar 带签名，改任何类都会 `SecurityException: SHA-384 digest error`；输出时剥掉 `META-INF/*.SF|*.RSA|*.DSA|*.EC|SIG-*`，并在报告里写 signatureEntriesDropped。
- 结果：18 类 / 28 个 `static ()V` 方法 / 358 段；拆分后方法形状最大 snapshotSites 从 7333 降到 3457（那 3457 是 `VanillaRecipeProvider.buildRecipes`，实例方法带参，v1 不处理）。真实客户端 6 GiB 下分析从“最多 10,153 类型就 OOM”变成 **32,531 类型 / 112,219 方法、39.7s、峰值 RSS 3.29GB**。
- 语义等价用 `interop/diagnostics/ClientInitDigest.java`：JVM 上 `SharedConstants.tryDetectVersion()` + `Bootstrap.bootStrap()`，把 Blocks 的 1144 个静态 Block 字段映射到 BuiltInRegistries.BLOCK 的 1168 个 id，排序取 FNV-1a。原版与拆分版都是 `4fce5dfeb9c2f39b`。注意 26.x 把 ResourceLocation 改名 Identifier，且 Registry.getKey 要在接口上反射（实现类包私有）。
- 完整构建的两个环境坑：① `execute()` 固定 `RLIMIT_FSIZE=64MB`（分析模式有意为之），镜像写盘直接 `File too large` → 完整构建单独放宽到 8 GiB 并记录 fileSizeLimitBytes；② 沙盒只允许 exec 单个 clang literal，链接时 clang 要 spawn ld → `posix_spawn failed, error: 0`，需要放开 toolchain 的 bin/lib/include 子树。
- 沙盒还要求允许列 `artifacts/b1/runtime-ios` 目录（`-H:CLibraryPath` 会 Files.list），只允许文件会报 Operation not permitted。
- 30–34轮全是环境/平台问题，没有一条是 Minecraft 的：`posix_spawn failed, error: 0` 的真正成因不是 clang 权限，而是 **JDK 用 `lib/jspawnhelper` 派生所有子进程**，策略只给 `bin/java` 时任何 ProcessBuilder 都失败（`artifacts/c0/spawn-probe/result.json` 四变体对比：只补 jspawnhelper 或改 FORK 机制都能过）。排查别猜，写 5 行 Java 探针比读 svm 源码快。
- 直接调工具链内部 clang 不会生成 `-syslibroot`（`/usr/bin/clang` 那个壳会先问 xcrun），于是 `ld: library 'dl' not found`。`SDKROOT` 能进构建进程环境（`command.json.environmentKeys` 有它）却到不了链接子进程 —— 改用 `-H:NativeLinkerOption=-isysroot <SDK>` 写死在命令行，既生效又可复现。
- svm 自己的链接目标永远是宿主：它会链 `darwin-aarch64/libdarwin.a`，镜像对象也没有 `LC_BUILD_VERSION`，因此 `-Dsvm.platform=$IOS_AARCH64` 也生不出 iOS 产物（第34轮：`building for 'macOS', but linking in object file ... built for 'iOS'`）。正路是 B1 配方：`-H:+ExitAfterRelocatableImageWrite` 只写对象，再用 `xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -dynamiclib` 自己链。
- 35轮：真实客户端对象生成 **exit 0**，`client-graph.o` 115,623,411 字节，1m22s，峰值 RSS 4.0 GiB（6 GiB 堆）。36轮首链只差 13 个符号，全是 iOS 运行库按设计不实现的 JNI 入口（`JNI_OnLoad_extnet`、`MacOSXSocketOptions.*`、`OperatingSystemImpl_initialize0`）；按 AGENTS.md 只给 `_Java_*`/`_JNI_*` 生成报名字后 abort 的桩，其他未解析符号仍须让链接失败。产物 `client-graph.dylib` 114,187,752 字节，`platform IOS, minos 17.0`，状态记 `LINKED_WITH_UNSUPPORTED_ENTRYPOINTS`，不写 LINKED。
- `tools/register_artifacts.py` 之前是「第一个路径失败就整体退出」，`artifacts/a1` 的符号链接使排在后面的 `artifacts/evidence` 从来没被登记过。现在失败收集进 failures 并以退出码 2 报告；符号链接只拒绝逃出证据树的（Xcode 的 `BuildProductsPath -> InstallationBuildProductsLocation` 是树内的）。AAR 自身仍然拒绝含符号链接路径组件的递归登记，a1 只能按子树登记，这个不能靠删链接绕过。
- 37轮：iOS 宿主拿到的是"能装"而不是"装上了"。Team Profile 的 `ProvisionedDevices` 为空时 IPA 仍能正常导出与签名，只是任何设备都装不上 —— 这不是签名失败，别去查证书。唯一解法是连接+解锁设备后带 `-destination 'platform=iOS,id=<UDID>'` 重建，让 Xcode 注册设备槽；设备锁屏时报错原文是 `needs to be unlocked to enable development services`（xcodebuild 会干等 60s 再抛 `Timed out waiting for all destinations`，别误判成网络问题）。
- `ios/C0Harness` 用 `dlopen` 加载 dylib 而不是链接：`tools/link_c0_ios.py` 写进镜像的 install name 是 `@rpath/FabricAOTClient.dylib`，而嵌入后的文件名是 `client-graph.dylib`，直接链接会在 dyld 阶段找不到；dlopen + dlsym 三个入口更省事，也不依赖头文件版本（`graal_create_isolate_params_t` 只按公开 version-1 前缀手写结构体）。
- iOS 26+ 宿主 App 必须有 UIScene 生命周期：缺 `UIApplicationSceneManifest`（或没实现 `configurationForConnectingSceneSession`）时，`UIApplicationMain` 直接 `EXC_BREAKPOINT (code=1, subcode=0x18xxxxxxx)`，崩点在自己 `main()` 那一行、堆栈里看不到自己的代码，极易误判成镜像或 dylib 问题。A1/B1 工程里本来是对的，新建宿主时一定要照抄。
- `devicectl device install app` 在锁屏状态也能成功；但 `devicectl device process launch` 会一直等到 60s 超时且**不产生崩溃报告**。判断"锁屏 vs 崩溃"的方法是看 `device info files --domain-type systemCrashLogs` 里有没有对应 .ips，以及 `device info processes` 里有没有进程 —— 两者都没有就是没起来。
- 真机 `devicectl` 在锁屏时**安装可以、拉起不行**（`FBSOpenApplicationErrorDomain error 7 Locked`）。每次改代码都要用户解锁点图标，迭代代价太高。破局办法是模拟器：`artifacts/a1/runtime-simulator`（`arm64-apple-ios17.0-simulator`，COMPILED）与同一个镜像对象用 `-sdk iphonesimulator` 链接，`simctl install/launch`，日志从 `simctl get_app_container` 的宿主路径直接读，全程不需要人工。镜像对象无平台标记，同一份 `.o` 能同时链出 device 与 simulator 两个 dylib。
- joptsimple 的 `"<type> is not a value type"` 与类初始化时机**无关**（我一开始先加 `--initialize-at-run-time=joptsimple`，没用）。真因是 `Reflection.findConverter` 的两条路都靠反射：`getMethod("valueOf", String.class)` 与 `getConstructor(String.class)`，两条都吞 `NoSuchMethodException`。按错误出现的顺序补 `java.io.File` 构造器 → `Integer.valueOf(String)` 即可。找全量的方法是 `javap -c net.minecraft.client.main.Main | grep -B6 ofType`。
- `run_main` 是 entry point，它自己建 isolate（`JavaMainWrapper` 的 `EnterCreateIsolateWithCArgumentsPrologue`，`MAIN_ISOLATE_PARAMETERS` 的 `reservedSpaceSize` 恒为 0）。宿主先 `graal_create_isolate` 再 `run_main` 没用，因为单 isolate 限制会让第二次创建失败；要限制预留只能把 `-XX:ReservedAddressSpaceSize=<字节>` 放进 argv。801 就是 `AddressRangeCommittedMemoryProvider` 对 0 的处理 → 32 GiB。
- log4j 把 `logs/latest.log` 当相对路径，iOS 的 cwd 是只读的 `/`，报 `Could not create directory /logs`。宿主 `chdir` 到 `--gameDir` 即可，不然后续日志全丢。
- **LWJGL 是 iOS 的真墙**：`org.lwjgl.system.Platform.<clinit>` 只认 Windows/FreeBSD/Linux/SunOS/macOS（`os.name` 的 `startsWith` 链），iOS 直接 `LinkageError: Unknown platform: iOS`。`-Dos.name=Mac OS X` 只是把失败推后，立刻变成 `UnsatisfiedLinkError: Failed to locate library: liblwjgl.dylib` —— iOS 上没有 LWJGL natives，GLFW 也没有 iOS 后端。这一层不是靠改参数能过的。
- **44轮：图形层的解法不是移植 LWJGL**。`com.mojang.blaze3d.systems.GpuBackend` 只有 4 个方法（`getName`/`setWindowHints`/`handleWindowCreationErrors`/`createDevice`），`GpuDeviceBackend`/`CommandEncoderBackend`/`RenderPassBackend` 也都是接口，`GpuDevice`/`CommandEncoder`/`RenderPass` 是转发类。`Minecraft.<init>` 里是 `GpuBackend[] { new GlBackend() }` + `BackendCreationException` 回退循环（字节码 803–1017），所以**注入点是一个数组**：构建期把 `iconst_1` 改 `iconst_2` 并在 `aastore` 后追加 `new MetalBackend()`，失败路径复用官方日志与 `WindowInitFailed`。
- 44轮关键断言：`org/lwjgl/opengl/*` 的 124 处引用**只出现在 13 个类**，且全部在 `com.mojang.blaze3d.opengl` 包内（`GlStateManager` 63、`GlCommandEncoder` 15、`DirectStateAccess$Core` 13、`GlDebug` 9、`GlDevice` 5…），筛选"引用方不在该包"的结果是空集。→ 不走 `GlBackend` 就完全不需要 GL 兼容层，也否掉了 Zink+MoltenVK/ANGLE/MoltenGL 这类 GL→Metal 逐调用转译。
- GLFW 是唯一横跨全局的本机依赖：85 个引用 / 74 个唯一符号（59 个 `glfw*` + 15 个 LWJGL 结构体访问器），集中在 `blaze3d/platform`（`Window` 29、`GLX` 13、`InputConstants` 12）。**其中 3 个不是上游 GLFW API**：`glfwSetIMEStatusCallback`、`glfwSetPreeditCallback`、`glfwSetPreeditCursorRectangle`（Mojang 定制分支的 IME 预编辑），另有 macOS 专用的 `glfwGetCocoaWindow`。替身库必须显式实现它们，不能只按 GLFW 3.x 官方头文件导出符号。
- 着色器语料：jar 内 88 个 GLSL 文件（`.vsh` 35 / `.fsh` 44 / `.glsl` include 9），**全部 `#version 330`**，共 54,213 字节，最大 `core/terrain.fsh` 3,374 字节；`core/` 69、`post/` 10、`include/` 9。`ShaderSource` 是单方法接口，后端可以忽略传入 GLSL 改按 id 查预构建 MSL，所以翻译只发生在构建期，iOS 上不跑 glslang。
- 44轮方案落成 docs/GRAPHICS_STACK_PLAN.md（工作包 G1 GLFW替身 / G2 LWJGL core替身 / G3 Metal后端 / G4 构建期GLSL→MSL / G5 触摸 / G6 音频，子门槛 C0a/C0b/C0c）+ evidence/ADR-008.md（否证 `os.name` 伪装、宿主库重标、GL→Metal 转译层、GLFW null platform、SwiftUI 顶替）。**本轮没写任何图形代码**，C0 状态不变。用户明确要求先交文档，不先实现。

- 第45轮：图形启动已有实现与模拟器证据，见GRAPHICS_BOOTSTRAP。GLFW 85条Java引用/74个唯一名称里59个glfw前缀名称包含Java辅助函数glfwFreeCallbacks，所以C导出需求为58个；LWJGL会一次加载125个Functions入口。缺失API须在Java包装层具名失败，并替换直接访问函数表的Callbacks清理，否则Window.close会调用空指针。
- C0宿主的重定向FD与独立fopen("a")曾使用不同偏移，延迟OS/Java输出覆盖宿主记录。`log_file.h`现统一O_APPEND，双写入方ASan/UBSan回归覆盖。device-run-03真机四色/四格式GPU比对通过，但该快照缺少入口返回行，不能视作正常退出证据；用户独立启动条件也未确认。
- LWJGL3.4.1的Java25多版本实现走FFM upcall；构建期overlay选择基础JNI、显式Platform.IOS并用17种ABI×32预编译回调替代Upcalls。WindowFocus/Iconify/CursorEnter的Java参数是boolean（JZ），不是int（JI）；JNI重载必须使用完整符号避免把数组当原生指针。
- 模拟器AOT实际Window/RenderSystem初始化与Metal清屏呈现通过；第46轮用户真机蓝屏和原始日志匹配（A20 Pro GPU，1398×2034，独立启动未确认）。纹理/视图、encoder传输、清除型renderpass、fence与构建期呈现metallib已实现，模拟器四格式读回与四分屏通过；151项回归PASS。G1/G2/G3/G5仍PARTIAL，STB/游戏pipeline/完整Main注入/着色器翻译未完成，C0/C0a仍BLOCKED。历史log4j元数据警告与宿主tear_down=2仍保留，入口返回0不代表完整isolate回收。

- 第47轮仅模拟器：STB头文件固定LWJGL3.4.1，image JNI进liblwjgl，LibSTB共用系统allocator；18种静态callback ABI。NativeImage PNG写读/alpha/resize/坏数据/回调异常及容量负例、GPU裁剪上传均在模拟器AOT通过（images-simulator-evidence-02）。JNI ThrowNew需要精确声明异常类及String构造器，否则错误分支会变NoClassDefFoundError。G4工具准备中，游戏pipeline/Main仍未实现。

- 第47轮原版60程序（79入口+9include、87静态pipeline+6后处理）GLSL→SPIR-V→MSL→模拟器metallib全部通过；varying必须按名称统一位置，不能相信glslang自动位置跨阶段一致。Metal绑定取SPIRV-Cross实际分配值，Projection/Lighting/Fog/Globals四个UBO为原版隐式绑定。draw-simulator-evidence-02验证87条PSO和真实shader像素断言，仍非Main菜单。
- 运行时必须用client-split-04，02缺少移出clinit的final字段修正，会在RenderPipelines初始化报END_PORTAL_SNIPPET。probe_client_graph现核验拆分元数据和后端注入的递归输入指纹。InjectBackend只扩容候选数组，回退循环原样保留。变换JAR须清除失效逐entry签名段，保留manifest主属性；否则Graal资源收集反复解压4.5MB清单。
- 26.1.2官方版本元数据assetIndex=30；Swift Craft当前30.json与该版本固定SHA1不同，不能直接信任缓存。stage_game_assets按固定官方索引、对象大小/SHA1复制，缺失对象仅从固定Mojang源获取；不碰账户/存档。

- 第47轮真实Main已在main-harness-sim-04/05初始化UIKit窗口与Metal设备。HTTP/HTTPS协议和资源索引30、OpenJDK libextnet已补齐；链接只剩未触发的OperatingSystemImpl.initialize0。精确补RuntimeMXBean.getStartTime、MarkerFilter.createFilter后日志警告消失。
- OpenAL模块要移除MR FFM并改ALC.create()加载bundle内openal；ThreadLocalUtil不得改JNIEnv函数表。替换为显式分发的指针向量（缺失保留0，由静态JNI适配器报错），比较函数保留原语义；host窗口/NativeImage与空指针负例PASS。最新bridge=lwjgl-sim-12、metal=metal-sim-11。170项Python回归PASS（regression-13）。
- Apple公开OpenAL框架的实测上下文有效，但初始化留AL_INVALID_NAME，核心能力不完整；真实Main直接调用缺失的alcEventIsSupportedSOFT而失败（main-simulator-run-05）。正在转为固定OpenAL Soft1.25.2源码（官方tag commit b2c48f7718ef3fcf67921a8b6534c4914e328970）构建CoreAudio音频库。音频探针当前均未PASS，不宣称游戏音频可用。
- Simulator同BundleID重装后data容器绝对路径会变，Documents继承；采集旧run日志应先查询当前容器并按run文件名取，不能沿用历史harness报告的旧container路径。build_c0_harness现逐库核对模拟器App实际嵌入指纹，防止新增输入遗漏复制。
- 2026-11-09 新专用模拟器 `8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3`。原版单人通过移动、跳跃、放置破坏及存档重开。WorldSimulator Scheme 仅支持左右横屏，实测 2622×1206。AOT 输入是 client-metal-04，模拟器链接 main-link-sim-15，本地 Xcode 输入 world-simulator-input-02。已验证 CPU/GPU 预算 2 GiB/768 MiB，首次设置 8/5 区块和 30 FPS 上限。
- WorldSimulator 与 WorldSimulatorTests 指向独立的 FabricAOTWorld 模拟器目标，沿用原 Bundle ID 保留存档。Xcode 27.2 仍可能把物理 iPhone 列为兼容目的地，游戏目标检查构建平台和运行目的地平台，误选时在安装前终止。入口见 [BUILDING](../BUILDING.md)。
- 用户要求做真机测试。WorldDevice 使用重新链接的 iPhoneOS arm64 游戏镜像及 Metal/OpenAL 库，在本地签名包内放入已核验的用户资源索引 30。首次启动预算沿用模拟器世界的 2 GiB 地址空间和 768 MiB 图形资源上限。手机安装与启动由用户操作，真机 Gate 以实际画面、输入和存档证据为准。入口和复现命令见 [BUILDING](../BUILDING.md)。
- iPhone 的 Metal API Validation 会按着色器结构体含尾部填充的大小校验 uniform。原版 GUI 文字的 Fog 有效字段为 40 字节，Metal 结构体为 48 字节。原生缓冲区向上取整到 16 字节，Java 保留逻辑长度与切片边界。WorldDevice 使用 `world-device-input-02`，回归入口为 `MetalDrawProbe.guiTextFog`。
- 世界加入时的停顿由 Authlib 聊天公钥 Future 导致。构建期只短路不要求签名的标志与空会话数据，原签名校验路径保留。图集顶点方向、光照行序、云层私有缓冲、物品图集 UV 和局部清除均有实测记录。仍仅限模拟器原版，设备与整合包 Gate 未验收。


## 统一原版与 Fabric AOT 构建

- 两个加载入口共用已验证的方法拆分、Metal 注入和 relocatable Native Image。设备 App 复用 WorldDevice 的既有签名设置。模拟器验证必须将相同 AOT 对象重新链接为 IOSSIMULATOR。源码与命令见 [BUILDING](../BUILDING.md)。
- Fabric 0.19.3 的真实 Knot 导出包含启动和品牌补丁。所有被重定向的类均须重新序列化，品牌类没有启动入口计数。遗漏时真实 AOT 客户端可先成功运行 Mod 入口，随后因缺少 `net.fabricmc.loader.impl.game.minecraft.Hooks` 退出。用 javap 和真实世界烟测分别验证。
- 外层工具沙盒禁止嵌套 `sandbox-exec`。使用支持原有默认拒绝沙盒的执行环境。当前 Xcode 签名可只包含 DER entitlements，`codesign -d --entitlements -` 可读出有效字典。
