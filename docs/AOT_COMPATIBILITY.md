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

## 两条启动回归

- **RenderPipelines** · `AotExport` 曾在所有 Fabric 导出中无条件调用 `RuntimeLowering.lowerRenderPipelineRegister`。该函数把游戏注册替换为 Metal 着色器包守卫 `fabricaot.metal.BundledPipelines.register`。GL41 的编译输入缺少这个 Metal 专用类，内容 Mod 访问 `Sheets` 时便会触发该引用。现在仅原生 Metal 安装守卫，GL41 保留游戏注册及正常 Knot Mixin 输出。最终类路径检查会阻断旧 Metal 类型定义和客户端符号引用。
- **Freecam** · 本地 `1.4.0-alpha.3+mc26.1.2` 的 `ModConfigDTO` 有 `public <init>()V`。其配置控制器把该 DTO 的 class literal 传给 Gson 加载器。加载器在默认配置分支用动态 `Class#getConstructor()` 实例化，普通 Native Image 静态推断可能缺少该构造器注册。规则从字节码核对构造器参数、同一 Class 字段的赋值、无参反射和 Gson 读取，再为确有公开无参构造器的目标及其配置字段闭包生成元数据。类型缺少公开无参构造器时给出独立诊断。

自动处理写入生成的客户端 JAR 或构建专用元数据。安全的已知类路径资源由直接 `Class.getResource*` 字面量和唯一来源确定。受控范围是有限大小的包内声明文件。Fabric 转换及其前置、后置条件继续使用现有规则引擎和固定输入。Mod 自带的宿主 Native Image 参数可改变整个构建的初始化策略，导出器继续过滤这些参数。

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
