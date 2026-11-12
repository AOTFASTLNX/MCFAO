# 图形启动集成结果

日期：2026-11-09，第47轮。**实现状态 PARTIAL；C0/C0a BLOCKED；C0b/C0c NOT RUN。**

真实 Minecraft 26.1.2 的 `Window` 和 `RenderSystem.initRenderer` 已在模拟器与用户 iPhone 执行，用户确认看到蓝色画面后返回日志。本轮继续实现纹理、传输、清除通路与预编译呈现着色器；模拟器完成四格式 GPU 读回比对并显示四分屏。诊断夹具现已验证原版87条管线和真实Metal绘制；完整游戏Main已执行至Metal设备初始化，正在补音频扩展。

## 实现与已验证行为

| 层 | 源码 | 验证范围 |
|---|---|---|
| GLFW-lite | [glfw-lite](../ios/glfw-lite/)、[构建器](../tools/build_glfw_lite.py) | UIKit `UIWindowScene`/`CAMetalLayer`、点/像素尺寸、单屏模式、单调时钟、回调队列、窗口释放；仅允许 `GLFW_NO_API` |
| LWJGL iOS overlay | [Java overlay](../compiler/lwjgl-lite/)、[JNI](../ios/lwjgl-lite/)、[生成器](../tools/lwjgl_codegen.py) | 明确的 `Platform.IOS`、显式加载签名目录、1721个预编译 JNI 调用适配器、17种GLFW回调 + 1种STB写回ABI，各32个静态槽；超额/未知 ABI 明确失败 |
| Metal resources | [Java backend](../compiler/metal-backend/)、[Metal bridge](../ios/metal-bridge/) | device/shared buffer/sampler；RGBA8、RED8、RED8I、DEPTH32纹理、mip视图；缓冲区映射/切片/复制、纹理上传/复制/读回；整面颜色/深度清除与清除型 RenderPass、fence |
| 呈现 | [present.metal](../ios/metal-bridge/present.metal) | 构建期编译为平台对应的 metallib；经真实 `CommandEncoder.presentTexture` / `GpuDevice.presentFrame` 呈现纹理，无运行时源码编译 |
| 集成夹具 | [MetalProbe](../interop/graphics/MetalProbe.java)、[MetalResourceProbe](../interop/graphics/MetalResourceProbe.java) | 真实游戏类初始化；旧探针蓝色清屏，新探针 GPU 字节比对与红/绿/蓝/黄四分屏，保持20秒后关闭窗口并返回0 |
| 宿主与采集 | [C0Harness](../ios/C0Harness/)、[构建器](../tools/build_c0_harness.py)、[采集器](../tools/collect_graphics_probe.py) | 验证 dylib 平台、嵌入/签名3个图形库及预编译资源；按输入指纹隔离构建；新日志/读回/截图/入口返回联合检查 |

GLFW 计数口径已复核：85条 Java 方法引用、74个唯一方法名，其中59个名称以 `glfw` 开头；`Callbacks.glfwFreeCallbacks` 是 Java 辅助函数，因此实际客户端调用的 C 导出为 **58个**。15个其余名称也不是15个待导出的 C 函数。LWJGL `GLFW$Functions` 还会一次初始化 **125个**函数地址；overlay 对未实现的 Java API 生成具名 `UnsupportedOperationException`，并替换直接遍历函数表的回调释放辅助类，防止调用空指针。

Java25 默认选择 LWJGL 多版本 JAR 中的 FFM 实现。iOS overlay 选择基础 JNI 实现，并替换 `Upcalls` 与 GLFW 回调描述符初始化。所有回调函数随 dylib 预先编译；没有运行时发射机器码、FFM upcall stub 或 libffi closure 分配。JNI 重载使用带描述符的长符号名，避免把数组对象当原生地址。

## 真实证据

