# 版本总览与下一步唯一方案

> 时点：2026-11-13 15:50（Asia/Shanghai）。材料来源：`docs/STATUS.md` 台账、各 `artifacts/mcfao/*/result.json`、
> `docs/MOD_ADAPTATION_PLAN.md`、`docs/END_DIMENSION_CRASH_PLAN.md`、真机日志与用户确认记录。
> 本文只做归纳与选路，不替代逐关证据。

---

## 1. 口径

这个项目里"版本"有两层，混着说会算错账：

- **构建版本**：`fabric-pack-NN` / `techreborn-*` / `content-samples-build-NN`，一份 AOT 镜像 + 一个 `.app`。
  一次构建约 2.5–3.6 GB，编号只增不减；历史目录已按记忆文件里的口径清理过，现存 31 个。
- **交付版本**：签好名（或剥好签名）的 IPA，用户拿去真机装。

下面按阶段归纳，代表版本点名，完整逐关记录看 `docs/STATUS.md`。

---

## 2. 七个阶段

| # | 阶段 | 代表版本 / 日期 | 结论（当时真正证明了什么） | 遗留 |
| --- | --- | --- | --- | --- |
| 1 | **工具链门槛** | 11-08，A0/A1/B0/B1 | Java 25 小程序经 GraalVM AOT 成 iOS arm64、签名、在普通 iPhone 无 JIT 启动；Fabric Mixin/入口点能在构建期静态化 | 真机只到"小程序"，不是游戏 |
| 2 | **原版客户端 C0** | 11-09，`main-*` / `metal-*` | 模拟器跑出真实主菜单、建世界、移动、取放/破坏、存档重进；Metal 后端 + GLFW/LWJGL 替身 + 87 条 shader 构建期翻译 | 真机 C0 仍 BLOCKED；C1/C2 NOT RUN |
| 3 | **整包 AOT 底座** | 11-10，pack-43 → 60 | 四个"静默失败"（类不可加载、residue stub、反射缺失、资源不进包）被逐个做成检查；堆从 7G 涨到固定 9G | 每轮都在"构建成功但跑不起来"之间来回 |
| 4 | **逐 Mod 闭包** | 11-11，pack-49 → 86 | 配置反射（AppleSkin/NCR/Chat Heads/ETF）、Indigo 查询、Jade 元数据、Kotlin 入口、Mixin Args、嵌套 JAR、资源命名空间 | 13 个 BLOCKED 收敛完成；玩不到世界 |
| 5 | **整包进世界** | 11-12，pack-87 / 88 | 判据 F1 + F3 + `Dev joined the game` 首次齐现；`[MCFAO_ENTRYPOINT]` 83 条全覆盖，`LOAD_PASS` 58 | 只证明"能进世界"，不证明"能用" |
| 6 | **交互与功能证据** | 11-12，pack-89 → 92 | 交互探针打通（`glfwGetMouseButton` 轮询、Mixin 合成内部类、Jade 元数据改写）；第一条 `FUNCTION_PASS`（Jade 的方块/物品 tooltip）；未签名 IPA 导出 | 127 行矩阵仍是 56 BUILD / 57 LOAD / **1 FUNCTION** / 13 BLOCKED |
| 7 | **真机迭代** | 11-12 晚 → 11-13，pack-93 / techreborn-* / content-samples-build-04→07 | 用户装包实测，按真机日志逐个修：末地龙阶段构造器（**用户确认修好**）、`getModContainer` 空 Optional、`ModCore` 构造器查询、`getEntrypoints`/`getEntrypointContainers` 语义、Mixin 重定位 Guava 闭包 | 每个修复版都只验证到"下一个崩溃点"；内容样本包一次都没跑过；TechReborn 包模拟器卡在 `MTLSimDriver/XPC` signal 6 |

### 2.1 交付过的 IPA

