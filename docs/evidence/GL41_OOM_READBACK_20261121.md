# GL41 全屏读回分配失败与原生崩溃调查

日期：2026-11-21。研发阶段修复；设备验收仍为 BLOCKED。

## 结论与证据边界

三份 COMPAT-r5-IRIS-FMA 日志和原始 ARM64 二进制共同确认：OSMesa 在读回映射失败后未检查 NULL，继续逐行 memcpy，构成这次原生空指针崩溃的直接原因。13,794,176 字节是 2222 × 1552 × 4 的全屏线性 BGRA 读回 staging PIPE_BUFFER。它由 Zink 的 image_map 路径创建，用于把 GPU 图像交回 OSMesa 的 CPU framebuffer。

首次 vkAllocateMemory 返回 VK_ERROR_OUT_OF_DEVICE_MEMORY 的原因仍未确定。现有日志不足以证明物理内存耗尽、持续泄漏、MoltenVK MTLHeap 策略缺陷或 BSL 专属问题。第三次日志在关闭 BSL 后仍失败，排除了“必须启用 shader pack 才触发”的前提，但不能排除此前分配、缓存或全进程内存竞争。

本轮实际修改 Mesa、Zink 集成、GLFW/OSMesa 桥接及 UIKit 呈现层，完成主机故障注入、源码构建和签名诊断 IPA。尚无本轮真机游戏运行数据，不能宣称已满足关闭/开启光影稳定游玩的验收标准。

## 原始证据

输入源码版本为 4a1787c30526ac036590555d0b5ec15076775b08，原始构建指纹为 cf8038be13d85873cf42d58f3de0d3bc0d2427d69d3eb33ce1d254bd2d8397ef。日志位于维护者本机 /Users/kexin/Documents/临时/，未提交玩家日志。

| 日志 | SHA-256 | 关键行 |
| --- | --- | --- |
| run-1795237851544-COMPAT-r5-IRIS-FMA-20261121.log | 57df946094a4055b71f241f1fb98d5c2a93ee4b07d613e8d81e06d06c20f88ce | 4032–4090 heap=3 多种大小失败；4111–4116 heap=5 全屏读回失败；4118 Segfault |
| run-1795238437591-COMPAT-r5-IRIS-FMA-20261121.log | f53ba23a7df0f3e9665605a0e59ee050a71c4b131ba49e629dbe94b5e085e658 | 4083–4086 heap=3；4087–4092 heap=5；4094 Segfault |
| run-1795238897107-COMPAT-r5-IRIS-FMA-20261121.log | 30ac3744f4113e09a3f1b51423d040426d2f4d6b8f7ce6a7a2513fae023f9aef | 657 启用 BSL；1988 禁用光影；6188–6195 heap=5；6197 Segfault；6202–6231 寄存器 |

原始 OSMesa 的 osmesa_read_buffer 偏移为 0x631c；0x637c 调用 texture_map，0x6380 将结果存入 x22；0x63f0 调用 memcpy，返回地址为 0x63f4。第三份日志的 x1、x22、x24 均为 0，x2=0x22b8（8888=2222×4），LR=0x122a263f4。源代码的未检查映射、逐行复制和原始机器码/寄存器吻合，定位超过了“大小恰好相等”的推测。

本机保留的原始证据：

- artifacts/gl41-oom-20261121/original-log-evidence.json：输入哈希与关键日志原文/行号。
- artifacts/gl41-oom-20261121/original-osmesa-readback-disassembly.txt：原始二进制反汇编。
- artifacts/iris-fma-20261121/ios-build-r5/NCL-game-COMPAT-r5-IRIS-FMA-20261121.ipa：原始 IPA，SHA-256 ca5b9070f2b18782402ad42ab6b48b9960b1474d0481e061542d85acf69058bb。

