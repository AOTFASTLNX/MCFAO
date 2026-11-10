# 当前证据索引

最后复核：2026-11-08（第44轮）。结论见 [ADR-001](ADR-001.md)、[ADR-002](ADR-002.md)、[ADR-003](ADR-003.md)和 [ADR-008](ADR-008.md)（iOS 图形栈，方案在 [GRAPHICS_STACK_PLAN](../GRAPHICS_STACK_PLAN.md)）。路径相对项目根：

| 内容 | 路径 |
|---|---|
| 固定官方源下载/许可文件摘要 | artifacts/evidence/upstream-source-download/、.cache/upstream/{jdk,graal}.json |
| Apple Metal 组件下载/确认 | artifacts/evidence/metal-toolchain-download/ |
| 官方 java.base 头文件 | artifacts/evidence/openjdk-java-base-headers/ |
| iPhoneOS 119 单元/6个原生库 | artifacts/a1/runtime-source-v4/result.json |
| iPhoneOS Framework 完整链接 | artifacts/a1/ios-linked-v2/result.json |
| iPhoneOS 未签名 App | artifacts/evidence/a1-ios-build-unsigned-v2/ |
| 最新build 3 开发签名归档 / IPA 本地导出 | artifacts/evidence/a1-ios-archive-run-state-v3/、a1-ios-export-run-state-v3/ |
| build 3 IPA ARM64/描述文件/哈希 | artifacts/a1/device-handoff-v3/result.json |
| build 3 IPA 嵌套签名/实际权限 | artifacts/evidence/a1-ios-ipa-signature-run-state-v3/、a1-ios-ipa-entitlements-run-state-v3/ |
| 用户首轮真机失败 / 只读采集 | artifacts/evidence/a1-user-device-run-01/、a1-user-device-copy-01/；createIsolate=801 |
| build 2 用户真机Java断言通过 | artifacts/evidence/a1-user-device-run-02/、a1-user-device-copy-02/ |
| build 2 新运行及独立启动确认 / A1 PASS | artifacts/evidence/a1-user-device-run-03/、a1-user-device-copy-03/；含用户退出Xcode/拔线确认和变化日志名 |
| build 3 当前运行显示与用户PASS | artifacts/evidence/a1-user-device-run-04/、a1-user-device-copy-04/ |
| Simulator 原生库和 Framework | artifacts/a1/runtime-simulator/、ios-linked-simulator/ |
| Simulator App 编译/本地签名 | artifacts/evidence/a1-simulator-build/ |
| Simulator 创建/安装/启动 | artifacts/evidence/a1-simulator-{create,boot,install,launch}/ |
| 实际 Java25 / 原生生命周期断言 | artifacts/evidence/a1-simulator-run/{result.json,runtime.log,native-report.json} |
| Swift Craft 本地客户端匹配 | artifacts/evidence/swiftcraft-assets.json |
| Swift Craft 历史启动记录的脱敏版本摘要 | artifacts/evidence/swiftcraft-existing-baseline.json；历史采集仅PARTIAL，当前A0结论见a0-desktop-reference/ |
| 当前A0真实主菜单 / Java进程 / 依赖清单 | artifacts/evidence/a0-desktop-reference/；Java25.0.1 + Fabric0.19.3，A0 PASS |
| Fabric0.19.3官方源码下载 | artifacts/evidence/fabric-loader-source-download/、.cache/fabric/；源码审读见ADR-002 |
| B0真实转换 / 重放 / 精确负例 / 沙盒 | artifacts/b0/run-04/；B1使用此轮。修订运行器复验run-05也PASS |
| B0对应源快照 | artifacts/b0/source-snapshot-04/；19个输入与当轮准备指纹匹配 |
| B1 AOT对象 / 输入链 | artifacts/b1/ios-probe-03/；转换后Target字节匹配B0，未包含游戏JAR |
| B1自建iOS运行库 / Framework | artifacts/b1/runtime-ios/、ios-linked/、ios-framework/ |
| B1签名归档 / 导出 / 验签 | artifacts/evidence/b1-ios-{archive,export,ipa-signature,ipa-entitlements}/ |
| B1 build 4诊断IPA | artifacts/b1/device-handoff/result.json；包创建时为设备NOT RUN，历史不回写 |
| B1用户两次真机PASS与独立启动确认 | artifacts/evidence/b1-user-device-run-01/、b1-user-device-copy-01/ |
| 真实客户端原生方法引用清单 | artifacts/evidence/client-native-call-inventory.json；静态候选，不是iOS支持矩阵；图形面细分见 GRAPHICS_STACK_PLAN §2 |
| 真实客户端入口原始分析阻断（历史） | artifacts/c0/client-graph-07/、13/、19/、22/；保留不变，结论已被拆分路线取代 |
| 分析墙定位（线程栈/快照/形状普查） | artifacts/c0/client-graph-22-supervisor.json、census-summary-24.json、method-shape-census-26.1.2.json |
| 方法拆分器与真实客户端转换 | compiler/splitter/、artifacts/c0/client-split-04/（18类/28方法→358段） |
| 拆分语义等价（注册表摘要） | artifacts/c0/init-digest/result.json；FNV `4fce5dfeb9c2f39b` 与原版逐字节相同 |
| 完整分析通过 | artifacts/c0/client-graph-26/、27/、28/；32,531类型/112,219方法 |
| 可重定位镜像 / iOS 链接 | artifacts/c0/client-build-35/（client-graph.o）、client-link-02/、client-link-sim-02/ |
| iOS 宿主 App 与真机/模拟器运行 | ios/C0Harness/、artifacts/c0/harness/（含 export/FabricAOT C0.ipa 与 Documents/c0-logs 抓取） |
| 真实客户端运行到 Datafixer 之后 | artifacts/c0/harness/logs*/；LWJGL `Unknown platform: iOS` 为当前阻断 |
| 构建JFR导致的目标配置影响 | artifacts/c0/client-graph-08/；缺LibMDependencies.cap，未作为内存对照 |
| 堆/GC有界诊断与源码快照 | artifacts/c0/client-graph-09/、10/、11/；6/8 GiB Parallel与8 GiB G1均OOM，无完整分析统计 |
| 受控变量验证 | artifacts/c0/heap-comparison-verified.json、gc-comparison-verified.json |
| 元数据审计 | 各轮metadata-audit.json；声明来源与范围，不是反射/JNI闭包完成证明 |
| 当前自动化测试 | artifacts/evidence/unit-tests-c0-diagnostics-verified/；79项PASS；第30–36轮123项见 unit-tests-20261108-c0-link/；第44轮本机133项PASS（未单独归档） |
| 日志/二进制/源文件核验 | artifacts/evidence/verification-c0-diagnostics-final.json |

