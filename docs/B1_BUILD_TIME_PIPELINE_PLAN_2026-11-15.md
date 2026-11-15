# B1 线 · 构建期转换管线（方案 B）实施计划

> 决定日期：2026-11-15
> 目标：NeoForge / Minecraft 1.21.1 / iOS 无 JIT。先把 **Better MC BMC5** 作为集成目标，
> 但第一验收物不是整合包，而是「构建期把 FML 的转换结果冻结成可 AOT 的类图谱」。

## 1. 为什么是"构建期"

N0/N0.5 已经证明：

- NeoForge 21.1.250 的引导链能在 macOS 上 `Done (3.6s)` 启动；
- 转换后的类字节可以被 javaagent 完整捕获；
- **GraalVM native-image 能消费这份图谱**：15.8 秒链接出 13 MB 可执行文件并能运行。

唯一没解决的是「图谱不完整」：dump 只包含运行期被加载过的类，而
`ModuleLayer` 不可用（游戏类在未命名模块）、jar 条目名是 SRG 而非运行期官方名，
按名字强推只成功 220 / 26,067。

方案 B 的判断：**不要把"抓全类"当成设备侧问题，而是把它变成构建期的一次性产物**——
在 macOS 构建机（有 JVM、无 JIT 限制）里把 FML 的转换全部跑完，冻结结果，再拿去 AOT。

## 2. 管线结构

```
 [1] 源获取            Mojang 1.21.1 client + NeoForge 21.1.250 + 整合包 mods
        │
 [2] 构建期引导        macOS JVM 跑 FML：ModList 发现、Mixin、AT、jarjar 展开
        │
 [3] 类图谱冻结        所有类的最终字节 + 映射表 + mod 元数据 → graph.tar
        │
 [4] 静态运行期生成    注册表 / 事件总线 / 生命周期 → 生成的初始化代码（替代 ModLauncher）
        │
 [5] AOT              GraalVM native-image（复用 A1 的 iOS 工具链）
        │
 [6] 签名 + 真机       zsign → IPA → iPhone
```

与 A1 的关键差异：A1 只有 Fabric loader，加载语义简单；NeoForge 有模块层、ModLauncher、
注册表 DSL 与事件总线，[4] 是全新的工作量。

## 3. 分阶段与验收

| 阶段 | 内容 | 验收 | 估计 |
|---|---|---|---|
| **B0** | 类图谱补全：从 FML 实际使用的加载器/模块位置取类，或驱动转换器，产出**完整**类集合 | 纯 JVM 加载冒烟 10/10；类数 ≥ 25k | 1–3 天 |
| **B1** | 原版（0 mod）客户端在 macOS 上 AOT 启动到主菜单 | 13 MB 级镜像 → 主菜单截图 | 3–5 天 |
| **B2** | 引入整合包的 ModList：FML 发现 + mixin/AT 全量应用 | 与 JVM 对照的类哈希一致 | 1 周 |
| **B3** | 静态运行期生成：注册表/事件总线/生命周期 | 原版 + 3 个 mod 进世界 | 1–2 周 |
| **B4** | 整合包放量 + 不兼容 mod 报告 | 目标子集可玩 | 按 mod 计 |

**停止条件**：B0 两周内拿不到完整图谱，或 B2 发现关键 mod 依赖运行期 `defineClass`，
则该整合包在无 JIT 前提下不可行，回到 A1 线。

## 4. B0 的三个候选实现（按代价排序）

1. **锚点 + 模块位置解析**（最小改动）
   用 `Instrumentation.getAllLoadedClasses()` 找到已加载的 `net.minecraft.*`，
   取它的 loader；若 loader 是 `cpw.mods.cl.ModuleClassLoader`，反射它的模块表，
   解析 `union:<jar>%23...!/` 里的真实 jar 路径，枚举后逐类 `Class.forName`。
   —— 优点：不重启游戏；缺点：依赖 FML 内部结构。

2. **转换器直驱**（最干净）
   在构建期 JVM 里用 ModLauncher 的 `ILaunchPluginService` /
   `ITransformerService`，对源 jar 的每个类直接调用转换，不加载类、不启动游戏。
   —— 优点：确定性、可离线；缺点：要摸清 ModLauncher 的初始化顺序。

3. **加载器白盒**（兜底）
   在 agent 里替换/包装 `ClassLoader.defineClass`（不能用 retransform 的场景），
   或对 `ModuleClassLoader` 注入自定义 `loadClass` 钩子，遍历其资源表。
   —— 优点：一定拿得到；缺点：侵入性最强。

B0 先做 1，失败立刻转 2；3 只在 1、2 都证明不可行时用。

## 5. 仓库与命名

- 主仓：`AOTFASTLNX/NativeCraftLauncher`（原 `AOTFASTLNX/MCFAO`，已改名，旧地址 301）
- CI 仓：`zhangrongxue/mc-aot-ios`，B1 分支 `build/b1-n0`
- 文档：本文件与 `docs/B1_N0_RESULT_2026-11-15.md`
- 本轮需同步的旧名引用：`.circleci/config.yml`、`ci/build_mac.sh`、`ci/build_sim.sh`、
  `ci/circleci/config.yml`、`ci/native-refresh-sign.yml`、`ci/snapshots/*`、
  4 篇 docs、`A1_VERSION.json`（共 12 个文件）

## 6. 下一步（立刻可做）

1. 仓库改名引用批量更新（12 个文件），避免后续 CI 依赖 301。
2. B0 候选 1 的探针：在 agent 里用 `Instrumentation` 锚点 + 模块表反射，
   输出「完整类集合」的统计与缺口清单。
3. 探针通过后，把产物接入 A1 的 AOT 工具链，进入 B1（原版客户端到主菜单）。
