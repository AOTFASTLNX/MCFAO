# MCFAO 多人联机 `Loading terrain` 诊断

日期：2026-11-10（北京时间）。范围：MCFAO 客户端，Minecraft Java 26.1.2，GraalVM Native Image 25.0.2，Apple Silicon 模拟器。**真机 NOT RUN。**

## 结论摘要

| 项目 | 结果 |
|---|---|
| 复现 | 使用未修复镜像连接隔离的 26.1.2 服务器，客户端在登录、接收区块后于约 15 秒断开；服务端已生成玩家实体，客户端报 `Internal Exception: ... Arena.ofShared`。 |
| 根因 | Native Image 默认关闭 `Arena.ofShared`。Netty 4.2.7 的 `CleanerJava25` 在 Native Image + Java 25 下用共享 foreign arena 分配/释放 direct buffer；释放区块缓冲时 `SharedSession.close` 调用 `ScopedMemoryAccess.closeScope0Unsupported`，抛出 `UnsupportedFeatureError`，关闭 Netty 通道。 |
| 修复 | AOT 命令加入 `-H:+SharedArenaSupport`，并把 `fabricaot` 包加入 `--initialize-at-run-time`。没有关闭加载界面、没有改协议、没有跳过数据包。 |
| 验证 | 修复后模拟器连接同一类服务器，`ClientLevelReady` 在登录后约 0.4 秒到达，出现真实地形；UI 测试完成前进、跳跃、破坏方块；服务端未再因 `Arena.ofShared` 断开。单人世界 UI 回归通过。测试记录与截图见 [结果 JSON](../artifacts/mcfao/mp-diag-sim-02/result.json)。 |
| 真机 | **NOT RUN**。不能据此宣布“联机已修复”；需要在用户 iPhone 上用同一构建复测。 |

## 现场证据

原始日志（模拟器、未修复镜像）：

- [before-shared-arena.log](../artifacts/mcfao/mp-diag-sim-01/evidence/before-shared-arena.log)
- 关键栈：

```text
[Netty NIO IO #0/WARN] An exceptionCaught() event was fired ...
io.netty.channel.ChannelPipelineException: net.minecraft.network.Varint21FrameDecoder.handlerRemoved() has thrown an exception.
Caused by: com.oracle.svm.core.jdk.UnsupportedFeatureError:
  Support for Arena.ofShared is not active: enable with -H:+SharedArenaSupport
  at com.oracle.svm.core.foreign.ForeignAPIPredicates$SharedArenasDisabled.fail(...)
  at jdk.internal.foreign.SharedSession.justClose(...)
  at io.netty.util.internal.CleanerJava25$CleanableDirectBufferImpl.clean(...)
  at io.netty.buffer.UnpooledDirectByteBuf.deallocate(...)
  at net.minecraft.network.Varint21FrameDecoder.handlerRemoved0(...)
```

服务端同时记录 `Dev joined the game`，随后 `Dev lost connection: Disconnected`。这与“其他玩家能看到实体、实体不能正常移动”一致：登录已完成，客户端在初始区块批次处理期间被 Netty I/O 线程的异常终止，渲染线程无法完成 `LevelLoadTracker` 的 `WaitingForPlayerChunk → ClientLevelReady` 转换。

Netty 4.2.7 的 `CleanerJava25` 在 `org.graalvm.nativeimage.imagecode` 存在且 Java 规范版本 ≥ 25 时，通过 `Arena.ofShared` 的 `allocate`/`asByteBuffer` 创建 direct buffer，并在释放时 `Arena.close()`。Native Image 默认不提供共享 arena，因此这是构建配置问题，不是服务器协议问题。

## 加载界面关闭条件（26.1.2）

`net.minecraft.client.multiplayer.LevelLoadTracker`：

1. `startClientLoad` 进入 `WaitingForServer`；
2. 收到 `ClientboundLoginPacket` 后进入 `WaitingForPlayerChunk`；
3. `WaitingForPlayerChunk.isReady()` 满足任一条件才进入 `ClientLevelReady`：
   - 超过 `CLIENT_WAIT_TIMEOUT_MS` 的强制超时；
   - 玩家在建筑高度外、旁观或死亡；
   - `LevelRenderer.isSectionCompiledAndVisible(player.blockPosition())` 为真。
4. `isLevelReady()` 还要等 `LEVEL_LOAD_CLOSE_DELAY_MS`，随后关闭“Loading terrain”。

诊断日志逐项记录上述状态、`ClientChunkCache.replaceWithPacketData` 的解码、区块批次、玩家位置包和 `isSectionCompiledAndVisible` 结果，因此以后若修复的是“渲染就绪”而不是网络异常，可以直接从日志判断是哪一个条件一直不满足。

## 代码改动

1. `tools/probe_client_graph.py`
   - AOT 命令加入 `-H:+SharedArenaSupport`；
   - `--initialize-at-run-time=... ,fabricaot`，保证诊断类的系统属性在运行时读取。
2. `compiler/metal-backend/tools/fabricaot/diag/PlayDiagnostics.java`（新增）
   - 可开关：`-Dmcfao.diag.play=true`（默认）/`false`；
   - 结构化事件：`configuration_to_play`、`level_load_tracker`、`chunk_received`、`chunk_decoded`、`chunk_batch_start/finished`、`server_position`、`client_position_send`、`section_visibility`、`level_load_ready`、`connection_exception`、`channel_inactive`；
   - 2 秒一次 `heartbeat`，包含主线程 tick 数、Netty 收包数、解码数、tracker 状态和年龄；
   - `WaitingFor*` 超过 `-Dmcfao.diag.stallSeconds`（默认 35 秒）时输出 Java 线程栈。
