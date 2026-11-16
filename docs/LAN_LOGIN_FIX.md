# 用户真机确认：LAN r4（2026-11-17）

用户反馈“测试成功，成功进入多人游戏”。已验证私有测试包 LAN-r4-20261117 / build 8，修复 GLFW OpenGL 桥接库不匹配；完整证据、IPA 指纹与范围见 [GL41_STARTUP_BRIDGE_FIX](GL41_STARTUP_BRIDGE_FIX.md)。双向联机矩阵和长时性能仍需独立验收。

# 局域网双向登录修复（2026-11-15）

状态：研发修复，联机验收保持 BLOCKED。2026-11-16 用户新日志确认主线程阻塞在 authlib 服务公钥就绪信号。上轮 IPA 后续审计发现旧 LWJGL 输入使游戏代码不可达；签名通过不能证明该包能启动游戏。下方保留历史交付记录，最新调查见本节。

## 2026-11-16 第二次用户日志与构建审计

- 用户提供 `run-1794759895707.log`，日志第 738–765 行主线程为 WAITING：`CompletableFuture.join → YggdrasilServicesKeyInfo.lambda$get$1 → ServicesKeySet.keys → SignatureValidator.from → Services.profileKeySignatureValidator → ClientPacketListener.initializeChatSession`。区块已经抵达，主循环停在 626，不能继续解码和加载地形。
- 第 324 行仍为旧诊断格式，没有新版 `tickStallSeconds` 与 handler 字段。日志中的游戏主循环和旧诊断不可能来自上轮交付 IPA 的新 AOT 二进制；现有日志缺少镜像 UUID，无法进一步确定设备实际运行的包。不能据此归因于用户安装操作。
- 上轮配置引用 `lwjgl-ios-world-02`；其 JAR 哈希有效，但产物早于当前 OpenGL 适配代码。`Configuration.OPENGL_LIBRARY_NAME_DEFAULTS()` 仍按桌面平台分派，`Platform.IOS` 永远走异常分支。原生反汇编显示 GlDevice 构造器调用 GL 初始化后无正常返回；AOT 对象与 IPA 中均缺少 Minecraft.runTick、ClientPacketListener 和 PlayDiagnostics。
- 上轮反射元数据确实进入 AOT，但后续游戏路径被裁掉，所以不能将它视为可用的联机测试包。旧包保留作失败证据，不应继续分发。
- 已按现有源码重建 LWJGL，主机 JNI / Minecraft Window / NativeImage 隔离夹具通过。新检查在 AOT、链接、最终 App 三处确认主循环、玩家信息处理器与新版诊断存在，并提前拒绝过期的 GL41 overlay。检查是可达代码下限，不等于运行验收。
- 宿主启动日志增加实际 run_main 所属 Mach-O 的 LC_UUID，供下次直接与 IPA 二进制核对。保持认证和聊天签名规则不变；日志中 accessToken=0 引起的账户授权失败需单独处理。
- 本轮 78 项针对性回归通过，0 跳过，原始记录在工作副本 `build/lan-regression-20261116-03/`。新增回归确认“只有 AOT 入口”和“只有旧诊断”的镜像均被拒绝。新包见下节，设备测试由用户完成。

## 第二版无 Mod 真机测试包（2026-11-16）

- IPA：`artifacts/mcfao/lan-vanilla-device-20261116-03/FabricAOT-26.1.2-Vanilla-LAN-r2-20261116.ipa`；481,516,686 字节（459.2 MiB）。SHA-256：`4348167082acef5bec02c956ed84bd9847a757d3064707a9a80d2f89d51b9f27`。
- 源码：`067e2f76e0fce17480fea07aaa9daa9a615d8d22`；构建时已跟踪源码无差异。Minecraft 26.1.2 Vanilla / GL41 / iOS ARM64；无 Mod、无 Fabric Loader/Mixin 运行时输入、无实例种子目录。
- LWJGL 从当前工作副本源码重新生成，保留与 GLFW 的输入哈希绑定。JNI / Window / NativeImage 主机夹具通过；额外 JVM 检查实际执行 iOS 下的两个 OpenGL 默认库方法，均返回 `lwjgl_opengl`。
- 新 AOT 4 分 17 秒完成，49,960 个可达类型、204,940 个方法；对象 242,180,191 字节，SHA-256 `6949be4649a263bd8eeaddb9dc884ffb922a08fe0f32cf2afd1778c07fc8e39d`。原生对象、链接结果和签名 App 均通过当前游戏代码检查，最终 IPA 解包后再次通过。
- 实际游戏镜像 UUID：`0AAAECFC-C42A-3F2D-B439-F19055A42CC5`。下次启动日志应有 `[FAOT] imageUUID=0AAAECFC-...`，进入世界后诊断应包含 `tickStallSeconds=5` 及 handler 字段。
- 解包后的逐文件哈希、ZIP CRC、全部资产、镜像来源 UUID、arm64/iOS、开发签名、描述文件和无动态代码权限检查通过。签名保留 Bundle ID `fab.aot.kexin`，覆盖 3 台设备，到期为北京时间 2026-11-20 00:13:37。链接仍保留原有 OperatingSystemImpl.initialize0 的显式不支持入口，不提升平台兼容性结论。
- 构建在 APFS 临时目录完成，外接盘挂载检查正常执行。最终 IPA 与原始日志、对象、输入指纹归档到上面的外接盘目录；`archive.json` 记录来源路径映射和复制前后哈希。`verification-final-03/result.json` 是最终检查记录。第一轮受限验签无法访问信任信息，第二轮精确符号检查写错嵌套类前缀；原始失败日志保留，最终使用正确符号并在可访问本机信任信息的环境全部通过。
- 构建后将代码检查改为只读，避免新增验证报告改变阶段检查点指纹；不改变游戏二进制。
- 尚未安装或启动设备。两方向联机、移动 / 物理、地形加载和保存仍待用户复测，状态保持 BLOCKED。