- [用户真机日志与结果](../artifacts/graphics/device-run-02/result.json)：`USER_DEVICE_METAL_DIAGNOSTIC_PASS`；Apple A20 Pro GPU，1398×2034，真实 Window/RenderSystem 初始化、蓝色清屏、`METAL_INTEGRATION_PROBE_PASS`、`run_main returned 0`。用户反馈“对，出现一堆蓝然后进日志”；本次断开 Xcode 后独立启动条件未确认。
- [用户真机资源结果](../artifacts/graphics/device-run-03/result.json)：用户确认四色；原始日志包含四格式GPU比对、fence、1398×2034纹理呈现及`METAL_RESOURCE_PROBE_PASS`，旧图形警告未出现。该次缺少宿主返回记录：重定向FD与宿主append流使用独立偏移，后续输出可覆盖宿主记录。已将全部写入改为O_APPEND；[双写入方ASan/UBSan回归](../interop/diagnostics/C0LogAppendProbe.c)验证延迟输出保留退出行。独立启动及资源探针的真机返回0仍未确认。
- [资源模拟器日志与结果](../artifacts/graphics/resources-simulator-evidence-04/result.json)：`SIMULATOR_METAL_RESOURCES_PASS`。RGBA8/RED8/RED8I上传、GPU复制与逐字节读回、3级mip/视图、非对齐行与buffer切片、DEPTH32清除/读回及fence通过；1206×2622四分屏[截图](../artifacts/graphics/resources-simulator-evidence-04/frame.png)方向、颜色正确。已请求 Main Thread Checker 和 Metal API validation，日志确认后者启用；旧的后台访问 UIView.layer / present后读取 drawable.texture 警告均未再出现。
- [主机契约与像素布局测试](../artifacts/graphics/metal-sim-07/result.json)：隔离 JVM 检查 mip/立方体/越界/溢出；C ASan/UBSan检查1–4分量上传布局。遵循游戏 `GlConst` 的 GL_RED/RG/RGB/RGBA 缺省通道语义。
- [资源 AOT](../artifacts/graphics/resources-aot-04/result.json)：6 GiB / 4线程 / 56.36秒完成 ARM64 对象生成，峰值RSS约2.90 GB；[Simulator链接](../artifacts/graphics/resources-link-sim-04/result.json)与[iPhoneOS链接](../artifacts/graphics/resources-link-ios-04/result.json)分别使用对应运行库。13个未覆盖 JVM 入口仍为明确终止的桩，不能推及完整客户端兼容性。
- [修复后模拟器结果](../artifacts/graphics/resources-simulator-evidence-05/result.json)：资源比对、呈现、探针完成和宿主返回0均保留，运行检查无上述图形警告。
- [回归](../artifacts/graphics/regression-06/stderr.log)：**151项 PASS**。
- [Xcode 默认设备构建](../artifacts/graphics/xcode-default-device-check-02/command.json)返回0；[嵌入核对](../artifacts/graphics/xcode-default-device-check-02/inputs.json)4个库UUID及metallib内容匹配。此为未签名构建，资源探针用户真机已确认四色与GPU读回通过，见上述设备记录。

第45轮的历史记录：

