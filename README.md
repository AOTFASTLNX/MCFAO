# FabricAOT

**在未越狱 iPhone 上本地运行 Minecraft Java Edition 26.1.2 + Fabric 的实验性工程。**

FabricAOT（仓库代号 MCFAO）的目标是让用户在 Mac 上导入 `.mrpack` 或 Prism Launcher 实例，经过依赖解析、构建期 Fabric 转换、Java AOT 编译和 iOS 签名后，得到一份可以在普通 iPhone 上本地游玩的 IPA。游戏逻辑、渲染和存档都在手机上执行，不需要 Java JIT、越狱或电脑串流。

> **项目状态：实验性研发阶段。** 工具链和 Fabric 静态化门槛已经打通，原版单人玩法在 iOS 模拟器上通过，但完整真机可玩、整合包功能覆盖和性能验收仍未完成。当前产物不能称为 v1 正式版。

本项目是非官方项目，与 Mojang Studios、Microsoft 没有关联，也未获其认可。仓库不包含 Minecraft 游戏本体、官方资源或用户存档。

## 要解决的问题

把 Java 版 Minecraft 搬到 iOS，难点不只是换一个渲染后端：

- **闭世界编译与 Fabric 动态机制冲突。** Mixin、Class Tweaker、嵌套 JAR、入口点和运行期类生成都发生在传统 JVM 的加载阶段，而 GraalVM Native Image 要求在构建时尽可能确定全部类型。项目使用真实 Fabric Loader 在构建期执行转换，并把无法静态化的 Mod 明确报告或排除。
- **桌面图形栈不能直接复用。** Minecraft 26.1.2 使用 OpenGL、GLFW、LWJGL 和 OpenAL；iOS 只提供 Metal。项目实现了 GLFW-lite、LWJGL-lite、OpenAL 适配和 Metal 后端，并在构建期把游戏着色器翻译成 Metal Shading Language。
- **iOS 签名和分发边界。** 免费 Personal Team 的描述文件通常 7 天过期；包含 Minecraft 代码的 IPA 不能作为公开通用安装包分发。

项目的硬约束是 Minecraft Java **26.1.2**、Java **25**、**Fabric Only**、官方未混淆命名空间，以及在普通未越狱 iPhone 上不依赖 JIT 运行。

## 当前进度

| 门槛 | 状态 | 已经证明什么 |
| --- | --- | --- |
| A0 / A1 | **PASS** | Mac 上 Java 25 + Fabric 能启动真实客户端；Java 25 小程序经 AOT、签名后能在普通 iPhone 上无 JIT 独立运行 |
| B0 / B1 | **PASS** | 真实 Fabric Mixin、Class Tweaker、嵌套 JAR 和入口点能在构建期转换，iOS 上的行为与桌面基线一致 |
| C 原版游戏 | 模拟器 **PASS**，真机 **BLOCKED** | 模拟器已出现真实主菜单，可创建世界、移动、取放和破坏方块、打开物品栏、保存并重进 |
| D 整合包 | **部分完成** | 41 个根 JAR 的整合包在模拟器进入世界，83 个入口点完成派发；真机整合包验收仍未完成 |
| E 性能与稳定性 | **BLOCKED** | 已有初步真机帧数据，但完整性能、温度和 30 分钟稳定性验收尚未完成 |

当前兼容矩阵覆盖 127 个 Mod 条目：

| 状态 | 数量 | 含义 |
| --- | ---: | --- |
| `BLOCKED` | 13 | 已确认无法进入闭世界，或平台级不可用 |
| `BUILD_PASS` | 56 | 类已进入 AOT 镜像，不等于 Mod 能正常运行 |
| `LOAD_PASS` | 57 | 入口点派发完成，初始化未抛异常 |
| `FUNCTION_PASS` | 1 | 实际功能在游戏内被观察到（目前只有 Jade 的方块提示框） |

