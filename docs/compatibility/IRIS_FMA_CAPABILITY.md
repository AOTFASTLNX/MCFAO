# Iris 高级阴影剔除的可选 JVM 能力查询

Last reviewed: 2026-11-21

## 根因与实际输入

本轮沿用 COMPAT-r3 的本地已审计 Fabric 输入，Minecraft 26.1.2、Iris
`1.10.9+mc26.1.1`、Sodium 0.8.11、BSL 10.1.3，渲染仍为 GL41 / Zink / MoltenVK。
Iris 文件为 `iris-fabric-1.10.9+mc26.1.1.jar`，SHA-256
`aea0eefb174d19ad97a812b6de2e304f0d3abc50357b316908cf1035f1514b07`。
只读取用户本地输入，未下载替换版 Mod。

实际 r3 AOT classpath 中的
`net.irisshaders.iris.shadows.frustum.advanced.AdvancedShadowCullingFrustum`
与原始 Iris 中同名类的 SHA-256 一致：
`013cee87944a1a76fcab24fb1ad41bfcb91c910bc2ae70401fef19e737516c6a`。
其 `<clinit>` 无异常处理，查询 `HotSpotDiagnosticMXBean`，读取 `UseFMA`，
仅设置 `FMA_SUPPORT`。该字段只决定 `checkCornerVisibility` 使用
`Math.fma` 还是原有 `safeFMA(a,b,c) = a*b+c`。

固定 GraalVM CE 25.0.2 的上游源码
`substratevm/.../jdk/management/ManagementSupport.java` 注册有限的管理接口，
没有 HotSpotDiagnosticMXBean。`getPlatformMXBean` 对未注册接口抛出
`IllegalArgumentException`，因此 Iris 的类初始化失败。
本机 Native Image 原始字节码探针已复现相同异常，日志见下文。

## 实现与边界

- `interop/fabric/tool/mcfao/aot/OptionalJvmCapabilities.java` 返回 ENABLED、
  DISABLED 或 UNAVAILABLE。查询真实管理接口，只将 IllegalArgumentException、
  UnsupportedOperationException、SecurityException 视为可选能力不可用。
  其他 RuntimeException / Error 原样传播。
- `interop/fabric/tool/mcfao/build/OptionalJvmCapabilityLowering.java` 是 MDAF
  规则 `jvm.optional.hotspot-fma.v1`。它匹配确切类名、static final boolean
  字段和整个已审计初始化器的指令、操作数及分支目标，拒绝未知形态，
  只替换 `<clinit>`。后置检查和两轮收敛记录进入 transform.json。
- `AotExport.java` 在常规 Fabric 导出阶段调用规则，runtime overlay 自动
  包含 helper 与状态枚举。转换后的类 SHA-256 为
  `b1b99739546a331601d781e9fd57abd6a4e6960bcfbbc42a2838e3cf5dfc57ca`，
  Fabric overlay 和最终 GL41 AOT 输入一致。其余 22 个算法方法保持不变。
- 能力不可用时选择 Iris 自带的非 FMA 数学路径；没有改变高级阴影剔除、
  光影设置、Iris/Sodium 内容或 ManagementFactory 的标准实现。

规则 evidence 的哈希来自输入 class 文件，上文分别记录 JAR 和 class 哈希。

## 自动回归与复现

测试入口 `tests/test_optional_jvm_capabilities.py` 使用实际 r3 AOT classpath，
包含以下检查：

1. JVM 能力为 true、false、null，以及三类预期异常；意外异常传播，
   标准 MemoryMXBean 仍可查询。
2. 开启和关闭 JVM UseFMA，分别执行真实 Iris 算法，对 20,000 个确定性
   包围盒核验独立参考计算。FMA/非 FMA 的点积误差不超过按量级计算的
   8 ULP 容差，远离边界时分类一致，覆盖完全可见、不可见和相交。
3. 规则幂等性、22 个算法方法字节保持一致，以及选项变更、额外指令、
   错误类名和反向分支四类拒绝样本。
