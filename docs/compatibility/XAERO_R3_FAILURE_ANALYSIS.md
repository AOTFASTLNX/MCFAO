# Xaero r3 故障链验证

日期：2026-11-21

样本：artifacts/compat-r3-20261121/fabric-signed-retry

设备日志：run-1795228318800-COMPAT-r3-20261121.log

## 结论

已定位近因：小地图类别转换收到 settingOverrides 为 null 的 DTO；随后地图 GUI 读取了没有建立的小地图 Session。目标 iPhone 当前活动的雷达类别 JSON 只有两个布尔字段。设备记录显示它在 r3 启动期间被写回；还不知道这一轮开始读取时，它是否已经残缺。

使用 r3 最终变换后的类、原构建 classpath 和原构建整份反射配置，Java 25.0.2 JVM 与严格模式 macOS Native Image 探针均能无损往返完整配置，也都会原样写回残缺配置。这个实验缩小了问题范围，但没有覆盖 iOS 游戏镜像里的完整 profile 流程，不能把文件的首次产生归为旧配置、Mod 自身或 AOT 缺陷。

两条运行时故障在这次设备日志中存在可由字节码证明的控制流关系：Minimap Stage 2 的类别转换异常被 Xaero 自己捕获并写入 Minimap.crashedWith；后续 Xaero 会话创建入口遇到该标志会提前返回。因此未创建/关联 Minimap session，World Map 的 SupportXaeroMinimap.checkWaypoints 随后读取该 session 时触发 NPE。这个关系解释当前日志顺序，但还没有通过使用完整配置的真机对照运行验证修复效果。

目前没有足够证据修改 NCLB 或 MCFAO 的兼容机制。

## 输入与字节码证据

| 输入 | 版本/哈希/状态 |
| --- | --- |
| JVM / Native Image | GraalVM CE 25.0.2；两边运行同一个探针与 Gson 2.13.2 |
| Gson JAR | SHA-256 dd0ce1b55a3ed2080cb70f9c655850cda86c206862310009dcb5e5c95265a5e0 |
| Xaero Minimap JAR | 26.1.2 / 25.3.12；SHA-256 8cb697918a2abbd6d04090ef72710bed46628bd79d4d2d74012091ad95f6c9f6 |
| 完整种子配置 | 5,531 bytes；SHA-256 94fc0e69a1754ef80c54e1f3c9193526c620b0ac646f94a4a0f560bcc58826a8；构建输入与 .app/instance-seed 相同 |
| 设备活动类别数据 | Documents/game/config/xaero/minimap/profiles/entity_radar_categories/default.cfg.json；64 bytes；SHA-256 fcc9b4b4a1fb0d50d68d0ff18298ad155e672ab688f309f8b4c875320b6c7829；缺少 settingOverrides、subCategories 等属性 |
| 设备活动 profile | Documents/game/config/xaero/minimap/profiles/default.cfg；3,754 bytes；SHA-256 d8c0c9484d49737eb72f28007317560c15d90da3543266728708433835684d03，与随包文件一致；client.cfg 的 current_profile 为 default |
| 反序列化适配器 | ReflectiveTypeAdapterFactory$FieldReflectionAdapter；结果类型为 EntityRadarCategoryData |

较早的只读探针（/tmp/mcfao-xaero-state-probe）额外配置了反射元数据；它只验证了两个输入的读取行为。以下往返实验使用实际出货输入与反射配置。

随包类文件哈希：

- ObjectCategoryData.class: e947d5a17602df9ed8bed492284840f20e8ae6b4f5a7cec1fdf6c4231401afa7
- HudMod.class: c9edfe650e4b3107efbb20f30d0f32149c3a5f6f97fe6d27b20ad424b6bf4a6d
- ModuleSessionHandler.class: d8a57d3e7da2dd6eaf0ee6a63815cff7cbc3901995828488fe105a5f7f38f2f1
- MinimapSession.class: 3a4fdc09e9846096868b20d22fec971e903e7f12930eaca1b709d503059f5db0

