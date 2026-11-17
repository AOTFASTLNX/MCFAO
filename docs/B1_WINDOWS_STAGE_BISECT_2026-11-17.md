# B1 · Windows 分阶段定位（2026-11-17 中午）

## 结论先行

Windows 镜像在 GitHub Actions 上稳定产出（约 13 分钟），并且用 `B1_STAGE` 环境变量可以分段执行，
已经精确定位到：**静态运行期没问题，GLFW 也没问题，崩溃发生在"把 GL 上下文设为当前/开始用 GL"这一步**。

## 分阶段结果

| stage | 结果 |
|---|---|
| `bootstrap` | ✅ `bootstrap ok in 1614 ms`，`blocks=1060` |
| `glfw` | ✅ `glfwInit()=true`、窗口句柄非 0；❌ 之后在 `glfwMakeContextCurrent`/首个 GL 调用处 segfault |
| 默认（完整客户端） | ❌ `Main.main` 开始后静默退出（同一个 native 崩溃） |

## 这一轮修掉的三件事

| 问题 | 原因 | 处理 |
|---|---|---|
| `UnsatisfiedLinkError: Can't load library: C:\...鎴戠殑涓栫晫\...` | 镜像里 `System.getenv` 对中文路径解码错误（我的世界 → 乱码） | 测试时把 natives 复制到纯 ASCII 路径 |
| `MemoryUtil` 字段偏移失败 | 整合包自带 `LWJGL 3.3.3-snapshot` 依赖 `sun.misc.Unsafe` | CI 里覆盖成官方 **LWJGL 3.4.3**（类 + Windows natives） |
| `jar(1)` 拒绝打包 | 3.4.3 的 jar 带回 Java 25 的 `module-info.class` | 覆盖之后再删一次 module-info |

## 下一步（针对 GL 上下文崩溃）

1. 用 `-XX:-InstallSegfaultHandler` 已试过：无 Java 栈，说明确实在 native 里；
2. 用 procdump 抓 dump 定位到具体 DLL/偏移（已会抓，下一步接符号化）；
3. 怀疑点：native-image 里 LWJGL 的 GL 函数解析（`GL.create()` 的 FunctionProvider）在镜像中被裁掉/初始化时机不对；
   可尝试 `--initialize-at-run-time=org.lwjgl` 或显式为 `org.lwjgl.opengl.GL` 注册反射；
4. 也可以直接跳过探针：用 MC 自己的窗口创建路径（它会设置 3.2 core hint），看是否只是我们探针的默认上下文问题。

## 当前状态

| 项 | 状态 |
|---|---|
| BMC5 在 PC 可玩（JVM） | ✅ 448 mods，光影关 |
| 静态运行期（Windows 镜像内） | ✅ 1.6 s / 1,060 方块 |
| GLFW 初始化 + 建窗（Windows 镜像内） | ✅ |
| GL 上下文 / 首帧 | ❌ 进行中 |
| iOS | ⏳ |

## 工程侧收获

- GitHub Actions `windows-2022`：**13 分钟**稳定出 394 MB 镜像 + natives，不再受本机 15 GB 内存限制；
- 仓库 secret `GH_PAT` 可让公开仓库的 Actions 读取私有 release（图谱与 overrides）；
- `B1_STAGE=bootstrap|glfw` 让同一份镜像可以分段执行，二分定位成本从"改代码重编"降到"设个环境变量"。
