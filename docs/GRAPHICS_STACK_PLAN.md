# 图形栈补全方案（C0 图形层）

日期：2026-11-08（第45轮更新）。状态：**G1/G2/G3/G5 PARTIAL；模拟器启动与诊断清屏通过；C0/C0a BLOCKED**。实现与证据见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。决策记录见 [ADR-008](evidence/ADR-008.md)。

适用范围：Gate C0 的图形/窗口/输入部分（C0a/C0b），不含音频（C1）与性能（E）。

## 1. 结论摘要

第 43 轮的阻断不是 AOT、不是签名、不是内存，而是两件 iOS 上不存在的东西：**LWJGL 原生库**与**GLFW 窗口后端**。本轮把客户端渲染路径拆开量过之后，方案定为三层替换，而不是"把 LWJGL 移植到 iOS"：

| 层 | 客户端现状 | iOS 方案 | 量级 |
|---|---|---|---|
| 窗口/输入 | `blaze3d/platform/*` 直接调 GLFW（58个C导出，另有Java辅助函数） | 第一方 `libglfw.dylib` 替身：UIKit 窗口 + `CAMetalLayer` + 事件转发 | 中，C/ObjC，符号集封闭可枚举 |
| 渲染 | `GlBackend` 实现 `GpuBackend`（blaze3d 的可插拔后端） | `MetalBackend` 实现同一接口，经 JNI 调 Metal | 大，Java ~25 类 + ObjC++ 桥 |
| 着色器 | 88 个 GLSL `#version 330` 文件，运行时编译 | 构建期 GLSL→SPIR-V→MSL，运行时按 id 查表 | 中，构建期工具链 |
| 其余本机符号 | `org/lwjgl` 的 `system`、`util`、`stb` 三组（68 个引用） | 第一方 `liblwjgl.dylib`：MemoryUtil/PointerBuffer/Configuration/STB | 小到中，C |

关键前提是**客户端渲染后端本来就是可插拔的**，这一条本轮才核实（§2）。它把"移植整条 GL 管线"变成"实现一个后端接口"。

## 2. 本轮核实的架构事实

证据均来自只读检查：客户端 jar（SHA-256 `b1b31585…d0b0`，与 A0 指纹一致）、`javap` 反汇编、`artifacts/evidence/client-native-call-inventory.json`。未执行游戏代码。

### 2.1 blaze3d 后端是接口化的

`com.mojang.blaze3d.systems.GpuBackend` 只有 4 个方法：

```java
String getName();
void setWindowHints();
void handleWindowCreationErrors(GLFWErrorCapture.Error) throws BackendCreationException;
GpuDevice createDevice(long windowHandle, ShaderSource, GpuDebugOptions);
```

配套接口：`GpuDeviceBackend`（26 个方法，资源创建/能力查询/`presentFrame`）、`CommandEncoderBackend`（19 个，render pass/clear/copy/map/fence/timer）、`RenderPassBackend`（14 个，pipeline/texture/uniform/scissor/vertex/index/draw）。`GpuDevice`、`CommandEncoder`、`RenderPass` 是**普通类**，把调用转发给 backend——即官方已经替我们写好了参数校验与生命周期，后端只需实现 `*Backend`。

### 2.2 后端选择是多候选回退循环

`net.minecraft.client.Minecraft` 构造函数字节码（偏移 803–1017）是一个标准回退循环，不是硬编码：

```
803: iconst_1 / anewarray GpuBackend        → new GpuBackend[1]
809: new GlBackend() ... aastore            → backends[0] = new GlBackend()
863: new Window(this, displayData, fullscreenMode, title, backend)
928: invokeinterface GpuBackend.createDevice(J, ShaderSource, GpuDebugOptions)GpuDevice
937: invokestatic RenderSystem.initRenderer(GpuDevice)
943: catch BackendCreationException → LOGGER.error("Failed to create backend {}", name, e)
                                    → 累加 "No supported graphics backend was found.\n- Tried <name>: <msg>"
                                    → window.close(); 继续下一个
1017: window == null → MessageBox.error(...) + throw WindowInitFailed
```