JVM、桌面 AOT、负例和早期编译失败亦保留在 artifacts/a1 与 evidence。旧实验无源码快照时不能精确恢复旧源码；指纹描述当时输入和产物。

原始签名/设备日志保留本地。A0/A1/B0/B1已具备各自范围的实际证据，见[ADR-002](ADR-002.md)。iOS游戏菜单、世界与游戏性能仍待验证。

## 第45轮图形启动集成

第45轮历史：真实Window/RenderSystem模拟器AOT与Metal诊断清屏通过，日志/截图在 [metal-simulator-evidence-01](../../artifacts/graphics/metal-simulator-evidence-01/result.json)，149项回归见 [regression-03.log](../../artifacts/graphics/regression-03.log)。当时设备目标构建见 [日志](../../artifacts/graphics/xcode-metal-device-debug-01.log)。

## 第46轮真机蓝屏与资源通路

当前入口：[GRAPHICS_BOOTSTRAP](../GRAPHICS_BOOTSTRAP.md)。[用户真机结果](../../artifacts/graphics/device-run-02/result.json)为蓝屏诊断PASS，独立启动未确认。[资源模拟器结果](../../artifacts/graphics/resources-simulator-evidence-04/result.json)包含四格式GPU读回、深度清除、fence与四分屏截图；[主机契约/布局](../../artifacts/graphics/metal-sim-07/result.json)通过；[151项回归](../../artifacts/graphics/regression-06/stderr.log)通过。[Xcode默认设备构建](../../artifacts/graphics/xcode-default-device-check-02/command.json)及[嵌入输入核对](../../artifacts/graphics/xcode-default-device-check-02/inputs.json)通过，工程已备好且用户已确认真机四色，见[资源设备记录](../../artifacts/graphics/device-run-03/result.json)。宿主日志覆盖修复后[模拟器复验](../../artifacts/graphics/resources-simulator-evidence-05/result.json)与[设备构建](../../artifacts/graphics/xcode-default-device-check-03/command.json)通过。完整Main、STB、游戏绘制与着色器未完成，C0/C0a BLOCKED。
