# Builder 的 Fabric AOT 兼容性检查

Builder 接收 `.mrpack` 和 Prism 实例，并把经校验的实例副本交给 `mcfao build`。Minecraft 26.1.2、Java 25 和 Fabric Loader 0.19.3 仍由现有输入清单锁定。GL41 使用 OpenGL、OSMesa/Zink 和 MoltenVK，原生 Java Metal 是独立的可选后端。

旧故障字节码、全类路径扫描结果和真机验收状态见 [2026-11-20 AOT 启动与链接审计](evidence/AOT_LINKAGE_AUDIT_20261120.md)。

## 构建顺序

1. 从整合包清单取得带哈希的依赖文件。Fabric 预处理检查 JAR 和声明的嵌套 JAR，使用固定版本 Loader 解析版本约束、选定 Mod、入口点及 Mixin。
2. 通过文件和网络拒绝探针后，在隔离环境中运行 Knot 获取实际转换字节。Fabric Mixin 转换失败会中止对应导出。可选目标、未解析的 accessor 和运行时替换点由转换报告记录。
3. 扫描拆分及后端补丁后的完整 Native Image 类路径，按实际顺序及 Multi-Release 规则建立类型索引。检查入口类继承和生成分派，并报告类型、调用、字段、构造器、静态初始化、方法句柄及 bootstrap 引用。可能只存在于兼容分支的缺失类型与 GL、LWJGL、JNI 和动态访问点作为警告。
4. 合并维护配置、静态推断、受控生成的 Fabric 服务和资源注册，以及可选的 GraalVM Tracing Agent 结果。随后执行现有 Native Image、ARM64 链接与 IPA 校验。构建工作区的阶段检查点绑定原始输入、工具源码和产物哈希，重试先验证这些哈希。
5. `compatibility.json` 是构建记录界面使用的报告。完整的字节码诊断在 AOT 阶段的 `bytecode-findings.json`，元数据来源及成员校验在 `work/mdaf-report.json`，Fabric 转换明细在 Fabric 阶段的 `result.json`。发行产物复验检查输入、原生编译参数、链接目标、已记录的报告和封装内容。

`PASS` 表示该阶段通过实际检查，`FAIL` 表示检查失败，`SKIPPED` 表示未执行或不适用，`UNVERIFIED` 表示缺少该阶段的行为证据。启动和真机状态由对应运行证据确定。导入无法解析的依赖时，报告会保留 Loader 的原因。现有排除确认仍要求用户同意，且只对独立构建副本生效。

## 2026-11-20：GL41 补丁校验回归

NCL Builder 0.2.91 的一次 Fabric 子集构建在 `gl41-patch` 阶段停止。外层只报 `GlDevice patch failed`；该次尝试的 `product/transform/stderr.log` 记录了 `Unexpected changed entries`。`GLX` 和 `SystemReport` 已被改写来避开 iOS 不支持的 OSHI 硬件探测，但 Java 的变更清单漏了这两个类。

Java 现在用同一份注册表执行补丁并要求每个目标实际发生变更。Python 仍逐项比对输入输出 JAR，只允许预期的改动与两个辅助类，并在 Java 失败时报告底层错误和日志目录。可使用本机工具链及该次任务 `split` 阶段生成的 `client.jar` 复跑回归：

```sh
MCFAO_TEST_GL41_TOOLCHAIN="$SPLITTER_DIR" MCFAO_TEST_GL41_CLIENT="$SPLIT_CLIENT_JAR" \
  python3 -B -m unittest discover -s tests -p test_gl41_manifest.py -v
```

使用原任务同一份拆分 JAR（SHA-256 `7a416a282dca8208bd2fd8e989d282a941a9570be95e80a9b1dbd649b0451337`）、GraalVM 25.0.2 与 ASM 9.9 复测，返回 `GL41_CLIENT_PATCHED`。缺少补丁目标的对照仍失败，并输出 Java 原因及完整日志位置。

切换本机存储路径后，`mcfao doctor` 返回 `INPUTS_VERIFIED`，共核验 4,332 项输入。再次出现相同报错的任务日志确认调用了旧 0.2.91 包内脚本。随后以相同的 41 个根 Mod JAR、实例文件、图标及 GL41 参数复跑。`GL41-r2-20261120` 的 Fabric 转换、GL41 补丁、Native Image（79,143 个可达类型）和 iOS ARM64 链接均通过。

