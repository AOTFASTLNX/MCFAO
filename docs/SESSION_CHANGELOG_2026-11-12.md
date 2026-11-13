# 改动日志：pack-91 → pack-92、功能探针与未签名 IPA

> **边界声明**：本文解释的是提交 `43bcd36`（"Extend closed-world Fabric AOT through pack-92 and export an
> unsigned IPA"）里**我这一轮做的判断和改动**。该提交是一次**整树快照**——工作区里还躺着 11-10 到 11-12
> 之间多轮会话留下的未提交成果（Metal 管线门禁、分割器、反射配置、13 个诊断探针、大部分 tools/tests），
> 它们随这次提交一起入库，但**不是这一轮写的**，§10 单独列了清单，避免把功劳/责任算错。
>
> 提交之后分支上又多了 `e23d7b5`（末地加载崩溃，另一轮会话）和一批未提交改动（Mod catalog / 内容采样），
> 那些同样不属于本文范围。

---

## 0. 一句话

接手时 pack-91 的"Jade 修复"**一行都没执行过**——哈希钉错让审计闸门把整个 Jade 排除出了包；修好哈希后，
同一段改写里还埋着三个会立刻炸的缺陷（`ALOAD 1`、缺 `optionalModName` 生成、`maxStack` 覆盖）。
四处全修后 pack-92 完成冒烟与交互探针，拿到第一条 `FUNCTION_PASS`；顺手做了未签名 IPA 导出。

---

## 1. 接手时的事实

我先把 WorkBuddy 里那条对话的完整 transcript 读出来（`~/.workbuddy/projects/…/7ee35aa7-….jsonl`，6202 行），
再对照仓库，得到三个互相独立的事实源：

| 来源 | 给出的信息 |
| --- | --- |
| transcript 末尾 | 最后一条真实指令是"总结目标、已完成、方法、注意事项，交接给 dsh"，但两次尝试都撞 429，**交接文档没写出来**；pack-91 的构建命令发出后没有后续 |
| `artifacts/mcfao/fabric-pack-91/result.json` | `SIGNED_DEVICE_APP`，14:33 完成，**没有 `-simulator` 目录**→ 从未冒烟 |
| `docs/C0_FABRIC_HANDOFF.md` + `docs/STATUS.md` | 台账停在 pack-88/89；`FUNCTION_PASS = 0`；用户约定"只用模拟器验证、不问问题、每轮新编号" |

结论：**不能从"上一个包构建成功"直接续跑**，先得确认 pack-91 到底改成了什么。

---

## 2. 诊断：为什么 pack-91 的"修复"是空的

### 2.1 静态校验先露头

`verify_aot_classpath.py --verify-members` 报 `204/52318` 不可加载，其中唯一的核心类失败是：

```
net.fabricmc.loader.api.ModContainer → ClassNotFoundException: ...metadata.ModOrigin
```

而 pack-90 的分类数是 **52727**。少了 409 个类。两个数字放在一起说明"有东西整块不见了"，不是链接细节。

### 2.2 从 1 个核心类失败追到"Jade 整包消失"

直接对比两个 pack 的 metal jar 条目：

```
pack-90 vs pack-91:
  only-90 = 463 条
    ├─ 409 个 snownee/**.class
    ├─ 53 个 assets/jade/**
    └─ jade.mixins.json
  only-91 = 0
```

再回读 `fabric/*/product/result.json`，原因写在脸上：

```json
"excludedMods": {
  "jade": ["Unaudited Jade loader metadata lookup: 1e4f14565ec8…"]
}
```

`RuntimeLowering.lowerLoaderMetadata` 的第一行是哈希审计，`sourceHash` 与常量不符就抛异常；
`AotExport` 对"改写失败"的策略是**把该 Mod 排除并记账**。所以构建"成功"了，只是少了一个 Mod。

拿真实 jar 验一下哈希来源：

```
sha256(snownee/jade/util/ClientProxy.class) = 1e4f1456…   ← 实际
RuntimeLowering.JADE_CLIENT_PROXY_SHA256   = 0a51a9a0…   ← 钉的
```

**钉的是 class 文件字节的哈希，不是 jar 的哈希**；写错的那一版对不上任何东西。

### 2.3 审计闸门挡住了坏改写，也掩盖了三个 bug

这一点值得单独说，因为它决定了修法顺序：

- 闸门的设计是对的——**未审计的字节码改写就该拒绝**，而不是硬改后祈祷。
- 但它让后三个缺陷**无法被任何测试发现**：改写根本没执行，`optionalModName` 不存在也不会在构建期报错。
- 如果我只把哈希改对就重跑，会在运行期炸；而如果只看"构建成功 + 静态校验通过"，会像 pack-91 一样
  交出一个**少了一个 Mod 的包**。

