# 局域网双向登录修复（2026-11-15）

状态：研发修复，JVM / macOS ARM64 AOT 对照通过；本轮完整游戏 AOT / IPA / 真机复测 NOT RUN。联机验收保持 BLOCKED。

修复分支：`integration/gl41-gui-ipa-20261115-lan-login-fix`。独立工作副本：`.worktrees/lan-login-fix/`，以便与根工作区的并行开发隔离；下述命令在该工作副本内执行。

## 用户现象与日志证据

用户提供 `run-1794747176132.log`：手机开局域网时，电脑停在认证后超时，手机未显示玩家加入；电脑开局域网时，手机停在加载地形，电脑已显示 Dev 加入并创建静止玩家实体，结束手机进程后连接退出。

- 日志 622–650 行：手机认证线程在 `hasJoinedServer` 解析成功响应时，缺少 `HasJoinedMinecraftServerResponse` 的 record 组件反射信息；随后登录超时。
- 日志 784 行：手机加入电脑时还有 `Failed to write value`。
- 日志 791–828 行：远程登录和区块已经抵达，但客户端帧循环计数保持 6952、区块解码计数保持之前单人世界的 401，最后 tick age 超过 20 秒；没有卡住时的线程栈，不能仅凭该日志确定具体阻塞调用。

## 已复现的根因

`interop/diagnostics/AuthlibJsonProbe.java` 使用真实 authlib 7.0.63、Gson 2.13.2 和项目固定的 GraalVM CE 25.0.2；请求 / 响应全部为第一方合成数据，公钥临时生成，HTTP 方法由内存替身覆盖，不访问任何服务器或真实账户。

使用修复前的反射配置生成桌面 ARM64 Native Image，可复现：

1. `HasJoinedMinecraftServerResponse` 解析抛出与用户日志一致的 `Record components not available`。
2. `JoinMinecraftServerRequest` 序列化失败，authlib 包装为 `Failed to write value`。
3. `YggdrasilServicesKeyInfo$KeySetResponse` 解析抛出 Gson `RuntimeException`。authlib 的获取逻辑仅捕获 `MinecraftClientException`，定时任务异常退出，未执行后续 `ready.complete(null)`。调用 `ServicesKeySet.keys()` 的线程永久等待在 `CompletableFuture.join()`；探针在 3 秒超时后记录该栈并失败。

第三条是可复现、与手机加载卡顿相符的阻塞机制；它仍需要新版 IPA 真机复测确认是否就是本次设备上的全部原因。

## 修复

- `compiler/reflection-config.json` 新增 15 个 authlib 类型的构造器、方法和字段元数据，覆盖加入请求、加入响应、玩家资料、服务公钥与嵌套公钥数据、账户权限 / 封禁状态、资料密钥及相关枚举。record 的组件访问方法和构造器必须同时可反射；仅注册字段不足以支持 Gson 的 record 适配器。
- 现有 MDAF 合并和构建指纹会自动纳入该配置；GL41 和可选 Metal 后端共用，需重新执行游戏 AOT 才能进入 IPA。
- `PlayDiagnostics` 将主循环停滞阈值单独设为 5 秒，保留加载状态阈值 35 秒。即使状态为 `WaitingForServer` 或网络还在收包，主循环停滞也会抓取线程栈。正常的加载状态检查由诊断线程执行，避免游戏线程自行遍历全部线程栈。
- 客户端数据包处理在 `PacketUtils.ensureRunningOnSameThread` 成功之后记录处理器名称，正常返回时标记结束；线程转交异常和原处理异常继续原样传播。心跳包含处理器名称、执行状态和耗时，线程栈包括认证线程。

上述改动保留原有签名校验、服务端安全聊天策略和地形就绪判定。

## 复现命令

先执行外接盘检查：

```sh
python3 -B tools/external_storage.py --json
```

使用本地已核验的六个官方依赖：authlib 7.0.63、Gson 2.13.2、Guava 33.5.0-jre、failureaccess 1.0.3、SLF4J API 2.0.17、commons-lang3 3.19.0。将这些 JAR 的完整路径按列表传给 `--libraries`，输出目录必须不存在：

```sh
python3 -B tools/probe_authlib_json.py \
  --libraries /path/to/authlib.jar /path/to/gson.jar /path/to/guava.jar \
    /path/to/failureaccess.jar /path/to/slf4j-api.jar /path/to/commons-lang3.jar \
  --output artifacts/mcfao/authlib-regression-new \
  --native-image --baseline-config /path/to/before-reflection-config.json
```

去掉 `--baseline-config` 仅验证修复版；去掉 `--native-image` 仅执行 JVM。所有子步骤保留命令、退出码和原始日志，`result.json` 记录输入和二进制 SHA-256。

## 本轮验证

- `artifacts/mcfao/lan-login-fix-20261115/probe-aot-02/result.json`：JVM 四模式 PASS，旧配置四模式预期失败复现，修复版桌面 AOT 四模式 PASS。
- 旧 / 新桌面探针 SHA-256：`45859ccc460c18503a7040b04b555913dff04f822c715425d1211dbfc775f10b` / `5579d94f93785b2635e1b467b8181b90017d6487937a3e9b76e5a53e2e425ce9`。
- `artifacts/mcfao/lan-login-fix-20261115/gl41-patched-final/result.json`：真实本地 26.1.2 客户端的 GL41 构建期转换通过，8 个预期类变更并带诊断 helper；未执行游戏。
- `regression-real-client-classfiles-verify/`：提取转换后的 classfiles，使用 JVM `-Xverify:all` 加载并解析 8 个修改类及 2 个 helper 的成员，通过。原版 JAR 的旧签名不适用于转换结果，直接从带旧签名条目的 JAR 加载的首轮失败日志保留在 `regression-real-client-verify/`。该验证不初始化游戏类。
- `tests/test_authlib_reflection.py` 验证实际 MDAF 合并后仍保留登录 / 公钥闭包；`tests/test_play_diagnostics.py` 验证持续收包时依旧抓取停滞客户端并保持可关闭；`tests/test_packet_diagnostics_injection.py` 实际执行变换后的第一方 handler，验证线程转交、提前返回及原异常传播。
- `artifacts/mcfao/lan-login-fix-20261115/regression-isolated-final-02/`：authlib 反射、配置扫描、末影龙阶段反射、停滞诊断、处理器插桩、MDAF 与 GL41 清单共 47 项回归全部通过，0 跳过。`command.json` 保存完整命令和日志指纹。
- 首轮组合回归 `regression-isolated-final/` 的两项 MDAF 用例因测试临时目录位于外接 exFAT，生成的 AppleDouble `._*.json` 被现有元数据扫描器当作 JSON 而失败。保留原日志；最终回归仅将测试夹具临时目录设为 APFS `/private/tmp`，证据仍写入外接盘，构建挂载检查正常执行。外接盘上的元数据伴生文件策略属于独立问题，本修复未改动该扫描器。

## 真机复测

重新 AOT、签名和导出包含本次配置的新 IPA 后，由用户分别执行手机开局域网 / 手机加入电脑。确认两端加入提示、手机加载完成、移动 / 物理 / 方块操作和断线重连；测试已有单人存档的加载与保存。若仍卡住，等待至少 8 秒导出本次新日志，检查 `client_tick_stall`、`clientHandler` 及 `thread_dump_start` 到 `thread_dump_end`。401 和真实账号授权仍需独立验证，补齐元数据不产生有效账户会话。