含义：**Metal 后端的注入点是一个数组**。构建期把 `iconst_1/anewarray` 改成 `iconst_2` 并在 `aastore` 后追加 `new MetalBackend()`，即可让客户端自己按"先 Metal、失败退回 GL"的顺序尝试。失败路径已有 `BackendCreationException` 与用户可读的错误汇总，不需要改控制流。

### 2.3 OpenGL 引用零泄漏

124 个 `org/lwjgl/opengl/*` 方法引用，只出现在 13 个类里，且**全部**在 `com.mojang.blaze3d.opengl` 包内：

| 类 | 引用数 |
|---|---:|
| `GlStateManager` | 63 |
| `GlCommandEncoder` | 15 |
| `DirectStateAccess$Core` | 13 |
| `GlDebug` | 9 |
| `GlDevice` | 5 |
| `DirectStateAccess$Emulated` / `VertexArrayCache$Separate` / `GlDebugLabel$Core` / `GlSampler` | 4 each |
| 其余 4 个类 | 1–3 each |

（按类累加为 130，大于 124 个唯一引用——同一个 GL 方法会被多个类各自引用一次，这是计数口径差异，不是统计错误。）

脚本断言 `referencingClasses ⊄ com/mojang/blaze3d/opengl/` 的结果是**空集**。所以只要不走 `GlBackend`，整个 GL 依赖面不参与链接——这是"不需要 GL→Metal 转译层"的硬依据，不是推测。

### 2.4 GLFW 是唯一横跨全局的本机依赖

85条Java方法引用 / 74个唯一方法名（59个 `glfw*` 名称包含Java辅助函数 `glfwFreeCallbacks`，实际C导出58个；其余15个名称也不是15个C导出），使用方集中在 `blaze3d/platform`：

| 类 | 符号数 |
|---|---:|
| `Window` | 29 |
| `GLX` | 13 |
| `InputConstants` | 12 |
| `VideoMode` / `Monitor` / `ScreenManager` / `GlDevice` | 5–6 each |
| `GLFWErrorScope` / `TextInputManager` / `CursorType` / `ClipboardManager` | 2–4 each |
| `Blaze3D` / `RenderSystem` / `MouseHandler` / `MacosUtil` / `GlBackend` | 1 each |

74 个唯一符号里有 4 个**不属于上游 GLFW 3.x 公开 API**，替身库必须按客户端调用签名单独实现：

- `glfwSetIMEStatusCallback`、`glfwSetPreeditCallback`、`glfwSetPreeditCursorRectangle`（IME 预编辑文本，`InputConstants` / `TextInputManager` 使用；来自 Mojang 的定制 GLFW 分支）
- `glfwGetCocoaWindow`（`MacosUtil`，LWJGL 的 macOS 访问器；iOS 上返回 0 并让上层降级）

实际58个C导出中有**54个上游符号 + 3个IME扩展 + 1个Cocoa访问器**；Java辅助函数另在overlay中实现。不能只按 GLFW 官方头文件导出符号——缺这 4 个会在 `InputConstants.<clinit>` 或 `MacosUtil` 调用处直接 `UnsatisfiedLinkError`。

`glfwMakeContextCurrent` / `glfwSwapBuffers` / `glfwGetCurrentContext` 在 Metal 路径下只做"记账"（记录当前 surface），不承载真实 GL 上下文。

### 2.5 着色器语料小且版本统一

jar 内 `assets/minecraft/shaders/`：

| 项 | 数值 |
|---|---|
| GLSL 文件总数 | 88（`.vsh` 35 / `.fsh` 44 / `.glsl` include 9） |
| 目录分布 | `core/` 69、`post/` 10、`include/` 9 |
| `#version` | **全部 330**（88/88，无例外） |
| 总字节 | 54,213 |
| 最大文件 | `core/terrain.fsh` 3,374 字节 |
| 特性出现次数 | `in`/`out` 73/77、`uniform` 54（其中 `sampler2D` 41）、`texture()` 28、`layout()` 22、`discard` 19、`const` 7、`#ifdef` 5 |

`ShaderSource` 是单方法接口 `String get(Identifier, ShaderType)`。所以后端可以完全忽略传入的 GLSL 源，改成"按 `<namespace>:<path>.<type>` 查预编译 MSL"。88 个文件的量级让**构建期全量预翻译 + 启动期校验**成为可行策略，不需要运行时翻译器，也不需要在 iOS 上跑 glslang。

