# Fabric 玩法模组：通用适配路线

Last reviewed: 2026-11-14

## 本次故障的教训

TechReborn 6.0.5 首次直接 AOT 构建通过，但用户真机日志 `run-1794497870260.log:77–81` 在 RebornCore 客户端初始化失败。`getModContainer("reborncore")` 被 `RuntimeLowering` 换成空 Optional，紧接着的 `get()` 抛异常。此前成功的是代码生成，不是 Fabric API 语义保持；扫描得到的依赖完整也不能证明运行时接口完整。

目标应从“让更多 JAR 编译通过”转为“为固定 Mod 图实现有契约、可对照的静态 Fabric 运行环境”。每次只修一个 Mod 的调用点，无法带来广泛的一键适配。

## 本次实现范围

- `ModCatalog` 使用导出期真实 Loader 图生成的目录，按 ID 返回稳定容器；名称、版本、描述来自解析后的元数据。
- 查询替换保持 Optional 合约及调用者后续操作，未知 ID 返回空；已有 Mod 不再假报不存在。
- 每 Mod 的 assets/data/resourcepacks 保留独立路径并嵌入镜像；首次访问解出到独立临时目录，Fabric 原有内置包注册/枚举逻辑使用真实文件。包含目录穿越检查；不执行 JAR、不运行时生成类。
- 保留所需 Loader 元数据接口声明，避免 resource pack 方法被残留处理器置空。
- 尚不支持的容器源归属、父子关系、扩展元数据读取明确抛出异常；本次没有宣称整个 Loader API 完整。`getAllMods` 等历史空值处理尚待替换。临时根目录只供资源读取，不代表原始可执行 JAR。

## 广泛一键适配的实现顺序

1. **固定运行时 ABI**：一次性补齐 ModContainer/ModMetadata 的所有常用字段、依赖、别名、嵌套图、origin、custom values，以及 getAllMods 和入口点 provider 身份。不可把不支持映射成“没有”。每个接口有参考 Loader 与 AOT 快照的差分测试；构建后不得再依赖 Knot。
2. **完整资源模型**：基础包、可选内置包和启用顺序分别保留；验证 namespace、tags/recipes 合并、reload、字体、语言、模型以及 builtin pack 的实际可选/可启用行为。建立可寻址的只读资源层，控制磁盘、RAM 和重复拷贝预算。
3. **通用反射闭包**：从实际序列化/配置/注册机制自动生成精确字段、构造器、方法元数据；隔离桌面轨迹只是补充，不把“一次未触发”当安全证明。测试首次启动、配置重读、存档往返，避免仅修首次创建。
4. **事件和时序**：保持 Fabric callback、main/client 顺序、静态初始化与 reload 边界，测试配方、机器 tick、物品/流体/能源存储、联网序列化及持久化；初始化返回不能升级为功能通过。
5. **可扩展图形能力**：对新增 RenderPipeline/shader 自动做构建期翻译、资源绑定和 GPU 断言；直接桌面 GL、缺失 JNI/AWT 或运行时造类给出具体阻塞。不得靠丢弃 draw 宣称自定义渲染可用。
6. **自动验收闭环**：安全导入→图解析→能力报告→转换→闭包检查→AOT→模拟器功能场景→IPA。每类玩法用实际状态断言（机器耗能产出、管线传输守恒、GUI 操作、退出重进）；错误回指 Mod/版本/调用链/接口缺口。

## 必须优先改变的成功判据

- 将每次改写分类为“语义等价”“明确禁用的诊断/开发功能”“不支持”；生成机器可读报告。
- 玩法可达路径的空值/no-op residue 不得自动算兼容；无法证明等价时应阻止兼容状态升级，随后逐步收紧为构建失败。不能在整个包里静默去掉依赖 Mod。
- 验收分开：转换、代码生成、入口执行、玩法功能、真机复验。任何前一级都不自动代表后一级。
- 用多种独立实现的玩法模组检验通用能力，版本变化重新验证。兼容范围按机制与版本报告，暂不提供没有代表性样本支持的成功率。

“一键”指对已覆盖的机制自动完成构建和诊断；运行时生成任意类、桌面专用 native/GL 等仍是需要源码级移植的边界。不得承诺任意 Fabric 模组。

## 本轮验证结果

- `tests/test_mod_catalog.py`：已知/未知 ID、同 ID 同实例、名称版本、内置包文件读取、路径越界拒绝、未实现字段明确失败，以及查询字节码降级通过。
- 全套 285 项测试通过，日志 `artifacts/mcfao/techreborn-audit-01/interface-tests-02.log`。
- `techreborn-interface-build-01` 因逐文件 native 资源清单超过已有 2 MiB 限制停止；保留失败记录。改为资源目录 glob、不重复快照内置游戏资源后，`techreborn-interface-build-02` AOT、iPhoneOS 链接、签名成功；没有排除 TechReborn/RebornCore/能源库。
- 成员检查为 189/40317 不可加载（含缺失可选依赖，不能写成全 PASS）；RebornCore、能源库及 mcfao 运行时类无成员加载失败。Fabric `ModPackResourcesUtil` 仍有 FabricLoader 私有方法签名残留，需要后续收敛。
- `techreborn-interface-simulator-01/game.log:78–79` 明确记录 RebornCore 与 TechReborn client 入口正常返回；原 `Optional.get` 故障未再出现。随后完成纹理图集加载，在 MTLSimDriver/XPC 命令提交时 signal 6。模拟器世界冒烟未通过；新原生故障根因未确定，不把它归咎于 Mod，也不宣称整包可玩。
- 修复版真机尚未复验，机器功能及存档仍 NOT RUN。本次修的是查询/资源接口，不是完整 Fabric Loader 实现。


