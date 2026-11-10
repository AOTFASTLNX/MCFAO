# FabricAOT 项目

Last reviewed: 2026-11-10

目标固定Minecraft Java26.1.2 / Java25 / Fabric Only / 普通iPhone本地无JIT。当前A0/A1/B0/B1 PASS，C0 真机 BLOCKED。原版单人已在 2622×1206 横屏模拟器通过，入口为 Xcode WorldSimulator。WorldDevice 已通过本地真机构建与签名检查，等待用户上机测试。

A0真实Mac主菜单和同一进程Java25.0.1/Fabric0.19.3；A1 build 2用户退出Xcode/拔线后独立通过，build 3补充当前进程反馈。B0在默认拒绝沙盒完成真实Knot/Mixin/访问修改/嵌套JAR/入口、导出重放和精确负例；B1 build 4同一转换输入经iOS AOT，用户两次真机PASS并确认一次未连接Xcode。

统一客户端入口为 `./mcfao doctor/build/verify/export`，配置与复现见 [BUILDING](../BUILDING.md)。原版与审计过的 Fabric 子集共用构建后端。原版和第一方 Fabric 夹具已分别通过模拟器世界复测，并导出经静态验签的开发 IPA。A1/B0/B1 诊断入口仍为 prepare_b0、run_b0_reference、build_b1_probe、build_ios_runtime、link_a1_ios。真实客户端的分析墙用 `compiler/splitter` + `tools/split_methods.py` 修复（18类/28个 `static ()V` → 358段），第28轮在6 GiB下完成完整分析（32,531类型/112,219方法，注册表摘要与原版逐字节一致）。第35–36轮经 `--relocatable` 写出可重定位对象并用 `tools/link_c0_ios.py` 链成 `platform IOS, minos 17.0` 动态库；第38–43轮用 `ios/C0Harness` 装机/上模拟器，镜像真的执行到 `Main.main` 之后（参数解析、log4j、291项Datafixer、JOML Unsafe）。

图形栈已开始实现：`ios/glfw-lite`、`compiler/lwjgl-lite`/`ios/lwjgl-lite` 与 `compiler/metal-backend`/`ios/metal-bridge`。第45轮在 iOS 模拟器 AOT 执行真实 `Window` 和 `RenderSystem.initRenderer` 并显示1206×2622 Metal诊断清屏；采集器验证新日志、帧提交、探针结束和入口返回0。固定17种回调ABI各32槽，Java25多版本FFM实现由构建期JNI overlay替换。第46轮用户真机1398×2034蓝屏与日志匹配，Apple A20 Pro GPU；独立运行未确认。已补纹理/视图/encoder传输/清除型renderpass/fence与构建期呈现metallib，模拟器四格式GPU读回及四分屏通过。第47轮已补STB最小图像通路，模拟器AOT的真实NativeImage PNG读写/缩放/回调负例及GPU裁剪上传通过（images-simulator-evidence-02）；第47轮完成60/60原版shader程序预编译，87条PSO及实际绘制像素断言通过；后端数组改写完成，真实Main已启动Metal与OpenAL Soft/CoreAudio，显示并响应原版菜单；模拟器原版世界已通过创建、移动、跳跃、方块操作、物品栏、保存和重进。正式真机 C0/C0a 仍为 BLOCKED。证据/包/命令见 docs/GRAPHICS_BOOTSTRAP.md。

助手执行 Mac 构建、隔离测试与模拟器运行。用户指定游戏为横屏，并要求自行做真机测试。当前170项Python回归PASS（artifacts/graphics/regression-18/stderr.log）。命令及测试边界见 [BUILDING](../BUILDING.md)、B0_TEST_HANDOFF.md、B1_DEVICE_HANDOFF.md 与 evidence/ADR-003.md、ADR-008.md。

Swift Craft 共享客户端和 Recollection3 实例原位保留。Recollection3 CurseForge ZIP 的 6 个随包 JAR 通过元数据预检。同名本地实例的 53 个根 JAR 和 168 个嵌套 JAR 可完成一次元数据预检。兼容报告仍有 AOT 阻断，清单文件 ID 的完整对应待核验。当前A0参考实例为26.1.2-fabric-0.19.3-20260804-145519，不以旧Recollection3日志替代当前参考。使用前刷新签名、工具链、设备和本地输入。

本地Git仅保存第一方源码/文档；没有远程或推送。artifacts与.cache保持忽略，证据另由verify_evidence指纹及中央AAR保存。

拆分器、iOS 宿主、链接器和图形适配基线已进入 Git `1d9af2d`；`artifacts/evidence/handoff-snapshot-20261108` 只覆盖第13轮之前的6个文件、已过时。接手优先读 docs/WORK_HANDOFF.md。未修改Graal/pointsto.jar。

真机首次反馈“直接进入日志”已定位为默认C0Harness仍引用旧Main镜像（设备日志在artifacts/graphics/device-run-01，File参数转换失败）。用户后来确认蓝屏并有device-run-02匹配日志。工程默认Debug/Release与MetalProbe现在引用resources-link-ios-04和xcode-device-input-02（含metallib）；设备默认Scheme构建与4库UUID核对通过，见xcode-default-device-check-02。用户已确认四分屏；device-run-03有GPU比对与呈现标记，宿主返回记录因日志偏移覆盖未保留。已修复所有写入为O_APPEND。
