# B1 · mod 构造层的第一版（2026-11-17 夜）

## 本轮做了什么

上一轮定位到"FML 没构造任何 mod 实例"。这一轮把**构造层**搭起来了：

| 组件 | 内容 |
|---|---|
| `gen_mod_entries.py` | 正确解析 class 文件里的注解（含 element_value 递归），扫出 **467 个 `@Mod` 类** |
| `B1EventBus` | `IEventBus` 的空实现（mod 构造时会往上注册监听器） |
| `ModConstruction` | 读取 `b1-mod-entries.txt`，按构造器签名 `(IEventBus, ModContainer)` / `(IEventBus)` / `()` 依次尝试实例化，每个都用 try/catch 兜住 |
| `ClientMain` | 启动时先跑一遍 `ModConstruction.construct()` |

## 效果与限制

- 构造流程**跑通了**（470 个类逐个尝试，日志里能看到谁成功、谁失败）；
- 但不少 mod 的构造器里会调用 FML 的 API（事件总线之外的），于是抛 `InvocationTargetException`：
  例如 Aether 系列（`com.aetherteam.aether.Aether` 等）。
- 同时 JVM 对照台上出现了 LWJGL 版本混用的报错（graph 里的 3.4.3 与 classpath 上的 3.3.3 同时存在），
  说明**对照台的 classpath 需要固化**，否则会在无关的地方翻车。

## 结论

"构造 mod 实例"这件事本身可行，但**mod 构造器依赖的 FML API 面积比预想大**：
事件总线只是第一层，后面还有 `ModContainer`、`IModInfo`、注册表事件、配置系统……
这印证了上一轮的判断：**A 路线（真正实现 ModList 容器层）是唯一可持续的路**，逐个打桩不可行。

## 下一轮计划

1. 补 `ModContainer` / `IModInfo` 的最小实现（mod 构造器最常碰的两个类型）；
2. 把 JVM 对照台的 classpath 固化成脚本（避免版本混用）；
3. 重跑，统计"467 个 mod 里有多少个能构造成功"，用这个数字衡量容器层完成度。

## 状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM 原版启动） | ✅ |
| 静态运行期 → 窗口 + GL + 资源 + 主循环 | ✅ |
| 静态运行期 → mod 构造（467 个入口） | 🟡 框架就绪，FML API 待补 |
| 静态运行期 → 主菜单 | ⏳ |
| iOS | ⏳ |