### 2.6 音频是独立的一小块（C1，不在本轮）

35 个 OpenAL 引用集中在 `blaze3d/audio` 的 7 个类（`Library`、`Channel`、`DeviceList`、`Listener`、`SoundBuffer`、`OpenAlUtil`、`CallbackDeviceTracker`）。iOS 上没有 OpenAL，方案是 `AVAudioEngine` + 软件混音替身，或在 C0b 之后先用"静音设备"让 `SoundEngine` 初始化不阻塞。

## 3. 三层结构与注入点

```
Minecraft.<init>
  └─ GpuBackend[] { MetalBackend, GlBackend }        ← 构建期 ASM：数组扩容 + 追加
       ├─ MetalBackend.createDevice(handle, src, opts)
       │     ├─ handle: GLFW-lite 的 window id → CAMetalLayer
       │     ├─ src: 被替换为 MslShaderSource（id → 预编译 .metal 文本）
       │     └─ return MetalDevice implements GpuDeviceBackend
       └─ GlBackend (iOS 上必然失败，走既有 catch 分支)

Window / GLX / InputConstants / ScreenManager / Monitor
  └─ libglfw.dylib（第一方替身，客户端58个C导出，含3个IME扩展）
        ├─ glfwInit / glfwCreateWindow → UIWindow + CAMetalLayer + CADisplayLink
        ├─ glfwPollEvents → 从 UIKit 事件队列取事件，同步派发 GLFW 回调
        ├─ glfwGetFramebufferSize / glfwGetTime / 视频模式查询 → 真实值
        └─ glfwSetIME* → UITextInput 预编辑桥

MemoryUtil / PointerBuffer / Configuration / STB
  └─ liblwjgl.dylib（第一方替身，system 36 + util 26 + stb 6 个引用对应符号）
```

## 4. 工作包

每个包独立可验收，失败只影响自身。顺序即优先级：G1→G2 能在没有渲染的情况下把"能跑但黑屏"变成"能跑且日志完整"，是后续一切的前提。

### G1 GLFW-lite 替身（第一个可运行里程碑）

- **产物**：`ios/glfw-lite/`（C/ObjC 源码）+ `tools/build_glfw_lite.py`，输出 `libglfw.dylib`（arm64-ios17+，`LC_BUILD_VERSION platform IOS`）。
- **范围**：覆盖客户端58个C导出，结构体访问器由LWJGL Java/JNI处理；`glfwInit` 返回 GLFW_TRUE；`glfwCreateWindow` 建 `UIWindow`+`CAMetalLayer` 并返回非 0 句柄；`glfwGetFramebufferSize` 返回真实像素尺寸（含 `contentsScale`）；`glfwGetTime` 单调时钟；`Monitor`/`VideoMode` 返回单屏合成数据；未实现的 setter 明确 `fprintf(stderr)` 后返回，不静默。
- **验收**：客户端日志越过 `GLX._initGlfw`，`Window` 构造成功，`getPlatform()` 返回稳定字符串；`glfwPollEvents` 派发真实队列；初始化尺寸/焦点只通知一次，空队列不伪造事件。**不要求出现画面。**
- **风险**：`Window` 内部对 GLFW 返回值语义的假设（如 `glfwGetWindowMonitor` 必须与 set 对称）；`GLFWErrorScope` 的错误码语义。用第一方 C 夹具逐符号对照，不靠读代码猜。

### G2 LWJGL core 替身

- **产物**：`ios/lwjgl-lite/`，输出 `liblwjgl.dylib`；同时解决第 43 轮的 `UnsatisfiedLinkError: liblwjgl.dylib`。
- **范围**：`MemoryUtil` 系列（`nmemAlloc/nmemFree/nmemRealloc/nmemCopyMemory/nmemSetMemory`）、`PointerBuffer` 分配与访问、`Configuration`（`Library` 用它决定 native 加载策略）、`STB`（`stbi_load_from_memory` 等 6 个，图像加载必需）、`Platform`/`Checks` 的 native 部分。
- **验收**：客户端越过 `org.lwjgl.system.Platform` 静态初始化；`STB` 能解出一张 PNG（用第一方夹具图，不放游戏资产）；`MemoryUtil` 与 Java 侧 `Unsafe` 视图地址一致。
- **风险**：LWJGL 3.4 的 `MemoryUtil` 大量走 `Unsafe` 快路径，native 侧只需提供分配器；但要保证对齐与 `nmemAlignedAlloc` 语义。

