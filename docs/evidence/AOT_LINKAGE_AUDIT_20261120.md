# 2026-11-20 AOT 启动与链接审计

## 字节码证据

对本机保存的 `build-768a7fa05da2-subset-57bf421d` 和 `build-365aeda02191-subset-61b08665` 的实际构建输入进行了只读审计。两个输入都是 GL41，包含 Biomes O’ Plenty、GlitchCore、TerraBlender、Freecam 和 Fabric API。这两份产物的 Mod 子集各有 41 个根 JAR。原 Recollection3 有 53 个根 JAR，历史导出报告记录了 8 个被排除的 Mod ID，因此子集的分析结果不能用于给 53 个根 JAR 的完整包判定通过。

- 旧 `AotExport` 在游戏类完成 Knot 转换后，无条件调用 `RuntimeLowering.lowerRenderPipelineRegister`。旧 Fabric 导出 JAR 的 `RenderPipelines.register` 已出现 `invokestatic fabricaot/metal/BundledPipelines.register`。该类由 `compiler/metal-backend` 编进 Metal 专用 JAR。旧 GL41 的实际 Native Image 类路径中没有这个 JAR，也没有该类定义。
- 方法拆分生成 `fabricaot$init$clinit$9b75$*` 并继续调用游戏自身的 `register`。旧 GL41 补丁后的方法仍然调用 Metal 守卫。两个补丁后 JAR 的 SHA-256 分别为 `a7d88fabed4026bac96e83425ca91ec0588b8b2f710d3fd86a6edfc8d086a233` 与 `c53f3cccd83ba775c9d015cae366a389adb59aa67c9d5053ad32a9fba653bfbf`。本轮扫描均在 `RenderPipelines#register` 报告 `METAL_REFERENCE_ON_GL41` 阻塞。
- 当前分支的 `0117600` 已把守卫限制在 Metal 选择下。实际的修复版 Prism 样本经过 Fabric 导出、拆分、GL41 补丁后三次反汇编均显示 `Map.put`。最终 JAR SHA-256 为 `3ad0d56c01d13cec3752312fc99f50e146cf8c1b43bdc9adfefcb0de460175d8`。本轮修复了独立 Fabric 导出的旧默认值与 CI 未传递后端参数的问题，增加了 Fabric 导出、拆分、补丁、编译及打包各阶段的后端一致性校验。
- Freecam 实际 DTO 有公开无参构造器。其配置控制器将 DTO 的类字面量传给 Gson 加载器，加载器的默认分支通过保存在字段中的 `Class` 调用 `getConstructor()`。本轮从 Freecam 和 Prism 的实际字节码重新生成了该 DTO 及配置字段图的注册。历史同版 GraalVM 第一方对照在缺少构造器注册时抛出 `NoSuchMethodException`，补齐后输出 `REFLECTIVE_CONSTRUCTOR_PASS`。

可用 `javap -p -c -classpath "$JAR" net.minecraft.client.renderer.RenderPipelines` 对照原版、Fabric 导出、方法拆分和后端补丁四级输入。Native Image 最终类路径及各 JAR 哈希见对应构建的 `aot/*/product/result.json`，命令见 `analysis/command.json`。

## 预检与产物

- Builder、CLI 和设备 CI 在 Native Image 前使用同一预检。并行建立归档索引和计算内容哈希，按 Native Image 类路径顺序选择实际类定义，遵守 Java 25 Multi-Release 规则。扫描覆盖应用类、合并游戏/Mod、库类及被引用的 JDK 声明。记录类、继承、方法、字段、静态初始化拆分段、方法句柄和 bootstrap 编码引用。
- 对后端串用、必需类型、生成的 Fabric 启动分派，以及主入口无条件前缀中能确定的缺失引用阻断。分支、异常处理、多态运行时目标、宿主 JDK 与设备替换差异、动态元数据覆盖范围仍需要结合运行证据。资源和服务声明从选定 JAR 校验，JNI ABI、平台和签名继续在现有原生验证层检查。完整报告保留归档和调用位置，Fabric 导出同时提供类所属 Mod ID。
- 扫描缓存按有序类路径内容、JDK 声明、扫描器源码、后端及入口点绑定。Native Image 对象缓存还要求同后端的成功预检、对象/命令哈希及生成的元数据证据。测试版本标签随打包变化可复用同一 AOT 对象。阶段检查点仍校验原输出内容。
- 打包前生成 `FAOTBuildProvenance.json`，包括构建指纹、源码提交、后端和每个嵌入 dylib 的 Mach-O UUID。打包与重导出复核 UUID，iOS 启动日志输出这些值并核对实际加载的游戏镜像。只有 GL41 广播 OpenGL shim 参数，只有 Metal 广播原生 Metal 资源预算。
- OSHI 的独立平台问题由共同 iOS 字节码适配处理。GLX 使用 JVM 报告的可用处理器数与架构，SystemReport 保留存储探测与已有通用信息，并明确记录 iOS 无法提供 OSHI 硬件清单。Profiler 或其他 Mod 自己调用 OSHI 仍需单独验证。DNS 缺少带目标域名、时间和对应包指纹的设备日志，无法归因到某个解析器或证明已修复。

