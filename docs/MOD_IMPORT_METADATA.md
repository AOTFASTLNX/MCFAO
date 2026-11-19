# Mod 导入与 macOS 元数据

Last reviewed: 2026-11-19

扫描、CLI 导入、桌面暂存、下载路径选择、归档覆盖文件提取和构建输入枚举共用 `tools/mod_file_policy.py`。路径任一分量为 `._*`、`.DS_Store` 或 `__MACOSX` 时不作为内容导入，不进入 Mod 数量、资源选择、输入哈希或阶段输出指纹。普通隐藏文件和大小写不同的 `.JAR` 仍正常处理。

`clean_staged_metadata` 仅用于构建器自己创建的暂存树：清理普通 `._*` / `.DS_Store` 伴生文件，清理空元数据目录；不跟随或删除符号链接，不删除普通 JAR（包括位于 `__MACOSX` 下的普通文件，这些文件只会被忽略）。用户原始 Prism 实例和 `.mrpack` 不做修改。复制/写入后、Knot 扫描前、恢复暂存清单校验前分别执行清理；exFAT 后续再次生成伴生文件时仍由过滤规则排除。

真实 JAR 继续做 ZIP 目录安全检查、成员 CRC 检查和 `fabric.mod.json` 检查；损坏压缩数据、CRC、JSON、路径越界、链接、哈希或文件大小均保持错误。缺少 Fabric 元数据仍报告既有 `NO_FABRIC_META`，后续 Fabric 闭包解析继续决定是否可构建。过滤不会将静态预检提升为运行兼容验证；声明的不兼容依赖和构建期转换失败仍会阻断。归档路径安全检查在过滤前保留，不以元数据名称绕过路径安全规则。

目录资源选择不受伴生文件增删影响。`.mrpack` 选择指纹使用过滤后的 manifest 和真实成员 CRC/大小，避免重新打包元数据造成失效；实际导入仍验证下载 SHA-1/SHA-512，最终内容和缓存仍验证 SHA-256。旧版本生成的 `.mrpack` 资源选择需要重新扫描；本次恢复只在原算法指纹仍与原任务匹配时迁移选择。已有构建输入不会被重写；策略源文件列入构建工具指纹，修复后的构建使用新输入，不能把旧检查点当作新工具链结果。

回归测试：`python3 -B -m unittest discover -s tests -p 'test_mod_file_policy.py'`，涵盖 CLI/GUI、本地/归档/远程导入、复制后生成伴生文件、损坏真实 JAR、Fabric 元数据错误、CRC、清理边界、资源选择和阶段缓存。桌面资源打包同时携带共享模块。

## 2026-11-19 Fabric 导出与后续阶段排查

构建 `build-bc966e1984c6-subset-73a2b52d` 在 `/Volumes/K`（exFAT）的 `runtime-classes` 中生成了 13 个 AppleDouble 伴生文件。Fabric 导出按 `.class` 后缀将它们写入客户端 JAR，方法拆分与 GL41 补丁保留了这些条目，最终反射扫描将 `00051607` 误当 Java classfile 文件头。错误发生在 Native Image 启动前。

| 入口 | 处理 |
| --- | --- |
| Fabric JAR 枚举、运行时 classfile 导出和客户端 JAR 合并 | 在实际读取前按相对路径过滤。归档成员的路径、重复名称、大小和链接检查仍在过滤前进行。有效名称下类头损坏会报出文件名。显式引用的伴生条目不能充当嵌套 JAR 或 Mixin 配置。 |
| AOT 反射、classpath 与 tracing-agent | 忽略伴生条目。真实 classfile 解析失败时记录 JAR 和条目路径，真实 JSON 错误继续报错。 |
| 工具链、源码包、LWJGL／Metal 及构建指纹 | 上游源码和 shader 工具缓存的根目录枚举过滤伴生文件。源码、产物和目录指纹只消费有效名称。无伴生条目的新 LWJGL JAR 保留原始字节。 |
| Xcode 资源复制、原生库检查及 IPA ZIP 写入 | 签名前复制资源时过滤。ZIP 写入再次检查相对路径，以排除归档前出现的伴生文件；CI 只将真实目录选为应用包。 |