## 提交链与资源身份

    JNI.invokePV → GLFW.glfwSwapBuffers
      → ios/glfw-lite/glfw_lite.c:glfwSwapBuffers
      → ios/glfw-lite/osmesa_gl.c: context bind / swap / glFinish
      → Mesa osmesa_flush_front → osmesa_read_buffer
      → Zink zink_image_map → PIPE_BIND_LINEAR staging PIPE_BUFFER
      → zink_resource_object / BO → vkAllocateMemory / BindBufferMemory / MapMemory
      → CPU 逐行复制到 OSMesa frame
      → uikit_surface.m:faot_surface_present_bgra / FAOTSubmitPresent
      → 三槽 Metal texture → CAMetalLayer drawable → command completion

Zink image_map 构造的临时资源 target=PIPE_BUFFER，bind=PIPE_BIND_LINEAR（0x200000），width0=layer_stride×depth；PIPE_BUFFER 的 height0/depth0 为 0。这解释了日志中的 BUF 13794176x0 和保留的 b8g8r8a8_unorm 格式标签。分配发生在提交阶段，是因为 OSMesa 在 glFinish/front flush 时要求把颜色附件映射回 CPU。它不是 CAMetalDrawable，也不是 Java 堆分配。Zink/Gallium 可以使用正常的 BO 缓存和延迟释放；一次 map 创建临时资源不自动构成泄漏。

Zink 的 heap=3 / heap=5 是 zink_heap 枚举中的 DEVICE_LOCAL_VISIBLE / HOST_VISIBLE_COHERENT_CACHED 分配属性策略，不是 Vulkan physical heap 编号。新增诊断单独记录实际 memoryTypeIndex、propertyFlags、physical heapIndex、heapSize 和可用的 EXT_memory_budget。

## 竞争假设

| 假设 | 已有证据及当前结论 | 下一步判据 |
| --- | --- | --- |
| A：资源泄漏或重复分配 | 审计发现失败 transfer 的源/staging 引用未释放，已修复；原始失败前没有资源时间序列，尚不能认定其导致首次 OOM | 世界/光影切换循环后比较同等静止状态的 live bytes、创建/销毁与内存预算 |
| B：失败后访问 NULL | 源码、原始反汇编、寄存器和读回失败测试一致，已确认并修复 | 真机持久注入读回分配失败，要求明确停止渲染且无相同 Segfault |
| C：MoltenVK 分配策略 | 原运行时输出 1.4.3；已固定二进制哈希，精确上游源码/构建选项尚未还原 | 按真实 memory type/budget 与 Metal 错误分类；目前不修改 MTLHeap 默认策略 |
| D：Java/native/GPU 竞争 | Java 最大堆 4 GiB、设备共享内存是相关条件，但地址空间预留不是物理占用证据 | 2/4 GiB 堆对照，同时采集 Java used/committed/max 与 physicalFootprint、resident |
| E：映射/复制/同步 | OSMesa map 未检查已确认；Zink 失败 transfer 引用和上传分配检查存在缺陷 | 单次、持续、after-N 注入；真实 GPU 映射和读回仍待设备 |
| F：上下文/线程/生命周期 | 已加线程归属、detach/rebind 和 resize 事务保护；呈现池按完成回收 | 设备旋转/前后台/尺寸切换，记录 reserved/drawable 数量是否有界 |

退出时仍有 GPU 内存已分配，不能独立证明泄漏。GraalVM 虚拟地址预留、启动时未触碰的 PROT_NONE/RW 映射也不能当作实际 RSS。

## 实际修复与同类审计

