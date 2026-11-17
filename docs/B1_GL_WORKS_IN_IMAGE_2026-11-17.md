# B1 · 突破：native image 里可以跑真实 OpenGL（2026-11-17 下午 3）

## 结论

最小镜像（只含 LWJGL，无 Minecraft）在 Windows 上**成功用显卡创建 3.2 core 上下文并读到 GL 版本**：

```
probe: init=true
probe: version=3.5.1 Win32 WGL Null EGL OSMesa VisualC DLL
probe: window=2228007674688
probe: current=2228007674688
probe: capabilities ok, OpenGL32=true version=true/false
probe: GL_VERSION=3.2.0 NVIDIA 617.14
probe: ok
```

也就是说：**GraalVM native-image + LWJGL + 真实 GPU（NVIDIA 617.14）在 Windows 上完全可用**，
之前所有的 segfault 都不是"镜像不能跑 GL"，而是 **GL 函数表没有为当前线程安装**。

## 关键区别

| 调用 | 作用 | 之前的问题 |
|---|---|---|
| `GL.create()` | 只加载 GL 原生库（opengl32.dll） | 只做这一步，函数指针仍是"缺失函数"桩 |
| `GL.createCapabilities()` | **为当前线程 + 当前上下文构建函数表** | 之前没调用它，`GL11.glGetString` 直接跳到非法地址 |

`glfwMakeContextCurrent` 之后必须调用 `GL.createCapabilities()`（或 MC 自己会调，见下），
否则 LWJGL 的函数指针是 0xffffffffffffffff，一调用就 segfault。

## 对完整客户端意味着什么

BMC5 的完整客户端在镜像里静默退出，很可能就是"某条 GL 调用早于 capabilities 安装"。
Minecraft 自己的 `Window` 初始化里确实会调用 `GL.createCapabilities()`，但我们的
`ImmediateWindowHandler` 被替换成空实现（原本它负责早期窗口 + 上下文），
导致 MC 的调用顺序被打乱。

**下一步**：在 `ClientMain` 里加一个看门线程——一旦发现"已有 current 上下文但 capabilities 缺失"，
就补一次 `GL.createCapabilities()`，把 MC 的调用顺序兜住。

## 附：build 期的类初始化报告

`-H:+PrintClassInitialization` 确认 `org.lwjgl.opengl.GL` / `GL11C` / `System.Library` 都是
**运行期初始化**（RUN_TIME），所以之前怀疑的"静态字段被烘进镜像"不成立。

## 状态

| 项 | 状态 |
|---|---|
| 静态运行期（镜像内） | ✅ |
| GLFW + 真实 GPU 上下文（最小镜像） | ✅ **本轮突破** |
| 完整客户端 | ⏳ 差一次 capabilities 兜底 |
| BMC5 在 PC 可玩（JVM） | ✅ |
| iOS | ⏳ |
