# 适配规则和证据

既有 `AdaptationRuleEngine` 为结构规则记录 ID、版本、启用模式、作用域、证据入口、匹配目标、实际编辑数和后置验证结果。同目标规则冲突时报出所有 ID，并保留原字节码。重复执行会检验已应用条件，实验规则默认关闭，UNSUPPORTED 不自动编辑。

| 处理 | 证据 |
| --- | --- |
| `fabric.resource.merged-namespace-index.v1` | 验证固定 Minecraft 方法签名和命名空间冻结形态，保留 JVM 对照、负例及幂等性测试。 |
| `ios.texture.png-native-image.v1` | 使用既有形态检查和像素回归，通过转换记录关联实际 Mod 调用。 |
| `classpath.resource.v1` | 候选路径分析、大小上限、冲突拒绝、最终合并 JAR 哈希与读取。Native Image 主机样本已有证据。 |
| `classpath.pack-stream.v1` | 对标准 `Class.getResourceAsStream` 的描述符执行幂等字节码替换。运行时只索引无歧义的应用类路径绝对 pack 路径，未命中沿用原 API。JVM 对照覆盖存储位置、缺失条目、相对路径和原版资源。真实 Sodium 方法和严格模式的主机 AOT 读取通过。 |
| `fabric.item.tooltip-order.v1` | 指纹锁定 Fabric 物品模块。把真实字节码扫描结果写成有序的组件读取。本轮按实际构建验证，玩法待测。 |
| `fabric.resource.mod-pack-enumeration.v1` | 指纹锁定的 Fabric pack 入口和内部调用点只替换 Loader 句柄传递，Pack 构造、排序和启用逻辑由原 Fabric 代码继续执行。 |

现有资源、纹理和固定指纹适配可在转换报告中追踪。它们的行为证据仍按实际夹具和构建记录评定。仓库中已有的定向补丁与通用机制保留各自的适用范围。