4. 原始与修复后 Native Image 可执行文件，前者必须复现原始异常，后者
   必须以 UNAVAILABLE / FMA=false 完成真实剔除算法。独立探针去除依赖
   内嵌的全游戏构建指令，保留所有有效类字节，强制运行期初始化，
   单独注册 JOML 四个 Java 版本探测方法的反射查询元数据。
5. 完整新构建的 AOT command classpath 必须包含实际修复类、helper 和
   枚举，且原算法方法与 r3 一致，transform.json 必须记录 APPLIED。

```sh
MCFAO_TEST_NATIVE_IMAGE=1 python3 -B -m unittest discover -s tests -p test_optional_jvm_capabilities.py -v
```

可用 `MCFAO_TEST_IRIS_BUILD` 指定原始 r3 构建，
`MCFAO_TEST_IRIS_FIXED_BUILD` 指定完成的新构建，
`MCFAO_TEST_IRIS_LOGS` 指定尚不存在的持久日志目录。
无本地受授权游戏输入时跳过依赖该输入的检查。
诊断夹具为 `interop/diagnostics/OptionalJvmCapabilitiesProbe.java`、
`OptionalJvmCapabilityLoweringProbe.java`、`IrisShadowProbe.java` 和
`IrisShadowOriginalProbe.java`。

对实际 classpath 的 53,746 个有效类进行管理接口调用及供应商接口引用扫描，
相关候选类只找到 Iris 和 FancyMenu
`PerformanceUtils#createOperatingSystemBean`。后者已有异常处理并返回 null，
本轮保留其实现。扫描结果记录调用者、所属 JAR 和具体描述符，
不将所有 JVM 管理查询作全局替换。
完整候选引用另存为 `logs/iris-fma-20261121/management-reference-candidates.json`。

日志目录为 `logs/iris-fma-20261121/`，包括原始/最终 javap、
`bytecode-evidence.json`、`regression-v2/management-call-sites.json`、
独立 Native Image 构建与运行日志及完整 iOS 构建日志。

## 完整 iOS 构建

```sh
python3 -B tools/mcfao.py build --version 26.1.2 --loader fabric --target ios-arm64 \
  --config artifacts/mcfao-gl41.json --mods "$AUDITED_INSTANCE/mods" \
  --instance-data "$AUDITED_INSTANCE" --renderer gl41 --audited-mods \
  --heap-gib 9 --parallelism 4 --builder-gc g1 \
  --test-version COMPAT-r4-IRIS-FMA-20261121 \
  --output artifacts/iris-fma-20261121/ios-build
```

`AUDITED_INSTANCE` 指本轮 r3 已审计的本地实例，不含账号导出。构建与设备
结果如下。构建、签名、独立数学探针均不能替代真机世界、
BSL 开关与阴影画面验收。项目整体 Gate 不因本项修复提升为完成。

- 完整新 Native Image 构建成功，未复用旧 AOT 对象，镜像生成耗时 10m47s。
  ARM64 iOS 动态库链接与本地开发签名成功，`mcfao.py verify` 返回 0。
- 测试版本：`COMPAT-r4-IRIS-FMA-20261121`。
- buildKey：`efede2e2779aef8ecd7370149f9e691b30ed53932614819c2c32a6f12bf26e89`。
- 游戏 dylib UUID：`01B1CFB8-FD90-3BC1-B52D-28B3C7943F15`。
- IPA：`artifacts/iris-fma-20261121/ios-build/NCL-game-COMPAT-r4-IRIS-FMA-20261121.ipa`。
- IPA 大小：587,091,985 字节；SHA-256：
  `30c14cc2858caa961be234dd34040908b904b72919887db3d1dbf80ab950f000`。
- 测试版本在构建记录、IPA 名称与包内 FAOTTestVersion 三者一致。
  解包比对确认游戏 dylib、Iris 配置和 BSL ZIP 与签名 App 相同；
  配置保留 enableShaders=true、shaderPack=BSL_v10.1.3.zip。