## 故障链

1. 设备日志 02:32:03 进入 Minimap Stage 2。ObjectCategoryData.getSettingOverrideIterator() 直接对字段调用 Map.entrySet()；该字段为 null 时抛 NPE。栈经过 EntityRadarCategoryManager.init() 和 HudMod.loadLater()。
2. 同一 HudMod.loadLater() 字节码把 Stage 2 主体包在 catch Throwable 中；异常路径记录 error，调用 Minimap.setCrashedWith() 后返回。类别初始化之后的 Stage 2 工作没有执行。
3. XaeroMinimapCore 的会话初始化入口首先检查 Minimap.getCrashedWith()，非 null 时直接返回。正常路径才会创建 XaeroMinimapSession、初始化它并写入 ClientPacketListener 的 mixin 字段。
4. 02:32:11 World Map 记录 New world map session initialized!；02:32:45 打开地图界面时，SupportXaeroMinimap.checkWaypoints() 在 236 行因 Minimap session 为空而 NPE。两条错误不是两个独立的 Gson 故障。

ClientPacketListener 的最终导出类已实现 Xaero session 接口，故现有材料不支持“Mixin 完全漏变换”这一解释。尚无真机逐事件记录覆盖连接 session 的创建、替换、清理和重入；无法据此断言所有生命周期路径正确。

## 配置来源与安全恢复分析

设备证据保存在 artifacts/compat-r3-20261121/device-evidence/original-default.cfg.json，哈希为 fcc9b4b4a1fb0d50d68d0ff18298ad155e672ab688f309f8b4c875320b6c7829，原始内容为：

    {
      "includeListInSuperCategory": false,
      "protection": false
    }

读取链已由同一 r3 出货类字节码确认：MinimapProfiledConfigOptions 将 RADAR_CATEGORIES 的 option id 设为 entity_radar_categories；其 value type 使用 LargeConfigValueIOCodec，扩展名为 .json，Gson codec 调用 ObjectCategoryDataGsonSerializer.deserialize。当前 profile 文件明确指出该值保存在 entity_radar_categories 子目录；设备 client.cfg 当前选择 default profile。EntityRadarCategoryManager.init 调用 mainIO.loadRootCategory(currentProfile)，随后将结果转换为 ObjectCategory。活动文件与故障读取链及空字段均吻合；崩溃瞬间没有路径与哈希的直接观测。

启动器只在活动路径不存在时复制 instance-seed。设备文件元数据表明 profiles/default.cfg 与类别子文件的修改时间都是 **2026-11-21 02:32:00 UTC（北京时间 10:32:00）**，对应日志第 320 行加载小地图客户端 profile，比第 807 行 Stage 2 异常早三秒。r3 的 ConfigChannelClientInit 在这条日志后调用 ConfigProfileManagerIO.load()，随后无条件调用 saveAll()。后者通过 ConfigIO 和 LargeConfigValueIOCodec 重新序列化并写入外置 JSON。这条写回路径和文件修改时间吻合；它可以保留已有残缺 DTO，因此时间戳不能证明启动前的数据完整，也不能确定是谁首次写出了这两个字段。

活动 profile 使用的 LargeConfigValueIOCodec 会在解码抛错时尝试备份文件；这份 JSON 语法有效，Gson 返回缺字段的对象，所以不会进入该分支。若 A/B 确认是历史输入问题，可先做通用配置来源记录（相对路径、首次读取与写回的哈希、候选 seed 来源）及基于实际结构约束的验证。恢复仅在原始字节备份成功并可回滚时执行，保留用户自定义配置。

日志还有连续的另一份 JSON 配置解析错误（MalformedJsonException，$.client，line 81），但现有栈未将其连接到 Xaero 类别文件；不作为这两个异常的证据。World Map Stage 2/3 完成，且在打开地图 GUI 时先触发上述 session NPE，因此本日志没有验证 World Map GUI 正常绘制。

## 出货反射配置的往返对照

