# 当前实现边界

Last reviewed: 2026-11-09

- compiler/ 固定 GraalVM25.0.2、OpenJDK/Graal 提交及归档指纹。fetch_upstream 仅读取官方源码；build_ios_runtime 用自行编写的 clang/libtool 编排生成119个原生翻译单元。
- interop/a1/ 是第一方 Java25/JNI/C 入口夹具。AOT 对象链接自建 iOS 运行库；iPhoneOS 与 Simulator 编译目标分别记录并校验。
- ios/A1Harness/ 提供真实调用 graal_create_isolate、Java 语义入口和 tear_down 的测试 App/Xcode 工程。结果写入其沙盒 Documents。
- A1Harness通过公开version-1参数限定256 MiB虚拟地址预留；build 2用户真机独立执行通过。build 3在主线程建立当前runID/报告名，UI只读本进程报告并显示RUNNING、时间、耗时、日志名，后台仍执行同一预编译语义入口。旧latest.json仅用于外部采集。
- ExportOptions.plist 定义本地 debugging 导出；device-handoff/ 保留签名归档、Xcode IPA、解包签名检查输入和包记录。设备运行结果不从构建/签名成功推断。
- interop/b0为第一方Mixin/访问修改/nested/Entrypoint夹具；prepare_b0只编译与打包，关闭注解处理。run_b0_reference执行时先执行第一方沙盒拒绝控制，通过后真实Knot.init并调用夹具入口，agent捕获最终第一方字节；新JVM只读导出结果，最后校验原始字节的精确失败原因。真实转换、重放、精确负例和文件/连接拒绝控制已通过；B0的run-04用于B1，run-05为运行器修订后复验。
- interop/b1/与ios/B1Harness/把B0固定闭包预编译为iOS ARM64，使用同一固定源码构建运行库和C ABI；无运行时Knot/Mixin/agent转换。build 4用户两次真机行为匹配B0。
- probe_client_graph只做真实客户端可达性分析与镜像生成，默认拒绝策略先过控制；分析墙由 `compiler/splitter`（ASM，构建期拆分 `static ()V` 巨型方法）解决，第28轮 6 GiB 下完整分析通过（32,531类型/112,219方法）。`--full-build --relocatable` 只写可重定位对象，再由 `tools/link_c0_ios.py` 用 `xcrun --sdk iphoneos|iphonesimulator clang -dynamiclib` 链成 iOS dylib；svm 自己的链接目标永远是宿主，不能用来产出 iOS 产物。C0 现只剩图形层阻断。inventory_client_native_calls只读取class常量池，319个LWJGL引用候选不等于实现或动态覆盖；第44轮把图形部分细分为 59 个 GLFW 函数、13 个 GL 引用类、88 个 shader（GRAPHICS_STACK_PLAN §2）。
- ios/C0Harness/ 是真客户端宿主：`dlopen` 镜像（不链接，避开 install name 不匹配）→ `run_main`，argv 注入 `-XX:ReservedAddressSpaceSize`，所有写入方以O_APPEND追加并逐行flush到 `Documents/c0-logs/`，`chdir` 到 gameDir，必须有 UIScene 清单。真机通道走 `devicectl`（锁屏可装不可起），模拟器通道走 `simctl`（无需解锁，默认迭代方式），两侧共用同一个无平台标记的镜像对象。
- 图形启动：`ios/glfw-lite` 提供UIKit/CAMetalLayer与游戏线程回调队列；`compiler/lwjgl-lite`替换Platform/Library/Upcalls及回调清理，基础JNI替代Java25多版本FFM。`tools/lwjgl_codegen.py`预编译1721个JNI调用适配器和17种GLFW+1种STBI写回ABI，各32固定回调，空函数指针/槽耗尽明确失败。Metal提供真实device/buffer/sampler、纹理/视图、同步传输/读回、整面清除、清除型renderpass与fence；构建期metallib呈现第一方纹理。游戏pipeline/draw/bind/scissor已通过87条原版PSO与GPU像素断言；60/60原版shader程序通过构建期翻译，按实际Metal绑定索引生成只读资源包。MetalProbe真机蓝屏日志匹配；MetalResourceProbe模拟器与用户真机四格式GPU读回与四分屏通过（真机返回行受旧日志覆盖问题影响，独立启动未确认）；不是完整Main或游戏帧。STB内存PNG解码/写回、1–4分量缩放和NativeImage裁剪上传已在模拟器AOT验证；源码锁与缓存见compiler/stb.lock.json、tools/fetch_stb.py。详见GRAPHICS_BOOTSTRAP。
- C0Harness通过显式`--native-library`验证并嵌入同目标原生库；`--output`保留独立构建和已有归档。宿主把签名目录经org.lwjgl.librarypath传给Java。collect_graphics_probe只接受新日志并同时验证初始化/呈现/结束/返回0，保留截图。
- collect_probe_result 同时检查原生返回值和 Java 成功标记；Simulator PASS 始终保留 iosGateA1=BLOCKED。
- locate_local_client 从显式选择的 Swift Craft profiles/<instance> 定位共享 meta/versions、libraries、assets、natives、runtime，不读取账户数据库或执行 Mod。
- capture 记录真实 argv/cwd/退出码/超时/日志哈希，拒绝覆盖旧目录；不是不信任代码隔离。
- .cache/ 保存可追溯输入及构建状态，artifacts/a1/ 保存编译/运行，artifacts/evidence/ 保存证据；用户游戏文件保留在工作区外。
- AAR 唯一数据库 /Users/kexin/Documents/Codex/monitor/registry.sqlite。源代码保留，安全删除标志均 false。

未完成：图形栈的完整窗口/IME/相对输入、STB其余API、完整Main菜单、资源探针真机独立启动验证、完整 Fabric 静态化全链、反射/资源/JNI 完整闭包、iOS 游戏渲染/世界、整合包闭包、完整构建隔离、游戏 IPA 与性能验收。
