# Better MC BMC5（NeoForge）上 iOS 的可行性评估

> 评估日期：2026-11-15
> 目标包：`C:\Users\zrxma\Desktop\我的世界\.minecraft\versions\Better MC [NEOFORGE] BMC5`
> 结论先行：**这是另一条产品线，不是 A1 线的参数调整。**当前 A1 线（26.1.2 + Fabric + Java 25 无 JIT）
> 对 NeoForge 一行代码都没有；要跑起来必须先过 N0 门槛，而 N0 的主要风险已经可以在静态扫描里看到。

## 1. 整合包事实

| 项 | 值 |
|---|---|
| Minecraft | **1.21.1**（241 个 mod 文件名带 1.21.1；neoform `1.21.1-20240808.144430`） |
| 加载器 | **NeoForge 21.1.250**（`neoforge-21.1.250-client.jar` / `-universal.jar`） |
| Java | **21**（版本 json `javaVersion.majorVersion = 21`） |
| 主类 | `cpw.mods.bootstraplauncher.BootstrapLauncher` |
| 启动链 | bootstraplauncher 2.0.2 → securejarhandler 3.0.8 → modlauncher 11.0.5 → FML fancymodloader 4.0.44 |
| Mod 数量 | **350 个 jar / 620 MB**，无重复 jar |
| Mixin 配置 | **256 个 mod** 带 mixin 配置 |
| Access Transformer | **177 个 mod** 带 AT |
| JarJar（嵌套 jar） | **68 个 mod** |
| 客户端资源 | assetIndex `17` |

## 2. 与 A1 线的差距

| 维度 | A1 线（已交付） | BMC5 需要 |
|---|---|---|
| Minecraft | 26.1.2 | **1.21.1** |
| Java | 25 | **21** |
| 加载器 | Fabric（已做构建期 Mixin/ASM 转换） | **NeoForge / FML**（模块层 + ModLauncher + Mixin） |
| 渲染 | GL41：OSMesa 4.1 → zink → MoltenVK | 1.21.1 的 LWJGL 3.3 调用面（可复用 GL41 思路，但要重新验证） |
| 规模 | 原版 + 少量 | **350 mod / 256 份 mixin 配置 / 177 份 AT** |

## 3. 阻断点（静态扫描证据）

对本地 `libraries` 里的启动链 jar 做了字符串级扫描（统计“出现该符号的 class 数”）：

| jar | class 数 | `defineClass` | `ModuleLayer` | `MethodHandles$Lookup` | `sun/misc/Unsafe` | `addReads` |
|---|---|---|---|---|---|---|
| bootstraplauncher 2.0.2 | 4 | – | 1 | 3 | – | – |
| securejarhandler 3.0.8 | 54 | **1** | **3** | **29** | 1 | – |
| modlauncher 11.0.5 | 78 | – | **20** | 36 | – | 1 |
| neoforge 21.1.250 client | 1603 | – | – | 839 | – | – |

含义：

1. **运行时模块层**：`modlauncher` 有 20 个类引用 `ModuleLayer`，NeoForge 靠它在运行时拼装模块图。
   GraalVM native-image 是**封闭世界**编译，模块图在构建期固定；运行时 `defineModules` 基本不可用。
2. **运行时定义类**：`securejarhandler` 里存在 `defineClass` 与 `Unsafe` 用法，用于把 jar 里的类加载进模块。
   A1 线的硬约束是「运行期不得动态定义类」，这正是 NeoForge 的核心机制。
3. **Mixin/AT 规模**：256 份 mixin 配置 + 177 份 AT。A1 线只处理过 Fabric 的小规模场景，
   这里的组合爆炸（mixin 冲突、AT 重映射、jarjar 嵌套）本身就要独立的验证流水线。

因此「把 BMC5 直接 AOT 成 iOS 包」在当前架构下不成立；必须先改变加载方式的实现路径。

## 4. 唯一现实的架构：构建期 FML 静态化

思路与 A1 线处理 Fabric 的方式同源，只是难度放大：

1. 在 macOS 构建机上用 **Java 21 JVM** 真正跑一遍 NeoForge 的启动链（ModLauncher + securejarhandler），
   把一个整合包的所有 mod 发现、mixin 应用、AT 重映射、jarjar 展开全部**在构建期完成**。
2. 把完成后的类集合导出成一份「扁平化 class 图谱」，并提供一份「运行期零动态定义」的清单。
3. 对这份图谱做 GraalVM AOT（iOS arm64），运行期不再需要 ModLauncher / ModuleLayer。
4. 运行期的 FML 语义（注册表、事件总线、生命周期）用静态生成的适配代码替代。

这不是参数问题，是**重写加载器运行期**的问题。风险点在于：某些 mod 在运行期真的会 `defineClass`（脚本、
动态代理、ASM 生成器），这些 mod 在无 JIT/无动态类的前提下只能剔除或改造。

## 5. Gate 划分与停止条件

| Gate | 内容 | 通过标准 | 备注 |
|---|---|---|---|
| **N0** | 构建期跑通 NeoForge 21.1.250 + 原版 1.21.1（0 个 mod），导出静态类图谱 | 能在 macOS JVM 上启动到主菜单；导出物可被 javap 校验；无运行期 defineClass | **最便宜的决定性实验**，失败就停止 |
| **N1** | 对 N0 的图谱做 AOT，iOS 启动到主菜单 | 真机出现主菜单，无 JIT | 复用 A1 的 AOT 工具链 |
| **N2** | 1–3 个带 mixin + AT 的 mod | 构建期转换成功、运行期行为与 JVM 对照一致 | 先挑 mixin 简单的 |
| **N3** | 30 个 mod 子集 | 真机进世界、可玩 | 此时才谈整合包 |
| **N4** | 350 mod 全量 | 逐 mod 兼容性报告 + 剔除清单 | 大概率需要裁剪 |

**停止条件**：N0 在 3 个工作日内拿不出可用的静态类图谱（或发现关键路径必须运行期定义类），
即判定该包在「无 JIT」约束下不可行，回到 A1 线做性能优化，或改用允许 JIT 的方案另立项。

## 6. 下一步（N0 的具体动作）

1. 在 CI 里加一个 `neoforge-n0` 作业（macOS，Java 21）：
   - 下载 1.21.1 客户端与 NeoForge 21.1.250（走 Mojang/NeoForged 官方 CDN，固定 SHA）
   - 以 headless 方式启动 ModLauncher，只加载原版，开 `-Dfml.debug` 与 mixin audit
   - 导出：模块清单、mixin 应用表、AT 结果、类加载来源、**运行期 defineClass 调用点**
2. 校验导出物：类数、包结构、关键类（`net.minecraft.client.Minecraft`）可用。
3. 出结论：能否在不改架构的前提下静态化；不能的话给出必须重写的运行期组件清单。

## 7. 工作量与建议

- N0：1–3 天（含 CI 环境搭建）
- N1：3–5 天（复用 A1 工具链，但要处理 Java 21 / 1.21.1 差异）
- N2：1 周起（按 mixin 复杂度）
- N3/N4：以周计，且 N4 大概率需要把不兼容 mod 剔除

**建议不要以「350 mod 全包」作为第一目标。**先用 N0 证明构建期 FML 静态化可行，再按 N2 → N3 逐步放量；
每一步都保留 JVM 对照与真机证据，避免把「能编译」当成「能玩」。
