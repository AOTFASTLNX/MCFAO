# FabricAOT 构建与复现

最后复核：2026-11-08。状态见 [STATUS](STATUS.md)，实验结论见 [ADR-001](evidence/ADR-001.md)。以下均在项目根执行，日志输出目录要求新建。

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
xcodebuild -project ios/A1Harness/A1Harness.xcodeproj -scheme A1Harness -configuration Release -destination 'generic/platform=iOS' -derivedDataPath artifacts/a1/xcode-handoff-new -archivePath artifacts/a1/handoff-new/A1Harness.xcarchive DEVELOPMENT_TEAM=P57SZ9Z7G2 -allowProvisioningUpdates archive
xcodebuild -exportArchive -archivePath artifacts/a1/handoff-new/A1Harness.xcarchive -exportPath artifacts/a1/handoff-new/export -exportOptionsPlist ios/A1Harness/ExportOptions.plist -allowProvisioningUpdates
```

ExportOptions.plist 使用本地 debugging 导出和当前 Team；其他用户须选择自己的 Team 并相应修改配置。最新 build 3 原始记录位于 a1-ios-archive-run-state-v3/ 与 a1-ios-export-run-state-v3/。IPA 解包后的 codesign --verify --deep --strict 已通过；签名检查需要访问系统信任服务。入口使用公开 version-1 isolate 参数，把预留地址空间限制为256 MiB。用户已验证build 2真机独立运行PASS；build 3补充当前进程状态、时间与runID，用户也已提供PASS截图。完整边界及证据见 [真机测试交接](A1_DEVICE_HANDOFF.md)。

## 专用模拟器调试

本轮用单独 iPhone18Pro / iOS27.2模拟器，ID BD25D247-F3BF-4883-A779-D2D46015616D。创建、安装、启动和原始结果见 evidence。模拟器结果不提升真机 Gate。

Simulator 必须重新编译上游原生库，不能重标记设备 archive：

```bash
python3 -B tools/build_ios_runtime.py --output artifacts/a1/runtime-sim-new --aot-object artifacts/a1/ios-relocatable-retained/native-tmp/SVM-1794076699687/a1probe.o --sdk iphonesimulator
python3 -B tools/link_a1_ios.py --runtime artifacts/a1/runtime-sim-new --probe artifacts/a1/ios-relocatable-retained --output artifacts/a1/linked-sim-new --sdk iphonesimulator
```

JNI 辅助库亦以 SDK iphonesimulator、target arm64-apple-ios17.0-simulator 从 interop/a1/native/probe.c 编译。本轮真实命令在 artifacts/a1/jni-simulator/command.json。App 构建参数和本地签名在 artifacts/evidence/a1-simulator-build/command.json。

运行结果采集：

```bash
python3 -B tools/collect_probe_result.py --container-file artifacts/evidence/a1-simulator-container/stdout.log --simulator BD25D247-F3BF-4883-A779-D2D46015616D --output artifacts/evidence/simulator-run-new
```

采集器限定所选模拟器及测试 Bundle ID，并同时检查原生生命周期退出码与 Java 成功标记。

## Swift Craft Launcher 资源定位

```bash
python3 -B tools/locate_local_client.py --profile "$HOME/Library/Application Support/Swift Craft Launcher/profiles/Recollection3" --version-metadata "$HOME/Library/Application Support/minecraft/versions/26.1.2/26.1.2.json" --output artifacts/evidence/swiftcraft-new.json
```

只读取指定实例、共享客户端和版本元数据。游戏 JAR、依赖、资源、Java runtime 均保留在启动器共享目录；账户、存档和既有 Mod 不复制到项目。

## 测试、证据与中央登记

B0准备、真实转换/重放/负例和沙盒控制已PASS，见[B0复现](B0_TEST_HANDOFF.md)。B1的iOS AOT、运行库、签名包和用户独立运行已PASS，见[B1记录](B1_DEVICE_HANDOFF.md)。真实客户端诊断见[ADR-003](evidence/ADR-003.md)，C0仍BLOCKED。

```bash
python3 -B -m unittest discover -s tests -v
python3 -B tools/verify_evidence.py --output artifacts/evidence/verification-new.json
```

本轮79项单元/安全回归测试通过，原始输出在artifacts/evidence/unit-tests-c0-diagnostics-verified/。Mac脚本由助手执行，真机由用户负责。verify_evidence 检查命令输出、二进制、运行库和 Framework 指纹；当前源清单含 docs/.codex。它不认证游戏或设备行为。

AAR 只使用 /Users/kexin/Documents/Codex/monitor/registry.sqlite。可靠可再取得的固定缓存带 regenerable；历史运行记录、耦合的源构建状态和设备状态保留。安全删除标志均 false，不执行清理。新产物需重新核验登记。外部专用测试目录可显式提供 --external-build-root，不能用主目录或系统目录作项目。

tools/register_artifacts.py 用于不含符号链接的实验树，发现链接会明确拒绝递归登记。Xcode 归档构建目录含有指向实际 App 的符号链接，按独立 BUILD 目录登记且不跟随该链接，方式与含内部链接的 JDK 缓存相同。device-handoff 的归档/解包文件和 evidence 可分别 include-files 登记；导出目录以 DISTRIBUTION 再登记，记录 xcodebuild 导出命令。不得为登记改动或删除 Xcode 的链接。

本地Git提交保存第一方源码与文档，`git log -1`查看；原始游戏/玩家数据和生成物未纳入。建立Git后中央AAR项目身份须重新登记同步，不能继续沿用旧身份。

真实客户端分析支持有界6/8 GiB与Mac构建GC对照，命令及测量限制见[CLIENT_GRAPH_DIAGNOSTICS](CLIENT_GRAPH_DIAGNOSTICS.md)。构建JFR会改变目标JFR配置，本轮08保留提前失败记录，09/10/11均OOM，C0继续BLOCKED。