- [模拟器原始日志与结果](../artifacts/graphics/metal-simulator-evidence-01/result.json)：`SIMULATOR_METAL_DIAGNOSTIC_PASS`；新日志包含 `MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal`、`DIAGNOSTIC_FRAME_PRESENTED 1206x2622`、`METAL_INTEGRATION_PROBE_PASS` 和 `run_main returned 0`。
- [Metal 清屏截图](../artifacts/graphics/metal-simulator-evidence-01/frame.png)：模拟器真实显示输出，蓝色诊断帧。
- [GLFW 状态/内存检查](../artifacts/graphics/glfw-sim-01/result.json)：C 夹具在 AddressSanitizer/UndefinedBehaviorSanitizer 下通过，覆盖尺寸、错误清除、回调、销毁中派发、单调时间与 fullscreen 记账。
- [JVM 桥接与真实 Window 构造](../artifacts/graphics/lwjgl-sim-08/result.json)：原生/Unsafe 地址视图一致、JNI 数组写回、Java 回调返回、回调槽耗尽负例及隔离的真实 `Window` 构造/关闭通过。
- [AOT 生成](../artifacts/graphics/metal-aot-01/result.json)：6 GiB 上限，默认拒绝控制 PASS，真实 Window/RenderSystem 集成入口完成 iOS ARM64 对象生成。运行库和链接分别使用真实 iPhoneOS/Simulator 目标。
- [真机包记录](../artifacts/graphics/metal-harness-ios-01/result.json)：当时归档、签名并导出本地蓝屏诊断 IPA，21,699,045字节；SHA256 `24c68540ffd56ce95b4bb4a70e30cd9c94c78c46f49c86d3eb58535a63cc6a6f`。该构建记录的 NOT RUN 是生成时状态；后续用户 Xcode 运行证据另存上述 device-run-02。
- [导出包签名核验](../artifacts/graphics/metal-ipa-verification-01/verify/command.json)：`codesign --verify --deep --strict` 返回0。[权限读取](../artifacts/graphics/metal-ipa-verification-01/entitlements-xml/command.json)仅有应用/团队标识与开发签名的 `get-task-allow`，不要求 JIT 或附加调试器。首次受限读取产生的警告也保留在同目录，完整读取以此条为准。

## 可复现入口

输出目录必须使用新的名称；构建器保留已有归档和导出目录。以下在项目根执行，工具链、参考依赖、既有拆分输入必须通过各构建器的指纹校验。

```bash
python3 -B tools/build_glfw_lite.py --output artifacts/graphics/glfw-sim-new --sdk iphonesimulator --test-host
python3 -B tools/build_lwjgl_lite.py --output artifacts/graphics/lwjgl-sim-new --sdk iphonesimulator \
  --glfw-library artifacts/graphics/glfw-sim-new/libglfw.dylib --test-host
python3 -B tools/build_metal_backend.py --output artifacts/graphics/metal-sim-new \
  --graphics-bridge artifacts/graphics/lwjgl-sim-new --glfw-library artifacts/graphics/glfw-sim-new/libglfw.dylib \
  --sdk iphonesimulator --test-host
python3 -B tools/probe_client_graph.py --output artifacts/graphics/metal-aot-new \
  --graphics-bridge artifacts/graphics/lwjgl-sim-new --metal-bootstrap artifacts/graphics/metal-sim-new \
  --metal-resource-probe --client-jar artifacts/c0/client-split-04/client-26.1.2-split.jar --full-build --relocatable
python3 -B tools/link_c0_ios.py --image artifacts/graphics/metal-aot-new --runtime artifacts/a1/runtime-simulator \
  --output artifacts/graphics/metal-link-sim-new --sdk iphonesimulator --stub-unsupported-jni
python3 -B tools/build_c0_harness.py --output artifacts/graphics/metal-harness-sim-new \
  --dylib artifacts/graphics/metal-link-sim-new/client-graph.dylib \
  --native-library artifacts/graphics/glfw-sim-new/libglfw.dylib \
  --native-library artifacts/graphics/lwjgl-sim-new/liblwjgl.dylib \
  --native-library artifacts/graphics/metal-sim-new/libfaot_metal.dylib \
  --metal-library artifacts/graphics/metal-sim-new/fabricaot-present.metallib \
  --simulator <UDID> --install --launch
python3 -B tools/collect_graphics_probe.py --simulator <UDID> --output artifacts/graphics/metal-evidence-new \
  --probe resources --check-runtime
```

iPhoneOS 使用相同入口，将三个原生构建器的 `--sdk` 改为 `iphoneos`，链接时选 `artifacts/b1/runtime-ios` 与 `--sdk iphoneos`。Java overlay 和 Metal Java 类的字节在两目标间一致，不能复用模拟器原生库。真机宿主省略 `--simulator` 即归档/导出；安装和运行由用户完成。

## 通过Xcode调试