| 层 / 文件 | 修复或检查结果 | 边界 |
| --- | --- | --- |
| compiler/gl41/patches/mesa-25.0.7-safe-readback.patch：osmesa_read_buffer | 检查资源、目的地址、map 和 transfer；部分成功先 unmap，失败停止复制；颜色/深度路径传播 sticky 错误 | 新增 OSMesaGetLastReadbackError，需匹配 GLFW |
| OSMesa framebuffer / context | 附件分配失败清理已创建输出及弱引用；检查 calloc/MakeCurrent；释放深度快照和 current_buffer 宿主结构 | st_destroy_context 负责附件状态，osmesa_destroy_buffer 只注销 drawable 并释放结构，避免重复释放 |
| Zink create_transfer / destroy_transfer / image_map / buffer_map | 统一释放 source/staging 引用，成功 unmap 删除重复释放；u_upload_alloc 检查资源和指针；DONTBLOCK NULL 转入失败清理 | 主机夹具 3000 次 transfer 循环回到引用基线；首次 OOM 因果尚未确定 |
| Zink BO/Vulkan wrappers | allocate/create/map 失败清空输出；第二 buffer 创建失败后清空已销毁的首句柄；保留并报告实际 VkResult | 不把失败对象当成功对象交给下游 |
| ios/glfw-lite/osmesa_gl.c/.h | 强制安全 ABI；API 初始化状态分离；尺寸溢出检查；resize 先建后换；失败 bind 可能被 Mesa 保留的 CPU frame 留到 context 销毁 | 线程不匹配拒绝 swap/release；detach 后失败 rebind 仍记录新 owner |
| ios/glfw-lite/glfw_lite.c | 真正解绑/重绑；swap 失败设置 GLFW_PLATFORM_ERROR 和关闭标记；错误 owner 销毁不释放仍使用中的窗口/表面 | 保留 NO_API 窗口能力 |
| ios/glfw-lite/uikit_surface.m | 三个槽位从入队保留至 GPU completion；旧尺寸全部空闲才更换；不足槽位有界丢帧；提交前复制 CPU 内容 | 正常三槽；重建短暂最多六个呈现纹理；不以无限队列掩盖压力 |
| Metal 创建/提交 | 检查 texture/queue/command/encoder；异步错误锁存并报告，下次 swap 停止 | 未进行真实 GPU 故障注入 |
| Java ↔ Native | swap 返回状态传到 GLFW，不能靠捕获 Java 异常修复 native NULL；NO_API 与 JNI 导出保持 | 未覆盖所有第三方 Mod 的直接 native 调用 |
| 世界卸载、Iris/Sodium pipeline、纹理上传/读回、缓存 | 通用 Zink buffer/image/memory 钩子覆盖实际资源路径；清理失败 transfer；不新增整合包名或 shader pack 特判 | 没有逐个 Mod pipeline ID 的精确快照，设备循环验证未运行 |

不可恢复的读回错误采用明确停止渲染。沿用 Zink 原有分配回退/回收尝试，不增加无限重试或反复复制可能已失效的 frame。单次注入可能被现有分配重试恢复；持续注入用于检查最终失败路径。没有把降低画质、关闭光影或禁用 GPU 能力作为修复。

## OpenAL 独立调查

本轮 R5 固定 OpenAL Soft 1.25.2（compiler/openal.lock.json）。对应源码 auxeffectslot.cpp:361 的 AL_OUT_OF_MEMORY 可以由槽位上限/EnsureEffectSlots 失败产生，alc 默认上限为 64；effect.cpp:241 和 filter.cpp:384 也有独立的 Ensure 分配失败路径。第三份日志 797–801 行的音效/滤波错误明显早于最终 GPU 故障，且没有底层 reason。Mod 的“effect slot”文字不能证明实际失败 API。当前没有证据认定音频与 GPU 同根，本轮不修改音频分配策略。

## 诊断配置及覆盖范围

在 App 的 Documents/gl41-diagnostics.json 保存以下内容并完全重启 App，即可开启汇总诊断。没有 Documents 配置时回退读取 bundle 的 instance-seed/gl41-diagnostics.json。交付诊断 IPA 已内置开启；分配注入默认关闭。

    {"enabled":true}

受控分配失败，匹配 13,794,176 字节的首次分配一次：

    {"enabled":true,"failAllocation":{"after":0,"size":13794176,"count":1}}

after 表示先允许多少次匹配分配；size=0 匹配所有大小；count=18446744073709551615 为持续注入。要越过内部有限重试并到达读回最终失败路径，应使用持续注入。此模式会有意阻断渲染；验证后移除 failAllocation 或设 enabled=false 并重启。配置严格校验布尔值、非负 uint64 和完整 JSON，校验成功后才改变进程配置；不接受任意环境变量键。

