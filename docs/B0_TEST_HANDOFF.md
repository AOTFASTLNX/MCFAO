# B0 第一方转换夹具测试

日期：2026-11-08。A0/A1/B0/B1均已通过各自范围的验收。Mac脚本测试由助手执行，真机安装和运行由用户负责。

实际B0成功记录为 artifacts/b0/run-04/result.json，来源 prepared-04；该版本源码指纹快照保留在 artifacts/b0/source-snapshot-04/。B1使用的就是这一轮转换结果。最新运行器的prepared-05/run-05复验也PASS；其转换字节指纹单独记录，不能替换B1的run-04输入链。后续运行器增加资源预算记录及关闭输出流后的超时处理，因此复现须从当前源码重新准备，不能将旧prepared目录用于新代码。

复现使用两个未存在的新目录：

```bash
python3 -B tools/prepare_b0.py --graalvm-home .cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home --output artifacts/b0/prepared-new
python3 -B tools/run_b0_reference.py --prepared artifacts/b0/prepared-new --output artifacts/b0/run-new
```

该命令不操作启动器的原实例、Mod或存档。它使用Java25与固定哈希的Fabric0.19.3依赖，自己的工作目录和仅含第一方夹具的mods目录。游戏本体从本地只读引用，不下载或复制进夹具JAR。

## 执行顺序与成功条件

1. 先在macOS sandbox-exec中运行第一方控制程序，检查工作目录外的测试文件不能读写、不能连接父进程提供的本地测试端口。该程序没有Fabric/Mixin类初始化。任一控制失败、Java不能启动或沙盒不可用，都在初始化Fabric前停止。
2. 控制通过后，初始化真实Knot/MinecraftGameProvider，到Knot.init返回时停止，不调用Minecraft游戏main。仅发现第一方Mod，测试真实Mixin、ClassTweaker访问修改、nested JAR发现和两个main Entrypoint。
3. 第一方Java agent在Knot定义第一方类时保存最终字节码。不会导出Minecraft游戏类；`net.minecraft.fabricaot_fixture.Target`也是本项目编写的测试类，该命名空间用于命中上游游戏类访问修改选择器。
4. 新JVM直接加载导出的字节码，按这个夹具固定的两个入口重放行为；最后用未转换的原始类作负例，必须明确因Mixin效果缺失而失败。

成功时result.json的status/gateB0均为PASS，sandboxProbe与negativeControl为PASS；reference/replay输出相同的`B0_BEHAVIOR mixed=42 widened=7 parent=1 nested=1`，并分别有B0_REFERENCE_PASS/B0_REPLAY_PASS。B1后续已通过真机行为验证，见[B1记录](B1_DEVICE_HANDOFF.md)。B0单轮记录仍保留该轮创建时的B1 BLOCKED，不回写历史。

失败时保留各阶段result.json、command.json、stdout.log和stderr.log。早期run-01/02/03因dyld根目录读取及JDK本机UID查询权限失败，修复使用精确根目录literal与两个命名mach服务；未开放用户主目录或通用网络权限。诊断摘要见 artifacts/evidence/b0-startup-diagnostics/。
## 范围

ClassTweaker本次验证其访问修改子集，使用Loader0.19.3仍采用的`accessWidener`元数据入口和v2 official格式；不包含枚举扩展等全部机制。重放入口列表只覆盖这个夹具，不代表已实现任意Mod的通用闭包化。Java agent只用于Mac构建期取证，不进入iOS运行时。

沙盒使用默认拒绝、明确的只读工具链/JAR列表、独立可写工作目录和最小环境，不传递用户会话环境或Java agent注入变量。子进程有CPU、超时、单文件大小、文件描述符限制；Java堆与元空间另有上限。这仍不是完整D0认证：跨进程攻击、总RSS/磁盘配额、所有系统调用和恶意Gradle/Mod逃逸场景未全部验证。当前入口也不会执行用户整合包或Gradle脚本。

使用`javac --release 25 -proc:none`编译，prepare仅打包不执行Mod。自动化回归命令为`python3 -B -m unittest discover -s tests -v`，当前输出见 artifacts/evidence/unit-tests-b1-c0-final/。源码、Java或固定JAR变化均必须重新prepare；运行器核验指纹后才执行。