### G3 Metal 后端（主体工程）

- **产物**：`compiler/metal-backend/`（Java）+ `ios/metal-bridge/`（ObjC++/Metal）。类清单按现有 GL 后端一对一命名（`MetalDevice`、`MetalCommandEncoder`、`MetalRenderPass`、`MetalTexture`、`MetalBuffer`、`MetalSampler`、`MetalRenderPipeline`、`MetalFence`、`MetalTimerQuery`），便于逐项对照语义。
- **范围**：`GpuBackend`（4）+ `GpuDeviceBackend`（26）+ `CommandEncoderBackend`（19）+ `RenderPassBackend`（14）+ 资源类。首个里程碑只做：清屏 + 一个全屏三角形 pipeline + `presentFrame`。
- **验收**：C0a——真机出现"非黑即明确颜色"的帧，且 `RenderSystem` 完成初始化；随后接 `MainTarget` 让客户端自己渲染主菜单（C0b）。
- **风险（按严重度）**：
  1. **渲染状态语义**：GL 的 blend/depth/cull/scissor 组合由 `RenderPipeline` 描述，Metal 的 `MTLRenderPipelineState` 是不可变对象——需要按 pipeline 描述做缓存键，键必须覆盖所有 state，否则出现"错的管线被复用"。这是最可能产生难查视觉 bug 的地方。
  2. **uniform 布局**：blaze3d 用 UBO/UTB（`Uniform$Ubo`/`Utb`），Metal 的 `setVertexBytes`/`setFragmentBytes` 有 4KB 上限，大 UBO 必须走 buffer + offset，且要遵守 `getUniformOffsetAlignment()`。
  3. **纹理格式映射**：`TextureFormat` → `MTLPixelFormat`，sRGB 与 depth/stencil 组合要逐项列表核对，不做隐式 fallback。
  4. **帧边界**：`presentFrame` 与 `CADisplayLink` 的节流关系；`setVsync` 在 iOS 上映射到 `CAMetalLayer.displaySyncEnabled`。

### G4 构建期着色器翻译

- **产物**：`tools/translate_shaders.py`（预处理 + 调 glslang/SPIRV-Cross）+ 输出到 App bundle 的 `shaders.msl/` 索引。
- **范围**：复用官方 `com.mojang.blaze3d.preprocessor.GlslPreprocessor` 的预处理语义（`#mojang` 指令、include 展开），然后 GLSL 330 → SPIR-V（`glslangValidator -G`）→ MSL（`spirv-cross --msl`）。`post/` 的 10 个后处理 shader 同样处理。
- **验收**：覆盖全部可执行shader及真实pipeline define变体的MSL，且`xcrun metal`编译通过（88个源文件含9个include，不能逐文件冒充入口覆盖）；每个 shader 保留 `#version 330` 源与 MSL 的对应清单（id、SHA-256、编译结果）；对 GLSL 侧的 uniform 名与 MSL 侧绑定做名字一致性检查（不一致会静默显示黑图）。
- **风险**：GLSL 330 的隐式类型转换与 `precision` 差异、`discard` 与 early-z、`texture()` 的 lod/bias 重载。**预设否证点**：若某个 shader 的 SPIRV-Cross 输出与预期语义不符，不手改 MSL——把该 shader 记为 `UNSUPPORTED` 并在启动时明确报错，宁可缺一个特效也不要静默错图。

### G5 输入层（触摸）

- **产物**：`ios/touch-bridge/`，把 `UITouch` 映射为 GLFW 的 cursor pos / mouse button / scroll / char 回调。
- **范围**：单指=光标（相对拖动，模拟鼠标），双指=滚轮，长按=右键，软键盘=`glfwSetCharCallback` + IME 预编辑。虚拟摇杆/按钮属于 UI 层，用 Minecraft 自己的 GUI 实现，不改客户端逻辑。
- **验收**：C0b——能在主菜单点按钮、能进设置滑条。
- **风险**：Minecraft 的 `MouseHandler` 假设绝对光标 + 抓取模式；触摸下的"相对位移"要自己维护虚拟光标并处理边界回中。

