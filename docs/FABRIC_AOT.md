# Fabric AOT 适配器

## 固定边界

当前实现面向 Minecraft 26.1.2、Java 25、Fabric Loader 0.19.3、Sponge Mixin 0.8.7 和官方未混淆命名空间。版本与构建引擎指纹来自 [Fabric 锁定文件](../compiler/fabric.lock.json)。Loader 内部导出接口按该版本固定，升级 Loader 时须重新验证。

| 环节 | 当前行为 | 验证方式 |
|---|---|---|
| 发现与解析 | ZIP 检查先限制展开大小、递归深度和成员路径。使用真实 `ModMetadataParser` 读取根 JAR 和声明的嵌套 JAR。 | `--prepare-only` 的 `result.json` |
| 依赖与环境 | 审计过的构建使用真实 Knot 初始化，交给 Loader 做客户端环境过滤、嵌套发现、版本匹配和依赖排序。 | `knot/stdout.log` 和 `transform.resolvedMods` |
| 字节码转换 | 在 Knot 的最终字节接口读取客户端及选中 Mod 的类。沿用上游游戏入口 patch、Fabric 环境和 Class Tweaker 转换及 Mixin 的执行顺序。以 ASM `BasicVerifier` 检查导出的类。 | `transform.gameTransforms` 保存变换前后 SHA-256。Native Image 继续验证实际可达类。 |
| 入口 | 从 Loader 的实际 Entrypoint 容器读取 `main`、`client` 的顺序和实现。把 Loader 注入的启动点重定向到生成的 Java 字节码，运行时直接构造并调用公开无参 Java 入口；`Class::method` 形式在构建期解析目标方法的访问标志，生成 `invokestatic` 或 `invokevirtual`。 | `transform.entrypoints` 的 `refOwner`/`refName`/`refStatic` 与实际客户端日志 |
| 资源和初始化 | 将无冲突的 `assets/`、`data/` 并入客户端，生成精确资源 glob 和 Mod 类的运行时初始化选项。Mixin 定义留在构建期，镜像含上游回调类型。 | `META-INF/native-image/mcfao/fabric/`、Native Image 日志、夹具实际资源读取 |
| 原生后端 | 适配器交付一个已封闭的客户端 JAR。与原版共用方法拆分、Metal 注入、Native Image、iPhoneOS 链接和签名。 | `inputs.json`、各阶段 `command.json`、签名包的 `result.json` |

桌面 Knot 在 `FabricLoaderImpl.load/freeze` 解析 Mod，安装 Class Tweaker 和 Mixin 后准备类加载。闭世界镜像把最终类放入分析输入，镜像运行时使用固定入口与回调。真实 Loader 的发现和入口选取发生在构建期。完整 Loader 公共 API、动态 ClassLoader 和任意入口查询仍需独立的运行时适配。

## 第一方游戏夹具实测

- F1 的 `ClientModInitializer` 由真实 Loader 发现。模拟器 AOT 客户端实际执行入口并校验 `assets/mcfao_fixture/proof.txt`。 [运行日志](../artifacts/mcfao/fabric-simulator-02/game.log)
- F2 反汇编确认 `Minecraft#setLevel` 调用 Mixin 生成的处理方法。F3 通过同一处理方法在单人世界实际触发 `GameMod.onWorldJoined`。服务器玩家登录、Mod 回调和渲染画面均已采集。`getVersionType` 只核验了转换后的字节码。 [反汇编](../artifacts/mcfao/fabric-bytecode-02/stdout.log) · [烟测结果](../artifacts/mcfao/fabric-simulator-02/result.json) · [世界截图](../artifacts/mcfao/fabric-simulator-02/world.png)
- 设备目标由同一 AOT 对象单独链接。开发签名 IPA 已验签并核对指定 iPhone 的描述文件覆盖，运行仍待真机。 [IPA 清单](../artifacts/mcfao/fabric-ipa-02/result.json)

## 整合包增量（第 48 轮）

- Recollection3 本地实例的元数据预检现在是 54 条诊断、31 组阻塞根 JAR；本轮开始前同一实例是 178 条、49 组。减少来自四处：`net/fabricmc/` 目录条目不再被误判为 Loader 类，`modmenu` 与提供者缺失的 `jei_mod_plugin` 入口记录跳过（17 条），`Class::method` 入口形式改为受支持，以及 `MixinConfigPlugin` 从拒绝项改为构建期钩子。 [预检报告](../artifacts/mcfao/recollection3-import-07/)
- `fabric-networking-api-v1-6.3.0` 与 `fabric-api-base` 已通过隔离转换。三个 `Class::method` 入口在生成的 `mcfao/aot/Entrypoints` 里落为三条 `invokestatic`，`javap` 核验启动路径无反射。 [转换报告](../artifacts/mcfao/networking-transform-01/result.json)
- `chat_heads-1.2.2` 已通过隔离转换：它的 `MixinPlugin` 在 Knot 里实际执行，18 个客户端类被 Mixin 改写（`ChatComponent`、`ClientPacketListener`、`GuiRenderer`、`PlayerGlyphProvider` 等），`CompatImpl#isModLoaded(String)` 的非字面量查询被改写成生成的成员测试。 [转换报告](../artifacts/mcfao/chat-heads-transform-01/result.json)
- 仍未生成整合包 IPA。剩余 54 条诊断：`META-INF/versions`/`services`/`native-image` 36 条、保留依赖 id 4 条、由已打包 Mod 消费的自定义阶段（`sodium:config_api_user` 3，`jade`/`glitchcore`/`ebe_v1`/`rei_client`/`voicechat`/`preLaunch` 各 1）、`fabric-language-kotlin` 的 Schema 1 与 Kotlin 语言适配器，以及 `CustomSkinLoader` 的 refmap。
- Kotlin 生态是当前最大的单一障碍：`fabric-language-kotlin` 要求 Schema 1 之外的 Kotlin 语言适配器，包内 20 余个 Kotlin Mod 的 `adapter: kotlin` 入口都依赖它。

## 整包转换（第 50 轮）

预检在这一轮之前已经降到 0 阻塞，所以 `--audited-mods` 的失败点全部落在转换阶段。此前一个类降不了就整包失败，现在拆成三条不同性质的策略，每种都在报告里留痕：

| 情况 | 处理 | 报告字段 |
|---|---|---|
| 查询能静态回答 | 改写成常量、生成方法或空集合 | `transform.staticAdaptations` |
| 查询属于构建期元数据 | 该方法整体变为返回类型空值（`List.of()`/`Optional.empty()`/`""`/`null`），签名不变 | `transform.stubbedMethods` |
| 需要运行期生成类、JNI 或动态代理 | Mod 无法进入闭世界，剪掉该 Mod 及其必需依赖 | `result.json` 的 `excludedMods` |

入口方法不允许被 stub：静默清空 `onInitialize` 等于把 Mod 关掉却不报告，所以入口一旦降不了就直接判失败。驱动脚本读 `incompatible.json` 逐轮剪枝，最多 5 轮收敛；丢弃一个 Mod 时会连带丢弃 `depends` 里依赖它的 Mod，避免把缺类问题留到 Native Image 才暴露。

新增的静态能力：

- **自定义入口阶段**：`glitchcore`、`jade`、`terrablender`、`modmenu`、`sodium:config_api_user`、`fabric-datagen`、`jei_mod_plugin`、`rei_client`、`voicechat`、`controlify` 共 10 个阶段的提供者在构建期物化成 `mcfao/aot/Entrypoints.stage*` 的分支，返回 `Entrypoints$Container`。容器实现 Loader 的 `EntrypointContainer`，`getProvider()` 返回 `null`（镜像里没有 ModContainer），`getDefinition()` 返回构建期记下的类名。调用点把 `getInstance` 换成 `ACONST_NULL`，因此生成的代码里不出现 `FabricLoader`。
- **版本常量**：`getModContainer(id).orElseThrow(...).getMetadata().getVersion().getFriendlyString()`（包括编译器把容器存进局部变量再读回的形式）折叠为构建期版本字符串。Lithium 的 `onInitialize` 因此不再是失败点。
- **`getAllMods()`** 折叠为空集合；`getEntrypoints(stage, type)` 与 `getEntrypointContainers` 走同一套阶段分发。
- **Mixin 类按类整体导出，不再按注解筛选**：Knot 拒绝交出任何 Mixin 拥有的类，所以 Mixin 的定义类是直接从 JAR 里读的，读出来去掉 Mixin 注解后全部随 overlay 出厂。上一版只保留带 `@Accessor`/`@Invoker` 的接口，代价是**合并后的目标类会引用一个镜像里不存在的类型**——例如 `net.minecraft.client.renderer.block.dispatch.BlockStateModel` 的 `interfaces` 表里就有 `...mixins...BlockStateModelMixin`，而 ETF 依赖的 TRender 嵌套 JAR 里的 `ScreenAccessor` 是普通接口、没有任何 `@Accessor` 注解。这类类在闭世界里根本不是「死代码」：**引用它的类无法加载**，而 Native Image 不会让构建失败，它把对这些类的每一次调用静默换成一个运行期抛 `NoSuchMethodError` 的 stub。`tools/verify_aot_classpath.py` 就是把这个静默失败变成一份清单的检查器。
  - 导出的副本要**提升为 public**：Mixin 合并时会把非 public 的 Mixin 接口提成 public（否则目标类跨包无法实现它），照抄的副本保留原访问标志，于是 30 个类（含 `BlockStateModel`、`SubmitNodeCollector` 等核心类）在加载期抛 `IllegalAccessError`。`RuntimeLowering.stripMixinMetadata` 现在统一加 `ACC_PUBLIC` 并清掉 private/protected。
  - **MixinConfigPlugin 不随镜像出厂**：它是构建期钩子（Knot 用它决定哪些 Mixin 生效），运行期不可达，却实现镜像里没有的 `IMixinConfigPlugin`。本轮 22 个 plugin 类记入 `droppedEntries`，`transform.mixinPlugins` 留痕。
- **分段方法名必须带方法身份**：方法分割器给分段和 spill 字段起名时只用序号（`fabricaot$part$1`、`fabricaot$spill$<boundary>$<slot>`），同一个类里两个方法被分割就撞名。`BlockStateData` 一个类里有 10 个 `bootstrapX` 方法被分割，全部挤进 `fabricaot$part$1..N`，class 文件加载期抛 `Duplicate method name "fabricaot$part$1"`（`ClassFormatError`）。现在名字里带 `<方法名>$<descriptor 哈希>`，并且分割器在写出前自检 name+desc 唯一，撞名在构建期就失败。

- **类名规则按 JVMS**：Kotlin inline reified 生成的 `VanillaAccessorsKt$(itemType)$1`、`Parser$match-impl$$inlined$sortByDescending$1` 是合法类名，此前被过严的正则拒绝。
- **资源分层**：`data/**/tags/`、`assets/**/atlases/` 按数据包语义合并，其余同名文件后层覆盖，覆盖了原版文件的条目必须出现在 `transform.overriddenResources`，`merge_client` 用这份清单校验 overlay，不再要求「零重叠」。

### 本轮实测（47 个根 JAR / 154 MB）

| 指标 | 结果 |
|---|---|
| 解析并导出的 Mod | 121（含 fabric-api 子模块与嵌套库） |
| 被剪枝的 Mod | 11 |
| 方法级 stub | 104 |
| 静态改写 | 201 |
| 自定义入口阶段 | 11（提供者共 46 个） |
| ServiceLoader 注册 | 38 |
| 跳过的 Mixin 类 | 1474 |
| 合并 / 覆盖的资源 | 230 / 183 |
| 输出客户端 JAR | 176 MB |

