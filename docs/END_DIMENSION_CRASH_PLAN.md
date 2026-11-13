# 末地加载崩溃调查与修复路线

复核日期：2026-11-12。调查阶段仅静态读取类文件、反汇编与核对工件。随后用户要求实施修复、生成签名 IPA，并明确运行测试由用户完成。

## 实施进度

- 已在 `compiler/reflection-config.json` 加入下述 11 个精确构造注册，构建输出目录为 `artifacts/mcfao/fabric-pack-93-end-fix/`。
- 新旧输入清单中的 Mod 哈希与配置相同。新 AOT 有效反射元数据由 138 条增至 149 条；全部 11 个精确构造注册在最终合并后保留。
- 原生编译、iPhoneOS 链接、签名归档和 IPA 导出已完成；`artifacts/mcfao/fabric-pack-93-end-fix-signed-ipa/result.json` 为 `DEVELOPMENT_IPA_VERIFIED`。IPA 为其 `export/FabricAOT World.ipa`，SHA-256 `649f7ae114093c246a013c0dca6d5d2093f8d1364f9f407b70bba8a5eecf8b70`。交付记录在同目录 `end-fix-handoff.json`。助手按用户要求未运行游戏、模拟器或测试套件。用户于 2026-11-12 对交付包复测后明确确认“确实修好了”；本次末地加载闪退已获用户真机确认。完整战斗、复活和长时稳定性未获得逐项反馈，仍待独立验收。
- 下述静态防漏检查器、配置合并改进和场景探针属于后续加固路线，本次没有实施。

## 故障链路

以用户更正为准：本轮仍在加载界面闪退，未看到末地地形。`run-1794486723800.log` 中，12:33:58 客户端为 `WaitingForPlayerChunk`、`ready=false`；12:33:59 内置服务器创建龙失败：

```text
NoSuchMethodException: net.minecraft.world.entity.boss.enderdragon.phases.
DragonHoverPhase.<init>(net.minecraft.world.entity.boss.enderdragon.EnderDragon)
```

调用链：`EnderDragonFight.tick → findOrCreateDragon → createNewDragon → EnderDragon.<init> → EnderDragonPhaseManager.<init> → setPhase(HOVERING) → getPhase → EnderDragonPhase.createInstance → getConstructor`。随后以 `Exception ticking world` 传播到客户端，日志最后生成 Minecraft 崩溃报告。

**高置信度根因：AOT 未登记龙阶段构造方法的反射调用元数据。** 修复已构建为 pack-93，用户复测确认本次故障解决；该确认限于所报告的末地加载闪退。

## 已完成的核验

原始证据：`artifacts/evidence/end-dragon-20261112/`，其中 `result.json` 保留输入哈希、命令、各阶段类签名、反汇编比较和镜像 UUID；`audit.py` 可用 `python3 -B artifacts/evidence/end-dragon-20261112/audit.py` 重跑。该工具只读输入，不加载或初始化 Mod。用户日志副本及游戏反汇编留在本地忽略目录，不提交。