| IPA | 来源构建 | 大小 | sha256（前 16） | 真机结果 |
| --- | --- | --- | --- | --- |
| `fabric-pack-92-unsigned-ipa/C0Harness-unsigned.ipa` | pack-92（41 mod 整合包） | 602,702,176 | `502c6b8c003b0542` | 未签名，未装 |
| `fabric-pack-93-end-fix-signed-ipa/export/FabricAOT World.ipa` | pack-93（末地修复） | 604,164,349 | `649f7ae114093c24` | **用户确认末地闪退修好** |
| `techreborn-signed-ipa-01/…` | techreborn-build-01 | 468,937,911 | `0c5b9b37649c3162` | 真机崩：`RebornCoreClient` 查询为空 |
| `techreborn-interface-signed-ipa-01/…` | techreborn-interface-build-02 | 470,792,773 | `a27a4b43b3a08145` | 待复验；模拟器同包 `signal 6` |
| `content-samples-signed-ipa-01/…` | content-samples-build-04 | 712,626,315 | `d1f7886e08437b2a` | 未跑 |
| （build-05/06/07） | 内容样本 5 mod | — | — | 只到签名归档 `SIGNED_DEVICE_APP`，未导出 IPA、未跑 |

---

## 3. 当前硬事实

**已经证明的：**

1. 闭世界 AOT 能产出可在真机安装启动的 arm64 iOS App（多次真机启动、末地修复经用户确认）。
2. 41 mod 整合包在模拟器能进世界并完成 7 步交互，Jade 的 tooltip 有截图证据。
3. 内容样本包（TechReborn / BetterEnd / BetterNether / BOP / YUNG's Better Dungeons，12 根 + 80 嵌套，89 个选中 ID）能完整转换、AOT、链接、签名，五个主模组都没被排除。
4. 285 项回归测试通过（最近一次记录）。

**没有证明的（不要当成"快好了"）：**

1. **没有任何一个玩法 Mod 的功能验收**。唯一 `FUNCTION_PASS` 是 Jade 的 tooltip。
2. **内容样本包一次都没进过世界**；build-07 之后全是"签名通过、真机待验"。
3. **存档往返、音频、长时间稳定性、性能**全部 NOT RUN。
4. **模拟器上 TechReborn 包的 `MTLSimDriver/XPC` signal 6 根因未定**——它可能是模拟器 Metal 驱动问题，也可能是我们的命令提交 bug，现在无法区分。
5. Gate C/D/E 按 `docs/ACCEPTANCE.md` 仍是未通过状态。

---

## 4. 一条明确的方案：ABI 闭包门禁

### 4.1 为什么是这条

把最近六次真机崩溃排在一起看，它们不是六个 Mod 的问题，是**同一类问题的六个样本**：

| 真机现象 | 实际缺口 | 性质 |
| --- | --- | --- |
| `RebornCoreClient` `Optional.get` 空 | `getModContainer(id)` 被降级成空 Optional | 语义错 |
| `ModCore(String,String)` 抛错 | 构造器里的查询表达式没被识别，被 residue 替换 | 覆盖缺 |
| `DatapackRegistryBuilderImpl` 强转失败 | `getEntrypoints` 与 `getEntrypointContainers` 被当成同一个 | 语义错 |
| `ImmutableList` 找不到 | Mixin 重定位后的 Guava 命名空间没进包 | 供给缺 |
| 末地龙 `NoSuchMethodException` | 反射元数据没登记构造器 | 元数据缺 |
| Fabric API 私有方法残留 | 改写没有覆盖私有签名 | 覆盖缺 |

共同点：**都是"某个 Mod 调用了 Fabric 平台 API 的某个成员，而我们的静态运行时对这个成员的供给缺失或语义不符"**。
现在的发现方式是"用户装机 → 崩 → 看日志 → 补一个"，所以永远滞后一轮。

结论：把发现机制从"真机试错"前移到"构建期差集"。这是一条能收敛的路；继续一崩溃一 IPA 不会收敛。

### 4.2 六步

**Step 0 · 冻结输入**
以 `artifacts/mcfao/content-samples-01`（89 个选中 ID）为唯一验收输入，不再边修边加 Mod。

**Step 1 · 生成 demand set（需求集）**
扫描包内全部类（含 80 个嵌套 JAR）常量池里的 `Methodref / InterfaceMethodref / Fieldref`，
筛出 owner 属于 Fabric 平台面的引用：

```
net/fabricmc/loader/api/**        Loader 元数据、容器、入口点
net/fabricmc/api/**               环境/模组容器接口
net/fabricmc/fabric/api/**        Fabric API 服务接口（事件、注册、网络、资源）
```

