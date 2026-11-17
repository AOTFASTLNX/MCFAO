# B1 · mod 构造层：359/467 成功（2026-11-17 深夜）

## 本轮结果

| 指标 | 数值 |
|---|---|
| `@Mod` 入口类 | 467 |
| **构造成功** | **359（77%）** |
| 构造失败 | 106 |
| 客户端 | 构造完成后继续进入 `Minecraft.<init>`，随后被 FoolProof 的崩溃装饰器挡住（真实异常未落盘） |

日志原文：`[b1] constructed 359 mods, 106 failed, 467 listed`

## 为达到这一点补齐的 FML 容器层

| 类 | 作用 |
|---|---|
| `B1ModInfo` | `IModInfo` 实现：modId / version / namespace / 依赖（空）/ logo（空） |
| `B1ModContainer` | `ModContainer` 子类：持有自己的 `B1EventBus` |
| `B1EventBus` | `IEventBus` 空实现（注册即吞掉，`post` 原样返回） |
| `ModConstruction` | 按构造器签名给 mod 传 `(IEventBus, ModContainer, IModInfo, Dist)`，逐个 try/catch 并统计 |

顺带修掉的两个硬问题：

1. **构造时机**：必须在 `SharedConstants.tryDetectVersion()` **之后**、`Bootstrap.bootStrap()` **之后**，
   否则 `DataFixers` 报 "Game version not set"、`BuiltInRegistries` 无法初始化；
2. **JVM 对照台 classpath 污染**：`stage/` 目录里残留过一份完整的游戏类副本（含整合包自带的
   LWJGL snapshot），导致类加载与原生库版本错配。清空后改用**原始图谱目录**（`graphdir`）＋
   overrides，问题消失。

## 一个有趣的卡死

`com.memorysettings.MemorysettingsMod` 在构造器里弹 **模态对话框**（`tinyfd_messageBox`），
自动化运行时永久阻塞。线程栈一眼可见，已加入跳过名单。

## 下一步

1. 把 FoolProof 的崩溃头部装饰器绕开（或给 `ConfigBase$CValue` 补一个可用的 `ModConfigSpec`），
   让真实异常落盘——现在所有失败都被它掩盖；
2. 继续收敛剩下 106 个构造失败的 mod（多数是缺 FML 生命周期 API）；
3. 主菜单之后再做资源/声音/iOS。

## 状态（诚实口径）

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM 原版启动） | ✅ |
| 静态运行期 → 窗口 + GL + 资源 + 主循环 | ✅ |
| 静态运行期 → mod 构造 | 🟡 **359/467** |
| 静态运行期 → 主菜单 | ⏳ 被崩溃装饰器掩盖，待取真实异常 |
| iOS | ⏳ 未开始 |
