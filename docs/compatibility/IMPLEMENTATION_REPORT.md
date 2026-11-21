# COMPAT 工程记录 · 2026-11-21

基线 `9126340497d8528cd52d23b6aac084b065e32262`，工作分支「通用fabricmod适配计划」。保留原有未提交 iOS 启动器、账号、工程和包内容索引修改。构建和审计证据保存在本轮独立输出目录。开发范围和既有行为见 [基线审计](BASELINE_AUDIT.md)。

## 状态

| 阶段 | 结果 | 已验证部分与缺口 |
| --- | --- | --- |
| 0 基线审计 | 完成 | 已读实际实现、版本锁和基线日志。 |
| 1 Fabric 语义 | 部分完成 | 别名、动态 ID、容器身份和基本元数据契约通过。现实 tooltip 初始化故障修复。任意 Loader receiver、自定义 adapter、入口异常聚合、tick/reload 和世界生命周期待验证。 |
| 2 资源闭包 | 部分完成 | 静态路径追踪、资源哈希、标准 Loader 查询和 Pack 分层已实现。多来源 ClassLoader 枚举的完整 URL 语义及真实 reload 待实现。 |
| 3 MDAF | 部分完成 | 配置类型推断、合并、条件、来源、成员签名和初始化风险。Gson 有严格模式运行证据。完整序列化、代理、JNI 元数据和 iOS 配置闭包待验。 |
| 4 iOS 平台 | 部分完成 | 既有 PNG 像素对照与资源目录安全提取通过。IAS、OpenAL EFX、图像写出及其余 AWT 在目标设备上待验。 |
| 5 动态代码 | 部分完成 | 保留 Sodium 静态计划，改进类定义、生成器和 Proxy 诊断，冻结确定的 tooltip 字节码扫描。任意代码生成保持不支持。 |
| 6 规则 | 部分完成 | 原规则引擎输出规则模式、作用域、版本和证据。覆盖冲突、禁用实验规则和幂等性。历史转换中的定向规则仍有自己的实现入口。 |
| 7 验证体系 | 部分完成 | B0、Java 25 和 macOS Native Image、最终类路径检查及按报告选测运行。设备测试和少量机制夹具仍缺。 |
| 8 Builder | 部分完成 | 持久任务上的逐 Mod 状态、风险、规则、待测机制和 Finder 证据入口通过浏览器验证。转换级颗粒缓存和用户从导入到签名的整套 GUI 自动化待进一步复验。 |
| 9 回归交付 | 部分完成 | 原版及 109 Mod 的 iOS ARM64 包通过完整构建和包校验，整包已产出开发签名 IPA。目标 iPhone 不在描述文件中，设备功能和存档复验受阻。 |

## 可重复的根因对照

- **Fabric 别名**。初始 `test_mod_catalog` 失败在固定 Loader 能以 `provides` 返回容器，而 AOT 查询为空。使用规范容器及别名共同索引之后同一夹具通过，未知/null ID 对照为空。见 `phase1-before.log`、`phase1-catalog.log` 及 [语义契约](FABRIC_SEMANTIC_CONTRACT.md)。
- **Fabric tooltip**。将未经验证的核心空返回改为显式失败后，COMPAT-r1 整包虽产生 AOT 对象，但从 79k 可达类型跌到 42,736，游戏代码校验找不到 tick、网络处理和诊断符号，正确拒绝了该包。反汇编定位到 Fabric item API 的 `scrapeVanillaOrder` 靠运行期 Mixin ASM 服务读取 `ItemStack`。COMPAT-r2 从构建期字节码冻结 31 个组件的访问序列，JVM 对照与真实组件值一致。r2 有 79,157 个可达类型，真实游戏符号复验通过。
- **Fabric pack 枚举**。固定指纹的 Fabric resource-loader 保留原构造、排序和注册逻辑，只改用静态目录。存在真实的 Knot 资源包挂钩时，Mod 的 `assets/` 和 `data/` 经各自 pack 层加载。导出不再将同一份文件叠加到原版层。隔离 JVM 实跑读取两个独立 Mod 的客户端与服务端内容并核对 SHA-256。
- **Iris 和 Sodium**。Sodium 图标与 Iris 当前版本实际调用的 `.fsh`、`.vsh` 经同一通用 Classpath 规则保留，合并 JAR 和严格模式 Native Image 探针实读比对通过。Iris 后续着色器及 GL 能力继续由独立运行证据评定。见 [资源闭包](RESOURCE_CLOSURE.md)。

## 验证与性能

| 样本 | 构建 | Native Image 阶段 | 校验 |
| --- | --- | ---: | --- |
| 原版 GL41 | `COMPAT-r1-20261121` | 141.48 秒 | 无签名 IPA `mcfao verify` 通过，481,544,924 字节 |
| 41 个根 JAR / 109 个解析后 Mod GL41 | `COMPAT-r2-20261121` | 398.06 秒 | 无签名 IPA `mcfao verify` 通过，585,462,832 字节 |
| 同整包开发签名 | `COMPAT-r2-20261121` | 372.57 秒 | 签名 IPA `mcfao verify` 通过，587,203,063 字节，无动态代码权限 |