记录 `(owner, name, descriptor)` + 调用者类 + 从入口点出发是否可达。
产物：`abi-demand.json`。**只算可达成员**，否则 Loader API 面太大，永远补不完。

**Step 2 · 生成 supply set（供给集）**
把静态运行时的实现登记成成员级清单：`mcfao.aot.Entrypoints`、`ModCatalog`、`ModSnapshot`、
资源层、以及 lowering 把调用改写到这些类的映射。产物：`abi-supply.json`。

**Step 3 · 差集即门禁**

```
demand − supply ≠ ∅  →  构建失败
```

失败信息必须能直接定位：缺哪个成员、被哪个 Mod 的哪个类调用、调用链是否可达。
同时：**可达路径上的 residue stub 一律失败**；不可达的进白名单，写明"为什么不会走到 + 什么条件下复查"。

**Step 4 · 语义等价测试**
每补一个成员，配一条差分测试：同一条调用，在**参考 Fabric Loader 0.19.3（JVM）**与**我们的静态实现**
上返回/异常/副作用一致。重点覆盖四类语义：

- Optional 空 vs 非空（`getModContainer` 这类）；
- 身份与缓存（同一个 Mod 的容器是否同一实例）；
- 顺序与枚举（`getAllMods`、入口点容器顺序）；
- 资源（内置包注册、namespace、reload）。

**Step 5 · 流水线**
差集归零 → AOT → 模拟器冒烟 → 真机冒烟 → 功能断言。每一级失败都不允许下一级开始。

**Step 6 · 功能断言**
每个玩法 Mod 至少一条"状态断言"，而不是截图猜：机器耗能产出、维度加载完成、GUI 打开后条目数、
配方查询命中。真机上跑，日志进 `artifacts/evidence/`。

### 4.3 完成判据（可直接检查）

1. `content-samples-01` 的 `demand − supply = ∅`，且可达 stub = 0。
2. 五个内容 Mod 全部进世界，且各有 ≥1 条真机功能断言。
3. 连续 3 次真机冷启动无新崩溃（同一崩溃复现不算新）。
4. 全量测试通过，且 `grep -rn '"techreborn"\|"betternether"' interop/ compiler/` 找不到按 Mod id 的特判——
   所有修复都按 **API 成员**触发。
5. 存档往返（退出→重进）在真机上通过。

### 4.4 明确不做

- **不再"一崩溃一 IPA"**：每次修复必须先落到 demand/supply 差集里，再出包。
- **不用 stub / 空 Optional 换绿灯**：语义不符比崩溃更危险，因为它会把错误推迟到存档或玩法深处。
- **不在门禁跑通前扩 Mod 列表**：内容样本包已经是 5 个玩法 Mod + 80 个嵌套库，够暴露机制问题了。
- **不用模拟器结果代替真机**：`MTLSimDriver` 那个 signal 6 就是例子——模拟器 Metal 与真机 GPU 路径不同，
  它可以帮你发现逻辑错误，但不能证明真机可玩。

---

## 5. 风险与回退

| 风险 | 影响 | 回退 |
| --- | --- | --- |
| demand set 太大，补不完 | 门禁长期红，无法出包 | 用可达性过滤 + 按"首次启动路径"分批；先关 `startClient` 之前可达的成员 |
| 参考 Loader 差分环境搭不起来 | Step 4 退化成人工核对 | 复用已有的 B0/B1 JVM 基线（`artifacts/b0/prepared-04`），它本来就能跑真实 Loader |
| 真机验证依赖用户时间 | 反馈周期以小时计 | 做一个"一键收日志"的脚本，用户装完点一次就把 `run-*.log`、崩溃报告、截图拉回来 |
| 模拟器 Metal signal 6 是真 bug | 阻塞模拟器回归 | 先用真机作为唯一验收通道；同时用 `MTLCaptureManager` 抓命令缓冲定位，不阻塞 ABI 工作 |

---

## 6. 一句话

**把"用户装包才发现的 Fabric API 缺口"变成"构建期就能算出来的差集"，在这条门禁归零之前，不再出新的 IPA。**