CLI/测试进程可使用 FAOT_GL41_DIAGNOSTICS=1，配合 FAOT_VK_FAIL_AFTER、FAOT_VK_FAIL_SIZE、FAOT_VK_FAIL_COUNT。iOS 配置优先确定这些变量。诊断约每 5 秒汇总：

- Vulkan DeviceMemory、Buffer、Image、Framebuffer 的 created/destroyed/live/liveBytes；按创建位置跟踪活动对象。
- 分配失败输出调用函数/行号、资源操作、VkResult、size、memory type、physical heap/flags/size；扩展支持时读取 budget/usage。
- 失败时日志列出最多 32 个活动内存对象，Documents/gl41-resources.txt 保存完整跟踪表。
- Metal 呈现 texture 创建/销毁/allocatedSize，reserved slot 和 drawableInFlight；进程 physicalFootprint/resident。
- 新编译的 PlayDiagnostics.java 每 5 秒输出 Java used/committed/max；本次复用旧 AOT 的诊断 IPA 不包含此新 Java 指标。

跟踪表固定 32,768 项，有锁且不在分配钩子里再分配宿主内存。tableOverflow 非零时活动字节不完整。DeviceMemory 是实际 Vulkan 分配量；buffer 字节是逻辑大小，image 是 requirements，framebuffer 字节为 0，不能把四类相加。缓存中仍活跃对象不自动等同于泄漏。正常状态是累计时间序列，不是每次 swap 的完整逐对象 delta。

未覆盖全部 image view、pipeline、descriptor 或 MoltenVK 内部 Metal 对象，也没有 Iris pipeline 标识级别的前后快照。这些诊断缺口仍需后续设备证据决定是否扩展，不能声称本轮已完整计数所有 GPU 对象。

## 构建与自动化验证

Mesa 25.0.7 从固定归档源码构建，SHA-256 592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6。Meson/Ninja/Mako/PyYAML/packaging 版本固定；源码/构建工作目录位于系统临时文件系统，输出可在维护者可选外接盘。仅构建 iOS arm64、OSMesa/Zink，minimum iOS 17。MoltenVK 继续使用原有固定二进制（SHA-256 e513ae03cde3e1a052cc51074665eeb1fab3c3b82b13bd8e00db7cf68e9e1037）；构建使用 v1.3.0 头文件不代表运行时降级。

    python3 tools/fetch_gl41_runtime.py --output <新的运行时目录>
    python3 tools/build_glfw_lite.py --output <新的 GLFW 目录> --sdk iphoneos --client-inventory artifacts/evidence/client-native-call-inventory.json --test-host
    python3 tools/test_gl41_native.py --mesa-source <已打补丁的 Mesa 25.0.7 源码> --output <新的测试目录>

原生依赖缓存指纹包括补丁与构建器；预检拒绝未打补丁、来源不匹配、二进制被改动或平台错误的 runtime，不静默复用旧库。GL41 继续是默认渲染路线。

| 验证 | 结果 / 原始记录 |
| --- | --- |
| Java PlayDiagnostics（真实 Java 25） | 6 项 PASS，artifacts/gl41-oom-20261121/java-diagnostics-tests-final.log |
| patched runtime/provenance | 4 项 PASS，python-runtime-tests-final4.log |
| renderer profile | 8 项 PASS，renderer-tests.log |
| native dependency | 22 项 PASS，dependency-tests-final.log |
| portability | 35 项 PASS，portability-tests.log |
| 实际提取 OSMesa/Zink 函数、真实 bridge/config、Vulkan 包装层故障夹具 | 5 次编译 + 8 次运行全部 PASS，native-tests-delivery/result.json；ASan/UBSan、warnings-as-errors |
| Vulkan 注入 | off / once / persistent / after-N、失败输出污染、budget 输出、哈希表删除碰撞及 transfer 引用回归 PASS；使用 fake Vulkan，不等于真实驱动 OOM |
| iOS GLFW arm64 与宿主状态夹具 | PASS，glfw-delivery/result.json |
| Mesa iOS arm64 完整构建 | PASS，runtime-final4/result.json；patchIdentity c1bb941bb7c770a85132897887ca21e4f64e560637fefacdadaf5259715fabc4 |
| 原始 GL/OSMesa 导出与 LWJGL 导入集合对比 | 缺失均为 0，runtime-final4/abi-comparison.json |
| Xcode / 签名 / IPA | 见下方交付记录；不作为真机稳定证据 |

