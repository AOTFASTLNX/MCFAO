# FabricAOT 技术审查与修订报告（2026-11-08）

## 审查范围和结论

审查了原交接工程的 README、AGENTS、PRODUCT、ARCHITECTURE、CODEX_TASK、ACCEPTANCE、STATUS、Python 预检和测试。基础目标保留：Minecraft Java **26.1.2**、**Java 25**、**Fabric Only**、未越狱 iPhone 本地执行、**无需 Java JIT**。但这条路线**尚未验证端到端可行**，不能承诺完全自动编译任意整合包。

## 已核对事实

- Minecraft Java 26.1.2 于 2026-04-09 发布；Java 25 是该版本的最低 Java 要求。
- Fabric 支持 26.1 系列，26.1 起 Minecraft 不再混淆；这一变化**不能**消除 Mod 本身的动态加载需求。
- Fabric 具有 Mixin、Class Tweaker/Access Widener、嵌套 JAR、Entrypoint、Language Adapter、依赖/冲突等机制。仅离线预处理 Mixin 无法达到全兼容。
- Native Image 的 closed-world 限制与构建后新增/生成任意 Java 类存在根本冲突。
- 26.1 使用 OpenGL；26.2 才引入实验性 Vulkan。Metal 适配仍需解决桌面 API 与资源/着色器差异。
- Xcode Personal Team 设备安装签名有效期为 **7 天**，不能把 IPA 长期安装、公开分发当作已解决条件。

## 原架构级问题（必须解决或证伪）

1. **工具链不可假定成立**：Mac 上 GraalVM 25 能 Native Image，不等于可交叉编译 iOS；更不等于 Java 25 完整 Java 库和 Fabric 可运行。须先找到可复现且有合法许可的 iOS toolchain，再真机证实。
2. **Mixin 静态化不足**：Mixin 插入点、目标类、优先级、初始化顺序、插件/入口点决定的动态变换需要可复现；同时处理 Class Tweaker、访问控制、环境裁剪、嵌套 JAR、ServiceLoader、反射/代理及字节码生成。
3. **缺少游戏运行时移植层**：LWJGL/GLFW、OpenGL、OpenAL、STB、原生 JNI、线程、文件资源、Java/JVM 假设和 iOS 生命周期均需验证。一个 Metal 立方体 ≠ Minecraft 游戏菜单。
4. **整合包兼容范围不明确**：必须建立逐 Mod 的 `VERIFIED / BLOCKED / UNKNOWN` 机制，验证版本/依赖树与真实运行行为。额外 Mod 一律触发重新构建；纯静态扫描永不提升为 VERIFIED。

## 原预检脚本具体问题（本版本已修）

- 不验证 `.mrpack` formatVersion、文件哈希字段、下载地址，误将损坏/恶意 manifest 当作有效元数据。
- 没有 ZIP 成员名称重复/大小写冲突、symlink、压缩炸弹早期检测；Prism Mod symlink 可能越界读取。
- 缺失 nested JAR、语言适配器、Class Tweaker、本地原生库风险提示；没有识别远程 Mod 的“未下载/未知”状态。
- 测试固定了历史 Loader 示例 `0.17.3`，容易误导。新测试仅以 `0.19.3` 作结构示例，**真实支持性始终由官方 metadata 解析**。
- 来源不存在等早退分支没有统一设置 `fatal` 字段。

修订后工具继续**仅读元数据**，不下载、不运行 Mod，也不主动展开解压到磁盘；15 项回归测试通过。已知未实现的能力见下。

## 严重遗漏（需要新模块）

1. **完整解析和取得文件**：官方 Minecraft version manifest/library index、Fabric Loader/Fabric API、合法的客户端文件、Modrinth 远程 JAR，哈希校验、缓存与 license-aware 拒绝策略。预检并不下载或验证实际文件哈希。
2. **解依赖**：Fabric 完整 `depends/breaks/conflicts/provides`、侧别、嵌套 JAR、loader API、语言适配器；loader 版本必须通过 metadata 验证。前 26.1 的 Mod 不能默认复用。
3. **构建隔离**：从不信任的整合包运行 Gradle/Mixin 插件/构建脚本时可能在 Mac 上执行任意代码。执行任何第三方代码前须沙盒、最小权限、断网默认、避免读取 SSH 密钥、浏览器、钥匙串和私人文档。
4. **可复现 AOT**：输入哈希/源/许可/工具链版本、Class initialization build-time vs run-time、reflection/JNI/resource metadata、AOT 缓存失效规则与错误报告。
5. **合法授权和账户**：微软登录/账户授权和正版资格确认、凭证保管与不回传、不绕过正版检查；仅 Mac 本地生成用户自用产物，不随仓库或 GitHub Release 提供含 Minecraft 代码的 IPA。不同司法辖区和分发方式需审慎评估。
6. **iPhone 系统设计**：含 App 生命周期、热限制与 jetsam、可恢复存档、升级换包/签名失败恢复、触屏坐标与多点触控、分辨率缩放、硬件键盘/手柄、声音与前后台切换。
7. **签名/安装**：Personal Team 的 7 天有效期、Bundle ID 不变与存档备份、iOS 设备注册/开发者模式、`xcodebuild` 真机安装与导出 IPA 的**分别验收**；不假定免费账号可以使用所有发布/导出路径。
8. **性能实测**：Metal/GPU 与 CPU 分别 profile、稳定帧时间、1% low、峰值/稳态 RSS、GC 停顿、视距/实体负载、30 分钟热降频；未测不能宣称“极强优化”。

## 原需求矛盾与明确决策

- 旧 `PRODUCT.md` 把联机列作目标，旧 `ACCEPTANCE.md` 却不要求联机。新版本将**可离线单人真实开玩**设为 v1 必需；联机列为后续独立验收目标，禁止在未实现时对外宣传。
- 旧验收 Gate A/B/C/D/E 太粗。新版本新增前置 A0（Mac 参考构建/工件来源）、B0（单个 Mod 的类变换正确性）、C0（无图形启动和资源/JNI）、D0（构建期安全与依赖/资产验证）等子门槛。
- 将“生成 IPA”与“可安装、重签名、保存世界不丢失”区别验收；仅能生成文件不等于可玩。

## 官方参考

- https://www.minecraft.net/en-us/article/minecraft-java-edition-26-1-2
- https://docs.fabricmc.net/versions/26.1.2/develop/loader/
- https://docs.fabricmc.net/versions/26.1.2/develop/porting/
- https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack
- https://developer.apple.com/help/account/basics/about-your-developer-account
- https://www.minecraft.net/en-us/eula
