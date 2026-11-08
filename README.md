# FabricAOT — Java 25 iOS AOT 研发工程

目标：Minecraft Java 26.1.2 / Java 25 / Fabric Only，Mac 构建并签名、普通 iPhone 本地运行。当前 **EXPERIMENTAL：A0/A1/B0/B1 PASS，真实客户端 Gate C0 BLOCKED**，尚无可玩Minecraft iOS客户端或游戏IPA。

已有真实结果：

- 第一方 Java25 探针在 JVM、桌面 AOT 和 iOS ARM64 模拟器通过线程、ScopedValue、GC、资源、JNI、文件保存断言。
- 从固定的 OpenJDK/Graal 官方源码构建 iOS 静态库，完成 Framework 链接、iPhoneOS 开发签名归档和本地 IPA 导出。
- 用户已验证 build 2 在退出 Xcode、断开USB后独立启动，线程、ScopedValue、GC、资源、JNI与文件断言全部通过；256 MiB预留解决了首轮801错误。
- build 3 明确显示本次开始时间、耗时和日志名，用户已反馈真机PASS截图；源代码/归档/开发签名IPA均保留。
- 用户已在Mac启动26.1.2真实主菜单；同一进程的Java25.0.1 / Fabric0.19.3、依赖指纹和复现步骤已核对。
- B0已通过默认拒绝沙盒控制、真实Knot/Mixin/访问修改/嵌套JAR/入口行为、导出字节重放及未转换负例。
- B1 build 4在用户iPhone两次运行通过；用户确认一次连接Xcode、一次未连接，原始行为与Mac一致。
- 真实客户端的6/8 GiB堆与构建GC对照仍OOM；已保存GC、元数据及诊断证据，尚无完整可达性统计或iOS游戏主菜单、世界、性能结果。Mac脚本测试由助手运行，真机测试由用户负责。

入口：

```bash
python3 -B -m unittest discover -s tests -v
python3 -B tools/preflight.py /path/to/pack.mrpack
```

[B0复现](docs/B0_TEST_HANDOFF.md) · [B1真机结果](docs/B1_DEVICE_HANDOFF.md) · [客户端诊断](docs/evidence/ADR-003.md) · [A1 真机记录及 IPA](docs/A1_DEVICE_HANDOFF.md) · [A0 桌面记录](docs/A0_DESKTOP_HANDOFF.md) · [状态](docs/STATUS.md) · [构建与复现](docs/BUILDING.md) · [ADR-001](docs/evidence/ADR-001.md) · [证据索引](docs/evidence/README.md)

源码布局：tools/ 为预检和实验工具，compiler/ 固定工具链输入，interop/a1/、b0/、b1/ 为语义及转换夹具，ios/A1Harness/、B1Harness/ 为可编辑的原生测试 App/Xcode 工程。产品验收见 docs/ACCEPTANCE.md 与 docs/TECHNICAL_GATES.md。

项目不包含 Minecraft 专有客户端或玩家存档；现有游戏文件按用户选择的本地路径读取。Mod 的静态预检不能认证 iOS/AOT 兼容性。