### G6 音频（C1，本轮不启动）

OpenAL 35 个符号 → `AVAudioEngine` 替身，或先"静音设备"。放在画面通过之后。

## 5. 门槛拆分

现有 Gate 定义里 C0（无图形入口）与 C1（画面/输入）之间没有中间档，而图形补全是一个长过程，必须有可停靠的验收点。建议在 [TECHNICAL_GATES](TECHNICAL_GATES.md) 增加：

| 子门槛 | 内容 | 通过标准 |
|---|---|---|
| C0a | Metal 后端清屏 | 真机出现由 Metal 渲染的首帧（非黑或明确清屏色），`RenderSystem` 初始化完成，日志有后端名与设备信息 |
| C0b | 真实主菜单 | Minecraft 自己渲染的主菜单可见（文字/按钮为真实资源），触摸可点击并响应 |
| C0c | 创建世界 | 新建世界进入、区块渲染、移动、破坏/放置、退出重入，存档保留 |

C0 本身（无图形入口可达）保持现状：**第 43 轮已经到过 `Main.main` 之后的 Datafixer 阶段，但"到达菜单前启动阶段"仍不算完成**——因为 `Window` 创建就失败在 GLFW。G1/G2完整验收及真机真实Main窗口启动证据齐备后才可把C0记为PASS。第45轮独立集成入口的模拟器结果仅证明窗口/设备启动，不升级该Gate。

## 6. 明确不做的事

- **不用 `-Dos.name=Mac OS X` 伪装平台**。第 43 轮已证明它只把 `LinkageError` 推后成 `UnsatisfiedLinkError`，宿主里的注释也写明它不会让渲染工作；它只保留为诊断开关。
- **不做 GL→Metal 逐调用转译层**（Zink+MoltenVK、ANGLE、MoltenGL 路线）。理由见 [ADR-008](evidence/ADR-008.md)：客户端已有后端抽象，转译层要多背一整套 GL 状态机与 GLSL 编译，且 iOS 上 Vulkan 只有 MoltenVK 一条路，链路更长、可观测性更差。
- **不用 GLFW null platform 顶替**：它没有窗口/输入/呈现，`glfwCreateWindow` 之后 `Window` 拿不到 framebuffer 尺寸，等于把问题挪到下一层。
- **不用 3D demo 或 SwiftUI 画面冒充菜单**（AGENTS.md 硬约束）。
- **不在 iOS 上跑 glslang**：翻译只在构建期。

## 7. 复现本轮的检查

本轮数据来自一次性只读检查（未固化成工具，后续若要回归需先落成 `tools/` 脚本）：

```bash
JAR="/Users/kexin/Library/Application Support/Swift Craft Launcher/meta/versions/26.1.2/26.1.2.jar"
# 2.3 OpenGL 引用零泄漏
python3 - <<'PY'
import json
d=json.load(open("artifacts/evidence/client-native-call-inventory.json"))
refs={r for m in d["methods"] if m["owner"].startswith("org/lwjgl/opengl/") for r in m["referencingClasses"]}
print(sorted(r for r in refs if not r.startswith("com/mojang/blaze3d/opengl/")))  # 期望 []
PY
# 2.5 着色器语料
unzip -l "$JAR" | grep 'assets/minecraft/shaders/' | awk '{print $4}' | grep -E '\.(vsh|fsh|glsl)$' | wc -l
unzip -p "$JAR" 'assets/minecraft/shaders/core/terrain.fsh' | head -3
# 2.2 后端回退循环
javap -p -c -cp . net.minecraft.client.Minecraft | grep -n -A4 'anewarray.*GpuBackend'
```

## 8. 工作量判断与不承诺

按上述拆分，**能出第一帧（C0a）**需要 G1+G2+G3 的最小闭环；**能进主菜单（C0b）**还要 G4 全量通过 + G5；**能玩（C0c）**要在此基础上补音频、存档与性能。这不是"几轮补丁"的规模：G3 是主体，按现有 GL 后端 25 个顶层类的实现面对齐。

本文不给出时间估计，也不承诺"补完就能玩"。每个 Gate 按证据推进，失败就记 BLOCKED。