本次生成的无签名 IPA 通过 Builder 0.2.92 附带的 `mcfao verify`。输入清单、IPA 文件名和包内 `FAOTTestVersion` 均为 `GL41-r2-20261120`。IPA SHA-256 为 `1c83c160add42f7980a46916780eb832f0e5baa3e0a706a98d1c58c570e00246`。后续真机日志证实进入游戏启动和首轮资源重载，未通过主菜单门槛。

包含修复的 Builder 0.2.92 arm64 本地测试版已打包。版本号、macOS 临时签名、压缩包及包内源码清单验核通过，应用进程从新版路径启动。原失败任务仍可读取，重试解析到新版的包内源码。

## 2026-11-20：模组 JAR 资源与配置元数据

真机日志 `run-1795186717923-GL41-r2-20261120.log` 显示游戏已执行 Fabric 客户端入口、初始化 GL41，并在首次资源重载结束前退出。Sodium 用 `Class.getResourceAsStream("/config-icon.png")` 直接读 JAR 根目录里的图标。源 JAR 有该文件，但导出器的旧规则只收包目录下的文本文件；重载时空流传入 `NativeImage.read`，最终触发未处理的异常。

导出器按资源所属 Mod 的字节码识别 `Class`、类字面量的 `ClassLoader` 和系统 ClassLoader 的字面量查找。保留既定文本类型和常用图片、字体、音频的准确 JAR 路径，为保留的文件生成 Native Image 资源条目。Minecraft `assets/` 和 `data/` 继续走原资源合并规则。单文件上限 1 MiB，同名冲突报告为歧义；不从其他 Mod 随意选择副本，也不导入原生库。此次同一份整合包的 Sodium 图标经字节级比对一致。

同一日志还暴露了两个被捕获的配置兼容问题。配置图现在为实际引用的枚举（含 `EnumMap` 泛型键）注册枚举字段，不继续展开其引用的游戏类。对于把类字面量通过构建器交给 Gson 的序列化器，元数据扫描核对 `Class` 参数、字段传递和最终 `fromJson` 调用，并注册配置类型及继承字段。实际类路径已验证能发现 Sodium Extra 的 `FogType`、Xaero 雷达数据及其父类。

Presence Footsteps 在设备上读到语法错误，但同版 Gson 的宽松解析可读取原 IPA 的配置副本，因此不能据此认定导入源损坏。IAS 的 `toRealPath(NOFOLLOW_LINKS)` 被 iOS 拒绝遍历 `/var`；认证及旁白也有各自的诊断。这些日志均未中止启动。本轮未改写用户配置或账号数据。

第一方 Java 25 / GraalVM 25.0.2 对照在 JVM 和 macOS Native Image 上实际读取 JAR 根目录下的资源，并恢复 Gson 配置的继承字段和 `EnumMap` 键；两次均输出 `RESOURCE_GSON_NATIVE_PASS`。

`GL41-r3-20261120` 复用原构建的 41 个根 Mod JAR 和 181 项实例输入，Fabric 转换、GL41 补丁、Native Image、iOS ARM64 链接和 `mcfao verify` 均通过。已在最终链接的 `client-graph.dylib` 中找到和源 JAR 完全一致的 Sodium PNG（1,832 字节）。无签名 IPA 的测试标识与输入和包内配置一致，SHA-256 为 `6c88ec09bed2ec7bcc2c52a244b2e954b09e589d3f52625a9052e3fefbd89322`；修复版真机启动和主菜单待复测。

## 2026-11-20：地图模组的纹理解码

`GL41-r3-20261120` 的真机日志确认首次资源重载结束、进入单人世界并执行了 274 个客户端 tick。随后 Xaero 世界地图生成地图纹理，`MapWriter.loadBlockColourFromTexture` 调用 `ImageIO.createImageInputStream`，初始化 `IIORegistry` 和 `Toolkit` 时因 iOS 缺少 `awt` 原生库退出。小地图读取方块纹理也使用同一调用形态。

