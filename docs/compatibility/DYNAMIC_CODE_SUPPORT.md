# 动态 Java 行为

A / B 类需要确定的输入及有限输出。继续使用 Sodium 的 `GenericVertexSerializer`，按源布局和目标布局生成固定复制计划。仓库保留 92 个布局组合的历史逐字节对照记录。本轮重新转换当前 Sodium 样本，未重跑该历史对照。

C 类按业务机制保留普通已编译逻辑。Fabric 物品 API 的 tooltip 运行期 ASM 扫描是一个实际案例。固定指纹的实现从 Knot 的构建期字节码提供者读 `ItemStack`，提取顺序后生成直接读取 `DataComponents` 的静态代码。组件值和初始化仍发生在客户端运行期。

D 类继续报告明确的 `defineClass`、`defineHiddenClass` 和类似路径。ASM 写出、Javassist 和 Byte Buddy 生成器调用属于待验证能力证据，写出字节本身不足以证明运行时定义代码。Proxy 调用独立列出，固定接口代理仍需真实实例化证明。没有增加运行时代码定义、JIT 或解释器入口。