所以我先把"被挡住的改写"本身审查了一遍。

---

## 3. 修复：五处

| # | 缺陷 | 如果不修的后果 | 修法 | 位置 |
| --- | --- | --- | --- | --- |
| 1 | 哈希钉错（`0a51a9…`） | 审计拒绝 → Jade 被排除，包"成功"但缺 Mod | 换成真实 class 字节哈希 `1e4f1456…`，并在注释里写明是**哪个 jar 里的哪份 class** | `RuntimeLowering.java:96-99` |
| 2 | `ALOAD 1` | 局部变量 1 是 `boolean modMenu`，把它当 `String` 传给 `optionalModName` → 验证失败/类型错乱 | 改为 `ALOAD 0`（`getModName(String id, boolean modMenu)` 的 id） | `RuntimeLowering.java:251` |
| 3 | 生成类里根本没有 `optionalModName` | 改写后调用一个不存在的方法 → `NoSuchMethodError`，而且只有 tooltip 渲染时才触发 | 在 `AotExport` 生成 `optionalModName(String)Optional`：命中表返回 `Optional.of(name)`，未命中返回 `Optional.empty()`（与 Loader 语义一致，Jade 自己会 filter 掉） | `AotExport.java:1721-1741` |
| 4 | `maxStack` 被从 5 改成 1 | 保留下来的 I18n 分支需要 5（`LDC / ICONST_1 / ANEWARRAY / DUP / ALOAD 0 / AASTORE`）→ 栈溢出 | **不再碰 `maxStack/maxLocals`**：只删代码不会让它们变大；同时清掉 `localVariables`（它的区间终点是被删掉的标签） | `RuntimeLowering.java:255-258` |
| 5 | 探针只断言"有表调用"，不断言怎么调 | #2 #4 都能通过原探针 | 增加三条断言：表调用前必须是 `ALOAD 0` 且描述符匹配、`maxStack/maxLocals` 不得被改、`localVariables` 必须清空 | `LoaderMetadataProbe.java:80-108` |

设计取舍：为什么用 `Optional.empty()` 而不是已存在的 `modName(String)`（未知 id 抛异常）？
因为 Jade 的参数来自**方块命名空间**，`minecraft` 不在 Mod 表里是常态；抛异常会把"原版方块"的 tooltip 打死，
而 Loader 对不存在的 Mod 本来就是空 Optional。

---

## 4. 为什么不信单测：真实字节码重放

单元测试用的是**自己拼的合成类**，它恰好没有 `iload_1/ifeq` 头部、也没有真实的帧表，所以：

- `ALOAD 1` 在合成类里能"跑通"（探针只检查有没有调用）；
- `maxStack` 被改小也不会暴露（没人真的执行那个方法）。

所以我另写了一个一次性 harness（没入库）：读**真实** `ClientProxy.class` → 跑改写 → `ClassWriter` 重新序列化 →
再读回来，检查 `MAXSTACK`、`ALOAD 0`、无 `net/fabricmc/loader` 引用。输出：

```
ALOAD 0
INVOKESTATIC mcfao/aot/Entrypoints.optionalModName (Ljava/lang/String;)Ljava/util/Optional;
ARETURN
MAXSTACK = 5   MAXLOCALS = 3
MCFAO_REAL_JADE_PASS returns=2 bytes=30136
```

这一步是这轮唯一能证明"改写真的合法"的证据；`javap` 反编译只能看形状，不能证明可重新序列化。

---

## 5. 构建与验证链

按项目约定**必须换新编号**（`BACKEND_TOOLS` 是构建指纹，同目录续跑会被输入哈希挡住）：

```
./mcfao build --version 26.1.2 --loader fabric \
  --config artifacts/mcfao-local.json --mods artifacts/mcfao/curated-verification-mods-01 \
  --audited-mods --target ios-arm64 --output artifacts/mcfao/fabric-pack-92
```

`fabric` 阶段先核对两件事（这两条是本轮的验收点）：

- `excludedMods` 回到只剩 `entity_model_features`、`net_lenni0451_reflect`（预期内的两个）；
- `staticAdaptations` 里出现 `snownee/jade/util/ClientProxy#getModName(String,boolean) fallback = mcfao/aot/Entrypoints.optionalModName`。

然后整条链：冒烟 → 探针 → 矩阵。

