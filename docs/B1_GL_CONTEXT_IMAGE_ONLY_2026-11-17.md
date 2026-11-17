# B1 · GL 上下文：JVM 正常，镜像里 crash（2026-11-17 下午 2）

## 关键对照实验

同一份 `ClientMain`（`B1_STAGE=glfw`）分别在 JVM 与 native image 里跑：

| 步骤 | JVM | native image |
|---|---|---|
| `glfwInit()` | ✅ true | ✅ true |
| `glfwGetVersionString` / `glfwGetTime` / `glfwPollEvents` | ✅ `3.5.1 Win32 WGL Null EGL OSMesa VisualC DLL` | ✅ 同 |
| `glfwCreateWindow(320x240, 3.2 core)` | ✅ 句柄非 0 | ✅ 句柄非 0 |
| `glfwMakeContextCurrent` | ✅ `current=<handle>`、`ctxVersion=3.2`、`clientApi=GLFW_OPENGL_API` | ❌ **segfault** |
| 大栈线程（256 MB） | — | ❌ 无改善 |

结论：**JNI 绑定没问题，GLFW 本身也没问题；崩溃精确落在 `glfwMakeContextCurrent` 这一条原生调用上，
且只在 native-image 里发生。**

## 这意味着什么

`glfwMakeContextCurrent` 内部会走 WGL 的 `wglMakeCurrent`（需要当前线程已关联桌面/像素格式），
而 substrate 的线程在这条路径上和 HotSpot 线程的行为不同——这类"驱动 + 非 HotSpot 线程"的组合
正是 AOT 桌面应用的老问题。

## 下一步候选（按成本）

1. **最小镜像复现**：只含 GLFW 的小镜像（几 MB），确认是 image 环境问题而非 MC 相关；
2. 用 `-H:+Uninterruptible`/线程相关选项、或把 GL 调用放到 substrate 的主线程（不用 Thread）对比；
3. 若确认是 WGL 路径不兼容，考虑 A1 的方案：用 OSMesa/自研 glfw 绕开 WGL（`ci/headless_glfw.c` 已备）；
4. 或者干脆先不追 Windows：把资源投到 iOS 那条已经跑通渲染的 A1 栈上。

## 状态

| 项 | 状态 |
|---|---|
| 静态运行期（镜像内） | ✅ 1.6 s / 1,060 方块 |
| GLFW 初始化、窗口创建（镜像内） | ✅ |
| GL 上下文绑定 | ❌ image-only segfault |
| BMC5 在 PC 可玩（JVM） | ✅ |
| iOS | ⏳ |

## 附带确认

- 镜像里 `System.getenv` 对中文路径解码错误（`我的世界` → `鎴戠殑涓栫晫`），所以本地测试要把 natives
  放到纯 ASCII 路径；这本身也是一个该记录的限制（用户目录含中文时，镜像内路径要显式转码）。