打开 [C0Harness.xcodeproj](../ios/C0Harness/C0Harness.xcodeproj/)，选择共享Scheme **MetalProbe** 或默认 **C0Harness** 和自己的iPhone后运行（⌘R）。两者均已引用 `resources-link-ios-04` 的资源探针；[GraphicsProbe.xcconfig](../ios/C0Harness/GraphicsProbe.xcconfig)指向 `artifacts/graphics/xcode-device-input-02`，包含iPhoneOS的GLFW/JNI/Metal库与metallib。[输入清单](../artifacts/graphics/xcode-device-input-02/manifest.json)记录来源和SHA256。

启动时先显示宿主日志，随后左上红、右上绿、左下蓝、右下黄，约20秒后回到宿主；用户已确认该画面。日志应有 `METAL_RESOURCE_ROUNDTRIP_PASS`、`METAL_RESOURCE_PROBE_PASS` 及宿主返回记录。助手没有安装/启动实体手机；由用户运行。[main.m](../ios/C0Harness/main.m)可下原生断点；Java代码为AOT，LLDB不是Java源码调试器。宿主日志覆盖修复后的[设备目标构建](../artifacts/graphics/xcode-default-device-check-03/command.json)通过。

窗口库使用 `glfw-*-04`，将 UIView.layer 读取及窗口释放移到主线程；Metal呈现前缓存drawable纹理尺寸。旧包与旧截图保持当时输入指纹。

## 第47轮：PNG与NativeImage通路（仅模拟器）

用户要求后续只使用模拟器、不操作真机、不提问，继续自主推进。以下新增结果全部为Mac隔离测试或模拟器，不增加真机结论。

- `compiler/stb.lock.json`固定官方LWJGL 3.4.1随附的三个STB头文件（Git blob与SHA256），`tools/fetch_stb.py`核验并登记缓存。原样保留头文件双许可文本；没有执行上游Gradle或Mod脚本。
- `ios/lwjgl-lite/stb_images.c`加入内存解码/释放、缩放与PNG回调JNI。`LibSTB`使用同一个系统分配器和已签名core库；第三个overlay移除STB的Java25 FFM实现。STBI写回新增一种静态ABI，总计18种×32槽。
- [JVM真实NativeImage](../artifacts/graphics/lwjgl-sim-09/result.json)通过PNG写/读、颜色/透明度逐像素一致、带stride的子矩形缩放、回调异常传播/容量与坏数据拒绝。
- [模拟器AOT](../artifacts/graphics/images-simulator-evidence-02/result.json)为`SIMULATOR_METAL_IMAGES_PASS`：同时完成真实NativeImage断言、NativeImage裁剪上传到GPU后的逐字节读回、既有四格式资源测试、最终呈现及入口返回0。失败的第一轮[记录](../artifacts/graphics/images-simulator-evidence-01/result.json)暴露JNI异常类未声明；只补IllegalStateException/IllegalArgumentException/UnsatisfiedLinkError及String构造器，负例现在准确失败。
- [158项回归](../artifacts/graphics/regression-09/stderr.log)通过。后续着色器和绘制验证见下节。

## 第47轮：原版着色器与实际绘制（仅模拟器）

