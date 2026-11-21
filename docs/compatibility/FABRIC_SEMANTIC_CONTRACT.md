# Fabric 静态运行时契约

目录按构建期 Loader 枚举顺序保存真实容器。一份容器可通过规范 ID 或 `provides` 别名找到。枚举只产生规范容器。动态表达式查询通过 ASM 栈来源识别，保留 ID 的计算和 Optional 消费操作。未能保留的 Loader 调用携带方法描述符写入残留清单，运行到相应方法时抛出有位置的错误。保护的初始化入口仍在转换期明确拒绝。

## RuntimeLowering 规则审计

| 规则位置 | 分类 | 依据和边界 |
| --- | --- | --- |
| `lowerQueries` 的 Mod 查询、生产环境和资源目录查询 | SEMANTIC_EQUIVALENT | 固定 Loader 图、生产 client 标记和宿主启动目录。动态 receiver 逃逸待覆盖 |
| `lowerQueries` 的自定义入口、provider 投影 | REQUIRES_REVIEW | 已生成的静态 stage 和 provider 容器有 JVM 夹具。未识别 stage、任意 adapter、异常聚合待对照 |
| `MAPPING_HOOKS`、`lowerLoaderMetadata` | REQUIRES_REVIEW | 仅 official 命名空间的 identity 有契约。跨命名空间解析及旧 Loader 兼容行为待验证 |
| `lowerVersionLookup`、`lowerImmediatelyFastVersion`、`lowerSodiumMetadata`、`lowerJadeMetadata` | REQUIRES_REVIEW | 指纹锁定的历史适配。需要分别对照缺失 ID、注入字段和配置行为 |
| `lowerModFile` | OPTIONAL_DEGRADED | 只可使用名义位置。源 JAR 字节读取需要另一个文件能力 |
| `lowerVanillaPackBuilder`、`lowerConfigDiscovery` | REQUIRES_REVIEW | 命名空间与配置发现结构已匹配。Pack 栈与 reload、真实配置的行为待验收 |
| `lowerRenderPipelineRegister` | REQUIRES_REVIEW | 显式 Metal 路径的旧着色器守卫，GL41 编译仍走原注册 |
| `collectMixinPluginEarlyInit`、`foldIndigoGate` | REQUIRES_REVIEW | 受审计类仅为固定插件保留已知运行期逻辑。未覆盖一般插件状态 |
| `stripMixinMetadata`、`removeUnusedEventProxy` | SEMANTIC_EQUIVALENT | 前者剥离构建期标注，后者删除固定指纹中的私有未引用助手。常规事件工厂保留 |
| `replaceGeneratedSerializer`、`lowerGlitchCoreEvents` | REQUIRES_REVIEW | 已有静态算法与具名类型计划。需要独立验证应用到的版本和玩法路径 |
| `printBeforeReport` | OPTIONAL_DEGRADED | 崩溃诊断改写 |
| SystemReport 的 handler/Loader 诊断裁剪 | OPTIONAL_DEGRADED | 仅保留既有诊断范围，转换记录列出精确方法 |
| 其余 Loader 调用残留 | UNSUPPORTED | 记录完整方法和调用签名。一般方法保留链接能力并在实际执行时显式失败，入口点阻断导出 |

游戏类变换记录包含原始 JAR、Knot 输出、出货类三份 SHA-256（其中原始和出货仍沿用原字段）。它可定位变更发生阶段。Fabric 事件注册、资源 reload、世界 tick 和配置 reload 仍须以对应运行场景验收。
