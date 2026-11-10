# 先证伪、再迭代：FabricAOT 可执行 Gate 计划

以下每项都必须生成命令、版本、日志、二进制 SHA-256、代码提交、真实运行结果和负例。无法运行时写 `BLOCKED/NOT RUN`，不编造产物。

| Gate | 最小实验 | 通过标准 | 失败时处理 |
|---|---|---|---|
| A0 参考基线 | Java 25 + Fabric 26.1.2 在 Mac 原生 JVM 正确启动；记录官方客户端和依赖工件 | 可复现 Mod 环境/启动命令、依赖清单 | 优先修版本/资源/Loader，不进入 AOT |
| A1 Java25 iOS AOT | 非 JavaFX 的 Java25 线程、GC、资源、JNI 与小程序经签名跑在普通 iPhone | 不依赖 JIT 权限/调试器/后台电脑，真机日志 | 验证 iOS fork/补丁/链接方式；无路径则报告 BLOCKED |
| B0 Fabric 静态化实验 | 26.1.2 样例 Fabric Mod 含 Mixin + Class Tweaker + Entrypoint + nested JAR | 变换后类在桌面 JVM 行为正确、可比较字节码与调用结果 | 不可仅调用 Mixin API 后就视作完成 |
| B1 AOT 语义一致性 | B0 经同一 iOS AOT 运行时执行行为测试 | 与 JVM 基线断言一致；无运行时代码定义 | 每个不支持机制标明具体条件 |
| C0 游戏无图形入口 | Minecraft 真实客户端引导、资源索引、类初始化、JNI 清单 | 到达可复现的菜单前启动阶段 | 禁止以空壳 SwiftUI 画面代替 |
| C0a 图形后端首帧 | Metal 后端清屏（G1 GLFW 替身 + G2 LWJGL core 替身 + G3 最小后端） | 真机出现由 Metal 渲染的首帧，`RenderSystem` 初始化完成，日志有后端名与设备信息 | 后端未起来就写上层渲染，禁止用渲染 demo 顶替 |
| C0b 真实菜单/输入 | 88 个 GLSL 330 经构建期翻译为 MSL，触摸映射为 GLFW 回调 | Minecraft 自己渲染的主菜单可见（真实资源），触摸可点击响应 | 不得手改 MSL 掩盖语义不符；不符的 shader 记 UNSUPPORTED 并报错 |
| C0c 单人可玩 | 新建世界、加载区块、移动、破坏放置、退出/重入 | 真机可持续游玩，世界数据和行为复核 | 失败仍是 experimental |
| C1 画面/输入 | 真实 Blaze3D/LWJGL 使用的调用映射到 iOS，显示真正游戏菜单 | 菜单真实图文、点击可响应 | 不得用 3D demo 代替 |
| C2 单人可玩 | 新建世界、加载区块、移动、破坏放置、退出/重入 | 真机可持续游玩，世界数据和行为复核 | 失败仍是 experimental |
| D0 安全构建 | 恶意 ZIP/URL、无效 hash、依赖冲突、潜在执行任意构建脚本 | 均安全失败，无凭据外泄 | 默认不可执行第三方构建脚本 |
| D1 整合包 | 指定 26.1.2 Fabric pack，下载/哈希/依赖检查 + 静态化 + 真机验证 | 与被标记 VERIFIED 的 Mod 运行结果一致，能保存世界 | UNKNOWN 不自动升级为 VERIFIED |
| D2 签名与安装 | Xcode Personal Team 免费签名与 IPA 生成分别验证 | 设备安装可运行，7 天过期/重装/数据迁移有明确处理 | 若仅可直接安装不能生成 IPA，必须如实写 BLOCKED |
| E 性能/稳定性 | 指定 iPhone、场景、画质、视距、30min 持续实验 | 记录每帧/GC/RSS/温度/降频与负载 | 无门槛数据不称“高性能终版” |

2026-11-09。原版 26.1.2 单人在模拟器通过菜单、创建世界、转视角、移动、跳跃、取放和破坏方块、物品栏及保存重进。横屏方案已实测 2622×1206。G4 的 60 种程序已预编译，87 条原版管线通过 GPU 测试。CoreAudio PCM 探针通过，原版声音引擎启动。正式 C0/C0a 保持 BLOCKED，真机 C1/C2、整合包与性能仍待验收。详见 [图形证据](GRAPHICS_BOOTSTRAP.md)。

## 必须先做的 ADR

- ADR-001：iOS Java25 AOT fork、源码/许可证、依赖版本、是否真的支持需要的 Java 核心库/JNI。
- ADR-002：Fabric Loader 26.1.2 初始化顺序、Mixin、Class Tweaker、嵌套 JAR 和闭包化证明。
- ADR-003：真实 Minecraft 26.1.2 图形 API 的差异清单（OpenGL 版本、GLFW、LWJGL、OpenAL、资源/着色器）、Metal 路线（直接移植或兼容层），含逐调用测试。
- ADR-008：iOS 图形与窗口栈替代方案（**已接受**）。GLFW 替身 + blaze3d Metal 后端 + 构建期 GLSL→MSL；否证 `os.name` 伪装、宿主库重标、GL→Metal 转译层（Zink/MoltenVK/ANGLE/MoltenGL）、GLFW null platform。执行计划见 [GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md)。
- ADR-004：合法 Minecraft 客户端下载/本地编译/授权流程，及分发边界。
- ADR-005：无付费 Developer Program 签名与安装，BundleID/世界保留测试。
- ADR-006：不信任 Mod 的构建期隔离与供应链控制。
- ADR-007：iOS 生命周期、数据保护与损坏世界恢复。

## 不可犯的架构性错误

- 不能因为 iOS AOT Hello World 成功就宣称 Minecraft 可运行。
- 不要把“Java 25 可以在 Mac 上使用 GraalVM”写成“Java 25 交叉编译 iOS 已支持”。
- 不能把 Fabric 的 build-time 类变换当成执行游戏启动器或运行游戏逻辑；静态预处理必须保留运行时初始化时序。
- 不能把任何 AOT 失败简单兜底为解释器、浏览器、云串流后仍称目标达成。
- 不能静默跳过不能编译的 Mod 后宣称整合包成功；需明确报告 Mod 和实际行为差异。