- 固定glslang16.1.0、SPIRV-Cross官方源码及CMake归档，在默认拒绝环境构建，见[主机工具](../artifacts/graphics/shader-toolchain-03/result.json)。实际调用原版RenderPipelines和GlslPreprocessor收集87条静态管线与6个后处理定义，形成60种程序变体，覆盖全部79个可执行入口和9个include。
- [60/60预编译结果](../artifacts/graphics/shaders-sim-02/result.json)：GLSL→SPIR-V→MSL→模拟器metallib全部通过。按名称统一跨阶段varying位置，使用SPIRV-Cross报告的真实Metal绑定；不手改MSL。运行时索引验证程序键、资源声明及metallib指纹。
- [模拟器绘制结果](../artifacts/graphics/draw-simulator-evidence-02/result.json)：87条原版管线成功创建Metal状态；原版GUI着色器的纹理、透明混合、归一化顶点、UBO、scissor、索引偏移/baseVertex/实例和三角扇通过GPU像素断言。最终四分屏截图已检查，入口返回0，Metal验证与主线程检查无警告。这是原版着色器加第一方几何夹具，尚非Main菜单。
- 旧client-split-02缺少移出初始化方法的final字段处理，首次绘制初始化因END_PORTAL_SNIPPET失败。必须使用已有修正包client-split-04；构建器现验证拆分报告及指纹，拒绝旧输入。
- [后端注入](../artifacts/graphics/client-metal-02/result.json)只改Minecraft.class中的候选数组为Metal、OpenGL，并清理失效的逐文件签名清单，保留原回退循环。静态自测与重复注入拒绝通过，未在宿主初始化游戏。真实Main的模拟器首次启动进入Minecraft构造后，因AOT未启用HTTPS处理器退出；已按该证据启用HTTP/HTTPS重建。官方资源索引30及4,750项对象已哈希核验并复制到专用模拟器。

## 真实Main与OpenAL（仅模拟器）

- [真实Main启动证据](../artifacts/graphics/main-simulator-run-04/result.json)：固定资源索引30、HTTP/HTTPS与OpenJDK libextnet就绪，原版Minecraft构造了UIKit窗口和Metal设备。13个缺失链接入口降为1个未触发的management入口。
- [OpenAL Soft构建](../artifacts/graphics/openal-soft-sim-04/result.json)：固定1.25.2源码归档，默认拒绝环境，CoreAudio为必需编译项；保留上游许可。公开系统OpenAL缺少原版直接调用的SOFTSystemEvents，历史失败见[启动日志](../artifacts/graphics/main-simulator-run-05/result.json)。
- [PCM模拟器证据](../artifacts/graphics/audio-simulator-evidence-03/result.json)：指定真实CoreAudio播放后端，创建上下文、上传并消费4,410字节PCM、销毁上下文和设备、入口返回0；夹具静音，未作为听感或游戏内音频验收。
- [首帧失败诊断](../artifacts/graphics/main-simulator-run-06/result.json)：真实Minecraft.run进入资源重载的Logo绘制；默认ShaderManager尚未提供源文件，但Logo与已验证的GUI_TEXTURED共用着色器。现仅允许这类已验证程序在两个默认源都未就绪时复用，并随资源重载清除验证状态；真实资源变化仍明确拒绝。
- [本地世界登录](../artifacts/graphics/main-simulator-run-09/result.json)：已创建世界并保留存档；补齐 Netty 本地通道构造器后，集成服务器记录玩家加入。原版三个区块层各申请 128 MiB，透明层另有 32 MiB 索引，合计 416 MiB。旧 256 MiB 总限额导致地形初始化退出。模拟器宿主现在显式设置 768 MiB，设备宿主维持旧默认；两者的单缓冲上限仍为 256 MiB。图形资源的逻辑计量不包含暂存和在途命令，不能当作进程内存上限。
- [真实世界画面](../artifacts/graphics/main-simulator-run-14/result.json)：原版集成服务器和地形、云层、准星、快捷栏均已显示；截图仍有光照缺陷。启动补齐 Authlib HTTP 错误响应记录的构造器/字段/访问器；模拟器 Java 地址空间从 1 GiB 调至 2 GiB。云层缓冲使用对齐的 GPU 私有副本，在独立上传队列完成后绑定。截图来自启动既有测试存档，不能代替移动、方块编辑与退出重入验收。
- [图集和光照像素复验](../artifacts/graphics/draw-simulator-evidence-03/result.json)：编译期修正三个以 OpenGL 底部为第零行的顶点入口，Metal 渲染状态同步反转绕序。非对称图集区域四个色块与天空亮度首尾行均通过真实 GPU 读回。
- [加载停顿线程记录](../artifacts/graphics/main-simulator-run-16/result.json)：本地服务器持续运行，客户端在 Authlib 聊天公钥的 Future 上等待。构建期为未要求签名的服务器标志和缺少会话数据的分支增加短路，保留有签名数据的校验路径。
- [原版单人验收](../artifacts/graphics/simulator-recovery-01/result.json)。专用模拟器从菜单创建世界，转视角、步行 348 厘米、跳跃 1 次，放置沙块并破坏，随后保存退出。重装同 Bundle ID 应用后，玩家回到磁盘记录的坐标。物品栏图标的行序在后续横屏构建修正。
- [横屏验收](../artifacts/graphics/landscape-acceptance-01/result.json)。Xcode 的 WorldSimulator 方案限制为左右横屏。实测 2622×1206 下拖动视角、取放与破坏方块、移动、打开及关闭物品栏、保存退出和独立重开。重开准确读回保存位置。物品图集采样采用 Metal 的纹理行序，动态重画的局部颜色和深度清除已通过 [GPU 像素复验](../artifacts/graphics/draw-simulator-evidence-05/result.json)。