3. `compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java`
   - 构建期在 `Minecraft.runTick`、`ClientPacketListener` 的登录/区块/批次/位置处理、`LevelLoadTracker`、`LevelLoadTracker$WaitingForPlayerChunk`、`LevelRenderer.isSectionCompiledAndVisible`、`ClientChunkCache.replaceWithPacketData`、`LocalPlayer.sendPosition`、`Connection.exceptionCaught/channelInactive` 插入诊断调用；
   - 只在构建期修改客户端 JAR，不引入运行时 Mod，也不改变数据包内容。
4. `tools/inject_metal_backend.py`
   - 编译并打包 `PlayDiagnostics.class`；
   - 校验恰好新增该类，避免把构建工具类打进客户端。
5. `ios/C0Harness/main.m` / `WorldUITests.m`
   - 模拟器可用 `FABRICAOT_SIMULATOR_QUICK_SERVER` 和 `FABRICAOT_SIMULATOR_EXTRA_ARGS` 做可复现联机测试；显式空值清除上次手工运行留下的 Quick Play 参数；
   - 新增 `testMultiplayerTerrainAndMovement`：等待 `Move forward`，前进、跳跃、破坏方块并截图，加载界面未关闭则失败。

## 复现与测试命令

隔离服务器（不接触用户服务器和账户）：

```bash
mkdir -p /tmp/mcfao-server
# 用 26.1.2 客户端 JAR + 已验证 libraries 启动 net.minecraft.server.Main
# online-mode=false, enforce-secure-profile=false, server-port=25566, --nogui
```

客户端使用专用模拟器，Quick Play 参数通过 `SIMCTL_CHILD_FABRICAOT_SIMULATOR_EXTRA_ARGS` 传入：

```bash
SIMCTL_CHILD_FABRICAOT_SIMULATOR_EXTRA_ARGS="-Dmcfao.diag.play=true --quickPlayMultiplayer 127.0.0.1:25566" \
  xcrun simctl launch <simulator> org.fabricaot.research.c0.kexin
```

自动化：

```bash
xcodebuild test -project ios/C0Harness/C0Harness.xcodeproj \
  -scheme WorldSimulatorTests -destination id=<simulator> \
  -derivedDataPath <derived> \
  -only-testing:WorldUITests/WorldUITests/testMultiplayerTerrainAndMovement \
  FAOT_GRAPHICS_NATIVE_DIR=<staged> FAOT_CLIENT_LIBRARY=<staged>/client-graph.dylib
```

单人与联机日志分别在模拟器容器的 `Documents/c0-logs/run-*.log`；服务端日志在 `/tmp/mcfao-server/server-25566*.log`。

## 已通过

- **联机加载（模拟器）**：修复后 `level_load_tracker` 依次出现 `WaitingForServer`、`WaitingForPlayerChunk`、`ClientLevelReady`；`player_chunk_ready ready=true`；`level_load_ready ready=true`；截图见 [terrain.png](../artifacts/mcfao/mp-diag-sim-02/evidence/terrain.png) · [moved.png](../artifacts/mcfao/mp-diag-sim-02/evidence/moved.png)。
- **联机移动（模拟器）**：`client_position_send` 的 `z` 从 `-5.500` 变为 `0.323`（约 5.8 格），说明输入已转化为服务器位置包；服务端在测试结束前没有 `Arena.ofShared` 异常。
- **单人回归（模拟器）**：`WorldUITests/testLandscapeInventory` PASS（41.244 秒），覆盖移动、取放/破坏、物品栏、暂停和保存退出。
- **诊断单元测试**：`tests/test_play_diagnostics.py` 2 项 PASS；500 次 section 查询在短时间内不再产生 500 行日志。
- **注入器**：`BACKEND_INJECTION_SELF_TEST_PASS`，真实 split 客户端注入通过，新增条目恰为 `fabricaot/diag/PlayDiagnostics.class`。
- 说明：上述模拟器证据来自同一组 hook + `SharedArenaSupport` 的诊断镜像；当前源码进一步把 section 日志限流从“检查次数”改为“总调用次数”，只影响日志量，已由 `tests/test_play_diagnostics.py` 覆盖。

## 尚未验证 / 下一步

1. **iPhone 真机**：用同一构建（含 `-H:+SharedArenaSupport` 和诊断）在用户 iPhone 上连接同一 Fabric API 服务器；记录带时间戳的 `run-*.log`、服务端 `joined`/`lost connection`、以及 `MCFAO_DIAG` 的 `level_load_ready`。没有这一步不得报告“联机已修复”。
2. **其他玩家视角的移动**：服务端日志和客户端 `client_position_send` 只能证明客户端发送了位置；需要另一名玩家或录像确认实体移动。
3. **47 Mod 整合包**：并发中的 `fabric-pack-02` 构建是另一条工作线；本结论基于未加 Mod 的客户端。Mod 自身的 Mixin/网络行为仍需分别验证。
4. **AOT 回归**：`-H:+SharedArenaSupport` 增加 foreign 运行时路径，需确认不会改变单人世界、Metal、音频和启动时间；当前单人 UI 回归已通过，性能未测。
5. **日志体积**：默认诊断会产生少量心跳和状态日志；发布构建建议用 `-Dmcfao.diag.play=false`。
