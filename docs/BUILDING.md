# FabricAOT 构建与复现

最后复核于 2026-11-10。状态见 [STATUS](STATUS.md)，实验结论见 [ADR-001](evidence/ADR-001.md)。以下均在项目根执行，日志输出目录要求新建。

## 统一 CLI

在 Apple Silicon Mac 上用 Python 3.11+ 执行 `./mcfao`。配置文件中的相对路径以该配置文件所在目录为准。下面是放在仓库根目录的本机配置示例。将版本 JSON 指向本地启动器提供的 26.1.2 元数据。

```json
{
  "prepared": "artifacts/b0/prepared-04",
  "caps": "artifacts/b1/ios-probe-03/work/caps",
  "bootstrapRuntime": "artifacts/b1/runtime-ios",
  "splitter": "artifacts/compiler/method-splitter-01",
  "versionMetadata": "/绝对路径/26.1.2.json",
  "assets": "artifacts/graphics/game-assets-01/assets",
  "glfw": "artifacts/graphics/glfw-ios-world-01",
  "lwjgl": "artifacts/graphics/lwjgl-ios-world-01",
  "metal": "artifacts/graphics/metal-ios-world-03",
  "openal": "artifacts/graphics/openal-ios-world-01",
  "shaders": "artifacts/graphics/shaders-ios-world-01",
  "b1Evidence": "artifacts/evidence/b1-user-device-run-01/result.json"
}
```