前期试验中出现过 fixture 期望与新版 runtime 格式不一致、未配置 Java 导致跳过等结果；表中使用修正后的最终日志，没有把这些早期结果当作通过。

## 真机回归矩阵

当前设备只读检查返回 passcodeRequired=true；Documents 备份在 60 秒超时，部分副本未完成验证。未覆盖安装现有 App，未启动游戏。下表均为 NOT RUN / BLOCKED；需设备解锁并完成存档备份后执行。

| 场景 | 对照与验收数据 |
| --- | --- |
| 原版，无光影 | 相同设备长时间进入世界，基础资源走势、帧时间、日志无原崩溃 |
| Iris + Sodium，禁用光影 | 复现第三次输入条件，验证相同读回缺陷消失 |
| Iris + BSL | 保留 shader 能力，比较峰值/稳定值及真实分配错误 |
| 0.5 / 1.0 分辨率（原生 2222×1552） | 读回大小随实际 stride/尺寸变化，检查峰值和重建 |
| 30 / 60 / 120 FPS | 比较 reserved/drawable 上界、资源稳定值、帧提交积压；请求 FPS 不等于实际 FPS |
| 2 / 4 GiB Java 最大堆 | 比较 Java 指标与 physicalFootprint/native/Vulkan 预算；需包含新 Java 源码的完整 AOT 才有新 Java 指标 |
| 进入/退出世界 10 轮 | 同等静止状态 live bytes/创建销毁是否回落，保存与重开是否正常 |
| 尺寸/旋转/前后台及切换光影 20 轮 | framebuffer/pipeline 重建不遗留资源，线程迁移和异步完成无损坏 |
| 单次 / 持续 13,794,176 字节注入 | 单次可被内部回退恢复或明确停止；持续失败停止渲染、留下报告，无同类 NULL Segfault |

每个设备场景记录测试标识、配置、时长、峰值内存、稳态资源数/字节、FPS/帧时间、失败与退出原因。未规定一个未经验证的时长就宣称“稳定”。

## 交付与风险

诊断测试标识：GL41-OOM-r1-20261121。签名包与校验摘要保存在 artifacts/gl41-oom-20261121/diagnostic-package-delivery/；result.json 记录最终 IPA SHA-256、包内标识、签名、provisioning profile、架构/平台、资源与逐 ZIP 成员核验。

最终 IPA：NCL-game-GL41-OOM-r1-20261121.ipa，565,704,601 字节，SHA-256 ec322a008589cbe7298e9b24b16358538e62eaff14f5f96dbce81183bbae837b。Xcode 构建、严格代码签名、设备 profile、无 JIT entitlement、arm64 iOS、资源、UUID、测试标识和 ZIP 全量成员核验通过。配对 M2 设备在 profile 覆盖范围内；尚未安装运行。

此包复用已审计 COMPAT-r5 的游戏 AOT 和资源，重建 native Mesa、GLFW、UIKit 宿主；不是从本轮所有 Java 源码完整 AOT 重编译。GL41DiagnosticProvenance.json 明确保留旧 AOT 来源和新 native 源码哈希，javaHeapDiagnosticsIncluded=false。打包时 sourceCommit 是工作区当时的 HEAD，另有修改中源文件哈希；不得将后续提交号冒写为已编译 AOT 来源。包内启用汇总诊断，没有启用分配注入，Bundle ID 保留以延续存档。

主要风险：源码重建 Mesa 的配置与原预编译库不同，即使符号集合通过仍需设备验证图形和性能；新 GLFW 必须与带安全 ABI 的 Mesa 一起交付；不可恢复错误会关闭渲染而非继续提交坏帧；繁忙 resize 可有界丢帧。原版、Iris、Sodium 及其他 Mod 的实际兼容/性能均等待本轮真机矩阵，不据本地测试提升任何产品 Gate。