- 最终原生符号表包含 OptionalJvmCapabilities_optionalBoolean、
  能力查询 lambda 及 AdvancedShadowCullingFrustum_checkCornerVisibility；
  见 `logs/iris-fma-20261121/native-symbols.txt`。

专项 6 项测试的独立 Native Image 部分记录于 `regression-v3.log`
（5 通过，完成构建输入检查当时跳过）；完成 AOT 后的
`regression-export-v2.log` 补验导出产物（5 通过，本轮未重复 Native Image）。
合并覆盖全部 6 项。原始原生探针复现预期 IllegalArgumentException；
修复探针输出：

```text
IRIS_SHADOW_PASS FMA=false capability=UNAVAILABLE planes=8 visible=2319 outside=16580 intersect=1101 nearBoundary=0
```

普通 JVM 在 UseFMA 开启/关闭时分别得到相同分类计数。测试以有限确定性
样本校验数值行为，不代表覆盖全部临界浮点输入或 GPU 阴影画面。

既有回归合并覆盖 49 项，47 通过，2 因本地历史 Fabric/Metal 夹具不可用而跳过。
其中 runtime lowering 通过 10 项、跳过 2 项；AOT compatibility 13 项、
MDAF 9 项及 renderer/cache 12 项通过；GL41 manifest 3 项在指定当前工具链后通过。
旧 runtime 测试默认准备目录指向已迁移的工具链；通过
MCFAO_TEST_FABRIC_PREPARED 指定本次实际准备目录后回归通过。
详细命令与结果见 `existing-runtime-v2.log`、`existing-compat.log`、
`existing-mdaf.log` 和 `existing-build-regression.log`。

## r4 真机复测与实体顶点格式阻断

2026-11-21，目标 iPad 安装和系统启动均成功，未附加调试器。
设备日志首行确认 COMPAT-r4-IRIS-FMA-20261121，buildKey 和游戏 dylib UUID
与上述交付一致。用户反馈进入世界时闪退，真机验收保持 BLOCKED。
本轮日志加载了 BSL，并出现世界/区块处理与 Iris 手部渲染调用；
未出现原始 HotSpotDiagnosticMXBean / ExceptionInInitializerError。
这些记录尚不足以验收阴影显示和光影切换。

闪退前最后错误为 MoltenVK 创建图形管线失败，提示
Cannot convert attribute from MTLAttributeFormatUShort4 to a signed integer type。
随后 Zink 报 vkCreateGraphicsPipelines failed。系统 IPS 记录 PC=0，
调用者为 libOSMesa 的 update_gfx_pipeline、zink_draw_vbo，
Java 调用链位于 Iris HandRenderer → LevelRenderer。
系统 termination 字段为 CODESIGNING / Invalid Page；它与上述管线失败
相邻，不能据此把所有签名问题都归因于顶点格式。

原始设备证据保存在 logs/iris-fma-20261121/ 下的
device-install.json、device-launch.json、device-after-crash/ 和
C0Harness-2026-11-21-124300.ips。设备报告系统版本为 iPadOS 27.2.1。

实际 IrisVertexFormats 的 ENTITY_ID_ELEMENT 使用 USHORT、4 分量；
EntityPatcher.patchEntityId 注入 in ivec3 iris_Entity，并直接赋值给
有符号 iris_entityInfo。EntityPatcher 原始 class SHA-256 为
d0072c583ba1ef21896198dc12966bbc90d8f52570152f37426285bb970addf3。

GL41 构建阶段只对上述已审计哈希的 EntityPatcher 修改两条字符串常量。
输入改为 uvec3，赋值显式使用 ivec3(iris_Entity)；所有下游有符号 varying、
实体/方块/手持物品 ID、顶点缓冲布局和阴影算法保留。
未知哈希在构建时明确报错，要求重新审计；没有 Iris 的原版输入不添加此补丁。
修改由 PatchDevice.java 执行，patch_gl41_client.py 验证 changedEntries
并在 result.json 记录 irisEntityAttribute。