Sodium 不再被剪枝。它的顶点序列化器在运行期用 `MethodHandles.Lookup.defineClass` 生成，但生成结果只是两个 `VertexFormat` 布局的纯函数，所以 `createSerializer` 被改写为返回 `mcfao.aot.GenericVertexSerializer`：构造时按目标格式的每个元素在源格式里的偏移算出复制计划，相邻且两侧都连续的段合并成一次 `MemoryIntrinsics.copyMemory`，与 Sodium 生成器合并的是同一种段。生成器本体（`VertexSerializerFactory` 及 `$Bytecode`/`$MemoryTransfer`）改写后没有调用者，被记入 `droppedEntries`。等价性用 Sodium 自己的 `createMemoryTransferList` 在 15 种 `DefaultVertexFormat` 的 225 个组合上验证：92 个兼容组合逐字节相同，133 个不兼容组合两边同样拒绝。

被剪枝的 7 个 Mod 及其原因：

| Mod | 原因 |
|---|---|
| `entity_model_features` | 自带 ASM 小型编译器，运行期 `defineClass` 生成数学表达式 |
| `net_lenni0451_reflect` | 反射加速库，核心就是 `defineClass` |
| `org_javassist_javassist` | 运行期类定义（嵌套库） |
| `org_jetbrains_kotlin_kotlin-reflect` | `Proxy.newProxyInstance`（嵌套库） |
| `org_reflections_reflections` | 动态代理 + `URLClassLoader.getURLs`（嵌套库） |
| `net_neoforged_bus` | `MethodHandles.Lookup.defineHiddenClassWithClassData`（嵌套库） |
| `net_lostluma_battery` | JNI 原生方法与 `System.load` |

这 7 个都是「运行期必须生成新类」才成立的能力，不是可以在构建期折叠的查询。

**剪枝必须同时退场 jar。** Knot 应用一个 Mod 的 Mixin 配置，依据是 jar 在 mods 目录里，而不是它是否被请求导出。只从导出列表里删掉 Mod，会留下「Mixin 已注入、类不在镜像」的状态：真机上 `SystemReport` 带着 Iris 的注入方法，第一次生成崩溃报告就抛 `NoClassDefFoundError: net.irisshaders.iris.Iris`。现在一个 jar 声明的全部 id 都被剪枝时才整体移入 `work/excluded/` 并记入 `retiredJars`，注入的 Mixin 集合与镜像包含的类保持一致。同一轮还给 `SystemReport` 里所有 `handler$` 开头的 Mixin 注入方法加了无条件 stub：崩溃报告本身不能因为某个 Mod 缺席而二次崩溃，否则真正的异常会被掩盖。

## 第 51 轮：Sodium 恢复、剪枝一致性与真机首跑

第 50 轮的产出（121 个 Mod、181 MB `client.jar`）走完了 `split → metal-injection → aot → runtime → link → stage → package` 全流程，得到 `SIGNED_DEVICE_APP`（689 MB，`client-graph.dylib` 238 MB，Team `P57SZ9Z7G2`），并装进了 iPhone 19,4。首次启动的记录：

- `dlopen` 成功，2 GiB 预留地址空间探测通过，32768 MiB 探测按预期失败。
- GraalVM 入口进入 `net.minecraft.client.main.Main.main`，说明 AOT 镜像、Metal 后端加载与 iOS 运行时桥接都是通的。
- 退出码 1，日志里唯一的异常是 `NoClassDefFoundError: net.irisshaders.iris.Iris`，抛在 `net.minecraft.SystemReport.handler$cfc001$iris$fillSystemDetails`。

这是构建产物自身的矛盾，不是设备问题：Iris 在上一轮被剪掉（连带 sodium），但 jar 仍留在 mods 目录，Knot 照常把它的 Mixin 注入进 `SystemReport`，于是崩溃报告路径引用了一个镜像里不存在的类。修复见上文「剪枝必须同时退场 jar」。

同一轮的另外两处改动：

- `SystemReport` 中所有 `handler$` 开头的 Mixin 注入方法现在无条件 stub。它们在崩溃报告里只填诊断信息，但会引用注入方 Mod；报告不能因为某个 Mod 缺席而二次崩溃，否则真正的异常永远看不到。
- `mcfao/aot/` 下的第一方运行时类单独编译：它们的 classpath 必须包含 Mod jar 才能实现 Mod 接口，而 Mod jar 绝不能进入 AOT 主机的 classpath，否则 Mod 类会被系统类加载器和 Knot 双重加载。编译产物通过导出的第六个参数目录写进 overlay，并记入 `transform.runtimeClasses`。

剪枝集合随之从 11 个降到 7 个，`iris`/`sodium-extra`/`reeses-sodium-options` 随 `sodium` 一起回到闭世界，`resolvedMods` 125 个。

## 兼容边界



- `--prepare-only` 仅读取归档与元数据，最多检查 512 个根及嵌套归档；转换预算为 256 个归档，覆盖 Recollection3 本地实例解出的 53 个根与 168 个嵌套归档。两侧都保留原有展开大小限制。元数据读取容许顶层描述内的字面换行，其他字段继续接受严格检查。报告汇总现有 AOT 限制。构建须显式指定 `--audited-mods`，先通过项目沙盒的外部文件读写和环回连接负例，再执行 Knot。D0 仍缺少面向任意第三方 Mod 的完整隔离验证。
- 支持官方命名空间下的公开 Java 类形式 `main`、`client` 入口，以及 `Class::method` 形式的无参 `void` 方法引用。方法引用在构建期解析为静态或实例调用，运行时不经过 `MethodHandle`；签名不匹配或目标不存在会直接报错。自定义语言适配器、`preLaunch`、旧式入口会被拒绝。`modmenu` 阶段和提供者缺失的 `jei_mod_plugin` 阶段记录到 `optionalEntrypointsSkipped` 并跳过——封闭世界客户端里没有查询它们的代码。由已打包 Mod 查询的自定义阶段现在由生成的 `Entrypoints.stage` 分发，提供者在构建期物化；只有 `Class::method` 形式的自定义阶段入口仍会拒绝。所有 Mod 入口按依赖顺序在同一次调用里执行，任一个抛异常仍会终止启动，与上游 Loader 逐个容器调用的差异保留。
- 支持必需、无 refmap 重映射的官方命名空间 Mixin 配置，包括 `plugin` 声明的 `MixinConfigPlugin`。插件是构建期钩子：真实 Knot 在镜像组装时执行它，运行时不需要该类存在。父配置、显式 injection points 和动态选择器仍超出范围，因为它们会改变 Mixin 生成哪些类。Class Tweaker 由真实 Loader 装载，本轮的游戏夹具覆盖 Mixin，既有 B0/B1 证据覆盖访问修改与嵌套依赖。
- `FabricLoader.getInstance().isModLoaded(String)` 的字面量查询在构建期折叠为常量；参数不是字面量时改写成生成的 `mcfao.aot.Entrypoints.isModLoaded` 成员测试，答案与构建期 Loader 一致。`isDevelopmentEnvironment`、`getEnvironmentType` 同样静态化，其它 Loader 运行时调用仍直接报错。
- 字节码检查对直接调用 `defineClass`、`defineHiddenClass`、`URLClassLoader`、运行时 Loader API、动态代理和原生加载，以及声明的 native 方法给出 Mod、类和方法位置。任意反射、方法句柄间接生成类、动态 JNI 和服务发现仍需单独验证。`META-INF/services` 现在跨 Mod 合并后写回 overlay，provider 生成反射配置；自带 Native Image 配置的条目被丢弃并记入 `droppedEntries`，避免外来初始化策略作用到共享类；本地库仍会拒绝。
- 资源只有一个层：`data/**/tags/` 与 `assets/**/atlases/` 按数据包语义合并 `values`/`sources`（尊重 `replace`），其余同名文件按后层覆盖，覆盖原版文件的条目必须登记在 `transform.overriddenResources`。没有独立的 Mod 资源包优先级，也没有 Mod JAR 文件系统语义（`ModNioPackResources` 在镜像里返回空，资源来自合并后的客户端 JAR 本身）。类重名仍然直接失败。
- 因为闭世界没有 `ModResourcePackCreator`，内置 vanilla 包的命名空间集合必须扩大到出货 jar 里实际存在的全部 `assets/<ns>/`、`data/<ns>/` 命名空间，否则 `MultiPackResourceManager` 不为 Mod 命名空间建索引、所有 Mod 资源都取不到。由 `RuntimeLowering.lowerVanillaPackBuilder` 在 `VanillaPackResourcesBuilder.build()` 单点改写为构建期生成的 `mcfao.aot.ModNamespaces.withVanilla(...)`，清单落在 `transform.resourceNamespaces`（详见下文「已落地」章节）。

下一步是在同一物理 iPhone 上验证测试 Mod 的入口、注入和世界回调，再补静态 ModContainer/资源查找、可审计的反射和服务元数据，以及实际 Fabric API/整合包测试。版本和映射选择应在 Loader 适配层决定，原生后端继续接收已转换的输入。

