# B1 · 静态运行期跑进 Minecraft 主循环（2026-11-17 傍晚）

## 里程碑

用 JVM 对照台，BMC5 的客户端**真的跑起来了**：

```
[b1] created window 1280x720 handle=0x...
Minecraft.run() → runTick() → Minecraft.tick() → MusicManager.tick()
```

也就是说：窗口建好、GL 上下文可用、资源加载、注册表、mod 混入全部生效，
**已经进入 Minecraft 的主循环**。现在挂在一个 mod 的静态单例上：

```
AudioImprovements.getInstance() == null
  → Config.<clinit> NPE → MusicManager.tick 抛异常
```

## 这一轮补的两块

| 块 | 内容 |
|---|---|
| 资源层 | 从 350 个 mod jar 抽出全部非类资源（**141,737 个文件 / 474 MB**）做成 `resources.jar`；加上游戏本体资源 jar（8,448 个 assets）后，`blit_screen.json`、Iris 图片等都能找到 |
| 依赖层 | 把 JNA 5.14 放回 classpath，`darkwindowbar` 等 mod 的 JNA 调用不再缺类 |

## 现在的真正缺口：FML 的"mod 构造"

`Minecraft.run` 之所以中断，是因为 **FML 没有构造任何 mod 实例**：

- `ModList.getMods()` 在我们的 shim 里返回空；
- 所以 `ModLoader.constructMods` 不会构造任何 `@Mod` 类；
- 于是 `AudioImprovements.getInstance()` 之类的单例始终是 null。

这不是资源问题，也不是 GL 问题，而是**静态运行期还缺 FML 的 mod 容器层**。

## 两条可选路线

| 路线 | 做法 | 代价 |
|---|---|---|
| A. 补 ModList 容器层 | 从每个 jar 的 `META-INF/neoforge.mods.toml` 生成 mod 元数据资源 → 构建真正的 `ModContainer` → 让 `constructMods` 正常构造 | 1–2 天，但一劳永逸 |
| B. 逐个 mod 打桩 | 每个崩的 mod 写一个最小实现 | 350 个 mod，不可持续 |

**建议 A**：这是"静态运行期"与"真实 FML 启动"之间最后一块结构性差距。

## 本轮新增的工具（可复用）

| 工具 | 作用 |
|---|---|
| `build_resources_jar.py` | 把全部 mod 的非类资源打包成一个 jar |
| `gen_singletons.py` | 扫描带静态单例的类（1,702 个） |
| `gen_mod_entries.py` | 扫描 `@Mod` 注解类（当前解析为 0，需要修） |
| `collect_agent_configs.ps1` | 用 native-image agent 采集配置（未完成，agent 需要正常退出） |

## 状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM 原版启动） | ✅ |
| 静态运行期 → 注册表 | ✅ |
| 静态运行期 → 窗口 + GL + 资源 + 主循环 | ✅ **本轮** |
| 静态运行期 → 主菜单（无需 mod 容器） | ⏳ 缺 mod 构造层 |
| iOS | ⏳ |