| 步骤 | 结果 | 关键证据 |
| --- | --- | --- |
| 冒烟 | `SIMULATOR_WORLD_SMOKE_PASS` | F1 `game.log:159`、`TEXTURE_FRAME_PRESENTED 2622x1206:377`、`Dev joined the game:1010`、F3 `:1014`；1787 行、崩溃 0；83 条 `[MCFAO_ENTRYPOINT]` |
| Jade 加载 | 三条 addon 插件注册 | `:332-334` `CorePlugin` / `VanillaPlugin` / `UniversalPlugin` |
| 功能探针 | `SIMULATOR_FUNCTION_PROBE_PASS` | 7 张截图；`probe-aim-down` 显示 `Sand` + 蓝字 `Minecraft`，`probe-inventory` 显示 `Service Door` + `Minecraft` |
| 矩阵 | 127 行 | 56 `BUILD_PASS` / 57 `LOAD_PASS` / **1 `FUNCTION_PASS`** / 13 `BLOCKED` |

探针这一格是"能不能宣称功能"的分水岭：**冒烟只证明进了世界，探针证明 Jade 的 tooltip 真的画出来了**。
所以 `docs/MOD_MATRIX_EVIDENCE.json` 里 Jade 从 `LOAD_PASS` 升到 `FUNCTION_PASS`，其余 126 行不动——
没有为了凑数把"能加载"写成"能用"。

---

## 6. IPA 导出：三个决定

用户要"不用签名"的 IPA，所以不能走 `mcfao export-ipa`（它跑 `xcodebuild -exportArchive`，必须有描述文件）。

**决定一：剥掉签名，而不是保留开发签名。**
一份带着别人 Team 的 `embedded.mobileprovision` 的 IPA，重签工具会报"已被其他团队签名"，用户还要先清一遍。
所以删 `_CodeSignature/`、`embedded.mobileprovision`，并对每个 Mach-O 跑 `codesign --remove-signature`。

**决定二：打包前先核对 app 与构建清单逐字节一致。**
`tree_files(app) != appFilesSHA256` 就直接拒绝——否则"我导出的 IPA"和"我验证过的构建"可能不是同一个东西。

**决定三：拒绝 `__MACOSX` 条目。**
第一版用 `ditto --sequesterRsrc` 出了 10,431 个条目，其中 5,000+ 是 `__MACOSX/._*` 资源叉。
换成 `--norsrc` 后 5,084 个条目，并在工具里加断言：IPA 里一旦出现 `__MACOSX` 就报错。

产物：`C0Harness-unsigned.ipa`，602,702,176 字节，sha256 `502c6b8c…`，
`codesign -dv` 报 `code object is not signed at all`，`vtool` 确认 `platform IOS / minos 17.0 / arm64`。

**口径**：导出 IPA ≠ Gate D2 通过。`deviceRun` 仍是 `NOT RUN`，安装与存档保留没做，README 里写明了。

---

## 7. 文档与仓库卫生

- `docs/STATUS.md` 追加 "pack-89 → 92" 一节（`docs/STATUS.md:454`）：记录三轮各自清掉的崩溃点、
  pack-91 的四个缺陷、以及冒烟/探针的数字。**没有把 pack-91 写成"修复成功"**，而是明确标注"该轮包无效"。
- `docs/C0_FABRIC_HANDOFF.md` 顶部加"晚间更新"块（`:14`），让下一个接手的人先看到最新包与 IPA，
  而不是从 pack-87 的状态读起。
- `.gitignore` 增加 `/config/`：那是模拟器跑 Mod 时写出来的 ETF 配置，不是源码（已在 docs 里作为"空配置"
  证据被引用，但文件本身不该入库）。
- **PII 处理**：仓库是 public 的（`AOTFASTLNX/MCFAO`）。`artifacts/evidence/` 里 4 个 `stdout.log`
  早在 `e337d0b` 就含个人邮箱与证书名——这个已经发生，只能改历史清。我这轮新增的文档原本又复制了两处，
  已替换成 `<redacted-email>` / `<redacted-cert-id>`，不再增加暴露面。

---

## 8. 我判断错/被工具骗的地方（自纠清单）

写出来是因为这些坑比"改对了什么"更有复用价值：

1. **差点把 pack-91 当成有效包**。它 `status = SIGNED_DEVICE_APP`、静态校验"只有 1 个核心类失败"，
   单看这两条很像"可冒烟"。是"分类数少了 409"和 `excludedMods` 把它拽回来的。
   → 以后每轮先看 `excludedMods` 与 class 总数是否与上一轮连续。
