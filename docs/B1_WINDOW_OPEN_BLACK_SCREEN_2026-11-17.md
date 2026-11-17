# B1 · 静态运行期打开了 NeoForge 客户端窗口（2026-11-17 夜）

## 证据

窗口标题：**Minecraft NeoForge* 1.21.1**，进程常驻 947 MB，渲染线程持续工作
（日志里能看到 `TextureAtlasStitchedEvent`、`ModelEvent$BakingCompleted` 等渲染期事件）。

截图（黑色区域说明渲染尚未呈现，见下）：`docs/evidence-b1-window-2026-11-17.png`

## 这一轮跨过的两道坎

| # | 现象 | 修法 |
|---|---|---|
| 1 | 崩溃报告被 FoolProof 的头部装饰器覆盖（`ConfigValue.getRaw` 在配置未加载时抛 `IllegalStateException`），真实异常永远看不到 | 用"默认值容错版"替换 `ModConfigSpec$ConfigValue`（单独替换内嵌类，不动外层类） |
| 2 | 文本渲染时 `ICU UBiDiProps` 空指针（`ubidi.icu` 资源缺失） | 把 `icu4j-73.2.jar` 加到运行期 classpath |
| 3 | 没有日志后端，所有异常被吞 | 加 `log4j-core` + `log4j-api` |

## 现在的真实状态

- ✅ 窗口：标题、尺寸、句柄都正常（`Minecraft NeoForge* 1.21.1`）
- ✅ 渲染线程：在跑，纹理图集、模型烘焙都有日志
- ⛔ **画面全黑**，原因很明确：

```
Cowardly refusing to send event ... to a broken mod state   （40 次）
```

FML 的 `ModLoader` 认为每个 mod 都是 "broken"（因为 `ModList` 里没有真正的容器），
于是**拒绝派发所有客户端事件**；mod 的客户端初始化不执行，界面自然画不出来。

## 下一步（明确的下一步）

1. `B1EventBus` 从"吞掉一切"改成**真的注册和派发**（按事件类型存 listener，`post` 时调用）；
2. `ModList.getMods()` 返回真实的容器列表，让 `ModLoader` 不再认为 mod 是 broken；
3. 事件派发通了之后，主菜单应该能画出来——那时才谈得上"可玩"。

## 状态（诚实口径）

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM 原版启动） | ✅ |
| 静态运行期：注册表 / 资源 / GL / 窗口 | ✅ |
| 静态运行期：mod 构造 | 🟡 360/467 |
| 静态运行期：**窗口 + 渲染线程活动** | ✅ 本轮 |
| 静态运行期：**主菜单画面** | ⛔ 事件派发被 FML 判定 broken |
| iOS | ⏳ 未开始 |