重现命令（配置中的 LWJGL 指向本轮新生成依赖，输出目录需不存在）：

```sh
arch -arm64 python3 -B tools/mcfao.py build \
  --version 26.1.2 --loader vanilla --target ios-arm64 --renderer gl41 \
  --config .local-build/lan-gl41-config.json --bundle-id fab.aot.kexin \
  --heap-gib 7 --parallelism 3 \
  --output /private/tmp/mcfao-lan-vanilla-device-20261116-03
```

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

## 2026-11-16 原版真机测试 IPA

- 源码：`83d10133db3d96d31d7b763a22c9773ba33d6abc`，包含 `562346e` 联机修复及外接盘迁移后的 GraalVM 真实路径解析修正。
- Minecraft 26.1.2 Vanilla，无 Fabric Loader、无 Mod、无实例种子目录；GL41 / OSMesa-Zink / MoltenVK，iOS ARM64 原生 AOT。
- IPA：`artifacts/mcfao/lan-vanilla-device-20261116-02/signed-ipa-final/FabricAOT-26.1.2-Vanilla-LAN-fix-20261116.ipa`。452,051,230 字节（431.1 MiB），SHA-256：`f970c73a0db46aff5dc82bbab57eee6e2cb376262f593f1d76b143b58164418a`。
- Bundle ID：`fab.aot.kexin`；沿用已有本地开发签名与原始 App 权限，描述文件覆盖 3 台已登记设备，到期时间为北京时间 2026-11-20 00:13:37。未增加 JIT / 动态代码权限。
- 新游戏 AOT 约 1 分 58 秒完成，生成 167,149,918 字节的 relocatable 对象，SHA-256：`2b63a1761d07fe653416e7e75ecfd1b1f9979e3a754be286661f79e414b21596`。隔离负例控制 PASS；运行库重新构建并链接至 `arm64-apple-ios17.0`。
- `signed-ipa-final/result.json` 记录输入、AOT 对象、配置、脚本与最终 IPA 指纹。修复后的反射配置 SHA-256 为 `ce5c988152e318122a6798b626450db0476828cd10bdb6a4e9a85df67ba6cfc6`。
- 原 CLI 在 exFAT 完成 Xcode 构建后，因 `._*.dylib` 被识别为额外库而未完成最终验证；失败日志保留在 `lan-vanilla-device-20261116-build-log-02/`。将其新构建结果复制到 APFS 临时目录，删除副本中的 5,023 个 AppleDouble 文件，以相同本地身份和原始权限重新签名，生成上述 IPA。封装脚本和每次签名命令保存在 `signed-ipa-final/`。
- 最终 App 与 IPA 解包结果均通过 `codesign --verify --deep --strict`、ARM64 / iOS 平台、Native Image ABI、运行库 UUID 来源、全部游戏资源哈希校验；ZIP CRC 和解包前后逐文件 SHA-256 一致，无 AppleDouble 文件。外接盘挂载检查在构建和封装时均正常执行。
- 未安装、启动或操作设备；两方向联机、地形加载、移动物理与存档仍待用户真机复测。
- 本机中央 AAR 可执行文件不可用，登记请求保留为 `signed-ipa-final/registration-pending.json`；IPA 校验独立通过。

构建命令（从修复工作副本执行，输出目录需新建）：

```sh
arch -arm64 python3 -B tools/mcfao.py build \
  --version 26.1.2 --loader vanilla --target ios-arm64 --renderer gl41 \
  --config /Users/kexin/Documents/ChatGPT/MCFAO/artifacts/mcfao-gl41.json \
  --bundle-id fab.aot.kexin --heap-gib 7 --parallelism 3 \
  --output artifacts/mcfao/lan-vanilla-device-20261116-02
```
