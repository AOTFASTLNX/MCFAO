# B1 · 客户端图谱与客户端镜像冒烟（2026-11-16）

## 1. 客户端图谱已拿到

CI 的 macOS 机器没有 OpenGL，客户端起不来，所以图谱改在**本机**采集：

| 项 | 值 |
|---|---|
| 采集方式 | 本机 Windows 启动 BMC5（NeoForge 21.1.250 / MC 1.21.1），`-Xmx6G` + dumpagent |
| 前置修复 | 禁用 FancyMenu 与 Drippy Loading Screen（见 `B1_BMC5_LOCAL_PLAYABLE_2026-11-16.md`） |
| 类总数 | **72,571**（dump 目录 317 MB） |
| `net/minecraft/client/**` | **1,798** |
| 强制定义 | `jars ok=136554 fail=68176`（agent 把所有 classpath 类过了一遍转换） |
| 存放 | 私有 release `b1-client-graph`（`b1-client-graph.zip`，141,666,296 字节） |

## 2. 客户端镜像冒烟通过

CI 作业 **#177（success）**：

```
asset: …/releases/assets/752674038
extracted 73288 files into graph
classes: 73288   client classes: 1798
-rw-r--r--  1 distiller  staff   137M graph.jar

Finished generating 'b1client' in 21.4s
IMAGE BUILT: 14M
B1 client native-image smoke
net.minecraft.client.Minecraft
net.minecraft.client.gui.screens.TitleScreen
net.minecraft.client.renderer.GameRenderer
com.mojang.blaze3d.platform.Window
net.neoforged.neoforge.client.ClientHooks
ok
```

两个结论：

1. **客户端类图谱可以被 GraalVM 封闭世界分析消费**，21.4 秒链接出 14 MB 可执行文件；
2. 图谱里确实包含真正的客户端类（不是空壳）。

## 3. 距离"能玩"还差什么

冒烟只证明了「类可以被 AOT」，没证明「游戏能启动」。真实客户端镜像需要：

1. **静态运行期**：把 FML 的 ModList、注册表、事件总线、生命周期在构建期定死，
   运行期不再需要 ModLauncher / ModuleLayer（B3 的工作量，最大一块）；
2. **真实入口**：`net.minecraft.client.main.Main` 的启动参数与游戏目录/资源注入；
3. **iOS 侧**：Metal/GL 适配、触摸、存档，复用 A1 线已有的 GL41 栈；
4. **资源**：与 A1 一样不进包，用户本地导入。

## 4. 工件

| 工件 | 位置 |
|---|---|
| 客户端图谱 | 私有 release `b1-client-graph`（141,666,296 字节） |
| CI 配置 | `zhangrongxue/mc-aot-ios` 分支 `build/b1-n0`，`config-b1-image.yml` 对应内容 |
| 冒烟源码 | 同分支 `b1/n05/ClientSmoke.java` |
| 作业日志 | CircleCI #177 的 `b1-client-native-image.log` |
