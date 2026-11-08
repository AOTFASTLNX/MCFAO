# 当前证据索引

最后复核：2026-11-08。结论见 [ADR-001](ADR-001.md)、[ADR-002](ADR-002.md)和[ADR-003](ADR-003.md)。路径相对项目根：

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
| 真实客户端原生方法引用清单 | artifacts/evidence/client-native-call-inventory.json；静态候选，不是iOS支持矩阵 |
| 真实客户端入口分析阻断 | artifacts/c0/client-graph-07/；沙盒PASS，6 GiB Java堆耗尽，退出3 |
| 当前自动化测试 | artifacts/evidence/unit-tests-b1-c0-final/；69项PASS |
| 日志/二进制/源文件核验 | artifacts/evidence/verification-b1-c0-final.json |

JVM、桌面 AOT、负例和早期编译失败亦保留在 artifacts/a1 与 evidence。旧实验无源码快照时不能精确恢复旧源码；指纹描述当时输入和产物。

原始签名/设备日志保留本地。A0/A1/B0/B1已具备各自范围的实际证据，见[ADR-002](ADR-002.md)。iOS游戏菜单、世界与游戏性能仍待验证。
