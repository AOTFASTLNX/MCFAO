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

## 兼容边界

- `--prepare-only` 仅读取归档与元数据，最多检查 512 个根及嵌套归档；转换预算为 256 个归档，覆盖 Recollection3 本地实例解出的 53 个根与 168 个嵌套归档。两侧都保留原有展开大小限制。元数据读取容许顶层描述内的字面换行，其他字段继续接受严格检查。报告汇总现有 AOT 限制。构建须显式指定 `--audited-mods`，先通过项目沙盒的外部文件读写和环回连接负例，再执行 Knot。D0 仍缺少面向任意第三方 Mod 的完整隔离验证。
- 支持官方命名空间下的公开 Java 类形式 `main`、`client` 入口，以及 `Class::method` 形式的无参 `void` 方法引用。方法引用在构建期解析为静态或实例调用，运行时不经过 `MethodHandle`；签名不匹配或目标不存在会直接报错。自定义语言适配器、`preLaunch`、旧式入口会被拒绝。`modmenu` 阶段和提供者缺失的 `jei_mod_plugin` 阶段记录到 `optionalEntrypointsSkipped` 并跳过——封闭世界客户端里没有查询它们的代码。`jade`、`glitchcore`、`ebe_v1`、`sodium:config_api_user` 等由已打包 Mod 查询的阶段仍需单独支持。当前静态入口在第一个异常时退出，异常聚合与上游仍有差异。
- 支持必需、无 refmap 重映射的官方命名空间 Mixin 配置，包括 `plugin` 声明的 `MixinConfigPlugin`。插件是构建期钩子：真实 Knot 在镜像组装时执行它，运行时不需要该类存在。父配置、显式 injection points 和动态选择器仍超出范围，因为它们会改变 Mixin 生成哪些类。Class Tweaker 由真实 Loader 装载，本轮的游戏夹具覆盖 Mixin，既有 B0/B1 证据覆盖访问修改与嵌套依赖。
- `FabricLoader.getInstance().isModLoaded(String)` 的字面量查询在构建期折叠为常量；参数不是字面量时改写成生成的 `mcfao.aot.Entrypoints.isModLoaded` 成员测试，答案与构建期 Loader 一致。`isDevelopmentEnvironment`、`getEnvironmentType` 同样静态化，其它 Loader 运行时调用仍直接报错。
- 字节码检查对直接调用 `defineClass`、`defineHiddenClass`、`URLClassLoader`、运行时 Loader API、动态代理和原生加载，以及声明的 native 方法给出 Mod、类和方法位置。任意反射、方法句柄间接生成类、动态 JNI 和服务发现仍需单独验证。含 `META-INF/services`、自带 Native Image 配置或本地库的 Mod 当前会被拒绝。
- 当前资源仅覆盖无冲突的 `assets/`、`data/`，没有独立的 Mod 资源包优先级和 Mod JAR 文件系统语义。重名的类与资源会导致构建失败。

下一步是在同一物理 iPhone 上验证测试 Mod 的入口、注入和世界回调，再补静态 ModContainer/资源查找、可审计的反射和服务元数据，以及实际 Fabric API/整合包测试。版本和映射选择应在 Loader 适配层决定，原生后端继续接收已转换的输入。

实现依据见 [Fabric Loader 0.19.3 源码](https://github.com/FabricMC/fabric-loader/tree/0.19.3/src/main/java/net/fabricmc/loader/impl) 与 [GraalVM 25 Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)。
