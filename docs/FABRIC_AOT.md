# Fabric AOT 适配器

## 固定边界

当前实现面向 Minecraft 26.1.2、Java 25、Fabric Loader 0.19.3、Sponge Mixin 0.8.7 和官方未混淆命名空间。版本与构建引擎指纹来自 [Fabric 锁定文件](../compiler/fabric.lock.json)。Loader 内部导出接口按该版本固定，升级 Loader 时须重新验证。

| 环节 | 当前行为 | 验证方式 |
|---|---|---|
| 发现与解析 | ZIP 检查先限制展开大小、递归深度和成员路径。使用真实 `ModMetadataParser` 读取根 JAR 和声明的嵌套 JAR。 | `--prepare-only` 的 `result.json` |
| 依赖与环境 | 审计过的构建使用真实 Knot 初始化，交给 Loader 做客户端环境过滤、嵌套发现、版本匹配和依赖排序。 | `knot/stdout.log` 和 `transform.resolvedMods` |
| 字节码转换 | 在 Knot 的最终字节接口读取客户端及选中 Mod 的类。沿用上游游戏入口 patch、Fabric 环境和 Class Tweaker 转换及 Mixin 的执行顺序。以 ASM `BasicVerifier` 检查导出的类。 | `transform.gameTransforms` 保存变换前后 SHA-256。Native Image 继续验证实际可达类。 |
| 入口 | 从 Loader 的实际 Entrypoint 容器读取 `main`、`client` 的顺序和实现。把 Loader 注入的启动点重定向到生成的 Java 字节码，运行时直接构造并调用公开无参 Java 入口。 | `transform.entrypoints` 与实际客户端日志 |
| 资源和初始化 | 将无冲突的 `assets/`、`data/` 并入客户端，生成精确资源 glob 和 Mod 类的运行时初始化选项。Mixin 定义留在构建期，镜像含上游回调类型。 | `META-INF/native-image/mcfao/fabric/`、Native Image 日志、夹具实际资源读取 |
| 原生后端 | 适配器交付一个已封闭的客户端 JAR。与原版共用方法拆分、Metal 注入、Native Image、iPhoneOS 链接和签名。 | `inputs.json`、各阶段 `command.json`、签名包的 `result.json` |

桌面 Knot 在 `FabricLoaderImpl.load/freeze` 解析 Mod，安装 Class Tweaker 和 Mixin 后准备类加载。闭世界镜像把最终类放入分析输入，镜像运行时使用固定入口与回调。真实 Loader 的发现和入口选取发生在构建期。完整 Loader 公共 API、动态 ClassLoader 和任意入口查询仍需独立的运行时适配。

## 第一方游戏夹具实测

- F1 的 `ClientModInitializer` 由真实 Loader 发现。模拟器 AOT 客户端实际执行入口并校验 `assets/mcfao_fixture/proof.txt`。 [运行日志](../artifacts/mcfao/fabric-simulator-02/game.log)
- F2 反汇编确认 `Minecraft#setLevel` 调用 Mixin 生成的处理方法。F3 通过同一处理方法在单人世界实际触发 `GameMod.onWorldJoined`。服务器玩家登录、Mod 回调和渲染画面均已采集。`getVersionType` 只核验了转换后的字节码。 [反汇编](../artifacts/mcfao/fabric-bytecode-02/stdout.log) · [烟测结果](../artifacts/mcfao/fabric-simulator-02/result.json) · [世界截图](../artifacts/mcfao/fabric-simulator-02/world.png)
- 设备目标由同一 AOT 对象单独链接。开发签名 IPA 已验签并核对指定 iPhone 的描述文件覆盖，运行仍待真机。 [IPA 清单](../artifacts/mcfao/fabric-ipa-02/result.json)

## 兼容边界

- `--prepare-only` 仅读取归档与元数据，最多检查 512 个根及嵌套归档并保留原有展开大小限制。元数据读取容许顶层描述内的字面换行，其他字段继续接受严格检查。报告汇总现有 AOT 限制。构建须显式指定 `--audited-mods`，先通过项目沙盒的外部文件读写和环回连接负例，再执行 Knot。D0 仍缺少面向任意第三方 Mod 的完整隔离验证。
- 支持官方命名空间下的公开 Java 类形式 `main`、`client` 入口。自定义语言适配器、`preLaunch`、旧式入口、方法引用形式和自定义入口阶段会被拒绝。当前静态入口在第一个异常时退出，异常聚合与上游仍有差异。
- 支持必需、无插件、无 refmap 的官方命名空间 Mixin 配置。Mixin 插件、父配置和自定义选择器超出范围。Class Tweaker 由真实 Loader 装载，本轮的游戏夹具覆盖 Mixin，既有 B0/B1 证据覆盖访问修改与嵌套依赖。
- 字节码检查对直接调用 `defineClass`、`defineHiddenClass`、`URLClassLoader`、运行时 Loader API、动态代理和原生加载，以及声明的 native 方法给出 Mod、类和方法位置。任意反射、方法句柄间接生成类、动态 JNI 和服务发现仍需单独验证。含 `META-INF/services`、自带 Native Image 配置或本地库的 Mod 当前会被拒绝。
- 当前资源仅覆盖无冲突的 `assets/`、`data/`，没有独立的 Mod 资源包优先级和 Mod JAR 文件系统语义。重名的类与资源会导致构建失败。

下一步是在同一物理 iPhone 上验证测试 Mod 的入口、注入和世界回调，再补静态 ModContainer/资源查找、可审计的反射和服务元数据，以及实际 Fabric API/整合包测试。版本和映射选择应在 Loader 适配层决定，原生后端继续接收已转换的输入。

实现依据见 [Fabric Loader 0.19.3 源码](https://github.com/FabricMC/fabric-loader/tree/0.19.3/src/main/java/net/fabricmc/loader/impl) 与 [GraalVM 25 Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)。