新增 test_iris_entity_attribute.py 调用原始/修复后的实际 Iris AST 转换器，
验证生成声明、显式转换和原有 signed varying；另有未知哈希拒绝测试。
macOS Metal 探针复现原始 USHORT4/int3 管线创建失败，并验证修复管线成功。
该探针还实际绘制 65,536 个点，从 USHORT4 顶点缓冲读取三个不同排列的
0–65535 值，经 uint3 → int3 转换后写入 RGBA32Sint 纹理并逐值回读，
全部保持一致。此探针使用本机 Metal，不代替 iPad 游戏画面验收。
日志为 entity-regression-v3/metal-run/stderr.log。

通过当前 Java 25 和 ASM 路径重跑 GL41 manifest 的全部 3 项回归，均通过。
见 gl41-regression-r5.log。

```sh
python3 -B tools/mcfao.py verify --target ios-arm64 --output artifacts/iris-fma-20261121/ios-build
```

## r5 新构建与产物回归

2026-11-21，包含两项修复的完整 Native Image、iOS ARM64 链接、开发签名
及 IPA 导出成功。Native Image 耗时 8m5s，aotReused=false。

- 测试版本：`COMPAT-r5-IRIS-FMA-20261121`。
- buildKey：`cf8038be13d85873cf42d58f3de0d3bc0d2427d69d3eb33ce1d254bd2d8397ef`。
- 游戏 dylib UUID：`49479B48-A5ED-3B00-A0C3-194C475AF94C`。
- IPA：`artifacts/iris-fma-20261121/ios-build-r5/NCL-game-COMPAT-r5-IRIS-FMA-20261121.ipa`。
- 大小：586,994,242 字节；SHA-256：
  `ca5b9070f2b18782402ad42ab6b48b9960b1474d0481e061542d85acf69058bb`。

`mcfao.py verify` 通过。构建输入、result.json、IPA 文件名与包内
FAOTTestVersion 一致。解包逐字节比较游戏 dylib、Iris 配置及 BSL ZIP
与签名 App 一致；配置保留 enableShaders=true 和 BSL_v10.1.3.zip。
证据为 `ipa-verification-r5.json`、`verify-r5.log` 及 `native-symbols-r5.txt`。
原生符号包含安全能力查询、原有高级剔除方法和 EntityPatcher.patchEntityId。

对 r5 最终 AOT classpath 的 FMA 专项复验 5 项通过；原始/修复后
Native Image 独立探针沿用已通过的 regression-v3，本轮未重复编译。
实体属性专项 3 项全部通过，包括真实 Iris AST、Metal GPU 绘制与
65,536 个 ID 回读、最终 AOT 输入与 GL41 changedEntries 检查。

```sh
MCFAO_TEST_IRIS_FIXED_BUILD=artifacts/iris-fma-20261121/ios-build-r5 MCFAO_TEST_IRIS_LOGS=logs/iris-fma-20261121/regression-r5 python3 -B -m unittest discover -s tests -p test_optional_jvm_capabilities.py -v
MCFAO_TEST_IRIS_ENTITY_LOGS=logs/iris-fma-20261121/entity-regression-r5 python3 -B -m unittest discover -s tests -p test_iris_entity_attribute.py -v
python3 -B tools/mcfao.py verify --target ios-arm64 --output artifacts/iris-fma-20261121/ios-build-r5
```

日志为 `regression-r5.log`、`entity-regression-r5.log`。以上持久日志目录
首次运行时必须不存在；复跑请选择新目录以保留已有证据。
r5 已原位安装至目标 iPad，系统成功启动进程 33364，未附加调试器。
安装与启动证据为 device-install-r5.json、device-launch-r5.json。
启动后两次拉取日志尚未发现 r5 游戏 run 日志，因此不能把宿主进程启动
推断为 Minecraft 已进入世界。拉取记录位于 device-r5-after-launch/
和 device-r5-observe-1/。
真机世界、BSL 开关及阴影画面尚待用户复测，不能声明 BSL 完全兼容。