1. **转换没有破坏这组类。** 原版、Fabric 导出、方法拆分、Metal 注入四个 JAR 中，注册器、阶段管理器和全部 11 个具体阶段的 `javap -c -p` 输出完全相同。11 个公开 `(EnderDragon)` 构造方法都存在。
2. **确实是动态构造。** `EnderDragonPhase.getConstructor()` 从 `instanceClass` 字段取得 Class，再调用 `Class.getConstructor(EnderDragon.class)`；`createInstance()` 紧接着 `Constructor.newInstance(dragon)`。类存在、普通可达或仅查询注册，都不能代替可调用的构造方法注册。
3. **有效元数据缺失。** pack-92 AOT 的 `work/reflection-config.json` 共 138 条，阶段登记 **0/11**；基础配置也没有。有效配置 SHA-256：`bf3ff5a20c04bdab38c18397332798b44b65b1a65bf5c0421cc332275000f477`。
4. **扫描器存在明确覆盖缺口。** pack-92 的 `config_reflection.py` / `probe_client_graph.py` 留存副本与当前源文件相同。前者跳过 `net/minecraft/` 调用方，成员扫描只识别 Method/Field，不识别 Constructor；已有常量启发式也不能追踪注册表字段里的动态 Class。
5. **提供的 IPA 与构建记录对应。** IPA 内游戏镜像与导出 staging 镜像 SHA-256 相同；导出镜像与 pack-92 构建镜像 UUID 都是 `E733734D-AE79-3139-B5D9-E3DC47CDD01B`。完整文件哈希不同，不能宣称导出重签名文件与原文件逐字节相同。设备日志未打印 UUID，因此没有独立验证手机实际安装镜像 UUID。
6. **现有冒烟覆盖不足。** `smoke_mcfao_simulator.py` 在入服/F1/F3 后只再等 3 秒，没有维度切换要求。F3 在这次 `ready=false` 时已出现，不能单独证明末地加载完成。

Native Image 动态反射需要构建时元数据，见 [GraalVM 25 官方文档](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)；本项目固定 Graal 源码的 `DynamicHub.checkConstructor` 也包含查询失败后抛 NoSuchMethodException 的路径。

## 应覆盖的 11 个阶段

以下实现均在 `net.minecraft.world.entity.boss.enderdragon.phases`，构造参数均为 `EnderDragon`：

| 阶段 | 类 |
|---|---|
| HOLDING_PATTERN | DragonHoldingPatternPhase |
| STRAFE_PLAYER | DragonStrafePlayerPhase |
| LANDING_APPROACH | DragonLandingApproachPhase |
| LANDING | DragonLandingPhase |
| TAKEOFF | DragonTakeoffPhase |
| SITTING_FLAMING | DragonSittingFlamingPhase |
| SITTING_SCANNING | DragonSittingScanningPhase |
| SITTING_ATTACKING | DragonSittingAttackingPhase |
| CHARGING_PLAYER | DragonChargePlayerPhase |
| DYING | DragonDeathPhase |
| HOVERING | DragonHoverPhase |

HOVERING 是管理器构造时第一个实例化的阶段，故首先报错。其余 10 个共用同一工厂且都未注册，只修悬停不能覆盖后续战斗。

## 修复路线与通过标准

### 第一步：完整而精确的构造注册

- 在 `compiler/reflection-config.json` 加入全部 11 个精确条目，使用 `methods: [{name: "<init>", parameterTypes: ["net.minecraft.world.entity.boss.enderdragon.EnderDragon"]}]`。本轮生成的候选是 `artifacts/evidence/end-dragon-20261112/proposed-phase-reflection.json`，已接入本次生产配置。
- 保留原版工厂与 AI 时序。当前无需修改图形、龙行为或世界逻辑，也无需全游戏宽泛保留。
- 加入 AOT 前检查：从最终转换 JAR 解析注册器对 `create(Class,String)` 的注册集合，核验类存在、公开构造签名及最终合并配置的可调用覆盖。固定版本预期 11 个；集合或字节码结构变化应明确失败并重新审计。
- 静态检查按调用 owner / name / descriptor 识别，不凭类名后缀或关键字猜测，也不执行注册器静态初始化。
- 测试包含：完整正例、删掉非悬停阶段、错误参数类型、仅查询注册、缺失/非 public 构造、注册器结构变化、普通同名工厂误报。

通过标准：所有注册阶段均覆盖；删掉任何一个构造注册都在 AOT 前失败。

### 第二步：合并配置、重建与真实构造测试