签名 IPA SHA-256 为 `05802ac3af8ef712623d9143d3f3d461eba6b83324399a9ea937f5629ee076cf`。在外接盘 `/Volumes/K/AOTC/builds/compat-r2-20261121-4bjevahb/fabric-signed/`。构建记录、IPA 名称和 App 的 `FAOTTestVersion` 均为 `COMPAT-r2-20261121`。包含设备参数的校验已单独失败并保留日志 `r2-signed-device-verify.log`。本机无覆盖目标 iPhone 的有效描述文件。通用签名验证从原始 Xcode 成功检查点复核后进行，恢复命令和证据见 `finalize-verified-signed-app.py`、`r2-signed-verify.log`。

整包冷预检 53,744 类用时 33.06 秒，保持有序输入与规则指纹不变的暖扫描用时 0.28 秒。Native Image 阶段外部时间工具记录 r2 峰值 RSS 6,526,042,112 字节。最终 JVM 类路径检查 111 类加载失败，严格成员检查 268 条失败，Minecraft 和 mcfao 核心类在两份记录中均为 0。其余条目保留为 Report-Only。逐 Mod [兼容矩阵](../MOD_COMPATIBILITY_MATRIX.md) 由生成器读取本轮结果。

全量 Python 回归记录 635 项。临时 APFS 测试卷中通过 625 项、跳过 9 项。剩余 1 项替换了挂载查询，在 Mac 本地临时目录复跑通过。测试卷已卸载，原始失败、临时卷日志及挂载路径复验均保留。按机制选测六组、91 个 Builder 单测、Vite 和浏览器测试通过。详细命令、日志、未执行原因见 [测试矩阵](TEST_MATRIX.md)。

## 保留风险

当前整包报告仍含 Presence Footsteps 的 [未支持 Loader 路径](FABRIC_SEMANTIC_CONTRACT.md)，以及动态资源、反射、可选依赖和平台告警。要将逐 Mod 状态推进到功能或真机通过，需要使用相同包在设备上复验世界、关键 Mod 功能和重入存档。精确任务边界见 [AOT 元数据](AOT_METADATA.md)、[平台能力](IOS_PLATFORM_ADAPTERS.md)、[动态代码](DYNAMIC_CODE_SUPPORT.md) 与 [适配规则](ADAPTATION_RULES.md)。

## COMPAT-r2 设备回传与 COMPAT-r3 验证

`run-1795223619009-COMPAT-r2-20261121.log` 确认 r2 在 iOS 上加载镜像、启动客户端、加载单人世界并收到区块批次。最终异常来自 Sodium 动态读取地形 shader。Iris 的根路径 `colorSpace.csh` 缺失使其关闭 shader 管线。FancyMenu 的泛型 DTO 缺少反射注册。三个问题分别定位到出货 JAR 的资源路径、字面量过滤和反射输入。见 [资源闭包](RESOURCE_CLOSURE.md) 及 [AOT 元数据](AOT_METADATA.md)。

| 校验 | 实际结果 | 日志 |
| --- | --- | --- |
| 实际 Sodium 方法 JVM 对照 | r2 同输入重现 `Shader not found`。r3 退出码 0，返回原资源 SHA-256。 | `pack-contract/before/stderr.log`、`pack-contract/after/stdout.log` |
| Fabric pack 读和完整索引 | 隔离 JVM 实读两类 pack。合并、split 和 GL41 三阶段 JAR 各校验 8,867 个唯一索引目标。遗漏、错误路径和歧义索引负例失败。 | `pack-contract/run/stdout.log`、`full-pack-index-verification.log`、`resource-tests.log` |
| 反射推断和实际读取 | Gson TypeToken 正负例通过。真实 r3 反射配置含 FancyMenu DTO。在 macOS 严格 Native Image 运行资源 SHA-256 和 Gson 泛型往返。 | `probe-native-build.log`、`probe-native-run.log` |
| 同类回归 | RuntimeLowering、资源闭包、配置反射、MDAF、兼容性报告、类路径和 CLI 夹具通过。外部测试包和 Metal 样本条件缺失的条目按需跳过。 | `python-regression-retry.log`、`resource-tests.log` |

日志位于 `logs/compat-r3-20261121`。已有工作区以 `9126340497d8528cd52d23b6aac084b065e32262` 为基线。采用本地 `artifacts/mcfao-gl41.json` 和与 r2 相同的已审计实例，运行 `mcfao build`，使用 `--test-version COMPAT-r3-20261121`。r3 冷预检扫描 53,746 个类，用时 36.02 秒，解析 109 个 Mod。完整性校验加严后在三阶段的真实 r3 JAR 上分别执行。

r3 完成 iOS ARM64 Native Image（8 分 45 秒，79,159 个可达类型）、链接和 Xcode 开发签名。通用 `mcfao verify` 通过，核验真实游戏符号及无动态代码权限。签名镜像可定位完整索引和五份目标资源字节。IPA 位于 `artifacts/compat-r3-20261121/fabric-signed-retry/NCL-game-COMPAT-r3-20261121.ipa`，587,147,393 字节，SHA-256 为 `25b8b1796db07e0861f5df5be7f4af06005f415d624272bb1941e9437e88f5a3`。包名、Info.plist 和记录的测试标识一致。指定此前目标 iPhone 的核验因描述文件未覆盖而失败，见 `verify-device-host.log`。r3 设备和模拟器为 DEVICE_NOT_RUN。

设备日志还记录 IAS 的 `/var` 权限错误，Sound Physics 的 OpenAL EFX 创建失败，Xaero 类别配置空值及 Kirin 损坏 JSON。它们分别保留为待验证的沙盒、音频和配置问题。解析后所有 Mod 的测试状态继续按证据分层。
