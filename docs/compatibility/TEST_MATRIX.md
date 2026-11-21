# 验证记录

基线提交 `9126340497d8528cd52d23b6aac084b065e32262`。工具链为锁定 Java 25.0.2、Fabric Loader 0.19.3 和 Xcode 27.2。构建输入和每阶段命令的哈希由 `mcfao` 持久化。本次日志入口为 `logs/compat-20261121/`。

| 覆盖层 | 输入和结果 | 原始证据 |
| --- | --- | --- |
| Fabric JVM 元数据 | 固定 Loader 元数据解析对照，别名、动态字符串、嵌套、缺失及依赖谓词通过 | `test_mod_catalog.py`、`selected-checks/test_mod_catalog` |
| B0 | 隔离真 Knot、Class Tweaker、Mixin、嵌套 JAR，转换重放及错误输入控制通过 | `final-b0-replay/result.json` |
| Fabric Event | 原始与出货 Fabric API 的 ArrayBacked 事件行为一致。零监听者、一/多监听者的注册顺序、异常对象透传均通过 | `r2-event-runtime-verified` |
| Fabric 入口和 PNG | 自定义 stage 的惰性实例与 provider、宽栈、插件重放、像素对照、损坏/过尺寸拒绝 | `selected-checks/test_runtime_lowering` |
| 真实 Tooltip | 约束到当前 Fabric 物品 API。与原版 `ItemStack` 的扫描结果对照，31 个真实组件顺序一致，列表不可变 | `r2-tooltip-runtime-verified/run` |
| 真实 Pack | 使用转换后的 Fabric 资源实现枚举 client/server pack。读取 Sodium 和 Biomes O’ Plenty 文件，逐字节 SHA-256 对照 | `r2-pack-runtime-retry/run` |
| Classpath 与 Gson | macOS Native Image 和 JVM 完成实际资源实读、默认值、继承字段、EnumMap、保存重载和坏输入。无注册资源触发严格诊断 | `native-mechanism` |
| 兼容性检查选测 | 从 r2 报告选择六组已有测试并执行，六组退出码 0。报告保留序列化夹具和目标设备类测试缺口 | `selected-checks/result.json` |
| 材料扫描缓存 | r2 完整类路径 53,744 类，冷扫描 33.06 秒。相同输入及次序暖扫描 0.28 秒，命中 | `r2-warm-scan.json`、`r2-fabric-build.log` |
| Builder | 91 个 Vitest 用例、Vite 构建、Playwright 键盘展开逐 Mod 状态和诊断 | `desktop-unit.log`、`desktop-build.log`、`desktop-browser.log` |
| 原版 | COMPAT-r1 无签名 iOS ARM64 包经 `mcfao verify` 验证。真实游戏入口及诊断代码存在 | `full-vanilla.log`、`full-vanilla-verify.log` |
| 第三方 Mod 组合 | 上一轮合法输入的 41 个根 JAR 加散装资源，哈希重新核对。COMPAT-r2 转换 109 个，未排除。真实 Native Image 分析 79,157 类型。无签名及开发签名 IPA 均通过通用验证 | `r2-fabric-verify.log`、`r2-signed-verify.log` |
| TechReborn/RebornCore | 未找到同版完整输入做目标复验。通用容器查询回归已执行 | 见历史 `MOD_ADAPTATION_PLAN.md` |
| iOS 模拟器 | DEVICE_NOT_RUN。现有世界冒烟脚本要求 Metal 模拟器运行库，本轮默认 GL41。还需 GL41 模拟器输入和同构测试环境 | `simulator-list.log` |
| 装置上的世界和存档 | DEVICE_NOT_RUN。有效开发描述文件未覆盖目标 iPhone，已保留实际设备校验拒绝。 | `r2-signed-device-verify.log` |

常规回归可使用当前配置中 `prepared` 路径覆盖测试默认值。

```sh
export MCFAO_TEST_FABRIC_PREPARED="$PREPARED_DIR"
export MCFAO_TEST_PREPARED="$PREPARED_DIR"
python3 -B -m unittest discover -s tests -v
python3 -B tools/run_compatibility_checks.py --report "$BUILD/compatibility.json" --output "$NEW_CHECK_LOGS"
(cd desktop && npm test && npm run build)
(cd desktop && npm run test:e2e -- --grep 'build history shows AOT findings')
./mcfao build --version 26.1.2 --loader fabric --renderer gl41 --target ios-arm64 \
  --config "$GL41_CONFIG" --mods "$AUDITED_MODS_DIR" --audited-mods \
  --instance-data "$VERIFIED_INSTANCE" --test-version COMPAT-r2-20261121 --output "$NEW_BUILD"
./mcfao verify --target ios-arm64 --output "$BUILD"
```

包相关的单 Mod 和嵌套回归分别使用 Phase 1 Minecraft 夹具与 B0 夹具。多 Mod 包是当前 41 个根 JAR 的完整复跑。故障负例包含缺少资源、散列失配、动态路径、元数据签名失配、规则冲突和 r1 被拒绝的被裁剪镜像。没有从宿主 JVM、AOT 编译或包验证推断设备功能通过。