## 本轮静态验证

| 已有实际输入 | 全类路径有效类 | 预检结论 |
| --- | ---: | --- |
| 原版 GL41 最终 JAR | 37,862 | 0 阻塞 |
| Fabric API + Biomes O’ Plenty + GlitchCore + TerraBlender | 40,590 | 0 阻塞 |
| Fabric API + Freecam | 40,636 | 0 阻塞，DTO 注册存在 |
| 两组合并的 Prism 构建 | 41,290 | 0 阻塞，DTO 注册存在 |
| 第一方 Fabric/Mixin/资源样本 | 38,309 | 0 阻塞 |
| 两份旧 Recollection3 子集构建 | 各 53,742 | 各拦截 1 项 GL41 引入 Metal |

实际矩阵使用保存的 Native Image 类路径和相同 SHA-256 的归档。单组 Mod 样本与第一方夹具使用保存的 Fabric 导出加同一组库。独立 Fabric API 根包、重新导出的完整 53 根 JAR 组合、原生 Metal 的完整游戏与真机测试本轮未执行。第一方负例覆盖缺类、缺方法和字段、Lambda 方法句柄、错误构造器元数据、Multi-Release 类遮蔽、跨后端缓存、损坏缓存和产物 UUID 不匹配。

定向 Python 回归 100 项通过、2 项跳过。用仍可访问的固定 Java 25/ASM 输入在临时目录执行第一方字节码夹具，15 项通过、2 项因缺少历史工件跳过。Fabric 导出器经 Java 25 编译，iOS 宿主通过 Apple SDK Objective-C 语法检查，现有 GL41 样本的 7 个 dylib UUID 均可读取。前端 91 项单元测试、TypeScript 检查及 Builder 诊断的 Playwright 键盘交互通过。默认工作区的 597 项 Python 全套测试记录 574 项通过、5 项跳过和 18 项环境错误，涉及旧绝对路径、存储守卫及沙箱禁止调用 `ps`。进程取消测试在允许 `ps` 后单独通过。

同一份 Prism 输入的旧预检扫描 14,115 个类，实测 4.965 秒，峰值 RSS 205.9 MiB。新预检扫描 41,290 个类、451,202 个方法和 211 个拆分的静态初始化方法。冷扫描 25.786 秒、459.7 MiB，缓存命中 0.042 秒、45.3 MiB。冷扫描和缓存返回相同诊断，缓存命中会重新核对输入哈希。以下 Native Image 指标来自现存构建记录，仅作为基线。三个样本的 Mod 集不同。

| 已保存样本 | Native Image 耗时 | 峰值 RSS | 原生对象大小 | IPA 大小 |
| --- | ---: | ---: | ---: | ---: |
| 旧 Recollection3 子集 | 1,619.2 s | 6,365,511,680 B | 526,944,024 B | 634,864,479 B |
| 修复后 Prism 组合样本 | 196.8 s | 7,316,111,360 B | 310,951,528 B | 527,741,266 B |
| 原版 GL41 | 174.1 s | 6,271,942,656 B | 242,163,807 B | 480,692,865 B |

## 构建与真机状态

外接盘守卫报告 `data-directory-missing`，配置要求的 `/Volumes/K/MCFAO-data` 缺失。CoreDevice 本轮未列出设备。新 Native Image、完整增量与全量产物对照、新签名 IPA、真机启动、进菜单/世界、操作退出、Freecam 配置和性能均为 NOT RUN。游戏 Gate 保持 BLOCKED。

当原存储映射和本地签名可用时，从 Builder 用本地完整整合包构建，测试版本填写 `AOT-preflight-r1-20261120`。CLI 可复跑同一入口。

```sh
./mcfao build --version 26.1.2 --target ios-arm64 --renderer gl41 \
  --loader fabric --mods "$MODS_DIR" --audited-mods --config "$GL41_CONFIG" \
  --test-version AOT-preflight-r1-20261120 --output "$NEW_BUILD_DIR"
./mcfao verify --target ios-arm64 --output "$NEW_BUILD_DIR"
```

安装后核对启动页测试版本、日志 buildKey、renderer、源码提交和实际 imageUUID。依次验证 dylib 加载、Fabric main/client 入口点、管线注册、GLFW/设备初始化、主菜单、创建世界、渲染与操作、保存退出和重进。Freecam 验收分别覆盖首次生成配置和已有配置重读。若 DNS 失败，回传实际异常上下文及同次装机日志，以便定位 Mojang 端点、服务器 SRV/A/AAAA 解析或当前设备网络。
