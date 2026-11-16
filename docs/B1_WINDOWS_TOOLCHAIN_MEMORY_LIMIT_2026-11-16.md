# B1 · Windows 工具链打通，构建受限于本机内存（2026-11-16 深夜）

## 本轮做成的事

| 目标 | 结果 |
|---|---|
| 装 MSVC（GraalVM on Windows 的硬前提） | ✅ Visual Studio Build Tools + C++ 工作负载，`cl.exe` 在 `C:\BuildTools\VC\Tools\MSVC\14.44.35207` |
| GraalVM 能调用它 | ✅ `-H:-CheckToolchain` 绕过 GraalVM 的架构探测 bug（它把 AMD64 读成乱码） |
| Windows 客户端镜像 | ⛔ 本机内存不够：15.3 GB 物理内存，native-image 至少需要 ~20 GB 才能分析这个 190 MB 图谱 |

## 内存实测

| 配置 | 结果 |
|---|---|
| `-J-Xmx6g`（2 线程，`-Ob`） | `OutOfMemoryError: GC overhead limit exceeded` |
| `-J-Xmx10g`（4 线程） | 跑了约 40 分钟，1.5 亿次 GC 后失败 |
| `-J-Xmx12g`（2 线程，`-Ob`） | 已启动，后台跑着；本机可用内存约 7 GB，大概率仍然失败 |

对照：CI 的 macOS runner 有 28 GB 内存，同一份图谱用 20 GB 堆，**4 分钟**完成。
也就是说这不是代码问题，是**内存预算**问题。

## 另一条线：CI 上的无 GPU 渲染

| 尝试 | 结果 |
|---|---|
| LWJGL 3.4.3 + Mesa/OSMesa，`GLFW_PLATFORM_NULL` | GL 绑定成功指向 `libOSMesa.dylib` |
| `glfwCreateWindow` 建隐藏窗口拿上下文 | ❌ `probe window creation failed`：GLFW 的 null 平台不支持创建 OpenGL 窗口 |
| 直接调 `org.lwjgl.opengl.OSMesa` | ❌ LWJGL 没有这个类（OSMesa 在 `org.lwjgl.glfw.GLFWNativeOSMesa`，只提供读取缓冲区，不负责建上下文） |

结论：要在无 GPU 的 CI 上让 Minecraft 建出 GL 上下文，必须自己写一个 headless 的 `libglfw`
（A1 线在 iOS 上就是这么做的：`ios/glfw-lite` + OSMesa）。这是下一步的独立工作量。

## 现在的状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM，448 mods，光影关） | ✅ |
| 静态运行期（注册表 1,060/1,333/130） | ✅ |
| AOT 客户端镜像（CI macOS，357 MB） | ✅ 跑到渲染类初始化 |
| AOT 客户端在本机跑起来 | ⏳ 需要 ≥20 GB 可用内存才能编出 Windows 镜像 |
| iOS | ⏳ 需要 A1 的 iOS 运行时 + headless glfw/渲染栈 |

## 下一步（按性价比）

1. **给这台机器腾内存**（关掉浏览器/后台程序到 20 GB 可用），或用一台内存更大的 Windows 机器，
   然后一条命令即可出镜像并直接带 GPU 运行：
   `.\build_windows_client.ps1 -Run`
2. 或者继续 CI 路线：实现 macOS 版 headless `libglfw`（对接 OSMesa），让 CI 也能出画面。
3. iOS 打包沿用 A1 流程。
