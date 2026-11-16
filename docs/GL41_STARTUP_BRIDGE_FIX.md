# GL41 启动桥接修复与 LAN r4 测试包

2026-11-17。用户已确认 LAN r4 真机测试成功并成功进入多人游戏；双向联机完整矩阵、保存重进及长时性能仍需分别验收。

## 设备日志与原因

用户的 `run-1794846203079-LAN-r3-20261116.log` 首行带 `LAN-r3-20261116`，宿主 build=7，游戏镜像 UUID 为 `0AAAECFC-C42A-3F2D-B439-F19055A42CC5`，与 r3 交付记录一致。

游戏初始化 OpenGL 窗口时，原生库报告 `GLFW-lite requires GLFW_NO_API; select the Metal backend`，随后出现 `Failed to create backend OpenGL`。错误弹窗继续调用 TinyFileDialogs，缺少 `liblwjgl_tinyfd.dylib` 又产生二次异常。本轮修复对象是前面的图形库不匹配。

直接审计 r3 IPA 与其原始输入：GLFW 来自 `glfw-ios-05` 的历史产物，文件哈希正确，但没有 OSMesa 实现。其构建早于 GL41 接入；旧报告成功、符号齐全、签名有效均不能证明它支持所选渲染器。

## 修复

- 从当前第一方 `ios/glfw-lite/` 源码重编 iPhoneOS ARM64 库，实际包含 OpenGL/OSMesa 上下文与交换实现，保留 Metal NO_API 路径。宿主状态夹具实际创建两种窗口，拒绝未知 API。
- GLFW 导出固定 ABI 查询 `faot_glfw_client_api_contract`，返回 `FAOT_GLFW_CLIENT_APIS:v1:NO_API,OPENGL_OSMESA`。构建前、输入暂存及最终 App 验证均核对实际二进制的 ABI 字符串和 OSMesa 导出，拒绝旧 Metal-only 输入。
- iOS 宿主在进入 Java 前查询实际加载的 GLFW。若 GL41 库不匹配，直接在启动器和日志报告错误，避免进入 Java 弹窗路径再次触发 tinyfd 异常。正常启动日志增加 `[FAOT] glfwClientAPIs=...`。
- 新 IPA 的宿主源码来自 LAN 修复工作副本的独立快照，保留 r3 标记和镜像 UUID 诊断，加入本轮原生预检。原 LAN 工作副本及其未提交修改保持不动。未引入 tinyfd 占位库，也未修改登录、签名认证或游戏逻辑。

## 私有本地交付

- 路径：`artifacts/mcfao/lan-vanilla-device-20261117-r4/FabricAOT-26.1.2-Vanilla-LAN-r4-20261117.ipa`。
- 版本标记：`LAN-r4-20261117`，build **8**；Minecraft 26.1.2 / Java 25 / Vanilla 无 Mod / GL41。
- 大小：481,536,610 字节；SHA-256：`26b2434e78aa15f93a1f82812650d96507959b62a505952c2b994f7121ae2472`。
- Bundle ID 保持原交付的 `fab.aot.kexin`；本地开发签名到期为北京时间 2026-11-20 00:13:37。重签名工具可能使用自身应用标识。
- 游戏 AOT 沿用 r3；镜像 UUID 和 `__TEXT` 段 SHA-256 完全一致。其余原生库的 `__TEXT` 也逐一对照 r3；本轮变化是 GLFW 和启动宿主。
- 外接盘守卫及空间检查正常执行。原始构建位于 `/private/tmp/mcfao-lan-r4-20261117-2a829cb5/`；交付目录保留可重现 `build_r4.py`、源码快照、原生编译与签名日志、原始用户日志、结果及逐文件复制哈希清单。原游戏文件、存档、缓存与旧包均未迁移或删除。

## 验证及边界

Python 全套 **468 项通过**。新增回归覆盖旧 GLFW 即使哈希有效也被拒绝、ABI 符号/字符串检查，以及真实宿主预检对四种第一方共享库夹具的接受/拒绝。GLFW 原生状态夹具在 AddressSanitizer / UndefinedBehaviorSanitizer 下通过。iPhoneOS 编译、arm64 平台、原生 ABI、游戏可达代码、资产哈希、开发签名、描述文件、动态代码权限、ZIP CRC、解包后逐文件哈希与再次验签全部通过。

构建阶段未由助手安装或运行设备/模拟器。交付后用户明确反馈“测试成功，成功进入多人游戏”，作为 LAN r4 的用户真机确认记录；尚无本轮完整双向联机矩阵及长时性能数据，不据此提升全部 Gate 或标记项目 RELEASE。设备日志应同时出现 `LAN-r4-20261117`、build=8 和新的 `glfwClientAPIs` 行。