Fabric 导出规则 `ios.texture.png-native-image.v1` 按调用和数据流匹配：从 Minecraft `Resource.open()` 读入，图像、光栅和颜色模型保留在方法内，灰度走原始采样，彩色走 ARGB。规则只替换读取和取像素的调用，保留模组的采样循环、透明过滤、颜色计算、缓存和回退。解码复用 Minecraft `NativeImage`，并在复制像素后释放原生内存；读取上限为 16 MiB、4,194,304 像素，PNG 超过 8 位通道精度或无法解码时走原有异常回退。

同一组 41 个根 Mod JAR 已重新经过隔离导出，确认两个地图写入器的对应方法均已改写。Java 25 回归对照了原桌面实现的彩色、透明、灰度、灰度加 alpha 和调色板像素，并验证损坏 PNG、错误分支和对象逃逸。地图的在线组件图片及 PNG 导出等其余 ImageIO 调用由最终类路径扫描标为 `DESKTOP_IMAGE_IOS_UNSUPPORTED`；警告不等于运行时已到达该路径。

`GL41-r4-20261120` 保留 r3 的 109 个解析后模组、181 项实例输入和 Bundle ID。Native Image、iOS ARM64 链接、无签名 IPA 封装和 `mcfao verify` 均通过。构建记录、IPA 名称、包内 `FAOTTestVersion` 一致。IPA SHA-256：`ded8da9f14bb9732eb786f38413633c9ed7d293aadb626a44e4f9a32f69850de`。r4 仍需在真机进入世界，确认世界地图和小地图正常生成。

可用构建配置中 `prepared` 指向的工具链目录单独运行像素对照：

```sh
MCFAO_TEST_FABRIC_PREPARED="$PREPARED_DIR" \
  python3 -B -m unittest discover -s tests -p test_runtime_lowering.py -k texture_sampler
```

## 两条历史启动回归

- **RenderPipelines** · `AotExport` 曾在所有 Fabric 导出中无条件调用 `RuntimeLowering.lowerRenderPipelineRegister`。该函数把游戏注册替换为 Metal 着色器包守卫 `fabricaot.metal.BundledPipelines.register`。GL41 的编译输入缺少这个 Metal 专用类，内容 Mod 访问 `Sheets` 时便会触发该引用。现在仅原生 Metal 安装守卫，GL41 保留游戏注册及正常 Knot Mixin 输出。最终类路径检查会阻断旧 Metal 类型定义和客户端符号引用。
- **Freecam** · 本地 `1.4.0-alpha.3+mc26.1.2` 的 `ModConfigDTO` 有 `public <init>()V`。其配置控制器把该 DTO 的 class literal 传给 Gson 加载器。加载器在默认配置分支用动态 `Class#getConstructor()` 实例化，普通 Native Image 静态推断可能缺少该构造器注册。规则从字节码核对构造器参数、同一 Class 字段的赋值、无参反射和 Gson 读取，再为确有公开无参构造器的目标及其配置字段闭包生成元数据。类型缺少公开无参构造器时给出独立诊断。

自动处理写入生成的客户端 JAR 或构建专用元数据。Fabric 转换及其前置、后置条件使用现有规则引擎和固定输入。Mod 自带的宿主 Native Image 参数可改变整个构建的初始化策略，导出器继续过滤这些参数。

可选的本地 `mcfao build --tracing-config <目录>` 接受受审计的 Tracing Agent 输出，并允许重复传入目录。支持统一的 reachability metadata 以及 Reflection、JNI、Resource、Proxy 和 Serialization 分文件格式。默认 GUI 构建直接使用现有图形 JNI 配置和自动生成的静态元数据。动态类定义、计算出的代理接口列表、序列化类型图、特殊 JNI 库和扩展调用仍需相应行为证据或适配。Prism 实例缺少未锁定的远程依赖时需要补齐实例。追踪只覆盖执行过的路径。参见 [GraalVM 25 reachability metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/) 和 [Tracing Agent](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/AutomaticMetadataCollection/)。

## 本地验证

