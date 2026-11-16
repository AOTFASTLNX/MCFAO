# B1 · 客户端入口镜像：能编、能跑，卡在 LWJGL（2026-11-16）

## 已经做到的

| 步骤 | 证据 |
|---|---|
| 客户端入口镜像构建成功 | **358 MB 可执行文件**，`Finished generating 'b1client' in 4m 8s`（job 222） |
| 镜像能跑进 Minecraft 客户端入口 | `starting net.minecraft.client.main.Main with 22 args` → mod 初始化（Euphoria Patcher 等都在跑）→ `Main.main`（job 224-228） |
| 解析客户端参数 | 补了 `java.io.File` / 装箱类型构造器的反射注册（joptsimple 用它判断"value type"） |
| LWJGL 原生库加载 | 从 Maven 拉 macos-arm64 natives，`org.lwjgl.librarypath` 指向它们（job 228） |

失败点一路右移：

```
Main.main → Minecraft.fillReport → SystemReport → RenderSystem.<clinit> → Tesselator → ByteBufferBuilder
  → MemoryUtil.<clinit> → Unsafe.objectFieldOffset(java.nio.Buffer 的字段)
  → UnsupportedOperationException: Failed to find field offset in class
```

## 为什么卡在这里

LWJGL 的 `MemoryUtil` 用 `sun.misc.Unsafe` 读取 `java.nio.Buffer` 的 `address/mark/position/limit/capacity`
字段偏移。native-image 不提供这些 JDK 内部字段的偏移（`Unsafe` 只认注册过的字段），
而把 `org.lwjgl` 整体改成构建期初始化也不行——那会在镜像构建器里执行 `Library.loadSystem`
（加载本地库），构建器直接拒绝。

A1 线当初的解法就是**不用 LWJGL**：自建 `liblwjgl.dylib` + OSMesa/zink/MoltenVK 的 GL41 栈。
B1 要走通客户端，需要把同一套渲染栈接进来——这是集成工作，不是再补一个反射配置能解决的。

## 另一条硬约束

CI 的 macOS runner 没有 OpenGL 上下文（`NSGL: Failed to find a suitable pixel format`），
即使 LWJGL 的问题解决，也只能跑到 GLFW 创建窗口那一步。真正的"可玩"必须在有 GPU 的机器
（本机 Windows / iPhone）上验证。

本机 Windows 方向也有一条已知障碍：GraalVM on Windows 需要 MSVC，本机 Visual Studio 未装 C++ 工作负载。

## 现在的状态

| 目标 | 状态 |
|---|---|
| BMC5 在 PC 上可玩（普通 JVM） | ✅ 已完成（FancyMenu/Drippy 禁用 + `-Xmx6G`） |
| 静态运行期（注册表） | ✅ 1,060 方块 / 1,333 物品 / 130 实体，1.24 s |
| 客户端入口镜像 | ✅ 构建 358 MB、运行到 `RenderSystem` |
| 客户端真正进主菜单 | ⛔ 被 LWJGL/Unsafe 与 GPU 环境双重挡住 |
| iPhone 可玩 | ⛔ 需要 A1 渲染栈接入 + iOS 打包，属下一阶段 |

## 下一步（按可行性排序）

1. 用 A1 的 GL41 渲染栈替换 LWJGL 的原生绑定（A1 已有 `liblwjgl.dylib`、OSMesa/MoltenVK 链路）；
2. 在有 GPU 的 macOS 上验证同一镜像（CI 无 GPU）；
3. iOS 侧沿用 A1 的 IPA 打包流程，把 `client-graph.dylib` 换成 B1 的客户端镜像。