## 当前边界与后续工作

1. **G1 PARTIAL**：真实窗口与回调已在模拟器 AOT 通过；IME 仅 committed text，预编辑、相对抓取、硬件输入和多点手势尚未验收。事件只派发实际队列，初始真实尺寸/焦点通知仅一次。
2. **G2 PARTIAL**：内存/JNI/固定回调和Minecraft最小图像通路已在模拟器AOT验证；STB仅实现内存解码、释放、1–4分量缩放与PNG回调写出及必要全局变量，不覆盖完整STB/LWJGL或Mod JNI。
3. **G3 PARTIAL**。纹理与视图、传输、颜色和深度清除、渲染通道、fence 及原版绘制已实现。模拟器已通过实际菜单和地形渲染。数组/立方体附件、整数颜色清除与计时查询仍不支持。单次暂存上限 64 MiB，初始读回同步等待，回调在游戏线程执行。性能待验收。
4. **G4 原版语料模拟器PASS**：构建期GLSL→SPIR-V→MSL、绑定与变体索引已覆盖当前原版60种程序。资源包改变shader时明确要求重建；Mod新增着色器尚未验证。
5. **G5 PARTIAL / G6 PARTIAL**：真实菜单的 UIKit 绝对触摸已经验证。游戏捕获光标时提供方向、跳跃、物品栏、放置、破坏、暂停和 F3 调试信息按钮，并用手指拖动视角；待世界内验收。F3 按钮位于左上角（36pt，与右上暂停键对称），按开关语义只发一次 90ms 的按键沿，避免点按被同一次事件轮询吞掉。IME 仅提供提交的 Unicode 文本。固定 OpenAL Soft 1.25.2 的 CoreAudio PCM 播放探针通过，真实游戏声音引擎已启动，游戏内听感和真机音频尚未验收。
6. 探针仍记录 log4j `RuntimeMXBean`/`MarkerFilter` 元数据警告；宿主在入口返回0后调用旧清理路径得到 `graal_tear_down_isolate=2`。本轮没有验证 isolate 的完整回收，不能把入口返回0扩展为生命周期验收。

早期“直接进入日志”定位为默认Scheme引用旧Main镜像；第45轮已更正，第46轮用户先后确认蓝屏和四色，设备GPU比对与呈现日志匹配。完整Main初始化、游戏绘制与独立运行仍需分别留证。C0/C0a保持BLOCKED。

## 真机 GUI 缓冲区修复（2026-11-10）

用户在真机运行 WorldDevice 时，原版 GUI 的索引绘制触发 Metal 断言。片元缓冲区槽 1 只有 40 字节，着色器需要 48 字节。Metal bridge 将缓冲区物理分配向上对齐到 16 字节，保留游戏侧的逻辑大小。开启 Metal API Validation 的模拟器中，原版 `gui_text` 管线用 40 字节 Fog 数据通过 GPU 像素检查，日志含 `METAL_GUI_TEXT_FOG_PASS`，入口返回 0。WorldDevice 新库已通过设备构建及签名检查，真机复测待完成。[模拟器日志](../artifacts/graphics/draw-simulator-fog-01/run-1794265317247.log)