实现依据见 [Fabric Loader 0.19.3 源码](https://github.com/FabricMC/fabric-loader/tree/0.19.3/src/main/java/net/fabricmc/loader/impl) 与 [GraalVM 25 Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)。


## AppleSkin 配置闭包修复（2026-11-11，pack-49 验证中）

出货字节码确认 `ModConfig.init` 先创建 INSTANCE，随后 `load` 在已有 appleskin.json5 时用 Jankson.fromJson 覆盖 INSTANCE。此前仅注册 GUI 配置类，缺少实际 ModConfig 的反射构造器与字段；增加该类注册以保留配置持久化语义。构建与模拟器回归待运行，门槛状态不变。

pack-49 在宿主执行权限检查处失败，未执行转换；pack-50 使用相同源码在允许的本机构建环境重跑。209 项既有 Python 回归通过（`/tmp/mcfao-tests-20261111.log`）。另确认原 61 个根 JAR 不含 `mcfao_fixture`，交接默认 F1/F3 判据对该输入不可达；已构建仓库自有验证夹具，并复制原包至 `artifacts/mcfao/curated-verification-mods-01`（61 个原 JAR + 1 个夹具，原输入不改）。冒烟增加启动前夹具检查及测试；后续完整判据使用带夹具的包，诊断运行必须显式给出 marker。

pack-50 已完成构建；classpath 56,700 类中 112 个不可加载，核心游戏/Loader 0 个失败；AppleSkin JVM 与桌面 AOT 配置值往返回归均 PASS（`artifacts/mcfao/appleskin-config-aot-01/result.json`）。模拟器保留已有配置运行，先撞上 NoChatReports `JSONConfig.writeFile` 的空 fileName（`fabric-pack-50-simulator/game.log`）；不再靠删除 NCR 配置绕过。出货字节确认三个 NCR 配置类各有 protected 无参构造器初始化 fileName/filePath，缺反射导致 Gson 走无构造器分配。追加三个配置类构造器/字段、基类字段及 SigningMode 枚举字段注册，pack-51 连同验证夹具复验；AppleSkin iOS 路径仍待越过 NCR 后确认。

pack-51 核心类可加载性仍 0 失败；保留配置的模拟器已越过 NCR 与 AppleSkin，接着在 Chat Heads `ChatHeadsConfigData.<init>()` 缺反射构造器处失败。新增只读 classfile 结构扫描 `tools/config_reflection.py`：根据 ConfigData 继承链生成构造器/字段元数据，覆盖同配置包内的字段类型（含数组/泛型枚举）及继承字段；不加载、不初始化 Mod，不遍历 Minecraft 字段图。与手动反射配置合并，并记录 autoConfigReflection 与构建输入指纹。真实出货 JAR 扫描得到 12 个类型，含 ChatHeadsConfigData/RenderPosition/SenderDetection；五项扫描/继承/边界/截断负例回归通过。pack-52 完整复验中。

pack-52 模拟器已越过 Chat Heads，下一处为 Indigo.onInitializeClient 引用被排除的 IndigoMixinConfigPlugin。已审计插件原字节：shouldApplyIndigo 仅扫描所有 Mod 的 `fabric-renderer-api-v1:contains_renderer` 自定义键；生成同一布尔决定替换该调用，不在运行期加载插件。改写受原插件 SHA-256 934ac8f2002a53fcf5a095d44cfd1ce97625ff362058b2556b5d4f59941f0d47 限定，改版插件精确拒绝。第一方 JVM 字节码回归在插件不存在的 classpath 上分别执行 true/false 路径，并验证指纹不符拒绝和无关方法不变，PASS（`artifacts/mcfao/indigo-gate-regression-01/`）。pack-53 完整复验中。

pack-53 已消除 Indigo 插件缺失引用，核心类可加载性 0 失败；模拟器下一处是 Entity Culling ConfigUpgrader 的空 blockEntityWhitelist。字节码显示其 Gson.fromJson 使用 Config.class 字面量；缺构造器注册导致已有 JSON 分支的字段为 null。导出器现从 Gson/Jankson 的静态 Class 字面量反序列化调用收集实际 Mod 类型，写入本地出货 JAR 的 serialization-roots.json（不收游戏/库外部类型），配置扫描器据此合并构造器/字段和同包字段类型注册。动态 Class/TypeToken 不猜测；报告字段 serializationRoots / configurationReflection 可审计。新增非 AutoConfig 根及调用点收集回归通过。pack-54 验证中；保留已有配置，不以清配置绕过。

pack-54 模拟器已越过 Entity Culling，随后 Jade ClientProxy.<clinit> 抛 VerifyError。不执行初始化的 JVM 成员解析定位到 FabricJadeMetadata.<init> 被 residue stub 改成单独 RETURN，未调用 super。已审计并按原构造器语义生成构建期 Jade 元数据表：保留父类状态、OR 三个布尔标志、记录禁用物品 Mod 名提示的 id 列表；仅接受原类 SHA-256 0893768a286b48ac48e75ab7b8d7ecf2da3321d8743fbba0366abd0c42aa2184。其它未适配构造器改为合法 ATHROW 明确失败，避免 VerifyError；同批修正 residue stub 中 List/Set/Map.of 的接口调用标志。第一方 JVM 回归实际加载生成类、构造 Jade 数据并校验父类状态/列表/指纹负例，且验证未支持构造器可校验但明确抛错、集合返回可调用，PASS。原始定位证据 `artifacts/mcfao/jade-verify-01/`。pack-55 完整复验中。

223 项 Python/第一方 JVM 回归全通过（`artifacts/mcfao/regression-20261111-jade-01/`）。`verify_aot_classpath.py --verify-members` 提供不初始化的成员解析补充检查，单独输出 classpath-members-check.json；它比默认类加载更严格，可报告私有死方法签名里的可选类型，不直接替代运行结论。探针子进程失败/缺 SUMMARY/计数不全现在精确失败，防止把无输出当 0 个失败。

pack-55 模拟器首次出现 MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS，尚未进世界；下一处是 ModMenu 自定义阶段 NEW Zoomify Kotlin object 的 private 构造器而抛 IllegalAccessError。自定义阶段现按不初始化的类结构识别 INSTANCE，普通 provider 延迟创建并缓存（每项同步工厂），复现 Loader 的单次实例语义；第一方 JVM 回归验证 private 构造器单例、延迟创建及跨查询身份 PASS。

同轮成员校验主动找到 5 个合成 Args$N 的 VerifyError：手写 getter 从 Object 返回具体引用缺 CHECKCAST；原承载类还未实现 Args 的抽象 set/setAll。现从同一构建期 Mixin transformer 的 ArgsClassGenerator 注册表导出上游完整结果，校验所有真实调用成员匹配，运行期只用预生成字节。新增 ArgsBehaviorProbe 覆盖全部出货承载类的 typed getter、set/setAll、索引/数量/原始类型 null/引用类型负例，待 pack-56 产物执行。原始定位在 `artifacts/mcfao/args-verify-01/`。pack-56 完整复验中。

pack-56 在构建期检查到 AppleSkin 元数据声明的 rei_client 提供者 `squeek.appleskin.client.REITooltipPlugin` 本就不在 JAR 内，未进入 AOT。现在从实际保留下来的 Entrypoints.stage 调用收集 queriedEntrypointStages，只为有调用点的阶段生成派发；其余全部原始声明保留在 unqueriedEntrypointStages，不按消费者名字猜测或删除 Mod。对活跃阶段继续验证 public 构造器或 INSTANCE；静态阶段收集、单例及延迟身份回归通过。pack-57 复验中。

pack-57 已成功导出上游 Args 与 Kotlin 单例，实际保留的查询阶段为 appleskin / frex_flawless_frames / glitchcore / jade / modmenu / terrablender；其余阶段声明有独立台账。ArgsBehaviorProbe 在进入模拟器前发现生成器原始 maxStack 不含 long/double 的完整槽位（上游要求最终 writer 计算最大栈）；主动停止该轮 AOT，未作为有效模拟器构建。导出序列化现用 COMPUTE_MAXS，并追加实际 JVM 运行宽类型栈夹具（故意提供不足 maxStack，验证重算后可执行）的回归，PASS。pack-58 复验中；Args 完整行为仍待新产物执行。

pack-58 的 8 个真实出货 Args 已通过独立 JVM 行为回归（typed getter、set/setAll、索引/数量/原始类型 null/引用类型负例），`artifacts/mcfao/args-behavior-58-01/result.json` 记录输入指纹。此为构建期字节码行为辅助证据，模拟器进世界仍待验。

pack-58 核心类可加载性 0 失败，成员校验 VerifyError 0；模拟器越过 Zoomify/Mod Menu，F1 再次出现，随后 Presence Footsteps 的 TargettedVersion.getVersion 因 Optional 方法引用仍提到未出货 ModMetadata 而失败。已对原类 SHA-256 354dc01c8aff54e3b4543f1d441fcbbbefa32ee15ccc5041aad895a44196aa1b 的 getVersion(String) 改写为构建快照版本查询；保留并出货固定 Loader 的 8 类纯 Version/SemanticVersion/解析与异常闭包，经常量池/调用审计仅依赖 JDK 值操作，无 Loader 生命周期/类发现/IO。Residue 与代码审核仅豁免这 8 个固定值类型，仍拒绝其它运行时 Loader 行为。第一方 JVM 回归确认快照文本/比较、纯解析不被 stub、缺失 id 明确失败，PASS。pack-59 完整复验中。

pack-59 版本查询已越过，F1 出现；下一处 Sodium `ConfigManager.registerConfigs` 报核心配置未找到，根因是 collectConfigEntryPoints 因 getProvider→metadata→id 被 residue 清空。现在容器保存声明者 id，将该只读链折叠为 providerModId；保留 getEntrypoint/getDefinition 两个已实现的只读接口调用。按固定 Sodium ConfigLoaderFabric 指纹 13cb0cc07040be08158ab8cd53992f519d1430bcd40574bd651c93362efa2cfd，将 getModMetadata(String) 接到真实 name/version 快照，原核心与第三方配置注册代码继续执行，不跳过 Sodium。

已核对 Loader 0.19.3 EntrypointContainerImpl 的延迟创建：容器查询仅记录索引/定义/id，实际 getEntrypoint 时才调用预编译的缓存工厂；Kotlin INSTANCE 同样延迟读取。第一方 JVM 回归验证查询不初始化、实例身份、真实 owner id 和 Sodium 元数据值 PASS。日志中的非致命 HashedFingerprint record Gson getter 缺失由配置扫描器对 Record 类型补 allDeclaredMethods 解决，新增回归通过。尚不提供完整运行时 ModContainer/文件系统 API。pack-60 完整复验中。


## 真实路径优先与图像堆预算（2026-11-11，pack-60 → 61）

设计约束：**每修掉一个闭世界缺口，就有一批原先被 residue stub 剪掉的 Mod 真实代码重新进入可达集**。这会让镜像堆单调增长，不能靠把入口/配置注册重新 stub 回去来压内存——那等于用假路径换构建成功，违反 §5 判据和 `AGENTS.md` 的 Gate 规则。资源预算属于构建机，不属于运行期语义。

- 观测口径：AOT 分析是否 OOM 只看 `aot/*/product/analysis/stderr.log` 与 `work/gc.log` 的 Full GC 后 live old-gen；`-Xmx` 与 old-gen 容量不是一回事。pack-59 成功时 live 4.05GB，pack-60 失败时 5117M/5438M 老年代全满且连续 25 次 Full GC，RSS 6.50GB，属真实输入膨胀而非瞬时压力。
- 归因顺序：`fabric/*/product/result.json` 的 `transform.stubbedMethods` / `staticAdaptations` / `queriedEntrypointStages` → `work/reflection-config.json` 差异 → metal jar 大小。pack-60 三者分别 97→88、208→212、6→7，反射配置仅 1 条 record 方法注册新增，metal jar +5,122 字节，因此增长来自 Sodium 真实注册链重新可达。
- 处置：`tools/mcfao.py` 的 `--heap-gib` 从 7 提到 8；`tools/probe_client_graph.py` 的预检保持不变（choices 6/7/8，堆 ≤ 0.50×物理内存，8GiB 时 free ≥45%，磁盘 ≥8GiB），`hostMemory.heapLimitGiB` 会写进每轮 result.json 可审计。8GiB 不是放松验收，它只是让真实代码路径在 18GiB 构建机上完成闭世界分析。
- 若后续再 OOM，先做调用树/可达性归因，再考虑缩减分析输入或分批；**不得**回退 Mod 入口、配置注册或世界回调的真实执行。


## 事件总线的类型反射同样要在构建期折叠（2026-11-11，pack-61 → 62）

GlitchCore `EventManager.addListener(Consumer<T>)` 用 typetools 从 `consumer.getClass()` 反推泛型参数 T。四个 BiomesOPlenty 监听器是隐藏 lambda 类，一个是具名 `Consumer<RegistryEvent>`；闭世界镜像既没有这些类的泛型 Signature，也没有可供 TypeResolver 抓取的常量池，于是 `getEventClass` 返回 `Unknown` 并抛 `IllegalStateException`，整条事件总线在第一个 Mod 初始化时终止。这与 Mixin Args、Loader 版本查询是同一类问题：**运行期靠反射读取类型元数据的框架，在闭世界里必须换成构建期已知的常量**。

- 信息来源必须可审计：lambda 取 `LambdaMetafactory` 的 `instantiatedMethodType`（`(TEvent;)V`），具名类取 classfile 的 `Signature` 属性 `Consumer<TEvent;>`；两者都只接受 `glitchcore/event/**` 下的真实事件类（含 `RegisterColorsEvent$Block` 这个嵌套事件类），不猜泛型、不按类名前缀匹配。
- 调用点改写：在 `invokestatic addListener` 前压入 `LDC Class<TEvent>`，改为调用新增的 `addListenerResolved(Consumer, Class)`。该方法是原 `addListener` 方法体的克隆，只删掉开头的 `aload_0 / invokestatic getEventClass / astore_1`：原 slot 1 就是解析出的 `Class`，新第二参数落在同一槽位，后续指令、栈帧、异常表和局部槽全部保持原样。**不替换事件总线、不跳过注册、不改变监听器顺序**。
- 指纹与失败边界：EventManager / RegistryHelper 的原始 JAR 类字节 SHA-256 不匹配即拒绝；既不是 LambdaMetafactory 调用点也不是受审计具名 Consumer 的形状精确报错，避免悄悄把未知 Mod 的监听器丢掉；每个被改写方法 `maxStack` 补 1 槽（直线注册方法原本只有 1 槽，压入 Class 后需要 2）。
- 回归口径：第一方 JVM 探针构造一个 `getEventClass` 直接抛异常的 EventManager，实际 `defineClass` 改写后的类并注册两类监听器、执行一次回调、断言事件 key 正确且反射路径未被调用；同时覆盖指纹负例与未知形状负例。静态 `javap` 比对只是辅助，不能替代真实加载。
- **克隆方法体必须重算栈帧**：pack-63 的 `--verify-members` 报出 `Stack map does not match the one at exception handler 87`。相对 StackMapTable 帧以方法入口 implicit frame 为基准，参数个数从 1 变 2 后，复制来的 `F_APPEND`/`F_SAME` 全部错位。因此 `AotExport` 只对被改写的 EventManager 用 `ClassWriter(COMPUTE_FRAMES|COMPUTE_MAXS)` 输出，其它类保持 `ClassWriter(0)` 不动：既修帧，又不让全量字节码重写掩盖其它改写。探针里的 `RealManager` 是 javac 编译的 synchronized 方法，带真实相对帧，用来在 JVM 上复现并验证这条规则。
- 判据不变：核心类 `--verify-members` 的 VerifyError 必须回到 0 才进入模拟器；只通过默认类加载检查不足以放行。


## 字符串类发现（`Class.forName`）属于闭世界元数据（2026-11-11，pack-64 → 65）

Sodium 的 `DependencyInjection.load(Class<T>, String)` 把实现类全名当字符串传给 `Class.forName`，再用 `getConstructor().newInstance()` 构造。四个接口（`BlockEntityRenderHandler` / `SpriteUtil` / `VertexFormatRegistry` / `VertexSerializerRegistry`）的 `<clinit>` 都走这条路。类**在 classpath 上**不等于类**在镜像里**：没有静态引用，Native Image 不会为它建 `Class.forName` 查询表，运行期即 `ClassNotFoundException: ...VertexFormatRegistryImpl`，然后由 Sodium 的 Mixin 在 `VertexFormat` 构造时把整个渲染管线初始化拖崩。

- 处置优先保留真实语义：在 `compiler/reflection-config.json` 注册四个实现类及 `allDeclaredConstructors: true`。`Class.forName`、`isAssignableFrom`、反射无参构造全部继续执行，与桌面 Fabric 行为一致，不用 `new` 替换、不跳过注册表。
- 与 `META-INF/services` 的自动 `serviceProviders` 注册不同，这里是硬编码字符串，必须显式登记；改动后要同时确认原始 Mod jar 里确实存在同名 public 无参构造器，否则注册一个错误类只会把崩溃推后。
- 反射注册会让实现类的 `<clinit>` 与字段类型进入可达集（fastutil / StampedLock / slf4j 等），属预期增长；若后续堆预算吃紧，再考虑把 `<clinit>` 静态化为 `NEW Impl`，但那属于新的语义改写，需单独审计与回归。


## 出货的 Fabric API 声明必须构成闭世界闭包（2026-11-11，pack-65 → 66）

`AotExport` 把 Mod 入口派发生成成静态 `NEW` + `INVOKEINTERFACE` 序列。只要被派发的类实现了镜像里不存在的接口，该类就**整体不可链接**；Native Image 不会因此失败构建，而是在运行期把 `NEW` 变成 `NoClassDefFoundError`。XaeroLib / XaeroMinimap / XaeroWorldMap 的三个 client 入口类都额外实现了 `DedicatedServerModInitializer`，而这个接口不在原先手工维护的 `ModInitializer / ClientModInitializer / EnvType` 白名单里，于是三个类全部失效，客户端在 `Minecraft.<init>` 就终止。注意这与 `Class.forName` 字符串类发现（Sodium）不同：类本身和它的字节码都在 metal jar 里，缺的是它实现的一个**声明**。

- 处置口径：不再维护「猜哪些 API 会被用到」的白名单。`AotExport.fabricApiTypes()` 从固定 Loader jar 的 code source 枚举 `net/fabricmc/api/*.class` 全量出货，条目名与 `ClassReader.getClassName()` 逐一对应；这些类型是无状态接口与注解，不含 Loader 实例、类发现、反射或 IO，加入 classpath 不改变任何 Mod 的执行语义。变换报告新增 `pinnedFabricApi` 列出本轮补进的条目。
- 判据前移：构建后 `verify_aot_classpath.py` 的 failures 与 `fabric/*/product/result.json` 的 `transform.entrypoints` 做交叉核对，**不可加载的入口点必须为 0**。默认「核心类 0 失败」不足以放行，因为 Xaero 属于 Mod 类。pack-65 正是靠这次交叉核对在重新构建前确认只有 3 个入口点受影响、且同因。
- 回归边界：第一方 JVM 探针把 Fabric Loader jar 从定义类加载器上摘掉，只用导出字节定义一个双接口入口类并验证链接成功；这比 `javap` 看出货字节更接近 Native Image 的闭世界条件。任何将来把 API 集合改回硬编码、或换了 Loader 版本导致枚举为空，都会被该用例与 `fabricApiTypes()` 的非空自检挡下。


## 配置框架的反射元数据要按框架特征自动登记（2026-11-11，pack-66 → 67）

YetAnotherConfigLib v2 的每个配置类都暴露一个 `static ConfigClassHandler<...> HANDLER`，在 `<clinit>` 里用 `ConfigClassHandler.createBuilder(TheConfig.class)...build()` 初始化。`ConfigClassHandlerImpl` 在**这同一个 `<clinit>`** 里对配置类做 `getDeclaredConstructor()`、`getDeclaredFields()`，后续由 `ReflectionFieldAccess` 通过 `Field.get/set` 读写、Gson 反序列化。`YACLConfig` 自身有 public 无参构造器，缺的只是闭世界元数据；Native Image 把 `getDeclaredConstructor()` 变成 `NoSuchMethodException`，于是 `ExceptionInInitializerError` 在 `Minecraft.<init>` 阶段终止客户端。

- 与 Sodium 的 `Class.forName("...Impl")` 一样，这属于**框架的通用机制**，不是某一个 Mod 的缺陷。逐个把类名写进 `compiler/reflection-config.json` 会让包里每多一个 YACL 配置类就多崩一轮。
- 处置：`tools/config_reflection.py` 的 classfile 结构扫描扩展出「`<clinit>` + 字段描述符引用 `ConfigClassHandler`」这一框架特征（`yacl_config_roots()`），把识别到的配置类作为 `config_entries()` 的序列化根，复用既有的同包字段闭包与构造器/字段注册。扫描只读 classfile、不加载也不初始化 Mod；真实 metal jar 上命中 1 个类且无误报，`configurationReflection` 会随每轮 result.json 留下可审计清单。
- 判定依据来自出货字节：YACL 的 impl 包里出现 `getDeclaredConstructor` / `getDeclaredFields` / `getAnnotation` / `newInstance`，但**没有** `getDeclaredMethods`，所以不注册 `allDeclaredMethods`（Record 类型仍按原规则补）。避免为了「保险」把整个游戏图拖进反射注册。
- 既有教训继续成立：类在 classpath ≠ 类在镜像；闭包缺的是元数据而非代码，优先补齐元数据、保留框架真实路径，不要 stub 配置初始化。


## Mixin 插件的 onLoad 副作用必须在闭世界重放（2026-11-11，pack-67 → 68）

Fabric 的 `IMixinConfigPlugin.onLoad()` 在 Mixin 应用阶段由 Knot 调用，**早于所有 entrypoint**。本工程把 Mixin 变换前移到构建期、插件类不随镜像出厂，于是「插件在 onLoad 里初始化 Mod 静态状态」这一类设计会在运行期留下 null：ImmediatelyFast 没有 `main`/`client` 入口，全靠 `ImmediatelyFastMixinPlugin.onLoad → ImmediatelyFast.earlyInit()` 装载 `config` / `runtimeConfig` / `VERSION`；客户端一路走到 `RenderSystem.initRenderer` 才因 `Objects.requireNonNull(config, "Config not loaded yet")` 崩溃。这与 Indigo 插件（只做 `shouldApplyMixin` 布尔决定）不同：那个只需把决定折叠成常量，这个必须**在运行期重新执行一次真实的初始化**。

- 时序：`startClient` 先落 `GAME_DIR`，紧接着重放 early initializer，再按依赖序派发 `main`/`client` 入口。顺序对应 Fabric 的「Mixin 应用 → preLaunch → main → client」，且让配置目录查询（`Entrypoints.configDir()`）有值可用。
- 审计边界：只对固定 SHA-256 的两个原始类字节生效；插件 `onLoad` 里 `earlyInit()` 调用必须恰好一次，改版即精确报错。登记结果写进 `transform.earlyInitializers`，构建报告可查，不对未知插件做猜测。
- 配套的版本查询：residue 的 `getModContainer(query)=absent` 折叠对**动态 id** 是合理兜底，但 `earlyInit()` 用它读自己的版本会 `orElseThrow`。新增 `Entrypoints.optionalModVersion(String)`，按构建快照给 `Optional.of(真实版本)` / `Optional.empty()`；改写必须先于 `lowerQueries` 执行，否则通用 stub 会把钩子调用再压成 `Optional.empty()`。这是「折叠层次冲突」的一个实例，新增改写时要显式确认顺序。
- 不重放任何 Mixin 变换决策：那些已经在构建期体现在出货字节里。只重放插件对 Mod 运行时状态的一次性初始化，且保留 Gson 配置读写、runtime config 构造与兼容性检查的真实路径。


## 运行期生成字节码的库无法进入闭世界，必须按不兼容处置（2026-11-11，pack-68）

`net.lenni0451.reflect`（ImmediatelyFast 的 `META-INF/jars/Reflect-1.6.2.jar`）不是普通工具库：`accessor.FieldAccessor.makeGetter/makeSetter` 用 `BytecodeBuilder` 拼出 accessor 类的字节码，再经 `BuiltClass.defineMetafactory` 定义；`ClassLoaders.defineClass` / `accessor.InternalUnsafeAccess.defineClass` / `proxy.ProxyClassDefiner` 直接调 `Unsafe.defineClass`。`validateModCode` 把这些调用判为闭世界禁止项并排除整个 mod —— 这是正确判定，但下游必须处理「排除之后谁在用它」。

- 触发链：ImmediatelyFast 检测到 `iris` 后调用 `IrisCompat.init`，依次使用 `FieldAccessor.makeGetter` / `makeSetter` / `RStream.fields().by(...).get()`。库被排除 ⇒ `NoClassDefFoundError`；`IrisCompat` 的 catch 分支调用 `System.exit(-1)`，于是客户端在 `Minecraft.<init>` 直接结束，没有降级余地。
- 处置边界：这不是「补一个类」能解决的。`makeSetter` 的目标就是运行期造类，与 Native Image 的闭世界前提互斥。因此把它登记为 **pair 级不兼容**（Iris + ImmediatelyFast），jar 原样移入 `artifacts/mcfao/incompatible-01/` 并写 `result.json`（指纹、证据日志行、transform 报告定位、可重考条件），而不是把 `System.exit` 抹掉或伪造 `IRIS_LOADED=false`。将来若要支持，路径是构建期把 `IrisCompat` 的 `FieldAccessor`/`RStream` 调用降级为第一方 `MethodHandle`/`Field` 访问器，并给 `net.irisshaders.iris.vertices.ImmediateState` 注册字段元数据。
- 连带的、不影响进世界的缺口：ImmediatelyFast 的 `map_atlas_generation` mixin 会把 `net.lenni0451.reflect.Objects.allocate(DynamicTexture.class)` 合并进 `MapTextureManager$MapInstance.<clinit>`。`Objects` 本体不含 `defineClass`，但依赖 HotSpot 的对象布局常量（`KLASS_OFFSET`、`COMPRESSED_OOP_*`），在镜像里没有可靠语义；类缺失时表现为地图物品首次绘制时 `NoClassDefFoundError`。这条单独记入不兼容记录，不阻塞 Gate C。
- 判定经验：**「排除某个 Mod」不是终点，排除后要回头查还有谁静态引用它**。本次通过扫描出货 jar 里的常量池字符串（`lenni0451`）一次找出 4 处引用，其中 2 处是被 Mixin 合并进原版类的，靠读 transform 报告看不出来。

## 打包签名团队必须作为显式构建输入（2026-11-11，pack-68）

`ios/C0Harness/C0Harness.xcodeproj` 里 `DEVELOPMENT_TEAM = ""`（仓库不携带个人 Team ID），此前 `xcodebuild` 依靠已登录 Xcode 账户的隐式状态解析团队。同一条命令在 pack-67 解析到 `P57SZ9Z7G2`、在 pack-68 直接失败 `Signing for "C0Harness" requires a development team` —— 隐式状态不是构建输入，不可复现。

- 现在由 `tools/mcfao.py` 的 `resolve_development_team()` 决定：`MCFAO_DEVELOPMENT_TEAM` 优先（校验 10 位大写字母数字），否则解码本机已安装的 `.mobileprovision`（`security cms -D`），只接受 `application-identifier` 覆盖 `org.fabricaot.research.c0.kexin` 或通配、且未过期的描述文件，取到期最晚者的 `TeamIdentifier`；都没有时抛「No installed provisioning profile covers …」并提示两种补救方式。
- `device_xcode()` 把结果作为 `DEVELOPMENT_TEAM=<id>` 追加到 `xcodebuild` 命令行——命令行设置优先于工程里的空串，因此无需改动受版本控制的工程文件。`export_ipa()` 复用同一函数，archive/export 的团队与 build 阶段一致。
- 注意 `Build.step` 用 argv 做检查点键：团队解析结果变化只会让 `package` 阶段重跑，前七个阶段的 AOT/链接产物继续复用（本次 9m23s 的构建只补做了 `package`）。


## 堆预算第二步：Iris 移出后可达集涨到 9GiB 才装得下（2026-11-11，pack-69 → 70）

pack-61~68 在 8GiB 堆下稳定（Full GC 后 live ≈ 4.96GB，老年代容量 7.7~7.8G）。pack-69（第一个不含 Iris 的包）的 AOT 分析在 8GiB 下进入 **full-GC 死亡螺旋**：`Pause Full 7087M->7087M(7337M)`，每次都回收 0，单次 safepoint 停顿 8~15 秒，40 分钟没有任何进展。

- 判定它「不是泄漏」的依据：把全部 Full GC 的 live 值按时间排序是 5711M → 5963M → 7087M 后饱和，是可达集单调增长到顶，而不是每轮净增的失控；同时 `client-graph` 目录始终未生成，说明停在分析阶段。
- 为什么去掉一个 Mod 反而更大：`--initialize-at-run-time` 只覆盖 `net.minecraft`/`com.mojang`/`org.lwjgl`/`netty`，**Mod 自己的 `<clinit>` 仍在构建期执行**。Iris 在场时 Sodium/ImmediatelyFast 走的是「有 Iris」的分支，构建期不会实例化自己的完整渲染管线对象；Iris 移除后这些静态初始化走另一条分支，构建期实打实地造出更多对象。真实路径不能为了省内存再 stub 回去，所以只能加堆。
- 处置：`--heap-gib` 8 → 9；`tools/probe_client_graph.py` 的 choices 增加 9。硬上限仍是 **堆 ≤ 0.50×物理内存**：这台 18GiB 构建机上 9GiB 恰好等于上限（`>` 判定，不触发），所以 10GiB 不是「更保险」，而是会被预检直接拒绝——要更大就得换机器。free% 门槛在非 8GiB 档位仍是 35%，磁盘仍需 ≥8GiB。
- 复跑提示：`tools/probe_client_graph.py` 属于 `BACKEND_TOOLS` 指纹集合，改动它会让 `inputs.json` 与已有输出目录不匹配（`Build inputs changed. Use a new output.`）。这次必须换到新编号目录（pack-70），不能在同目录续跑。


## fabric 阶段可能跑两遍 Knot，超时要按两遍算（2026-11-11，pack-70）

`prepare_fabric_aot` 的流程是：Knot 变换 → `AotExport` 逐个类审计 → 若有类被 `validateModCode` 拒绝，写 `incompatible-1.json` 并把相关 Mod 从请求里去掉、**重新跑一遍 Knot**（因为合成 overlay 的结果必须由 Knot 重新产出），再合并 `client.jar`。所以一个「排除项只能在类审计阶段才发现」的包，`fabric` 阶段要跑 **两次完整 Knot**。

- pack-70 实测：第一次导出 23:24→23:28（约 4 分钟，报出 5 个不兼容库/Mod），重试 23:28→23:34（约 6 分钟，`client.jar` 已写出），但 `Build.step` 的默认 600 秒正好在这一刻到点，进程被 SIGTERM，日志尾部只有 `fabric failed (exit -15, timeout=True)`，产物看起来「已经好了」却拿不到检查点。pack-66/67/68 的同阶段只用 47~57 秒，是因为那些排除项在元数据解析阶段就被识别，没有触发重试。
- 处置：`mcfao.py` 里 `fabric` 阶段的 `timeout` 显式设为 1800 秒（两次 Knot + 余量）；AOT 阶段原本就是 3800 秒。
- 判据：不要用「`product/client.jar` 已存在」判断阶段成功——检查点只在进程正常退出且产物哈希齐备后写入，失败尝试的目录里可以留着看似完整的中间产物。


## 平台级不兼容：需要 OpenGL 的渲染器在 Metal 后端上没有路径（2026-11-11，pack-70 → 72）

Sodium 0.8.11 在模拟器里的崩溃点是 `liblwjgl_opengl.dylib` 加载失败，但缺的不是一个 dylib：

```
UnsatisfiedLinkError: Can't load library: .../Frameworks/liblwjgl_opengl.dylib
  at org.lwjgl.opengl.GL.<clinit>            <- Library.loadSystem("org.lwjgl.opengl", "lwjgl_opengl")
  at org.lwjgl.opengl.GL11C.<clinit>
  at ...sodium.client.compatibility.environment.GlContextInfo.create
  at RenderSystem.handler$dfb000$sodium$postContextReady
```

- `GlContextInfo.create()` 的字节码就是三句 `GL11C.glGetString(0x1F00 / 0x1F01 / 0x1F02)`（VENDOR / RENDERER / VERSION），随后 `Objects.requireNonNull`。
- `net.caffeinemc.mods.sodium.client.gl.device.RenderDevice.<clinit>` 无条件 `new GLRenderDevice()` 存进 `INSTANCE`；`RenderDevice.getCapabilities()` 的返回类型是 `org.lwjgl.opengl.GLCapabilities`；`SodiumWorldRenderer` 每个渲染层都走 `RenderDevice.INSTANCE.createCommandList()`，而它由 `LevelRenderer` mixin 每帧调用。Sodium 引用的 GL 入口覆盖 `GL11C`/`GL20C`/`GL30C`/`GL31C`/`GL32C`/`GL33C`/`GL40C`/`GL44C`/`ARBBufferStorage`/`KHRDebug`/`WGL`。
- 本工程没有 GL 实现：`compiler/metal-backend` 只实现 `com.mojang.blaze3d.systems.GpuBackend`（`MetalDevice`/`MetalCommandEncoder`/`MetalPipeline`/`MetalTexture`），`interop` 里没有任何 `gl*` 符号，`lwjgl-lite` 生成的 JNI 只覆盖 GLFW/STB/OpenAL（`artifacts/graphics/lwjgl-ios-world-01/graphics-jni.json` 21 条，无 `GL11C`/`glGetString`），模拟器 stage 也只铺 `libglfw/liblwjgl/libfaot_metal/libopenal` 四个 dylib。iOS 本身不提供桌面 GL（只有已废弃的 OpenGL ES）。
- 结论：这与 `Class.forName`、Mixin 重放那一类「闭世界元数据缺口」不同——类在镜像里、也能加载，缺的是一整个图形 API 实现。补 `unsafeAllocated`、加反射条目、写 stub 都不可能让 `glGetString` 返回有意义的值，更不可能让 `glDrawArrays` 画出东西。因此按 **platform 级不兼容**登记：`sodium` + 硬依赖它的 `sodium-extra` / `reeses-sodium-options` 移入 `artifacts/mcfao/incompatible-01/`，`result.json` 里 `level: "platform"`，`reconsiderWhen` 写明触发条件是「GL-on-Metal 翻译层」或「Sodium 提供纯 `GpuDevice` 后端」。
- 产品口径：**任何含 Sodium 的整合包在当前架构下都会被排除该项**，导入报告必须如实给出这条，而不是宣称「支持所有 Fabric Mod」。这一点写进兼容性报告，与 Gate D1 的「报告不兼容 Mod」要求一致。
- 顺带一条：`mcfao/aot/GenericVertexSerializer.java` 实现的是 Sodium 的 `VertexSerializer` 接口，Sodium 不在包里时 javac 会因缺包失败。`prepare_fabric_aot` 现在按 `RUNTIME_OVERLAY_MODS`（源码路径 → 必需 mod id）决定是否编译，跳过项记进 `result.json` 的 `runtimeOverlays.skipped`；`RuntimeLowering.replaceGeneratedSerializer` 按类名匹配，Sodium 不在场时本就不触发，无需改动。

## Gson 的类字面量可能只出现在 Mod 自己的包装器上（2026-11-11，pack-72 → 73）

pack-72 的崩溃点是 dynamic-fps 的静态配置：

```
ExceptionInInitializerError at dynamic_fps.impl.feature.volume.SmoothVolumeHandler.init
  -> DynamicFPSConfig.<clinit> -> Serialization.loadDefault
Caused by: IllegalArgumentException: Type dynamic_fps.impl.config.DynamicFPSConfig is instantiated
  reflectively but was never registered. Register the type by adding "unsafeAllocated" ...
```

- 字节码事实：`Serialization.loadDefault()` 是 `ldc class DynamicFPSConfig` + `invokestatic dynamic_fps/impl/util/JsonUtil.fromJson(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;`，`JsonUtil.fromJson` 内部才 `invokevirtual Gson.fromJson`，那里参数是 `aload_1`。**类字面量与 Gson 调用不在同一个类里**。
- 既有 `RuntimeLowering.collectSerializationRoots` 要求 `call.owner` 是 `com/google/gson/Gson` 或 `.../jankson/Jankson`，于是这个 Mod 的类从未成为序列化根 → 从未进反射配置 → Gson 找不到构造器 → 退到 `Unsafe.allocateInstance` → 闭世界拒绝。
- 修法一：判定改为「方法名 `fromJson`/`fromJsonCarefully` + 最后一个参数是 `Ljava/lang/Class;`」，不再要求 owner。Mod 包裹 Gson 并沿用同名方法是普遍写法，实测该放宽在 44 个根 mod 的包里只为 `transform.serializationRoots` 新增 **1** 条（`dynamic_fps/impl/config/DynamicFPSConfig`），没有过注册；反例（同名但尾参不是 `Class`、或尾参是 `Class` 但方法名不同）由 `interop/diagnostics/SerializationRootProbe.java` 钉住。
- 修法二：`config_reflection.class_shape` 现在记 `<init>` 描述符，`config_entries` 对**没有 `()V` 构造器**的选中类型补 `"unsafeAllocated": true`。这不是给某个 Mod 定制：Gson 的设计就是「先找已声明的无参构造器，没有就用 `sun.misc.Unsafe`」，而 `allDeclaredConstructors` 只解决前半段。`dynamic_fps` 的 `Config` 只有 6 参构造、`VolumeTransitionConfig` 只有 protected `(FF)`，这两个即便被登记也必然走 Unsafe 分支。
- 已知残留：只跟随一层包装器。若某个 Mod 用 `readConfig(Path, Supplier<T>)` 之类的非 `fromJson` 名字做中间层，本次修法抓不到，需要按日志逐例补静态条目。这条写在这里，避免下一轮误以为「Gson 已全自动」。

## Mod 按名字查游戏成员时，元数据得从字节码里挖（2026-11-12，pack-75 → 76）

Xaero 系列为了同一份 jar 能跨映射集工作，不用直接调用，而是
`ReflectionUtils.getMethodReflection(RenderType.class, "create", String.class, RenderSetup.class)`
——`ObfuscatedReflectionFabric` 里就是一层 `Class.getDeclaredMethod`。闭世界默认**不导出任何成员
元数据**，于是这条查找抛 `NoSuchMethodException: net.minecraft...RenderType.create(String, RenderSetup)`，
而 `RenderType.create` 确实是 `public static` 的。报错形态与「方法真的不存在」完全一致，这会把人
推向错误结论（以为是 Mod 与版本不匹配）。

判定顺序（踩过的错路）：

| 假设 | 反证 |
| --- | --- |
| Xaero 版本不配 26.1.2 | `create` 在出货类里就是 `public static`，javap 可查 |
| 类没进镜像 | `verify_aot_classpath.py` 显示该类可加载、0 失败 |
| 反射配置没生效 | 配置里 43 条全是**配置类**条目，成员条目 0 条——本来就没有人登记成员 |

修法是一类缺口而不是一个 Mod：`tools/config_reflection.py` 增加常量→成员的配对扫描。

**扫描规则。** 只读 classfile，不加载也不初始化 Mod：

1. 预筛：类常量池里出现 `getDeclaredMethod` / `getMethod` / `getDeclaredField` / `getField` 任一
   字符串才走指令流。43-mod 包里 26,919 个类只有 **80** 个命中，整轮扫描 ~3 秒。
2. 遍历方法的 `Code`，维护最近 8 条 `ldc`/`ldc_w` 常量（class 字面量、String 常量）。
3. 遇到 `invokevirtual/static/interface`：方法名命中 `MEMBER_SINKS`，**或**返回类型是
   `Ljava/lang/reflect/Method;` / `Field;`（Mod 包装器的情况），就取「最近的 class 字面量 + 紧随其后
   的 String」作为 (target, member)。取「最近的一对」而不是「最后一个 class」是必需的：Xaero 的调用
   在名字之后又压了 `String.class`、`RenderSetup.class` 两个字面量，用「最后一个 class」会把目标错认成
   `RenderSetup`。
4. 调用即清空常量窗口，避免上一句的字符串配到下一次查找上。
5. 调用方过滤：`net/minecraft`、`com/mojang`、`java/`、`org/lwjgl`、`com/google` 等平台的自身反射不登记；
   只登记 Mod 代码发起的查找。
6. 目标过滤：只登记**本次出货 jar 里存在**的类，避免给镜像里没有的类型写配置。

**产出（43-mod 包实测）**：14 个目标 / 18 条成员，全部进入 Native Image 的 reflection config，
`probe_client_graph.py` 把这些写进 `result.json` 的 `reflectiveMembers`（可审计），配置条目本身仍走
既有 `configurationReflection` 清单。命中项里既有 Xaero 需要的 `RenderType.create`、`ModelPart.children`、
`LevelChunk.xaero_chunkClean`（mixin 加的字段），也有 ImmediatelyFast / ETF 之类通过同一个 util 取的
`AvatarRenderer.setupRotations`、`GuiGraphicsExtractor.innerBlit`。

**边界**：名字来自变量的查找（`clazz.getDeclaredMethod(name)`）不登记——编译期没有常量可挖；
`Class.forName("...")` 不在本轮范围（43-mod 包里 0 处使用）；`getDeclaredConstructor` 未纳入
（构造器元数据目前由 `config_entries` 的 `allDeclaredConstructors` 覆盖）。

## Mod 的 assets/data 不在 ResourceManager 里（2026-11-12，pack-76）

pack-76 冒烟里 Xaero 已经越过反射元数据，撞在资源上：

```
NoSuchElementException: No value present
  at Optional.get  <- OldFormatSupport.loadVanillaStates(OldFormatSupport.java:262)
```

那一行是 `Minecraft.getInstance().getResourceManager().getResource(xaeroworldmap:vanilla_states.dat).get()`。

**已确证的事实：**

| 事实 | 证据 |
| --- | --- |
| 文件在出货 jar 里 | `assets/xaeroworldmap/vanilla_states.dat`，144,468 B |
| 镜像里也注册了它 | `work/game-resources.json` 的 `assets/.*` 包含规则 |
| 运行期资源包只有 vanilla | 崩溃报告 `Resource Packs: vanilla`；正常 Fabric 实例会多出 mod 包 |
| 缺的是**所有** Mod 资源，不只是这一个文件 | 546 条 `Missing model for variant` 全是 Mod 命名空间（biomesoplenty 等），vanilla 模型无报错 |
| 构建期还报过 `Assets URL 'resource:/assets/.mcassetsroot' uses unexpected schema` | 出自 `VanillaPackResourcesBuilder.pushJarResources`，它只认 `file:`/`jar:` 的 code source URL |

**为什么 AOT 天然缺这一层**：Fabric 的 `ModResourcePackCreator` 遍历 `FabricLoader.getAllMods()` 的根路径建包，而闭世界里没有 Mod jar、没有 `ModContainer` 根路径，于是 pack 列表只剩 vanilla。这和 pack-74 的 `fetchModFile` 是同一类问题——**Loader 的「路径类信息」在闭世界里并不存在**，凡是用到它的功能都要另给名义数据源。

### 已落地：在 `build()` 单点扩命名空间（方案 1）

先把「vanilla 包到底从哪个根读」查清了，结论是不用动根：

| 检查点 | 反汇编结论（出货 `client-26.1.2-metal.jar`，`javap -c -p`） |
| --- | --- |
| `VanillaPackResourcesBuilder.build(PackLocationInfo)` | 唯一一次 `invokestatic java/util/Set.copyOf(Collection)Set`，紧邻前一条是 `getfield namespaces:Ljava/util/Set;` |
| `VanillaPackResources.getNamespaces(PackType)` | 直接 `return this.namespaces`，不区分 `CLIENT_RESOURCES` / `SERVER_DATA` |
| `VanillaPackResources.getResource(PackType, Identifier)` | `lambda$getResource$0` 用 `Identifier.getNamespace()` 在 `pathsForType` 的每个 Path 上 `resolve(ns).resolve(path)` 后判断 `Files.exists`，**完全不查命名空间集合** |
| `VanillaPackResources.listResources` | 同样走 `pathsForType` + `PathPackResources.listPath` |
| `MultiPackResourceManager` 构造器 | 对每个 pack 调 `getNamespaces(PackType)`，只为返回的集合建 `namespacedManagers` 索引；`getResource` / `getResourceStack` 查不到索引就直接返回空 |
| `ClientPackSource` / `ServerPacksSource` | 分别 `exposeNamespace("minecraft","realms")` 与 `exposeNamespace("minecraft")`，最后都汇入 `VanillaPackResourcesBuilder.build()` |

所以文件本身**读得到**（vanilla 模型正常渲染就是证明），缺的只是索引条目。`build()` 是客户端与服务端唯一的汇合点，改它一次即可覆盖两条路径，无需自建 `PackResources`、无需注入 pack 列表。

实现（`RuntimeLowering.java` + `AotExport.java`，均为框架级，不含任何 Mod id）：

1. `RuntimeLowering.resourceNamespaces(Collection<String>)`：从合并 jar 实际出货的 `assets/<ns>/`、`data/<ns>/` 路径用 `^(?:assets|data)/([a-z0-9_.-]+)/` 提取命名空间，`TreeSet` 去重排序。`assets/.mcassetsroot` 这类标记文件不是目录，不匹配；大写/含空格的名字不是合法 Identifier 命名空间，也不匹配。pack-77 实测 **95 个**命名空间、28,683 条 assets/data 条目。
2. `RuntimeLowering.modNamespacesClass(...)`：生成 `mcfao.aot.ModNamespaces`，仅含一个 `private static final Set<String> NAMESPACES`（`<clinit>` 用 `Set.of(String...)` 构造）与 `public static Set<String> withVanilla(Set<String>)`（合并后 `Set.copyOf`）。整张表是镜像构建期常量，运行期无反射、无类加载、无资源查找——正是闭世界提供不了的三件事。
3. `RuntimeLowering.lowerVanillaPackBuilder(...)`：把 `build()` 里那一次 `Set.copyOf(namespaces)` 改写成 `ModNamespaces.withVanilla(namespaces)`（`INVOKESTATIC` 指向普通类，`itf` 必须置 0）。要求**恰好一处**匹配，多一处/零处/前驱不是 `getfield namespaces` 都直接构建失败，避免上游改版后静默失效。
4. `AotExport`：客户端类循环里即使 Mixin 未改动该 builder（`before == after`）也强制处理它；从 base client jar 与 `pendingResources` 收集出货路径，生成类写入 `overlay.jar`，并把 `resourceNamespaces` 写进 `transform.json`。同时断言 `gameTransforms` 里确实有这条改写，否则拒绝出包——防止生成一张没人调用的孤儿表。

`merge_client()` 不需要改：`gameTransforms` 已把该 builder 登记为「已声明的变更」，覆盖原版条目是允许的。

**为什么不选另两条路**：方案 2 要自己实现 `PackResources` 并插入 `PackRepository`，得复刻 `pack.mcmeta`、优先级、metadata section 等语义，却在「文件已经能读」的前提下只是补一个索引条目，改动面大一个数量级。方案 3 是死路——`--assetsDir` 指向 objects/indexes 对象库（`artifacts/graphics/game-assets-01/assets`），不是 `assets/<ns>/...` 命名空间树，往里丢 Mod 文件不会被 `getResource` 命中。

**回归**：`interop/diagnostics/ModNamespacesProbe.java` 对合成 builder 与**真实的 `26.1.2.jar`** 都做改写+字节码校验，并反射加载生成类验证 `withVanilla` 的并集、去重与不可变性；`tests/test_runtime_lowering.py::test_mod_resource_namespaces_reach_the_builtin_pack` 跑它。这样上游 Mixin 或 Mojang 改了 `build()` 形状，会在 1 秒内失败，而不是等 30 分钟 AOT 后才发现。

**仍然的边界**：这是单层合并资源包，没有 Mod 资源包优先级（`transform.overriddenResources` 记录覆盖原版文件的条目）；`resource:/assets/.mcassetsroot uses unexpected schema` 警告来自 `pushJarResources` 只认 `file:`/`jar:` 的 code source URL，与命名空间无关，属良性。

**pack-77 验证（2026-11-12）**：修复随 `SIGNED_DEVICE_APP` 构建出货；冒烟 F1 稳定，Xaero `Optional.get` 崩溃与 546 条 `Missing model for variant` 全部消失，资源重载进入 `ModelManager.loadBlockModels` → Fabric model loading API → mrcrayfish `OpenBlockModel` 反序列化——即 Mod 模型 JSON 已按命名空间索引真正取到并开始解析。下一个阻塞升级到别处（见下节）。

## `Class.forName` 的目标名可能在字节码里根本不存在（2026-11-12，pack-77 → 78）

pack-77 的崩溃链：`ServiceLoader` 实例化 mrcrayfish `FabricClientHelper` → 其 `<clinit>` 调 `createBlockElementDeserializerInstance()` → `Class.forName` 抛 `ClassNotFoundException: net.minecraft.client.resources.model.cuboid.CuboidModelElement$Deserializer`，把 `ClientServices.<clinit>` 连锁炸掉，整个资源重载 CompletableFuture 失败。

反汇编 `FabricClientHelper` 后确认目标名是**运行期拼出来的**：

```
ldc        class CuboidModelElement          // 类字面量，只有外层类
invokevirtual Class.getName                  // "net.minecraft...CuboidModelElement"
invokedynamic makeConcatWithConstants        // 配方 "\u0001$Deserializer"
invokestatic Class.forName(String)           // ← 字节码里没有任何一处常量等于目标名
invokevirtual Class.getDeclaredConstructor()
invokevirtual Constructor.newInstance()
```

pack-64 的字符串类发现（`tools/config_reflection.py` 的 `member_sites` + 字符串常量）对这种形态全盲：既没有 `ldc "完整类名"`，也没有嵌套类的 `ldc class`。而闭世界的 `Class.forName` 只对注册进反射配置的类回答按名查找——类本身在出货 jar 里（`CuboidModelElement$Deserializer.class`，9753 B）没有任何帮助。

**通用修法（`tools/config_reflection.py`，框架级）**：

- `bootstrap_recipes(class_attributes, pool)`：解析 `BootstrapMethods` 属性，把「单占位符且占位符在开头」的 `makeConcatWithConstants` 配方折算成字面量后缀（`\u0001$Deserializer` → `"$Deserializer"`）。多占位符或内嵌常量的配方依赖运行期数据，不解析。
- `forname_sites(code, pool, recipes)`：状态机配对「`ldc class X` → `Class.getName()` → `invokedynamic`（配方后缀）→ `Class.forName`」，还原精确目标 `X + suffix`；同时覆盖普通 `ldc "fqcn"` 字面量形态（点号换斜杠）。参数来自变量的调用点跳过——没有任何常量可登记。
- `forname_entries()`：为命中的目标登记 `allDeclaredConstructors: True`（`Class.forName` 要类可见、`getDeclaredConstructor().newInstance()` 要构造器元数据，两者一条全包）。目标不在出货 jar 里则丢弃，与成员条目同一口径。
- `class_shape` 因此改为**延迟 Code 扫描**：先收集方法体的 Code 字节，等类级 `BootstrapMethods` 解析完再跑两个扫描器（配方属于类级属性，方法循环时还不存在）。
- 扫描提示词加入 `forName`/`makeConcatWithConstants`——注意这扩大了被扫描类的范围，顺手修掉 `_instruction_length` 对 `tableswitch` 头部长度（default+low+high = 12 字节）少算 4 字节的潜伏 bug；此前它从未被触发是因为 litematica 这类只含 `forName` 提示词的类不在旧扫描范围内。

在真实 43-mod 出货 jar 上新增 17 条注册：`CuboidModelElement$Deserializer`（本次崩溃点）、Xaero `WorldMap`/`XaeroMinimap` 会话类、ambientsounds、clothconfig `ConfigBuilder`/`AbstractConfigListEntry`、ferritecore `PlatformHooks`、kotlin 协程 `BaseContinuationImpl`/`StackTraceRecoveryKt`、twelvemonkeys webp reader 等——全是「不登记就会在运行期以 CNFE 面目出现的按名查找」。

**回归**：`tests/test_config_reflection.py::ForNameScanTests` 6 项——拼接形态解析、字面量形态、变量形态跳过、平台调用方排除、jar 级「在场才登记」、`tableswitch` 头长度。合成类文件由 `forname_bytes()` 直接构造（含真实的 `CONSTANT_InvokeDynamic` 与 `BootstrapMethods` 属性），不依赖 javac。

## Mod 自带着色器管线会让整次资源重载失败（2026-11-12，pack-79 → 80）

pack-78 首次进入 GUI 渲染循环后立刻死亡，pack-79 的 `[MCFAO_SHADER]` 插桩把链条钉死在着色器预算上：

```
ShaderManager.apply(reload)
  → GpuDevice.clearPipelineCache()                      // 缓存全清
  → for (RenderPipeline p : RenderPipelines.getStaticPipelines())
        MetalDevice.precompilePipeline(p)                // 任一失败即记录
  → 有失败：再 clearPipelineCache() + throw RuntimeException
  → 换新 CompilationCache
```

撞上的是 `malilib:pipeline/legacy/wireframe`（顶点/片元都用 `malilib:legacy_terrain`）。Metal 后端的着色器 bundle 是**构建期从原版源翻译**的（`tools/ShaderCatalog.java` 只枚举原版静态管线 + post pass + standalone 源，`ShaderIndex.key()` 用「顶点 id + 片元 id + defines」算 SHA-256），bundle 里没有这份程序 → `UnsupportedOperationException: Rebuild required`。资源重载半途抛出，缓存停在空中状态，下一帧 GUI 绘制即崩——**一个 Mod 的着色器把整个共享重载状态带走了**。

**修法：在唯一漏斗上做门禁，而不是给每个 Mod 补翻译。**

`RenderPipelines.register()` 是所有静态管线（原版与 Mod）进入 `PIPELINES_BY_LOCATION` 的唯一入口，因此把门禁钉在这里：

- `compiler/metal-backend/src/fabricaot/metal/BundledPipelines.java`（新增）：
  - `register(Map byLocation, RenderPipeline pipeline)` —— bundle 支持则照原语义 `byLocation.put(location, pipeline)`；不支持则**不注册**，打一行 `[MCFAO_SHADER] dropped pipeline <location> vertex=… fragment=… (no precompiled Metal program)`，仍把 pipeline 对象返回给调用方。
  - `supports()` 查 `ShaderIndex.key(pipeline)` 是否在 `fabricaot-shaders/index.json` 的 programs key 集合里。
  - **fail-open 两条**：`org.lwjgl.librarypath` 未设（注册早于图形目录公布）返回 `true`；index.json 读不出来返回 `null` → 放行全部。宁可退回原行为，也不能因为读不到 bundle 就把原版管线全丢掉。
- `interop/fabric/tool/mcfao/build/RuntimeLowering.java`：`lowerRenderPipelineRegister()` 把 `RenderPipelines.register` 的方法体整体换成三条指令 + `ARETURN`：

  ```
  GETSTATIC RenderPipelines.PIPELINES_BY_LOCATION : Map
  ALOAD 0
  INVOKESTATIC fabricaot/metal/BundledPipelines.register(Map, RenderPipeline)RenderPipeline
  ARETURN
  ```

  找不到 `register` 方法直接抛 `RuntimeException` 让构建失败（改写的契约不能被静默跳过）。
- `AotExport` 在导出循环里加 `pipelines` 触发位（原先这种类只被扫描不被改写），并把改写记进 `adaptations`。

**语义取舍**：被丢弃的 Mod 管线不会被 `ShaderManager` 预编译，失败被推迟到**它自己那次绘制调用**——那里只是一个 Mod 的渲染特性坏掉，不会连锁摧毁资源重载与 GUI。这正是本轮的验收目标：让整包穿过 GUI 进入世界，而不是让每个 Mod 的自定义着色器都能跑。

**回归**：`interop/diagnostics/PipelineGateProbe.java` + `tests/test_runtime_lowering.py::test_render_pipelines_are_gated_by_the_shader_bundle`——
`rewrite <client.jar>` 在合成类与**真实出货 `RenderPipelines`** 上各改写一次，校验 adaptation 恰好 1 条、方法体 4 条指令、首条读 `PIPELINES_BY_LOCATION`、委托给 `BundledPipelines.register`、ASM `BasicVerifier` 通过；缺 `register` 的类必须构建失败；`bundle <dir> known|open` 用自己写的 index 校验门禁决策（bundle 内的 key 放行、bundle 外拒绝、index 不可读时全放行）。

## 类分析型库把「没有元数据」读成「没有覆盖」（2026-11-12，pack-80 → 81）

pack-80 第一次在同一轮里拿到 `Dev joined the game` 与 F3，随后在同一秒崩溃：

```
java.lang.AssertionError
	at net.caffeinemc.mods.lithium.common.entity.EntityClassGroup.<clinit>(EntityClassGroup.java:41)
	at net.caffeinemc.mods.lithium.common.world.WorldHelper.getEntitiesForCollision(WorldHelper.java:45)
	at net.minecraft.client.player.LocalPlayer.resetPos(LocalPlayer.java:776)
```

`EntityClassGroup.<clinit>` 只是自检：`contains(Minecart.class, EntityType.MINECART)` 必须为真。判定实现是

```java
while (clazz != null && clazz != superClass && superClass.isAssignableFrom(clazz)) {
    try { clazz.getDeclaredMethod("canCollideWith", Entity.class); return true; }
    catch (NoSuchMethodException ignored) { clazz = clazz.getSuperclass(); }
}
return false;
```

这是**类分析**而不是成员调用：库用「反射能不能找到」当布尔事实，来给每个实体选优化路径。闭世界对未注册方法抛的 `NoSuchMethodException` 与「真的没写这个方法」在调用方看来完全一样，于是所有实体都被判成「没覆盖」——优化悄悄退化的同时，库自己的自检断言把客户端打死。

**修法：只登记库真正会问的覆盖声明，不改变它的判断逻辑。**

- `tools/config_reflection.py` 新增 `OVERRIDE_QUERIES`（`canCollideWith`、`canBeCollidedWith`、`canHitEntity`、`canBeHitByProjectile`、`isPickable`、`isPushable`、`onClimbable`）——这是本轮对 4 个 lithium 类（`EntityClassGroup`、`EntityClassGroup$NoDragonClassGroup`、`ProjectileEntityClassGroup`、`PushableEntityClassGroup`）里全部 `hasMethodOverride` 调用点的穷举。
- `override_entries(shapes)`：扫描结果里**声明了**这些名字的类才登记 `methods: [{"name": …}]`（不带 `parameterTypes` 即登记该名字的全部重载，正好对上 `getDeclaredMethod` 的签名匹配）。真实 43-mod 出货 jar：32 个类 / 58 条方法，含 `AbstractMinecart#canCollideWith`、`AbstractBoat#canCollideWith`、`AbstractWindCharge#canCollideWith`、`Entity` 自身的 `canCollideWith`/`isPickable`/`isPushable`。
- 没声明的类仍然得到真实的 `NoSuchMethodException`，父类链继续上溯——**语义与常规 JVM 完全一致**，只是把「元数据」补成了「字节码事实」。

**为什么不改成构建期查表替换整个 `hasMethodOverride`**：那需要生成 classname→method 表并改写方法体，收益是能回答任意名字的查询，代价是多一处可能悄悄改变优化决策的改写点。这里的查询名是有限且已知的（7 个），按名登记既小又可验证，也不需要新生成类。

**回归**：`tests/test_config_reflection.py::ReflectiveMemberScanTests::test_class_analysis_queries_expose_the_overrides_they_ask_about`——声明 `canCollideWith` 的类得到 `methods: [{"name": "canCollideWith"}]`，只声明 `tick` 的类不产生条目。

## 配置发现也走 `FabricLoader.getAllMods()`（2026-11-12，pack-81 → 82）

pack-81 拿到 F3 后，第一个玩家 tick 就崩：

```
java.lang.IllegalStateException: Config property is not linked yet
	at com.mrcrayfish.framework.api.config.AbstractProperty.get(AbstractProperty.java:100)
	at com.mrcrayfish.backpacked.inventory.ManagementInventory.getMaxEquipable(ManagementInventory.java:98)
	at net.minecraft.server.network.ServerGamePacketListenerImpl.tickPlayer(...)
```

mrcrayfish framework 的配置**不是注解扫描出来的，是从 Mod 元数据里读出来的**：

```java
for (ModContainer mod : FabricLoader.getInstance().getAllMods()) {
    CustomValue framework = mod.getMetadata().getCustomValue("framework");
    for (CustomValue entry : framework.getAsObject().get("configs").getAsArray()) {
        Class<?> type = Class.forName(entry.getAsString());      // 类名只存在于 JSON 里
        for (Field field : type.getDeclaredFields()) {
            FrameworkConfig annotation = field.getDeclaredAnnotation(FrameworkConfig.class);
            if (annotation == null) continue;
            list.add(Pair.of(annotation, field.get(null)));      // ← 每条配置一对
        }
    }
}
```

闭世界把 `FabricLoader.getAllMods()` 折叠成空集合（没有 Mod jar 可枚举），这条链第一步就断了：`FrameworkConfigManager.configs` 空 → 没有任何 `AbstractProperty` 被 `ConfigScanData.scan` 链接 → `proxy == null` → 第一次 `get()` 抛异常。这也解释了为什么 `Class.forName` 那一层即使补了反射注册也没用——枚举根本没开始。

**修法：把「Mod 元数据」换成「出货字节」，其余交给框架自己的代码。**

1. **导出期枚举**（`AotExport.collectFrameworkConfigs`）：在导出前的 Mod 根目录扫描里，凡是类文件含 `Lcom/mrcrayfish/framework/api/config/FrameworkConfig;` 的，解析其静态字段的 `RuntimeVisibleAnnotations`，取出 `id`/`name`/`readOnly`/`type`/`separator`（缺省值取注解类声明的默认：`readOnly=false`、`type=UNIVERSAL`、`separator='.'`）。本轮真实包只命中一个类、五个字段：`com.mrcrayfish.backpacked.Config` 的 `CLIENT`/`BACKPACK`/`PICKPOCKETING`/`WANDERING_TRADER`/`AUGMENTS`。
2. **生成常量表**（`RuntimeLowering.frameworkConfigsClass`）：`mcfao.aot.FrameworkConfigs.ALL` 在 `<clinit>` 里逐条 `Pair.of(new FrameworkConfigAnnotation(...), GETSTATIC <owner>.<field>)`，与框架原来的产物结构逐一对应；相邻的 `FrameworkConfigAnnotation` 是一个普通类，`implements FrameworkConfig` 实现五个成员加 `annotationType()`——注解在 JVM 眼里就是接口，这样不需要在闭世界里合成注解实例，也不需要 `field.get(null)`。
3. **改写唯一入口**（`RuntimeLowering.lowerConfigDiscovery`）：`FabricConfigHelper.getAllFrameworkConfigs()` 整体换成 `return FrameworkConfigs.all();`，连带那两个做反射的 lambda 变成不可达代码被裁掉。框架的 `ConfigScanData.scan` / `initProperty` 一行不改，所以配置文件的读写、`ConfigType` 分派、同步逻辑全部保持原样。
4. **补字段元数据**（`tools/config_reflection.py::framework_config_entries`）：`scan` 用 `getDeclaredFields()` 遍历配置对象及其嵌套组，导出期把命中的根类写进 jar 内 `META-INF/native-image/mcfao/fabric/framework-config-roots.json`，AOT 准备阶段据此为「根类 + 所有 `$` 嵌套类」登记 `allDeclaredFields`。只登记字段：这条链只读字段，从不构造、也不调用。

**回归**：`interop/diagnostics/ConfigDiscoveryProbe.java` + `tests/test_runtime_lowering.py::test_framework_configs_are_discovered_without_the_loader`——生成的表必须为每条记录构造一个注解实例、`GETSTATIC` 一次配置字段、走 `Pair.of`，且 id/name/type/separator 与传入值一致；`all()` 只能读常量；真实出货 `FabricConfigHelper` 的 `getAllFrameworkConfigs` 改写后必须只剩一次表调用并通过数据流校验。Python 侧 `tests/test_config_reflection.py::test_framework_config_groups_register_their_field_metadata` 校验根类与 `$` 嵌套类拿到 `allDeclaredFields`、无关类不受影响。

**pack-82 的一次空转（值得记）**：表与注解类都按预期生成、`framework-config-roots.json` 也进了包，但出货的 `getAllFrameworkConfigs` 仍是 `List.of()` 循环、两个 lambda 还被压成空体——改写挂错了循环。`AotExport` 里有**两段**类处理：先是基础客户端 jar，再是按 Mod 逐个遍历的循环；`FabricConfigHelper` 属于后者，而第一段的 `configHelper` 分支只对基础 jar 生效。更关键的是顺序：Mod 循环里 `lowerQueries` 会先把 `getAllMods()` 折叠成空集合、把反射 lambda 压成 residue stub，所以表改写必须排在 `lowerQueries` **之前**。判别方法很直接——`fabric` 报告的 `staticAdaptations` 里没有 `FrameworkConfigs.all()`，就说明改写没进字节码，别等冒烟。

## Gson 配置类的「构造器 + 字段」两半都必须登记（2026-11-12，pack-83 → 84）

pack-83 在 F1 / `Dev joined the game` / F3 齐现之后 11 秒崩在实体 tick：

```
java.lang.NullPointerException: Ticking entity
	at traben.entity_texture_features.config.ETFConfig.canDoCustomTextures(ETFConfig.java:98)
	at net.minecraft.world.entity.animal.squid.GlowSquid.modify$zen001$entity_texture_features$mixin(...)
```

取证只有一步：模拟器的 `config/entity_texture_features.json` 是 **2 字节的 `{}`**（同一批里 `etf_warnings.json`、`modmenu.json`、`transition.json`、`trender.json` 也是空的）。反汇编第 98 行是 `entityRandomOverrides.isEmpty()`，该字段在构造器里赋值，而 `TConfigHandler` 的构造器确实执行过 `supplier.get().getClass()`（否则拿不到 configClass）。所以现场是「对象存在、字段为 null、构造器没跑过」——Gson 用 `Unsafe.allocateInstance` 建的对象。

两个方向一起坏，且都是**缺元数据**：

| 方向 | 需要的元数据 | 缺失后的表现 |
| --- | --- | --- |
| 写出（`Gson.toJson`） | `getDeclaredFields()` | 静默写出 `{}`，配置项全部丢失 |
| 读回（`Gson.fromJson`） | `getDeclaredConstructor()`（否则 `Unsafe`） | 全字段 null 的实例，第一次解引用就 NPE |

`RuntimeLowering.collectSerializationRoots` 抓不到这两个 Mod，因为它是「方法名 `fromJson` + 最后一个参数是 `Class`」的形状：

- ETF：`TConfigHandler.fromJson(String)` / `fromJson(FileReader)` 根本没有 `Class` 参数，类型是构造器里 `getClass()` 拿的；
- NoChatReports：`JSONConfig.loadConfig(Class, Supplier, String)` 的尾参是 `String`，`Class` 在**第一个**参数位。

所以在 `tools/config_reflection.py` 加了第二条腿 `json_config_roots()`，只看结构、不看类名清单：

1. **同类里既有 `X.class` 字面量又有 `X::new` 工厂句柄** —— 调用方同时给了类型和默认值工厂，这就是「Gson 装载器」的形状；命中的是 NoChatReports 三个配置和 CreativeCore 的 8 个包类。
2. **声明了 `Ltraben/tconfig/TConfigHandler;` 字段的类，它造的每个工厂目标都是配置类** —— ETF 的 `CONFIG`/`warningConfigHandler` 都是从 `ETF` 里 `X::new` 传进去的。

命中的根交给现成的 `config_entries()` 传递闭包（父类 + 同包字段类型），统一登记 `allDeclaredConstructors` + `allDeclaredFields`；没有 `()V` 构造器的类型仍按 pack-73 的规则补 `unsafeAllocated`。43-mod 包上新增 13 个根、反射条目 133 → 142。

**顺带修掉一个静默缺陷**：`class_shape` 的常量池解析对 `CONSTANT_MethodHandle`（tag 15）只 `take(3)` 跳过、不写 `pool`，于是所有 `X::new` 句柄对扫描器都是 `None`。`bootstrap_recipes`（字符串拼接配方）不需要句柄，所以这个洞一直没暴露；一旦要判断 `REF_newInvokeSpecial` 就完全失明。现在按 `(15, reference_kind, reference_index)` 保存。

诊断提示：`transform.serializationRoots` 里没有某个 Mod 的配置类，不等于它不用 Gson——先看它背后是「`fromJson` 包装器」还是「handler + supplier」形状，再去对应的一侧加规则。

## 逐 Mod 的运行期证据只能由框架自己打印（2026-11-12，pack-87 → 88）

pack-87 首次整包进世界（`SIMULATOR_WORLD_SMOKE_PASS`）之后，兼容性矩阵立刻暴露出另一个空洞：114 个 `BUILD_PASS`、**0 个 `LOAD_PASS`**。`LOAD_PASS` 的定义是「运行期入口点派发完成、该 Mod 初始化未抛异常」，证据要求「模拟器 `game.log` 中该 Mod 的初始化标记」——但日志里几乎没有这种标记。

扫一遍 1290 行日志，只有 7 个 Mod 会留下能对上号的自述：`backpacked`（`Registered synced data key backpacked:...`）、`jade`（`Start loading plugin from : snownee.jade...`）、`ias`、`terrablender`、`fabric-renderer-indigo`（`[Indigo] Registering...`）、`immediatelyfast`、`biomesoplenty`（区域注册）。其余 112 个是静默的——它们要么不打日志，要么只在出错时打。

根因不是 Mod 安静，而是**派发者换了人**。真机上 Fabric 的 `EntrypointUtils.invoke` 会留下痕迹；闭世界里 `Knot` 整个不参与运行，派发由导出器生成的 `mcfao.aot.Entrypoints.startClient` 重做，它只 `NEW` + `invokeinterface`，一句话都不说。于是「Mod 的初始化跑没跑」在证据层面是不可知的。

修法是把打印放进派发循环，且**必须放在回调返回之后**：

```java
start.visitMethodInsn(INVOKEINTERFACE, entry.type(), entry.method(), "()V", true);
emitEntrypointDispatched(start, entry);   // 只有返回了才会执行到这里
```

这行 `[MCFAO_ENTRYPOINT] mod=<id> stage=<main|client> class=<definition>` 的存在等价于「该 Mod 的初始化方法跑完了」：抛异常的初始化器永远走不到打印，而它一抛就是启动中断，不会产生「半条证据」。放在调用之前就成了「开始派发」，语义完全不同。

消费侧 `tools/scan_mod_evidence.py` 按四级可信度取证据，只认 `INFO`/`STDOUT` 级别：

| 级别 | 形状 | 例子 |
| --- | --- | --- |
| `class` | 入口点类名或包名出现 | `snownee.jade.addon.core.CorePlugin` |
| `name` | 显示名按原大小写出现 | `Initialized TerraBlender biomes` |
| `namespace` | Mod id 被当命名空间/前缀用 | `backpacked:selected_backpack`、`[Indigo]` |
| `id` | 裸 id 出现在散文里 | `Builtin shader registered` —— **不算证据** |

最后一级是必须的：`shader`、`sit`、`transition` 这类 id 会被普通英文句子命中，把它们当证据会让矩阵自己骗自己。品牌词（含内部大写或长度 ≥10，如 `TerraBlender`、`immediatelyfast`）允许折叠大小写匹配，「首个字母大写 + 短词」（`Shader`）不允许。

还有一类 Mod 永远拿不到这条证据：**没有入口点的资源包型 / 纯 Mixin 型 Mod**（`fabric-api` 的各个子模块、Kotlin 运行时等）。它们只能靠功能观察升级，不要为了让矩阵好看去给它们编 `LOAD_PASS`。