r3 的 reflect-config.json SHA-256 为 981acd8ae80eb7f4a4b69c94fb3253f45af7f2f5d1c4aa631fba0a6830cd93aa。其中 EntityRadarCategoryData、FilterObjectCategoryData、ObjectCategoryData 均登记了声明字段、声明构造器与 unsafe 分配。探针使用此文件原件和 r3 最终 classpath，通过真实 ObjectCategoryDataGsonSerializer 和出货工厂使用的 GsonBuilder.setPrettyPrinting() 读写；通过 DTO 自身的 getter 检查状态，没有给探针额外注册 DTO 字段。Native Image 用 --exact-reachability-metadata=xaero,com.google.gson 编译，并以 -XX:MissingRegistrationReportingMode=Exit 运行。

| 用例 | JVM 和 macOS Native Image |
| --- | --- |
| 完整种子读取与写回 | 13 个节点的 settingOverrides 均可读，根节点有 15 条；写回仍为 5,531 bytes，SHA-256 与种子相同 |
| 设备 JSON 读取与写回 | getter 复现空字段 NPE；写回为相同 64 bytes，SHA-256 与设备备份相同 |
| 正常 builder 创建 DTO 再写出 | 非空 override 正常写出；两边的 255-byte 输出哈希相同 |

两端均使用 FieldReflectionAdapter，均输出 R3_ROUND_TRIP_PASS。唯一文本差异是 JVM 输出增强型 NPE 消息而 Native Image 没有消息。探针未调用 Minecraft 生命周期或运行 iOS 游戏镜像；该结果只排除了这个对照中 Gson 会把给定完整种子序列化成 64 字节的假设。

复现材料在 artifacts/compat-r3-20261121/device-evidence/round-trip/：R3RoundTrip.java、native-arguments.json、jvm.log、native.log、native-build.log。以 r3 AOT product/analysis/command.json 的 -cp 参数编译和运行 R3RoundTrip，传入完整 seed 和 original-default.cfg.json；Native Image 使用记录的参数（将临时 Home 路径换为 tools/native_image_home.py 生成的干净 Home），运行新镜像时加上上述 MissingRegistrationReportingMode 并传入同两个路径。

## 根因分类与真机回归

| 故障 | 当前分类 | 证据边界 |
| --- | --- | --- |
| settingOverrides NPE | 活动 profile 子文件结构不完整；首次产生原因未确定 | 当前配置读取链、启动写回时点与探针结果吻合；缺首次读取前 SHA 和 iOS 完整种子对照 |
| 地图 GUI 的空 Minimap session | 字节码支持的控制流：前置 crashedWith 阻断会话建立 | 仍缺独立的真机会话事件轨迹，以及恢复完整类别配置后的世界地图回归 |
| NCLB/MCFAO 通用缺陷 | 未证实 | 没有充分证据支持兼容层代码修改 |

现有设备基线为 iPhone r3 日志中的 Stage 2 和 GUI 异常，缺启动前输入哈希。为了避免替换原 iPhone 的活动文件，已把同一份 COMPAT-r3-20261121 App 安装到 iPad Pro；安装前设备列表没有该 Bundle ID。安装成功，系统拒绝启动（CoreDevice 10002 / SBMainWorkspace Security），因此 iPad 尚未执行任何游戏代码。未写入或替换原 iPhone 的配置、地图、路径点及存档；重新拉取活动类别文件，与备份逐字节相同。

真机放行后，在同一测试 App 和可还原的配置副本运行两组，只切换类别 JSON。各组采集启动前与 Stage 1 写回后的文件哈希和日志；种子在首次写回仍完整时继续检查 Stage 2、进测试世界的小地图显示、世界地图打开／关闭／重开、退出重进和资源重载。若完整种子仍失败或被改写为 64 bytes，在隔离诊断构建中分别记录配置解码、crashedWith、会话创建／绑定／清除及线程。r3 出货日志未记录逐对象变更，A/B 与地图交互回归目前为 NOT RUN。
