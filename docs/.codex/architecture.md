# 当前实现边界

Last reviewed: 2026-11-08

- compiler/ 固定 GraalVM25.0.2、OpenJDK/Graal 提交及归档指纹。fetch_upstream 仅读取官方源码；build_ios_runtime 用自行编写的 clang/libtool 编排生成119个原生翻译单元。
- interop/a1/ 是第一方 Java25/JNI/C 入口夹具。AOT 对象链接自建 iOS 运行库；iPhoneOS 与 Simulator 编译目标分别记录并校验。
- ios/A1Harness/ 提供真实调用 graal_create_isolate、Java 语义入口和 tear_down 的测试 App/Xcode 工程。结果写入其沙盒 Documents。
- A1Harness通过公开version-1参数限定256 MiB虚拟地址预留；build 2用户真机独立执行通过。build 3在主线程建立当前runID/报告名，UI只读本进程报告并显示RUNNING、时间、耗时、日志名，后台仍执行同一预编译语义入口。旧latest.json仅用于外部采集。
- ExportOptions.plist 定义本地 debugging 导出；device-handoff/ 保留签名归档、Xcode IPA、解包签名检查输入和包记录。设备运行结果不从构建/签名成功推断。
- interop/b0为第一方Mixin/访问修改/nested/Entrypoint夹具；prepare_b0只编译与打包，关闭注解处理。run_b0_reference执行时先执行第一方沙盒拒绝控制，通过后真实Knot.init并调用夹具入口，agent捕获最终第一方字节；新JVM只读导出结果，最后校验原始字节的精确失败原因。真实转换、重放、精确负例和文件/连接拒绝控制已通过；B0的run-04用于B1，run-05为运行器修订后复验。
- interop/b1/与ios/B1Harness/把B0固定闭包预编译为iOS ARM64，使用同一固定源码构建运行库和C ABI；无运行时Knot/Mixin/agent转换。build 4用户两次真机行为匹配B0。
- probe_client_graph只做真实Main可达性分析，默认拒绝策略先过控制；6/8 GiB堆与G1对照仍OOM，保存GC日志、外部time、内置元数据审计和Native Image诊断。比较工具拒绝混入非实验变量；源码版本差异另行记录。构建JFR会自动开启目标JFR，因此08的缺CAP失败独立保留，后续不启用构建JFR。C0阻断。inventory_client_native_calls只读取class常量池，319个LWJGL引用候选不等于实现或动态覆盖。
- collect_probe_result 同时检查原生返回值和 Java 成功标记；Simulator PASS 始终保留 iosGateA1=BLOCKED。
- locate_local_client 从显式选择的 Swift Craft profiles/<instance> 定位共享 meta/versions、libraries、assets、natives、runtime，不读取账户数据库或执行 Mod。
- capture 记录真实 argv/cwd/退出码/超时/日志哈希，拒绝覆盖旧目录；不是不信任代码隔离。
- .cache/ 保存可追溯输入及构建状态，artifacts/a1/ 保存编译/运行，artifacts/evidence/ 保存证据；用户游戏文件保留在工作区外。
- AAR 唯一数据库 /Users/kexin/Documents/Codex/monitor/registry.sqlite。源代码保留，安全删除标志均 false。

未完成：真实客户端AOT分析与无图形引导、iOS游戏渲染/世界、整合包闭包、完整构建隔离、游戏IPA与性能验收。