2. **第一版 IPA 多出 5,000+ 个 `__MACOSX` 条目**，体积 604 MB；`--norsrc` 后 602 MB、5,084 条目。
3. **探针工具的"缺附件"是假警报**：`xcresulttool` 导出的是 UUID 文件名，测试标签在
   `suggestedHumanReadableName` 里；旧代码拿 UUID 去匹配 `probe-*`，7 张图全被判缺失。
   修完补了 2 项回归（重名不得互相覆盖）。
4. **`maxStack` 不能顺手改**：原值 5 是 javac 为整个方法算的，删代码只会让它"够用"，写死 1 反而制造验证错误。
5. **合成类的单测会给出虚假的安全感**：它绕开了真实帧表和局部变量布局，正是三个 bug 的藏身处。

---

## 9. 明确没做的事

- **没在真机跑过**：`deviceRun = NOT RUN`，Gate C1/C2、Gate D 的安装/存档保留全部未做。
- **没有把 `FUNCTION_PASS` 批量刷上去**：只有 Jade 有截图证据；Entity Culling、ImmediatelyFast 这类
  性能 Mod 用截图证明不了，矩阵里维持 `LOAD_PASS`。
- **没有修 pack-91 那个包**：它缺 Jade，保留原样作证；有效的是 pack-92。
- **没有改 git 历史**清 PII：那是另一件事，需要用户拍板。

---

## 10. 提交里"随带入"的改动（不是我这一轮写的）

`43bcd36` 是整树快照，以下按区域列清楚，方便 review 时分流：

| 区域 | 随带入的内容 | 来源轮次 |
| --- | --- | --- |
| `compiler/metal-backend/` | `BundledPipelines` + `MetalDevice/RenderPass/ShaderIndex`：管线 bundle 门禁，不支持的管线标 `skipped`、`close()` 无条件释放 activePass | pack-85 |
| `compiler/splitter/` | `MethodSplitter` 的方法拆分调整 | 更早 |
| `compiler/reflection-config.json` | 配置/序列化反射条目（133 → 142） | pack-83 前后 |
| `interop/diagnostics/*.java` | 13 个探针：AppleSkin 配置、Args 行为、配置发现、导出生成、Fabric API 闭包、GlitchCore 事件、ImmediatelyFast、Indigo 门禁、Mod 文件/命名空间、管线门禁、序列化根 | pack-77 → 91 |
| `interop/fabric/tool/mcfao/aot/` | `GenericVertexSerializer`、`ModFiles` 运行期 overlay | 更早 |
| `ios/glfw-lite/`、`interop/graphics/glfw_state_test.c` | `mouseButtons[8]` 轮询状态 + fixture | pack-89 |
| `ios/C0Harness/WorldUITests.m` | `testFabricModFunctions` 交互脚本 | pack-89 |
| `tools/`（除本轮 3 个） | 矩阵生成、证据扫描、AOT classpath 校验、闭包校验、配置反射、去重、调用树诊断等 | 多轮 |
| `tests/`（除本轮 2 个） | 对应上述工具/改写的回归 | 多轮 |
| `docs/BUILDING.md`、`FABRIC_AOT.md`、`GRAPHICS_BOOTSTRAP.md` | 累积文档更新 | 多轮 |
| `logs/*` | 11-08 的构建日志（已在仓库历史里） | 更早 |

本轮实际新增/修改：`RuntimeLowering.java`、`AotExport.java`（仅 `optionalModName` 生成）、
`LoaderMetadataProbe.java`、`tools/package_unsigned_ipa.py`（新）、`tests/test_package_unsigned_ipa.py`（新）、
`tools/function_probe_simulator.py`（附件命名）、`tests/test_function_probe_simulator.py`（+2）、
`.gitignore`、`docs/STATUS.md`、`docs/C0_FABRIC_HANDOFF.md`。

---

## 11. 建议的下一步

1. **把真实字节码重放固化成测试**：`skipUnless` 检测 `artifacts/mcfao/curated-verification-mods-01/Jade*.jar`
   存在时，从 jar 里取 `ClientProxy.class` 跑一遍改写并断言 MAXSTACK/ALOAD/可序列化。这样哈希钉错或
   上游 Jade 更新会在单测阶段就暴露，而不是"构建成功但少一个 Mod"。
2. **让"排除 Mod"变成构建失败的显式选择**：`excludedMods` 是诚实的记账，但它太安静；
   至少应在构建摘要里把"排除数变化"标成红色。
3. **探针扩容**：现在只覆盖"能看到的功能"。要证明配方查看、按键、HUD 类 Mod，需要给 `WorldUITests`
   加更多交互（例如打开配方书、按快捷键），并把每一步的断言写成不依赖像素比较的结构化检查。
4. **真机**：IPA 已经能装（需自签），但 `deviceRun` 必须真的跑一次才算 Gate C/D 有进展。