最新进展（2026-11-14）：修正了 PROFILE 诊断包的运行库打包问题，build 7 已通过链接、签名和 IPA 内容校验；另一个 Metal vsync 修复包已签名导出，但尚未在真机上运行验证。详见 [STATUS](docs/STATUS.md)。

## 实现路线

```mermaid
flowchart LR
  A[.mrpack / Prism 实例] --> B[预检与依赖解析]
  B --> C[构建期 Fabric 转换<br/>Mixin / Class Tweaker / 嵌套 JAR]
  C --> D[GraalVM Native Image<br/>iOS arm64]
  D --> E[iOS 原生运行时<br/>GLFW-lite / LWJGL-lite / OpenAL / Metal]
  E --> F[Xcode 签名与 IPA]
  F --> G[未越狱 iPhone 本地运行]
```

每轮构建都会保留命令、输入哈希、日志和产物指纹。构建成功、模拟器启动或签名通过都不能代替真机可玩证据；Gate 的判定标准见 [ACCEPTANCE](docs/ACCEPTANCE.md)。

## 仓库结构

| 目录 | 内容 |
| --- | --- |
| [compiler](compiler) | Fabric 静态化、方法拆分、Metal 后端、着色器翻译、反射配置 |
| [ios](ios) | A1/B1/C0 测试宿主、GLFW-lite、Metal bridge、启动器和诊断工具 |
| [interop](interop) | Java 与 iOS 原生层之间的窄接口、探针和测试夹具 |
| [tools](tools) | 预检、AOT 构建、链接、打包、签名和日志分析 |
| [tests](tests) | Python 回归、Java 测试和原生测试 |
| [docs](docs) | 产品、架构、Gate、兼容矩阵、构建说明和证据索引 |
| [ci](ci) | GitHub Actions、CircleCI 和云端构建脚本 |
| `artifacts/` | 本地构建产物与实验证据，体积很大，不属于源码 |

Mac 端目前以根目录的 [`./mcfao`](mcfao) 命令行和 `tools/` 下的 Python 编排为主。产品文档中规划的 SwiftUI Mac 图形界面尚未实现。

## 快速开始

### 前置条件

- Apple Silicon Mac，安装 Xcode 27.2 和对应 iPhoneOS SDK
- Python 3.11+
- GraalVM CE 25.0.2
- 用户自己合法获取的 Minecraft Java 26.1.2 客户端、资源和 Fabric 依赖
- 用于真机安装的 Apple 开发签名配置

首次构建需要先准备工具链、图形库、游戏资源和本机配置；仓库不提供游戏本体，也不存在从空目录一键生成 IPA 的脚本。

```bash
git clone https://github.com/AOTFASTLNX/MCFAO.git
cd MCFAO

python3 -B tools/bootstrap_toolchain.py
python3 -B tools/fetch_upstream.py
```

按照 [BUILDING](docs/BUILDING.md) 创建 `mcfao.local.json`，填入本机的游戏版本元数据、资源目录和已构建的图形/音频产物路径，然后运行：

```bash
./mcfao doctor --config ./mcfao.local.json

./mcfao build --version 26.1.2 --loader vanilla --target ios-arm64 \
  --config ./mcfao.local.json --output artifacts/mcfao/my-vanilla

./mcfao verify --target ios-arm64 --output artifacts/mcfao/my-vanilla
```

Fabric 整合包先做元数据预检，再对已审计的输入执行转换和完整构建：

```bash
./mcfao build --version 26.1.2 --loader fabric --target ios-arm64 \
  --config ./mcfao.local.json --mods <mods 目录> \
  --prepare-only --output artifacts/mcfao/my-fabric-metadata

./mcfao build --version 26.1.2 --loader fabric --target ios-arm64 \
  --config ./mcfao.local.json --mods <已审计的 mods 目录> \
  --audited-mods --output artifacts/mcfao/my-fabric
```

导出 IPA：