规则按路径生效，适用于项目内与外接存储。正常隐藏文件仍按原入口处理。工具源文件计入任务指纹，使用修复后源码重试时会从已更新的输入重新建立构建目录。

本地用 Java 25 编译并运行修复后的实际导出方法。原 exFAT 类目录与干净目录各产出 13 个真实类，两个 JAR 字节一致，真实名称下的错误头被拒绝。原 GL41 JAR 中 13 个伴生条目被过滤，66,718 个内容条目保留。旧 JAR 和过滤后 JAR 的反射扫描均生成相同的 148 条配置。另用注入元数据的第一方 Fabric 夹具走通沙箱控制和完整客户端导出，确认输出 JAR 无元数据且通过 CRC 校验。原整合包的完整 AOT、签名和真机未在本轮验证。

## 2026-11-20 GraalVM 与签名边界

`B249F8B4` 的 Native Image 驱动把 GraalVM 25.0.2 自身 `lib/svm/builder/._svm.jar` 加入了模块路径，报 `ZipException: zip END header not found`。过滤项目传入的 classpath 无法改变驱动对自身目录的扫描。

- 客户端 AOT、A1 和 B1 检查选中的 Java Home。遇到 AppleDouble 或 `__MACOSX` 时，在系统卷临时构造干净的 Java Home，保留内容文件、执行位和目录内链接。AOT 的沙箱以实际使用的 Java Home 生成规则，临时副本随调用退出清理。干净工具链及仅含 `.DS_Store` 的工具链原地使用。原 JDK 缓存和存储配置不参与清理。
- 后续阶段过滤 CAP 数据复制、A1/B1 头文件、旧 GL41 产物清单及 IPA 成品选择。Xcode 嵌入原生库与图标时省略扩展属性和资源叉。未签名 IPA 的签名移除和 macOS 工作台的签名先在系统卷完成。写入 IPA 时继续排除元数据路径，迁移任务配置时仅解析真实 JSON。
- 工作台更新后重试已打包应用的任务时，沿用原任务的整合包、构建配置与暂存目录，使用当前应用内置源码。若工具指纹变化，旧构建和日志保留，编译器会使用新的构建目录。CLI 使用新的输出目录。

验证使用同一套实际 exFAT 工具链。直接执行 Native Image `--dry-run` 复现模块扫描失败。以 `run_a1_probe.py --graalvm-home <原 Java Home> --output <新输出> --mode ios-relocatable` 执行第一方探针时，Native Image 退出 0 并写出 ARM64 Mach-O 可重定位对象。该探针的设备 Gate 仍为 BLOCKED。原 Fabric 整合包的完整 AOT、开发签名和真机运行需分别复验。

## 2026-11-15 Mod 导入复核

- 分支：`integration/gl41-gui-ipa-20261115-appledouble`。
- 原失败任务：`ff517934cf18406586bbd5137e404a49`，Recollection3 导入后的 AppleDouble JAR 误报。
- 外接盘守卫通过后，清理原任务暂存树 232 个元数据项；192 个真实文件的 SHA-256 在清理前后完全相同。真实根 Mod 共 53 个，ZIP/Fabric 静态检查无 error。
- 原始证据：`artifacts/integration-20261115/appledouble-fix/cleanup.json`、`resumed-job.json`。原 pack、Mod、资源及日志保留本地。
- 自动化测试：407 项全部通过，含 11 项本次专项回归。完整日志：`artifacts/integration-20261115/appledouble-fix/unit-tests.log`。
- 继续任务：`b6112a911fd9421da10b7cf96e9695e0`，使用原资源选择并重新下载校验，导入与 doctor 通过。随后 Fabric 阶段的 sandbox-control 阻止外接盘工具链 Java 启动：`sandbox-exec: execvp() ... java failed: Operation not permitted`（控制子进程退出 71，构建退出 2）。保持该独立阻断，不放宽隔离、不跳过控制。真实 JAR 静态检查无 error；完整 Fabric 依赖/转换兼容性尚未执行，不能据此判定整个整合包兼容。最终复核：`artifacts/integration-20261115/appledouble-fix/result.json`；原始失败日志在继续任务 build 目录的 `fabric/*/product/sandbox-control/stderr.log`。