## 不支持的管线必须在绘制处变成空操作（2026-11-12，pack-85 → 86）

门禁只拦注册（`RenderPipelines.register → BundledPipelines.register`）是不够的：Mod 自己持有 `RenderPipeline` 对象，会在自己的通道里直接 `setPipeline` 再画。`MetalRenderPass.setPipeline` 原来直接 `precompilePipeline`，于是抛 `UnsupportedOperationException`；异常被 Mod 的绘制循环吞掉，vanilla 的 `try`/`finally` 也不再收尾，`device.activePass` 留在原地，下一帧 `CommandEncoder.clearColorAndDepthTextures` 的第一条 `backend.isInRenderPass()` 就把整个客户端打死（`Close the existing render pass before creating a new one!`）。

两条约定从这一轮起固定下来：

- **`setPipeline` 先问门禁**：`BundledPipelines.supports(pipeline)` 为假时把这条通道标成 `skipped`，`draw`/`drawIndexed` 直接返回，只打一次 `[MCFAO_SHADER] skipping draws for unsupported pipeline <location>`。Mod 的绘制按设计被丢弃，通道本身继续走完。
- **`close()` 无条件释放槽位**：先 `closed=true`、清 `device.activePass`、成对收掉 debug group、再 `endPass`。设备此前报错或通道被重复关闭都不再抛，避免一个被吞掉的异常把全局唯一的通道槽位钉死。

判据：`game.log` 里同一轮既有 `skipping draws for unsupported pipeline`，又没有 `Draw Exception` 和 `Close the existing render pass`。`libfaot_metal.dylib` 不变（改动全在 Java 侧），图形输入可继续复用同一份 staged 目录。

## 轮询查询必须与事件回调共享同一份状态（2026-11-12，pack-88 → 89）

功能探针（`WorldUITests/testFabricModFunctions`）第一次真实交互就撞出了新崩溃：malilib 的 `KeybindMulti.reCheckPressedKeys` 每 tick 轮询 `glfwGetMouseButton`，而 GLFW-lite 只实现了事件回调（`FAOT_EVENT_BUTTON` → `GLFWmousebuttonfun`），轮询 API 被 Overlay 替换成 `UnsupportedOperationException`。冒烟跑了 88 轮没暴露——冒烟不交互，没有 mod 轮询鼠标状态；**交互一开始，轮询和回调的差异就藏不住**。

修法与 `glfwGetKey` 对齐（它一直有 `w->keys[349]` 状态表）：

- `GLFWwindow` 增加 `mouseButtons[8]`（GLFW_MOUSE_BUTTON_LAST=7），`FAOT_EVENT_BUTTON` 事件同时更新状态并调用回调（注意 `uikit_surface.m` 的入参约定：action 在 `e.b`，不是 `e.c`）；
- 失焦时按键清零的同一分支里把按钮状态也清零；
- `glfwGetMouseButton` 按钮越界/窗口无效返回 0（RELEASE）。

约定：**凡是事件回调里能发生的状态，轮询 API 必须能读到同一份真相**。`interop/graphics/glfw_state_test.c` 增加「按下 → 轮询为 1 → 释放 → 轮询为 0 → 失焦清零」断言，`GLFW_STATE_PASS` 覆盖。重建链：glfw（sim+device）→ lwjgl-lite overlay（supported 由 native `nm -gUj` 自动派生，新增导出即变为真实 FFM 调用）→ metal 后端 → `mcfao build`。模拟器 staged 输入用 `world-simulator-input-05`（glfw-sim-10 / lwjgl-sim-14 / metal-sim-27 拼装，来源哈希记录在其 result.json）。
