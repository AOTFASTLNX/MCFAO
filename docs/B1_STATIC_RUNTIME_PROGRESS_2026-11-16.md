# B1 · 静态运行期原型进展（2026-11-16 上午）

## 现在能跑到哪一步

`BootstrapSmoke`（native-image，205 MB）**已经在镜像里执行真正的 Minecraft 启动逻辑**：

```
B1 static-runtime bootstrap smoke
net.minecraft.server.Bootstrap.bootStrap()   ← 真的在跑
```

一路上推掉了三层障碍：

| 层 | 现象 | 处理 |
|---|---|---|
| 1 | `ModernFix.ManifestCompactor.compactManifests()` NPE（Mixin 注入到 `Bootstrap.bootStrap`，扫描 mod jar 清单） | 用 overrides 层替换成空实现 |
| 2 | `Entity Texture Features`：`FMLPaths.GAMEDIR.get()` NPE | 启动前调 `FMLPaths.loadAbsolutePaths(tmpGameDir)` |
| 3 | `BMCPaleGardenPatcher.<clinit>` → `isModLoadedWithMinVersion` NPE（查 ModList） | **未解决**，下一步 |

## 为什么卡在 ModList

NeoForge 的 mod 静态初始化普遍会问：
`ModList.get().isLoaded("xxx")`、`ModList.get().getModContainerById(...)`、`ModLoader.getModLoader(...)`。

在真实启动里这些由 ModLauncher 建好；在镜像里 `ModList.get()` 是 null，于是任何 mod 的 `<clinit>`
里一查就 NPE。这不是单个 mod 的问题，是**所有 mod 都会踩**的环境缺口。

## 下一步的设计（B3 的核心）

在静态运行期里实现一个 **最小 FML 环境 shim**，在 `Bootstrap.bootStrap()` 之前完成：

1. **ModList**：从整合包的元数据（每个 jar 的 `META-INF/neoforge.mods.toml`）生成
   `ModFileInfo` / `ModContainer` 列表，注入 `ModList.INSTANCE`（反射）；
2. **ModLoader / ModFile**：提供只读实现，`getModFiles()` 返回上面那份；
3. **ModStateManager**：初始化状态置为 `LOADED`，避免 mod 以为自己在跑之前；
4. 把这三件事做成 `StaticRuntime.bootstrap()`，由入口在任何 mod 静态初始化之前调用。

这样 `ModernFix`、`ETF`、`BMCPaleGardenPatcher` 这类查询都能拿到合理答案，而不是 null。

## 验收标准

| 步 | 验收 |
|---|---|
| 本轮 | 镜像能执行 `Bootstrap.bootStrap()`（已完成，跑到 mod 静态初始化） |
| 下一个 | `blocks/items/entities` 数量打印出来（注册表全部注册成功） |
| 再下一个 | 在 macOS/Windows 上用同一份图谱链接真实客户端入口（需要 GPU） |

## 工件

| 工件 | 位置 |
|---|---|
| 图谱 v3（111,452 类） | 私有 release `b1-client-graph3` |
| overrides 层 | 私有 release `b1-overrides`（`ManifestCompactor` 空实现） |
| CI | `zhangrongxue/mc-aot-ios` 分支 `build/b1-n0`，作业 #183 / #184 |
| 冒烟源码 | `b1/n05/BootstrapSmoke.java` |
