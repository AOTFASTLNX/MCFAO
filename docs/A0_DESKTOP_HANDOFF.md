# A0 Mac 参考启动交接

日期：2026-11-08。**A0已通过，运行由用户执行。** 当前证据在artifacts/evidence/a0-desktop-reference/，后续B0测试见 [夹具测试交接](B0_TEST_HANDOFF.md)。

本次实例为`26.1.2-fabric-0.19.3-20260804-145519`，用户提供真实主菜单截图。只读核对同一进程的日志文件句柄与已映射运行库：Java25.0.1、Minecraft26.1.2、Fabric0.19.3。启用的顶层Mod为Fabric API0.155.2+26.1.2，125个实际打开的JAR已记录指纹；日志未发现ERROR。启动器1.3.8(92)与GUI复现步骤已记录，未读取原始启动参数或账户数据库。

此前Recollection3历史日志的脱敏摘要保留在swiftcraft-existing-baseline.json，仅作历史记录。本次A0结论来自上面的新实例与当前进程核对，不依赖该旧日志。

在 Swift Craft Launcher 中单独新建一个参考实例，保留 Recollection3 原实例、Mod 与存档。选择 Minecraft26.1.2、对应的 Fabric Loader 和 Java25，先使用只安装 Fabric Loader 的基础配置。启动和登录由用户在自己的启动器中完成。

已找到的本地输入：

- 客户端：`~/Library/Application Support/Swift Craft Launcher/meta/versions/26.1.2/26.1.2.jar`，大小与SHA1已匹配。
- Java25：`~/Library/Application Support/Swift Craft Launcher/runtime/java-runtime-epsilon/jre.bundle/Contents/Home`。
- 共享依赖和资源：启动器的 `meta/libraries`、`meta/assets`。

请记录以下结果：实际 Java版本、实际 Fabric Loader版本、能否进入真实游戏主菜单，以及包含 `Loading Minecraft 26.1.2 with Fabric Loader ...` 的启动日志片段。主菜单截图与相应版本信息可以作为首轮反馈；失败时保留具体错误。

只需提供版本、启动行为和相关错误片段。账户密码、登录令牌、个人世界或整份账户数据库均不需要提供。Agent 不会代执行现有整合包中的未知 Mod。

A0/A1均已通过，现开始B0第一方Mixin / ClassTweaker / nested JAR / Entrypoint实验。游戏图形、世界和整合包仍按后续Gates验收。