```bash
./mcfao export --target ios-arm64 --build artifacts/mcfao/my-vanilla \
  --export-options ios/C0Harness/ExportOptions.plist \
  --output artifacts/mcfao/my-vanilla-ipa
```

### 测试

```bash
python3 -B -m unittest discover -s tests -v
```

部分用例依赖本机已有的 `artifacts/` 构建产物、Xcode 或测试设备；没有这些输入时相关测试不会代表真机结论。测试边界和图形/设备验证命令见 [BUILDING](docs/BUILDING.md)。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [PRODUCT](docs/PRODUCT.md) | 产品定位、Mac/iOS 功能和明确非目标 |
| [DESKTOP](docs/DESKTOP.md) | 实验版跨平台桌面工作台：源码、能力边界与验证结果 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 技术事实、建议流水线和风险登记 |
| [TECHNICAL_GATES](docs/TECHNICAL_GATES.md) | A0 到 E 的可执行门槛和停止条件 |
| [ACCEPTANCE](docs/ACCEPTANCE.md) | 验收清单、测试矩阵和发布标准 |
| [STATUS](docs/STATUS.md) | 当前状态、历史实验和最新证据 |
| [BUILDING](docs/BUILDING.md) | 工具链、构建、签名、模拟器和真机命令 |
| [FABRIC_AOT](docs/FABRIC_AOT.md) | Fabric 静态化、Mixin、嵌套 JAR 和闭世界处理 |
| [MOD_COMPATIBILITY_MATRIX](docs/MOD_COMPATIBILITY_MATRIX.md) | 逐 Mod 兼容状态和证据 |
| [SECURITY_AND_DISTRIBUTION](docs/SECURITY_AND_DISTRIBUTION.md) | 不可信输入、授权、签名和再分发边界 |
| [REVIEW_REPORT](docs/REVIEW_REPORT.md) | 架构审查、已核对事实和严重遗漏 |
| [证据索引](docs/evidence/README.md) | 工具链、A1/B1 和图形实验的原始记录 |

## 证据与判定原则

- 所有结论必须来自真实执行。未执行的测试写 `NOT RUN`，无法继续的 Gate 写 `BLOCKED`。
- 模拟器结果不替代真机结果；构建成功不替代启动成功；签名成功不替代安装和游玩。
- 一个 Mod 的 `BUILD_PASS` 只说明类进入了镜像，必须再有入口点日志（`LOAD_PASS`）和游戏内行为证据（`FUNCTION_PASS`）。
- 运行期动态生成类、动态代理、JNI 原生加载等能力如果无法在构建期封闭，必须明确报告或排除，不能静默跳过。

## 安全、授权与分发

- 不要提交 Minecraft 客户端、官方资源、用户存档、访问令牌或签名私钥。
- `.mrpack`、Prism 实例、Mod JAR、Gradle 构建脚本和 Mixin 插件都可能不可信。默认不执行未隔离的第三方构建代码，并限制 ZIP 路径、展开体积和下载来源。
- 含 Minecraft 代码或资源的 IPA 仅供用户本机构建和安装，不作为公开 Release 或通用安装包分发。
- 免费 Personal Team 的签名有效期和重装后的存档保留需要单独验证；工具不保存个人签名证书。
- 仓库中的第一方代码目前没有附带开源许可证文件；复用或再分发前请先联系维护者确认授权。

## English overview

FabricAOT is an experimental build pipeline and iOS runtime for Minecraft Java Edition 26.1.2 with Fabric. It performs Fabric class transformation at build time, compiles the client ahead of time to iOS arm64, replaces the desktop graphics/audio stack with native iOS adapters and a Metal backend, and produces a locally signed app. It does not use JIT, jailbreak, cloud streaming, or a desktop game server. The project is under active research: toolchain and Fabric gates A0/A1/B0/B1 pass, vanilla single-player works in the iOS Simulator, but full device gameplay, modpack functional coverage, and performance acceptance remain incomplete.