- `probe_client_graph.py` 当前以字典 `update` 合并同类配置，可能替换整个 `methods` 数组。本次阶段未与推导项重名，未证实被覆盖；仍须测试额外成员不会冲掉构造条目。若需修复，按 `(name, parameterTypes)` 合并，不能只按方法名去重重载。
- 用新输出目录重建，核对 `inputs.json`、有效配置和 AOT 命令。`mcfao.py` 已将 compiler 文件与扫描器纳入输入指纹；不得手改旧 checkpoint 或复用旧 AOT 对象。
- 在专用复制世界中添加测试探针：对真实龙逐个调用 `getPhase(getById(i))`，确认 11 个对象类型正确、重复获取返回缓存对象。先做 JVM 对照，再由同一 iOS AOT 运行时验证。此探针只构造阶段，不强制切换活动 AI。
- 若另用第一方小夹具验证元数据机制，必须有无配置失败/补配置成功对照；夹具不能代替真实游戏 AOT 运行。

通过标准：新对象和配置指纹可追溯，真实游戏 AOT 输出逐阶段 11/11 通过；编译成功不能替代此运行结果。

### 第三步：模拟器末地与战斗回归

- 尝试用旧 pack-92 镜像在可丢弃末地世界复现同一异常；不能复现则记录实际结果，不以其他失败代替。
- 新镜像分别验证原版 26.1.2 和当前 Fabric 包，覆盖首次传送进末地、出生点区块可见、移动/交互、龙生成和逐阶段实例化。
- 再覆盖自然战斗的盘旋/攻击/降落/起飞、击败龙、返回主世界、保存退出、冷启动重进末地及复活龙。死亡/复活和存档是独立行为检查，不能从构造探针推断通过。
- 扩展冒烟工具为维度场景：记录明确的末地 ready、区块可见、阶段探针和存活观察结果；首轮至少观察 60 秒。完整战斗另记，不以 60 秒存活代替。
- 每轮保留新进程日志、截图、观察时长和退出状态。

通过标准：原版和 Fabric 包均能稳定在末地操作，11 阶段构造通过，战斗与保存重进有独立证据。

### 第四步：新 IPA 与用户真机复测

从已验证的新对象链接 iPhoneOS 镜像，记录构建编号、UUID、IPA SHA-256 并保留调试符号；维持 Bundle ID，安装前备份测试存档。安装和手机操作仍由用户完成，独立启动验证首次进入、战斗、返回和保存重进。

原包真机末地结果为 FAIL；修复包的本次加载闪退已由用户真机复测确认解决。下述完整场景验证与项目 Gate 分别记账，不将这一反馈提升为 FINAL/COMPLETE/RELEASE。

## 其他问题与范围

- **P0：11 阶段反射闭包；P1：维度场景回归。** 按上述顺序实施。
- **后续反射审计：** 最终 Minecraft 命名空间的构造查询关键字清点命中两类；反汇编确认 `MenuScreens.getConstructor` 只是 Map 工厂，并非 Java 反射。清点不覆盖其他查询 API、库内包装、Mod 注册等，不能宣称全游戏反射已完整；后续审计应带调用 owner/descriptor 与来源。
- **另案处理：** 日志有 minelittlepony 配置读取链的 `MalformedJsonException` 和音频 `AL_INVALID_NAME`，不是最终崩溃链中的异常。Java 堆 used 608 MiB / max 1767 MiB 不能证明原生/GPU内存充足，但本次已有明确 Java 致命异常，应先修此阻断。

调查阶段保留原包；实施阶段仅修改精确反射注册并构建独立新包，现有 IPA 保留。

## 用户复测日志补充（2026-11-12）

用户确认修复后提供 `run-1794489429441.log`。日志在 13:17:42 显示 `ClientLevelReady`、`sectionVisible=true`，最终报告维度为 `minecraft:the_end`，与原加载阻断解除一致；没有原先龙阶段构造查询异常。随后 13:17:43 出现 `kIOGPUCommandBufferCallbackErrorBackgroundExecutionNotPermitted`：`MetalNative.synchronize → mapBuffer → writeUniforms → prepareChunkRenders`，说明发生了后台 GPU 提交拒绝。此前有保存/暂停记录；具体前后台切换动作未知，需另行核对生命周期和渲染同步。这是新的待修问题，不构成末地完整稳定性通过。本地日志副本及指纹见证据目录的 `user-retest.json`。