| 输入 | 静态检查 | Fabric 转换 | AOT / IPA | 启动 / 真机 |
| --- | --- | --- | --- | --- |
| Freecam 1.4.0-alpha.3 + Fabric API 0.148.0 | PASS | PASS，47 个 ID（含嵌套） | SKIPPED | UNVERIFIED |
| Biomes O’ Plenty 26.1.2.0.5 + GlitchCore 26.1.2.0.0 + TerraBlender 26.1.2.0.2 + 同版 Fabric API | PASS | PASS，50 个 ID（含嵌套） | SKIPPED | UNVERIFIED |
| 两组 Mod 合并，经 Builder 暂存 Prism 实例 | PASS | PASS，54 个 ID（含嵌套），无排除 | PASS，无签名 IPA | UNVERIFIED |
| 第一方 Fabric + Mixin + 包内声明资源夹具 | PASS，客户端 JAR 资源逐字节核对 | PASS，5 个游戏类已转换 | SKIPPED | UNVERIFIED |
| 原版 26.1.2 GL41 | PASS | SKIPPED | PASS，无签名 IPA | UNVERIFIED |

组合包使用仓库锁定的 GraalVM CE 25.0.2 构建。Native Image 分析报告记录 54,771 个可达类型。ARM64 可重定位对象中有 `RenderPipelines.<clinit>`、`ModClient.addWoodType`、`GsonConfigLoader.read` 以及 Fabric 渲染适配符号。Native Image 读取的反射配置包含 `ModConfigDTO` 及其嵌套配置类型。Prism 暂存前后的五个根 JAR 哈希一致，生成的无签名 IPA 经 Builder 逐文件复验。该次构建对象 SHA-256 为 `9f46ba6e27f2aae0f946cc0730666752e10636c3a7606b466ee6552d0e568b23`，无签名 IPA SHA-256 为 `b00fed1de348ba662c83a72c5dd28d368c15c32bafb872d1a0f9c7411c708553`。链接报告仍列出已知的 JDK 管理 JNI 入口 `Java_com_sun_management_internal_OperatingSystemImpl_initialize0`。

第一方 macOS Native Image 对照使用同一 JDK 及 `--no-fallback`。对同一个确有公开无参构造器的夹具，只注册类型时运行抛出 `NoSuchMethodException`，使用扫描器生成的元数据时实际实例化成功，输出 `REFLECTIVE_CONSTRUCTOR_PASS`。

原版回归使用同一组 GL41 原生依赖，生成 ARM64 可重定位对象及完整无签名 IPA，IPA SHA-256 为 `1bdbe340ceaa09833240cfe9d94ee5b232d885daecfe406c7d1f08424df17f24`。

本地任务基线通过 585 个 Python 测试、90 个前端单元测试和兼容性摘要的 Playwright 键盘交互测试。公开 Builder 基线上的移植另行运行了测试，并完成真实组合包的隔离转换。

已有 LAN-r4 记录对应原版 GL41 IPA。本次报告中的 Mod 构建为新生成的测试样本，设备启动、菜单、世界交互和存档均保留 UNVERIFIED。

用本地已验证的 GL41 配置及 Mod 目录可复跑。两个 Mod 组合分别跑一遍 `--prepare-only`，实际构建组合包时省略该参数。原版将 Loader 改为 `vanilla` 并省略 Mod 参数。

```sh
./mcfao build --version 26.1.2 --target ios-arm64 --renderer gl41 \
  --loader fabric --mods "$MODS_DIR" --audited-mods --unsigned \
  --config "$GL41_CONFIG" --output "$NEW_BUILD_DIR"
./mcfao verify --target ios-arm64 --output "$NEW_BUILD_DIR"
python3 -B -m unittest discover -s tests -p 'test_aot_compatibility.py'
```

## 2026-11-21 通用机制回归

新增别名与动态 Mod ID 的目录查询、可跟踪的类路径资源闭包、元数据来源、严格诊断模式和逐 Mod 状态。兼容性报告在 Builder 的构建记录中可逐项展开，并能定位到实际报告。启用严格缺失注册诊断的 CLI 参数为 `--exact-reachability-metadata`。见 [本轮实现与验证](compatibility/IMPLEMENTATION_REPORT.md)。

COMPAT-r3 增加 pack 层的动态绝对 Classpath 流读取及最终 JAR 完整性校验。Gson 从内联或不可变字段的 TypeToken 读取泛型类型时，扫描器可注册具体 DTO。相关机制已运行 JVM 对照、严格 macOS Native Image 探针及整包 iOS ARM64 构建。见 [资源闭包](compatibility/RESOURCE_CLOSURE.md) 和 [反射验证](compatibility/AOT_METADATA.md)。