## 2026-11-13 通用接口扩展与样本集

`ModSnapshot` 现在保存 environment、provides、作者/联系人、许可、custom value 树、依赖谓词、图标选择边界和嵌套关系；`ModCatalog` 提供只读查询/枚举及入口点 provider 身份。PATH origin 指向本机提取的资源根，NESTED 保留逻辑父 ID/子位置，不嵌入宿主个人目录。资源根不是原始可执行 JAR；仅提供已打包的资源、描述和声明图标，不能作为完整 JAR 文件访问兼容性承诺。

与固定 Loader 元数据解析器的对照测试覆盖依赖 OR 匹配、custom null/嵌套值、图标边界、环境/别名/许可/联系人。`getAllMods` 改为构建图枚举；保留未支持残留方法的机器可读 `semanticCompatibility`（REQUIRES_REVIEW），不会将残留列表为空自动标为运行兼容。当前仍是报告门禁，不是默认严格拒绝所有残留；后续需按可达性与诊断白名单收紧。

TechReborn 的 catalog-expansion-transform-03 已通过隔离转换、未排除模组，并对 5 条残留方法报 REQUIRES_REVIEW；最终描述/图标资源闭包复验为 catalog-expansion-transform-04。新接口还未重做完整 AOT/运行验收。前一版真机修复 IPA 不包含本轮新增接口。

新增 [内容样本包](CONTENT_SAMPLE_PACK.md)：五个内容模组和全部当前解析出的必需依赖，目标版本预检通过，整包转换/运行未做。它提供后续扩展覆盖的固定输入，不能提升原有功能兼容矩阵。

## 2026-11-14 MDAF 首批自动化

AdaptationRuleEngine 为结构规则提供 ID、机制、目标、匹配、前置条件、变换和字节码后置验证；同一目标多规则冲突会报告并跳过，最多两轮并验证幂等性。当前首条规则 fabric.resource.merged-namespace-index.v1 按 VanillaPackResourcesBuilder#build 的目标方法及 Set.copyOf(this.namespaces) 调用形态匹配，将其改为 ModNamespaces.withVanilla，不依赖 Mod ID。规则前置条件/目标冲突以 Report-Only 跳过；变换失败或后置条件不成立会明确失败。

tools/mdaf.py 将人工反射配置、静态推断和 GraalVM tracing-agent 输出稳定合并，并保留其他受支持的 agent 元数据类别；反射类型与命名成员采用出货 classfile 静态检查，JDK 类型单独列出。标量配置冲突保留较早的人工值并记录冲突。tools/mcfao.py build --trace-agent --audited-mods 可在现有隔离的桌面 Knot 演练中收集轨迹；该选项必须与 --audited-mods 一起使用，之后轨迹目录会自动传给 AOT 配置准备。单独使用 probe_client_graph.py --tracing-config <目录> 可重复合并轨迹目录。轨迹只覆盖实际执行场景，不能证明动态访问闭包完整。

第一方夹具实跑证据：artifacts/mcfao/mdaf-fixture-audited-trace-01/result.json 显示 FABRIC_AOT_INPUT_PREPARED，文件/网络拒绝控制通过；该规则首轮改写 1 处，第二轮验证已应用且没有重复编辑。导出 classfile 与规则后置条件通过，但 jvmBehavioralRehearsal 为 NOT RUN。GraalVM 25 agent 收集到 635 条统一格式反射观察和 860 条资源观察，输出位于 artifacts/mcfao/mdaf-fixture-audited-trace-01/tracing-agent-attempt-1/reachability-metadata.json。合并报告 artifacts/mcfao/mdaf-fixture-aot-config-02/mdaf-report.json 检查 697 项：362 项在选定归档中解析，49 个类型未解析，1 项格式无效，285 个 JDK 类型未在归档中检查；合并冲突为 0。该报告中的完整 classpath 成员检查仍为 NOT RUN，对应 helper 目前只以独立小型 classpath 测试覆盖。

该转换演练没有运行游戏目标方法。样本同时记录 mixinAccessorsRefused 一项，诊断内容为 mcfao_fixture!mcfao/fixture/mixin/WorldMixin.class (null)；不能据此声称 Mixin 或资源行为兼容。未知 Fabric API 未做穷尽扫描，stub/no-op、Mixin、动态反射与平台差异继续 Report-Only。Native Image 完整 AOT、IPA、模拟器和真机验证均为 NOT RUN。相关回归：test_mdaf 7、test_mcfao 36、test_runtime_lowering 11、test_verify_aot_classpath 4、test_config_reflection 29 项均通过；这些结果只证明各自自动化检查通过，不提升可玩 Gate。
