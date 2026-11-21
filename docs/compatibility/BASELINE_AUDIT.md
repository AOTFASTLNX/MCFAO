# Fabric 兼容性基线审计

2026-11-21，`9126340497d8528cd52d23b6aac084b065e32262`。当前分支「通用fabricmod适配计划」与本地集成分支 `integration/gl41-gui-ipa-20261115-aot-compatibility` 起点一致。工作区原有 iOS 启动器/账号、Xcode 工程、BUILDING.md 及打包内容索引改动。

`./mcfao doctor --config artifacts/mcfao-gl41.json` 验证 4,341 项输入。环境为 Apple Silicon、Xcode 27.2、iPhoneOS SDK 27.2、Java/GraalVM CE 25.0.2+10.1。Minecraft 26.1.2、Loader 0.19.3、Mixin 0.8.7、ASM 9.10.1 由仓库锁定，默认 GL41。已找到历史 GL41-r4 产物和合法本地客户端。当前进程的内层 `sandbox-exec` 遇到 `Operation not permitted`，CoreSimulatorService 连接失败，Instruments 无权创建缓存目录，设备执行待确认。

`python3 -B -m unittest discover -s tests -v` 初始基线 627 项，10 失败、24 错误、8 跳过。旧测试默认准备目录中记录的 Java/依赖路径已失效。其他失败涉及工作台环境、路径与空间检查、FSEvents。原始记录在 `logs/compat-20261121/baseline-unittest.log` 和 `doctor.log`。下表区分静态证据和待执行对照。

| 机制 | 已有实现 | 存在缺口 | 风险 | 修复位置 | 验证方案 |
| --- | --- | --- | --- | --- | --- |
| Fabric Loader API | `AotExport` 调用固定 Knot。`ModSnapshot` 捕获元数据，`ModCatalog` 供动态容器查询 | membership 包含 provides、容器映射遗漏别名。枚举使用按 ID 排序的 JSON。复杂参数只覆盖部分 API | 可选集成先查到已加载、随后取不到容器。依赖枚举次序改变 | `interop/fabric/tool/mcfao/{build/RuntimeLowering,build/AotExport,build/ModSnapshot,aot/ModCatalog}.java` | 与固定 Loader 的身份索引、嵌套关系、元数据对照。执行改写后的 JVM 字节码 |
| Entrypoint 与生命周期 | 构建图生成 main/client 和 custom stage、lazy 容器及 owner。main/client 进行依赖排序 | 只生成已识别的自定义 stage，事件、reload、tick、世界功能缺少覆盖。派发的异常与 Loader 聚合语义待对照 | 早期退出、初始化顺序差异 | `AotExport`、现有 JVM 夹具 | 分别检查对象身份、注册、派发、失败顺序。设备回放 |
| Mixin | 直接读取 Knot post-Mixin 字节，保留 Class Tweaker、接口和辅助类 | 若干目标/访问器拒绝，日志没有逐类输入及输出指纹 | 最终类路径遗漏成员、失效的 Mixin 被当作已变换 | `AotExport`、`verify_aot_classpath.py` | B0 样本、原始/转换签名、最终类路径核对 |
| Classpath 资源 | 按 Mod 收集字面量查找、合并 assets/data、独立提取内置包，合并 service 描述 | 计算路径、跨 Mod 查找、多来源顺序有缺口。资源缺少最终哈希/读取证据 | 冲突被折叠成一个文件，合并资源并非 Fabric 原始包栈 | `AotExport`、`aot_compatibility.py` | 根目录、包相对、冲突、服务供给者、Native Image 实读 |
| 反射 | `config_reflection.py` 推断 Gson/DTO、继承字段与 EnumMap。`mdaf.py` 合并维护/扫描/Agent | 动态查找仍不完整。初始化风险和精确缺失注册诊断需补齐 | 镜像可建立但访问失败 | `config_reflection.py`、`mdaf.py`、`probe_client_graph.py` | 真正实例化、首次配置与往返、缺失元数据负例 |
| 序列化 | 已提取部分根和条件注册、保留 Agent 元数据 | 动态类型/代理、可达类型图待分析 | 首次加载正常、存档或反序列化失败 | `RuntimeLowering`、`mdaf.py` | 真实往返与损坏输入 |
| AWT/ImageIO | `ios.texture.png-native-image.v1` 匹配安全采样链，`TextureImage` 复用 NativeImage | 其他绘制、字体、输出链待分类。GL41-r4 地图设备功能待测 | 不完整改写破坏像素或临时资源 | `TextureImageLowering`、`aot_compatibility.py` | 现有 JVM 像素对照、新 PNG 负例、设备世界路径 |
| 文件系统 | `ModCatalog` 将容器内容提取到沙盒临时目录。`ModFiles` 是既有名义安装路径辅助 | PATH origin 与原始文件不同，失败目录回收和 IAS 真机路径待补 | 残留临时文件、真实路径 API 无法满足 | `ModCatalog`、iOS 现有文件入口 | 防穿越与提取失败、真实 iOS NOFOLLOW_LINKS |
| 动态类生成 | Sodium 静态顶点转换计划、最终字节码扫描直接动态类定义 | 子类名、间接生成器和固定代理区分不足 | 未识别的运行时定义导致启动或玩法失败 | `GenericVertexSerializer`、`aot_compatibility.py` | 固定机制对照，签名/未知类生成诊断 |
| 报告与缓存 | CLI 兼容报告、Builder 任务摘要、终态扫描与 Native Image 对象缓存 | 缺少逐 Mod 证据、能力选测和结构归因。复用需考虑规则实现变化 | 推断或构建成果被误读成功能验证 | `aot_compatibility.py`、`generate_mod_matrix.py`、Builder 现有摘要 | schema 兼容、缓存失效、旧记录与 UI 对照 |

历史 TechReborn / RebornCore 的 Optional 空值已由快照机制修复到模拟器入口返回，历史记录停于后续原生图形故障。此 checkout 新一轮世界和设备证据待执行。Iris 资源故障需按实际版本和调用点核查。上一轮 Xaero 的已知方块采样有 JVM 像素对照和 GL41-r4 构建，但未取得该版本的地图真机功能证据。

## 本轮顺序

1. Fabric 查询、报告残留、Mixin 字节证据和语义夹具。
2. Classpath 索引、顺序和缺失诊断。
3. 动态元数据及初始化诊断。
4. 平台行为与负例。记录真机阻断。
5. 动态 Java 分类和现有静态替代回归。
6. 规则契约和证据输出。
7. 接入现有验证与生成矩阵。
8. 将逐 Mod 状态、证据和归因接入 Builder。
9. 运行回归、合法输入构建和产物校验，记录每级验收。