本机验证使用 `artifacts/mcfao-local.json`。通过下方的工具链、B0 准备、方法拆分和 [iPhone 原版单人测试](#iphone-原版单人测试) 步骤取得这些前置产物。可用 `openjdkSource` 和 `graalSource` 指定已准备好的源码目录，默认从 `.cache/upstream/` 的源码记录读取。OpenJDK 源码目录内须具备下文的 JNI 头文件。CLI 每次从拥有的客户端重做方法拆分、Metal 注入、Native Image 和 iOS Java/SVM 库编译。图形、音频、着色器与已核验的游戏资源通过配置导入，使用原有构建工具单独更新。

```bash
./mcfao doctor --config ./mcfao.local.json
./mcfao build --version 26.1.2 --loader vanilla --target ios-arm64 \
  --config ./mcfao.local.json --output artifacts/mcfao/my-vanilla
./mcfao verify --target ios-arm64 --output artifacts/mcfao/my-vanilla
# 指定真机 UDID 时，额外要求该设备在描述文件内。
./mcfao verify --target ios-arm64 --output artifacts/mcfao/my-vanilla --device <iPhone-UDID>
```

构建输出本地签名的 `.app`，位置见 `result.json` 的 `app` 字段。Xcode 沿用 WorldDevice 设置和本机已安装的签名资料，目标为 `generic/platform=iOS`。设备验证检查包内哈希、Mach-O 平台、签名、JIT 权限及描述文件。使用现有 Team 的开发导出配置可以从同一构建导出 IPA。

```bash
./mcfao export --target ios-arm64 --build artifacts/mcfao/my-vanilla \
  --export-options ios/C0Harness/ExportOptions.plist \
  --output artifacts/mcfao/my-vanilla-ipa
```

导出命令重新归档已校验的原生输入并解包验签，记录 IPA SHA-256。可传 `--device` 检查指定设备覆盖。安装前核对描述文件有效期。原版和 Fabric 测试包沿用同一个 bundle ID，安装后会替换该设备上的同 ID App。更新时的存档保留属于真机验收。

`inputs.json` 记录工具链、依赖 SHA-256、映射命名空间和参数。每个阶段在独立尝试目录中保留 `command.json`、`stdout.log`、`stderr.log` 及其原生子步骤日志。失败后用相同参数重跑，配置、输入、阶段参数和产物 SHA-256 均匹配时才复用检查点。修改输入时用新输出目录。构建要求能调用项目自己的 `sandbox-exec`，且 Xcode 可访问现有签名和描述文件。

### Fabric 夹具和诊断

```bash
python3 -B tools/prepare_fabric_aot.py --prepared artifacts/b0/prepared-04 \
  --fixture --output artifacts/mcfao/my-fixture

./mcfao build --version 26.1.2 --loader fabric --target ios-arm64 \
  --config ./mcfao.local.json --mods artifacts/mcfao/my-fixture/mods \
  --prepare-only --output artifacts/mcfao/my-fabric-metadata

./mcfao build --version 26.1.2 --loader fabric --target ios-arm64 \
  --config ./mcfao.local.json --mods artifacts/mcfao/my-fixture/mods \
  --audited-mods --output artifacts/mcfao/my-fabric
```

`--prepare-only` 可读取第三方 Mod 元数据，并在 `result.json` 的 `compatibility` 字段汇总每个归档遇到的第一条限制和重复根 Mod ID。命令成功表示预检报告已生成，`compatibility.status` 单独记录 AOT 筛查状态。加上 `--audited-mods` 时运行构建期转换，再于 Native Image 之前退出。完整构建须使用已经审计过的输入。边界和变换链见 [Fabric AOT 适配器](FABRIC_AOT.md)。

模拟器测试用 `tools/smoke_mcfao_simulator.py`。该工具从完整构建的 `result.json` 找到 AOT 对象，单独链接为 `IOSSIMULATOR`，以显式的测试模拟器和一份可丢弃的单人测试存档执行 Quick Play。复制源存档，原目录保留。对应的输出目录中保留截图和新进程日志。

```bash
python3 -B tools/smoke_mcfao_simulator.py \
  --expect fabric --build artifacts/mcfao/my-fabric \
  --runtime artifacts/graphics/runtime-sim-02 \
  --graphics artifacts/graphics/world-simulator-input-02 \
  --assets artifacts/graphics/game-assets-01/assets \
  --seed-world "<测试存档目录>" --simulator <专用测试模拟器-UDID> \
  --output artifacts/mcfao/my-fabric-simulator
```

用 `--expect vanilla` 和原版构建目录可回归原版进世界。Fabric 夹具要求同一份新日志中出现 `MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS`、`MCFAO_F3_CLIENT_WORLD_JOIN_PASS`，以及游戏集成服务器的 `Dev joined the game`。世界回调由 `Minecraft#setLevel` 的 Mixin 注入产生，同时验证 F2 注入生效和 F3 进世界行为。

## 工具链和官方源码

```bash
python3 -B tools/bootstrap_toolchain.py
python3 -B tools/fetch_upstream.py
GRAALVM_HOME="$PWD/.cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home"
```

已存在 JDK 提取目录时用 bootstrap_toolchain.py --download-only 核验归档。源归档固定提交和 SHA256，解包不执行脚本。需要 Xcode27.2、Python3.11.8+；本轮 OpenJDK 头文件用已有 JDK24 引导编译，实际 AOT/运行时均为 Java25。

若缺 Metal，使用 Apple 官方 xcodebuild -downloadComponent MetalToolchain；本轮下载/安装的是27B47，导出缓存在 .cache/apple-metal。

## OpenJDK JNI 头文件

```bash
python3 -B tools/capture.py --output artifacts/evidence/configure-new --timeout 180 --cwd .cache/upstream/jdk/labs-openjdk-3bdcc4536ac3ee02420bcfbfa6fdd3f4bc7d6831 -- bash configure --with-conf-name=fabricaot-host --with-boot-jdk=/Library/Java/JavaVirtualMachines/jdk-24.jdk/Contents/Home --with-debug-level=release --with-native-debug-symbols=none --disable-warnings-as-errors --with-num-cores=4 --with-memory-size=4096
python3 -B tools/capture.py --output artifacts/evidence/headers-new --timeout 900 --cwd .cache/upstream/jdk/labs-openjdk-3bdcc4536ac3ee02420bcfbfa6fdd3f4bc7d6831 -- make CONF=fabricaot-host JOBS=4 java.base-java
```

其他机器需改为自己的受支持 Boot JDK 路径。捕获工具记录真实 cwd、退出码、超时和输出哈希。

## Java25 AOT 与 iOS 静态库

```bash
python3 -B tools/run_a1_probe.py --graalvm-home "$GRAALVM_HOME" --output artifacts/a1/ios-new --mode ios-relocatable
```

该命令生成 C 入口、JNI 辅助库、ARM64 AOT 对象，整体返回2，因为它本身没有完成真机 Gate。对象在输出 native-tmp/SVM-*/a1probe.o；具体路径及哈希见 result.json。

下列命令使用本轮已保留的对象路径；新实验请替换为对应路径：

```bash
python3 -B tools/build_ios_runtime.py --output artifacts/a1/runtime-new --aot-object artifacts/a1/ios-relocatable-retained/native-tmp/SVM-1794076699687/a1probe.o
python3 -B tools/link_a1_ios.py --runtime artifacts/a1/runtime-new --probe artifacts/a1/ios-relocatable-retained --output artifacts/a1/linked-new
```

Framework 生成在 linked-new/FabricAOTProbe.framework。静态库和 Framework 的 COMPILED/LINKED 只表示该构建阶段成功。未支持的 JVM 原生入口明确终止，详见 result.json。

## iPhoneOS App 与签名

可编辑工程：ios/A1Harness/A1Harness.xcodeproj。默认使用本轮 artifacts/a1/ios-framework 与 ios-relocatable-retained 的输出；新构建可以覆盖 FAOT_FRAMEWORK_DIR 和 FAOT_JNI_LIBRARY。

```bash
xcodebuild -project ios/A1Harness/A1Harness.xcodeproj -scheme A1Harness -configuration Release -destination 'generic/platform=iOS' -derivedDataPath artifacts/a1/xcode-unsigned CODE_SIGNING_ALLOWED=NO build
```

此未签名构建已通过。签名时在 Xcode → Settings → Accounts 登录用户 Apple ID，选择自己的 Personal Team，再构建同一工程。命令行可提供 DEVELOPMENT_TEAM=自己的TeamID 和 -allowProvisioningUpdates；不要把密码、令牌或私钥放入命令。

账户恢复后已成功生成开发签名归档并由 Xcode 导出 IPA。使用新的输出目录复现：

```bash
xcodebuild -project ios/A1Harness/A1Harness.xcodeproj -scheme A1Harness -configuration Release -destination 'generic/platform=iOS' -derivedDataPath artifacts/a1/xcode-handoff-new -archivePath artifacts/a1/handoff-new/A1Harness.xcarchive DEVELOPMENT_TEAM=YOUR_TEAM_ID -allowProvisioningUpdates archive
xcodebuild -exportArchive -archivePath artifacts/a1/handoff-new/A1Harness.xcarchive -exportPath artifacts/a1/handoff-new/export -exportOptionsPlist ios/A1Harness/ExportOptions.plist -allowProvisioningUpdates
```

ExportOptions.plist 使用本地 debugging 导出和当前 Team；其他用户须选择自己的 Team 并相应修改配置。最新 build 3 原始记录位于 a1-ios-archive-run-state-v3/ 与 a1-ios-export-run-state-v3/。IPA 解包后的 codesign --verify --deep --strict 已通过；签名检查需要访问系统信任服务。入口使用公开 version-1 isolate 参数，把预留地址空间限制为256 MiB。用户已验证build 2真机独立运行PASS；build 3补充当前进程状态、时间与runID，用户也已提供PASS截图。完整边界及证据见 [真机测试交接](A1_DEVICE_HANDOFF.md)。

## C0 客户端宿主（C0Harness）

`ios/C0Harness/C0Harness.xcodeproj` 把真实 Minecraft 26.1.2 的 AOT 镜像装进 iOS App。宿主用 `dlopen` 装载镜像，再调用 `run_main(argc, argv)`。Java 输出保存在 `Documents/c0-logs/`。设备诊断和原版单人模拟器分别使用各自的 Scheme。

镜像在 `run_main` 里自行创建 isolate。宿主通过 `-XX:ReservedAddressSpaceSize=<字节>` 传入预留空间，设备诊断默认 1 GiB，模拟器默认 2 GiB。

打开 Xcode 工程，选择 **WorldSimulator** 和 **FabricAOT World 26.1.2**，按 ⌘R 可进入原版横屏菜单。左右横屏均由应用支持。本地 AOT、Metal 着色器和原生库由下面的命令核验并准备。新模拟器安装应用后，需要将经过哈希验证的资源目录复制到该应用的 `Documents/assets`。本次测试模拟器已经准备好。

`WorldSimulator` 使用独立的 `FabricAOTWorld.app` 目标，并沿用原有模拟器应用标识以保留存档。Xcode 27.2 仍可能列出物理 iPhone。误选时构建会报 `FabricAOTWorld requires an iOS Simulator destination.`，请选择模拟器后再运行。

```bash
python3 -B tools/stage_simulator_xcode.py --harness artifacts/graphics/main-harness-sim-19
sim_id=$(cat artifacts/graphics/simulator-recovery-01/udid.txt)
sim_data=$(xcrun simctl get_app_container "$sim_id" org.fabricaot.research.c0.kexin data)
/usr/bin/ditto artifacts/graphics/game-assets-01/assets "$sim_data/Documents/assets"
```

模拟器首次启动使用 8 区块视距、5 区块模拟距离与 30 FPS 上限。游戏会保留已存在的设置。触控方向键移动，拖动空白区域转视角，Pick、Break 和 Place 分别取、破坏和放置方块。Items 打开物品栏，右上角返回游戏或打开暂停菜单。左上角 36pt 的 **F3** 按钮（与右上的暂停键左右对称，避开拇指操作区）发送 GLFW `F3` 按键切换调试信息；它是开关式按键，按下后由宿主在 90ms 后自动抬起，避免按压与抬起落在同一次事件轮询里被丢弃。

两条通道共用同一份无平台标记的镜像对象：

```bash
# 模拟器（默认迭代方式，不需要解锁设备）
python3 -B tools/build_c0_harness.py --dylib artifacts/c0/client-link-sim-02/client-graph.dylib \
  --simulator <UDID> --install --launch --pull-logs artifacts/c0/harness/sim-run
# 真机（需要设备已连接并解锁，Xcode 才会把设备注册进 Team Profile）
xcrun devicectl list devices
python3 -B tools/build_c0_harness.py --dylib artifacts/c0/client-link-02/client-graph.dylib \
  --device <UDID> --install --launch --pull-logs artifacts/c0/harness/logs
```

产物：`artifacts/c0/harness/{export,sim-run}/` 与 `result.json`（含 dylib 与 IPA 的 SHA-256、`provisionedDevices`）。**镜像本身怎么来（拆分 → `--full-build --relocatable` → `link_c0_ios.py`）见 [WORK_HANDOFF](WORK_HANDOFF.md) §8 的"C0 链路"命令块。**

`result.json` 里 `provisionedDevices` 为空表示当前账号尚无已注册设备（新 App ID 的 Team Profile 就没有设备槽），此时 IPA 能导出但装不上——这不是签名失败。设备处于锁屏或未连接时，`xcodebuild -destination 'platform=iOS,id=<UDID>'` 会报 `needs to be unlocked to enable development services`。

最省事的路径仍然是 Xcode：打开工程 → 顶部选择已连接且已解锁的设备 → ⌘R。Xcode 会自动注册设备、重签并把控制台接到 `stdout`。

宿主支持选择 1G、2G、4G 或 6G 的地址空间。`TMPDIR` 与 `HOME` 指向应用沙盒，工作目录指向 `--gameDir`。调试宿主使用本地测试玩家 Dev，启动参数固定 Minecraft 26.1.2 和资源索引 30。日志目录可在“文件”App 中查看。

反射配置在 `compiler/reflection-config.json`（参数转换和日志实际访问的精确构造器/方法），由 `tools/probe_client_graph.py` 的 `ReflectionConfigurationFiles` 引用。缺一条就会在 `Main.main` 的 joptsimple 参数解析处抛 `"<type> is not a value type"`。

## iPhone 原版单人测试

打开 [C0Harness.xcodeproj](../ios/C0Harness/C0Harness.xcodeproj/)，选择 **WorldDevice**，目的地选择自己的 iPhone，然后按 **⌘R**。该方案使用真机 arm64 游戏镜像、真机 Metal 库和用户本地已核验的资源索引 30，沿用现有开发签名和应用标识。首次进入时用左右横屏，建议从菜单新建测试世界，验证移动、跳跃、放置和破坏方块、声音、保存退出与重进。

验证独立启动时，在 Xcode 停止运行，断开连接，从 iPhone 主屏幕重新打开 **FabricAOT World**。启动失败时可在「文件」→「我的 iPhone」→「FabricAOT World」→ `c0-logs` 找到最近一次 `run-*.log`。安装和运行由测试者在手机上完成。

本地重建使用与横屏模拟器相同的 `main-aot-15` 可重定位对象。以下命令从本机已锁定的构建输入重新生成真机库。输出目录必须是新路径，生成后按实际路径更新 `WorldDevice.xcconfig`。

```bash
g=artifacts/graphics
obj=$(jq -r '.imageObject.path' "$g/main-link-sim-15/result.json")
python3 -B tools/build_ios_runtime.py --sdk iphoneos --with-extnet --aot-object "$obj" --output "$g/runtime-ios-world-02"
python3 -B tools/link_c0_ios.py --sdk iphoneos --stub-unsupported-jni --image "$g/main-aot-15" --runtime "$g/runtime-ios-world-02" --output "$g/main-link-ios-world-01"
python3 -B tools/build_glfw_lite.py --sdk iphoneos --output "$g/glfw-ios-world-01"
python3 -B tools/build_lwjgl_lite.py --sdk iphoneos --glfw-library "$g/glfw-ios-world-01/libglfw.dylib" --output "$g/lwjgl-ios-world-01"
python3 -B tools/build_metal_backend.py --sdk iphoneos --graphics-bridge "$g/lwjgl-ios-world-01" --glfw-library "$g/glfw-ios-world-01/libglfw.dylib" --output "$g/metal-ios-world-03"
python3 -B tools/build_openal_soft.py --sdk iphoneos --output "$g/openal-ios-world-01"
python3 -B tools/translate_shaders.py --sdk iphoneos --catalog "$g/shader-catalog-03" --toolchain "$g/shader-toolchain-03" --output "$g/shaders-ios-world-01"
python3 -B tools/stage_device_xcode.py --client "$g/main-link-ios-world-01" --glfw "$g/glfw-ios-world-01" --lwjgl "$g/lwjgl-ios-world-01" --metal "$g/metal-ios-world-03" --openal "$g/openal-ios-world-01" --shaders "$g/shaders-ios-world-01" --output "$g/world-device-input-02"
xcodebuild -project ios/C0Harness/C0Harness.xcodeproj -scheme WorldDevice -destination 'generic/platform=iOS' -derivedDataPath "$g/world-device-signed-02/DerivedData" build
```

## iPad Pro 原生与妙控键盘测试

PR #2 的真机失败根因、修复、包契约检查和触控板验收步骤见 [IPAD_INPUT](IPAD_INPUT.md)。关键点：

- `WorldDevice` 必须由 `TARGETED_DEVICE_FAMILY=1,2` 构建，最终 `Info.plist` 的 `UIDeviceFamily` 必须是 `[1,2]`；构建阶段和 `tools/verify_ipad_bundle.py` 会拒绝 iPhone-only 包。
- 只有 iPad 全屏场景才能获得指针锁定；窗口化、分屏或 iPhone 兼容模式会记录 `fullScreen=0`，此时相机使用相对位移 fallback，不能把“光标移动”误当作视角已修复。
- 进入世界后检查 `Documents/c0-logs/input-*.log` 的 `locked`、`fullScreen`、`scene/screen/drawable` 和 `source=gcmouse|hover|touch-drag`；菜单中应看到锁定释放。

## 专用模拟器调试

本轮用单独 iPhone18Pro / iOS27.2模拟器，ID YOUR_DEVICE_UDID。创建、安装、启动和原始结果见 evidence。模拟器结果不提升真机 Gate。

Simulator 必须重新编译上游原生库，不能重标记设备 archive：

```bash
python3 -B tools/build_ios_runtime.py --output artifacts/a1/runtime-sim-new --aot-object artifacts/a1/ios-relocatable-retained/native-tmp/SVM-1794076699687/a1probe.o --sdk iphonesimulator
python3 -B tools/link_a1_ios.py --runtime artifacts/a1/runtime-sim-new --probe artifacts/a1/ios-relocatable-retained --output artifacts/a1/linked-sim-new --sdk iphonesimulator
```

JNI 辅助库亦以 SDK iphonesimulator、target arm64-apple-ios17.0-simulator 从 interop/a1/native/probe.c 编译。本轮真实命令在 artifacts/a1/jni-simulator/command.json。App 构建参数和本地签名在 artifacts/evidence/a1-simulator-build/command.json。

运行结果采集：

```bash
python3 -B tools/collect_probe_result.py --container-file artifacts/evidence/a1-simulator-container/stdout.log --simulator YOUR_DEVICE_UDID --output artifacts/evidence/simulator-run-new
```

采集器限定所选模拟器及测试 Bundle ID，并同时检查原生生命周期退出码与 Java 成功标记。

## Swift Craft Launcher 资源定位

```bash
python3 -B tools/locate_local_client.py --profile "$HOME/Library/Application Support/Swift Craft Launcher/profiles/Recollection3" --version-metadata "$HOME/Library/Application Support/minecraft/versions/26.1.2/26.1.2.json" --output artifacts/evidence/swiftcraft-new.json
```

只读取指定实例、共享客户端和版本元数据。游戏 JAR、依赖、资源、Java runtime 均保留在启动器共享目录；账户、存档和既有 Mod 不复制到项目。

## 测试、证据与中央登记

B0准备、真实转换/重放/负例和沙盒控制已PASS，见[B0复现](B0_TEST_HANDOFF.md)。B1的iOS AOT、运行库、签名包和用户独立运行已PASS，见[B1记录](B1_DEVICE_HANDOFF.md)。真实客户端诊断见[ADR-003](evidence/ADR-003.md)：分析墙已由方法拆分器解决，镜像已在真机/模拟器执行到 Datafixer 之后，**C0 只剩图形层阻断**，方案见[GRAPHICS_STACK_PLAN](GRAPHICS_STACK_PLAN.md)与[ADR-008](evidence/ADR-008.md)。

```bash
python3 -B -m unittest discover -s tests -v
python3 -B tools/verify_evidence.py --output artifacts/evidence/verification-new.json
```

当前151项单元/安全回归通过，见artifacts/graphics/regression-06/stderr.log（79/123/133项为历史轮次）。Mac脚本由助手执行，真机由用户负责。verify_evidence 检查其支持的命令输出、报告及二进制字段；图形库另有构建指纹及Xcode嵌入核对，当前源清单含 docs/.codex。它不认证游戏或设备行为。

AAR 只使用 $HOME/Documents/Codex/monitor/registry.sqlite。可靠可再取得的固定缓存带 regenerable；历史运行记录、耦合的源构建状态和设备状态保留。安全删除标志均 false，不执行清理。新产物需重新核验登记。外部专用测试目录可显式提供 --external-build-root，不能用主目录或系统目录作项目。

tools/register_artifacts.py 用于不含符号链接的实验树，发现链接会明确拒绝递归登记。Xcode 归档构建目录含有指向实际 App 的符号链接，按独立 BUILD 目录登记且不跟随该链接，方式与含内部链接的 JDK 缓存相同。device-handoff 的归档/解包文件和 evidence 可分别 include-files 登记；导出目录以 DISTRIBUTION 再登记，记录 xcodebuild 导出命令。不得为登记改动或删除 Xcode 的链接。

本地Git提交保存第一方源码与文档，`git log -1`查看；原始游戏/玩家数据和生成物未纳入。建立Git后中央AAR项目身份须重新登记同步，不能继续沿用旧身份。

真实客户端分析支持有界6/8 GiB与Mac构建GC对照，命令及测量限制见[CLIENT_GRAPH_DIAGNOSTICS](CLIENT_GRAPH_DIAGNOSTICS.md)。构建JFR会改变目标JFR配置，08保留提前失败记录，09/10/11均OOM——这三轮是"加堆无解"的原始证据；分析墙最终由构建期方法拆分（`compiler/splitter`，18类/28方法→358段）解决，第28轮 6 GiB 下完整分析通过。C0 现只剩图形层阻断（见 WORK_HANDOFF §1.2）。

## 图形启动探针与Xcode调试

第46轮资源诊断命令与源码入口见 [GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。打开 `ios/C0Harness/C0Harness.xcodeproj`，选择共享Scheme **MetalProbe**（默认C0Harness也可）和自己的iPhone，⌘R；已引用资源探针AOT与iPhoneOS的3个图形库及预编译metallib。预期四分屏红/绿/蓝/黄约20秒后回日志，成功标记为METAL_RESOURCE_PROBE_PASS。模拟器需使用对应Simulator库，并通过构建器显式传入。

`build_c0_harness.py --output <新目录>`保留既有归档/导出；`--native-library`逐个验证并嵌入libglfw/liblwjgl/libfaot_metal，资源探针另传`--metal-library`。宿主使用org.lwjgl.librarypath定位签名库，overlay明确识别iOS。当前Scheme运行真实Window/RenderSystem与GPU资源比对，四分屏保持20秒；该设备Scheme仍为历史资源诊断；原版着色器与实际绘制已另在模拟器验证，真实Main正在接入，C0/C0a保持BLOCKED。

### 第47轮真实Main模拟器通路

完整命令与逐步失败证据见[GRAPHICS_BOOTSTRAP](GRAPHICS_BOOTSTRAP.md)。以修正后的`client-split-04`为输入执行`tools/inject_metal_backend.py`；真实Main构建传`--include-game-resources`，自动启用HTTP/HTTPS协议。`tools/stage_game_assets.py`按26.1.2版本元数据固定索引30与对象SHA1复制资源；可用`--fetch-missing`只从固定官方源补齐不匹配对象，不覆盖启动器缓存。模拟器运行库通过`build_ios_runtime.py --with-extnet --sdk iphonesimulator`补充真实Darwin扩展套接字JNI。音频库由`build_openal_soft.py --sdk iphonesimulator`在隔离环境编译固定OpenAL Soft1.25.2，要求CoreAudio。音频PCM探针验证真实后端和播放推进，保持静音。

设备诊断、原版单人模拟器与 iPhone 原版单人测试各用独立方案。手机安装和运行由测试者执行。
