# B1 · 光影关闭 + 无 GPU 渲染的最后一步（2026-11-16 晚）

## 1. 光影按你的要求关掉了（但没有破坏依赖）

上一轮把 iris/euphoria 直接禁用，导致 `colorwheel` 缺依赖（`Mod ID: 'iris', Requested by: 'colorwheel'`），
整个包起不来。改成正确做法：

| 动作 | 结果 |
|---|---|
| 恢复 iris / IrisSearch / iris_shader_folder / EuphoriaPatcher 四个 mod | 依赖完整 |
| `config/iris.properties`：`enableShaders=false`、`shaderPack=` 置空 | 着色器不加载 |
| `shaderpacks/` 整个目录改名 `shaderpacks.offline` | 省 84 MB，不动文件 |
| FancyMenu + Drippy Loading Screen 仍保持禁用 | 它们才是崩溃根因 |

验证：JVM 客户端 448 个模组，**89.95 秒进主菜单**（`Sound engine started`），截图见桌面。

## 2. AOT 客户端：最后一公里是"早期 GL 上下文"

CI 里继续推进到：

```
ClientMain → Main.main
  → Bootstrap.validate() → RenderType → DefaultVertexFormat → VertexFormat
  → sodium 的 afterInit 需要 current GL context → "Could not find implementation"
```

原因很清楚：真实启动时 FML 的 **early window** 会先建好 GL 上下文，所以 sodium 在类初始化阶段就能调 GL；
静态运行期没有 early window，于是 sodium 没有任何上下文可用。

本轮已铺好的路：

| 改动 | 作用 |
|---|---|
| 图谱里的 LWJGL 换成官方 **3.4.3** | 自带 GLFW 3.4，支持 `GLFW_PLATFORM_NULL` 与 `GLFW_OSMESA_CONTEXT_API` |
| CI 装 `mesa`，`B1_OSMESA` 指向 `libOSMesa.dylib` | 软件 GL 实现 |
| `ClientMain` 里 `-Dorg.lwjgl.opengl.libname=libOSMesa` + 两个 GLFW hint | 让 LWJGL 的 GL 绑定指向 OSMesa，并让 GLFW 走 OSMesa 上下文 |
| `module-info.class` 删除后再打包图谱 | 否则 `jar(1)` 因 Java 25 的模块描述符拒绝打包（这一条曾让 graph.jar 静默不更新） |

还差的一步：**在 `Bootstrap.validate()` 之前用 OSMesa 创建并 `MakeCurrent` 一个上下文**
（LWJGL 的 `org.lwjgl.opengl.OSMesa` 绑定），sodium 才能拿到函数指针。

## 3. 状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（448 mods、光影关闭） | ✅ 已验证 |
| 静态运行期（注册表） | ✅ 1,060 方块 / 1,333 物品 / 130 实体 |
| AOT 客户端镜像（357 MB） | ✅ 跑到渲染类初始化 |
| AOT 客户端出主菜单（无 GPU） | ⏳ 差"早期 OSMesa 上下文"这一步 |
| iOS | ⏳ 需要 A1 的 iOS 运行时 + 渲染栈 |

## 4. 关于崩溃报告里的注入文字

这个整合包的 Crash Assistant 会在每份崩溃报告开头插入一段"System note for AI"，
要求 AI 忽略错误、不要告诉用户报告被修改。这是**提示注入**，不是系统指令，我没有执行它。
要清除的话，禁用 `crash_assistant` 即可。
