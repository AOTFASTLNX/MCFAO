# 持久决策

Last reviewed: 2026-11-08

- 根AGENTS/TECHNICAL_GATES是验收依据。A0/A1已通过：A0主菜单+同一进程Java25.0.1/Fabric0.19.3；A1为build 2独立运行。B0构建期转换/重放/负例及B1真机同等行为随后均已通过；C0仍BLOCKED。
- 官方桌面 GraalVM25.0.2直接 iOS 尝试报缺 java/nio/net。当前通过固定官方源码和第一方构建器编译目标库，数值 CAP 的版本契约固定25.0.2。
- static JNI 编译需要逐库设置 LIBRARY_NAME；A1 还需要实际 ZIP 原生函数和 JNI_OnLoad_zip。locale 要包含 java_props_macosx.h 的真实声明。
- 编译119单元；未提供 JVM 入口生成明确终止诊断。当前探针没有触发这些入口，不能推广为完整 Java/Mod 兼容。
- iPhoneOS 与 Simulator 原生库分开构建，link_a1_ios 拒绝目标不匹配。A1Harness 可通过 FAOT_FRAMEWORK_DIR / FAOT_JNI_LIBRARY 选择构建输入。
- JVM、桌面AOT、模拟器和用户真机build 2均通过Java25线程/ScopedValue/GC/资源/JNI/文件保存及isolate生命周期。a1-user-device-run-03原始日志与用户退出Xcode/拔线/重新打开确认共同支持A1 PASS；不会据此提升Minecraft/Fabric/性能Gate。
- 固定 Graal AddressRangeCommittedMemoryProvider 默认至少预留32 GiB，801=RESERVE_ADDRESS_SPACE_FAILED。build 2 使用 graal_create_isolate_params_t 的公开 version-1 reserved_address_space_size=256 MiB，已解决用户首轮801；不得填写内部保留字段。
- build 3以当前进程报告名显示结果，冷启动先显示RUNNING，STARTED/结束通知UI；报告有runID/processID，界面显示开始时间/耗时/日志名。每进程一次，后台恢复不重跑，划掉后启动生成新名。用户PASS截图/日志在a1-user-device-run-04；原生AOT输入未重建。
- Swift Craft 的 Recollection3 是实例目录；26.1.2.jar 在共享 meta/versions/26.1.2，大小/SHA1匹配。不得因标准 minecraft 目录缺 JAR 而断言本机没有客户端。
- A0使用新实例26.1.2-fabric-0.19.3-20260804-145519，Fabric API0.155.2+26.1.2。只读lsof关联进程所打开latest.log与映射libjvm，release确认25.0.1，依赖指纹与GUI复现步骤存a0-desktop-reference。未读取原始命令参数/令牌或启动游戏。Recollection3历史日志不用于当前A0结论。
- Loader0.19.3的getClassByteArray(true)是PreMixin，不能当最终导出；B0采用第一方Java agent只捕获Knot定义的第一方类。访问修改选择器只覆盖游戏命名空间，所以自写Target使用net.minecraft.fabricaot_fixture；元数据accessWidener由ClassTweaker读取，当前只测访问修改子集。
- interop/b0与prepare_b0已编译12类/3JAR，-proc:none。run_b0_reference必须先通过文件读写和本地连接拒绝控制，才初始化真实Knot；源码/Java/JAR指纹不符即停止。Mac脚本现由助手执行；B0真实参考/重放/负例和拒绝控制已通过，D0完整隔离未认证。不得跳过控制，不执行原有用户Mod/Gradle。
- 不执行既有整合包 Mod，不改账户/存档/原始客户端。已按TECHNICAL_GATES建立本地Git提交；不包含游戏资产/缓存/产物，不设置远程或推送。证据另外通过指纹记录。
- 所有持久生成物使用中央 AAR；可靠可重取缓存与历史证据分开标记，无自动清理。
- Xcode ArchiveIntermediates 的 BuildProductsPath 包含 App 符号链接；AAR 拒绝跟随，构建树只登记专用根，实际归档/解包文件另登记。不要删除链接迁就登记。
- 用户最新明确分工：助手运行Mac脚本测试，用户负责真机。不要因早期“测试暂时交给我”停止已授权Mac验证，也不要自动安装/启动iPhone App。69项回归PASS，含关闭输出流后仍强制超时的进程控制回归。
- B0 run-04是B1输入，19个源码输入保留source-snapshot-04；运行器后续增加资源记录与关闭流超时修复，需重新prepare。run-05复验PASS，不以其不同Target指纹替换既有B1链。
- B1 build 4两份原始日志匹配B0_BEHAVIOR与B1_SEMANTICS_PASS，用户称一次连接Xcode、一次没连。设备结论存b1-user-device-run-01；包创建时的deviceRun NOT RUN保持历史，不回写。
- C0 client-graph-07先过拒绝控制，再分析真实Main。6 GiB Java堆OOM退出3，CPU约566秒，无游戏对象/执行；不是不兼容证明。319个LWJGL静态引用候选不是动态覆盖或iOS适配完成。
