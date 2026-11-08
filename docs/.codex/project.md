# FabricAOT 项目

Last reviewed: 2026-11-08

目标固定Minecraft Java26.1.2 / Java25 / Fabric Only / 普通iPhone本地无JIT。当前A0/A1/B0/B1 PASS，C0 BLOCKED，尚无可玩iOS客户端或游戏IPA。

A0真实Mac主菜单和同一进程Java25.0.1/Fabric0.19.3；A1 build 2用户退出Xcode/拔线后独立通过，build 3补充当前进程反馈。B0在默认拒绝沙盒完成真实Knot/Mixin/访问修改/嵌套JAR/入口、导出重放和精确负例；B1 build 4同一转换输入经iOS AOT，用户两次真机PASS并确认一次未连接Xcode。

入口：prepare_b0、run_b0_reference、build_b1_probe、build_ios_runtime、link_a1_ios。真实客户端诊断为inventory_client_native_calls与probe_client_graph，C0的09/10轮6/8 GiB Parallel与11轮8 GiB G1均Java heap OOM退出3，无完整分析统计、客户端对象或执行结果；源快照/GC日志/审计/对照见CLIENT_GRAPH_DIAGNOSTICS。

用户最新授权分工：助手执行Mac脚本和隔离测试，用户负责设备安装/运行。79项自动化回归PASS。不要自动安装或启动手机App，不再对已授权Mac脚本反复询问。命令/边界见docs/BUILDING.md、B0_TEST_HANDOFF.md、B1_DEVICE_HANDOFF.md与evidence/ADR-003.md。

Swift Craft共享客户端、53个Recollection3 Mod、账户和存档保留原位。当前A0参考实例为26.1.2-fabric-0.19.3-20260804-145519，不以旧Recollection3日志替代当前参考。使用前刷新签名、工具链、设备和本地输入。

本地Git仅保存第一方源码/文档；没有远程或推送。artifacts与.cache保持忽略，证据另由verify_evidence指纹及中央AAR保存。
