# Mod 导入与 macOS 元数据

Last reviewed: 2026-11-15

扫描、CLI 导入、桌面暂存、下载路径选择、归档覆盖文件提取和构建输入枚举共用 `tools/mod_file_policy.py`。路径任一分量为 `._*`、`.DS_Store` 或 `__MACOSX` 时不作为内容导入，不进入 Mod 数量、资源选择、输入哈希或阶段输出指纹。普通隐藏文件和大小写不同的 `.JAR` 仍正常处理。

`clean_staged_metadata` 仅用于构建器自己创建的暂存树：清理普通 `._*` / `.DS_Store` 伴生文件，清理空元数据目录；不跟随或删除符号链接，不删除普通 JAR（包括位于 `__MACOSX` 下的普通文件，这些文件只会被忽略）。用户原始 Prism 实例和 `.mrpack` 不做修改。复制/写入后、Knot 扫描前、恢复暂存清单校验前分别执行清理；exFAT 后续再次生成伴生文件时仍由过滤规则排除。

真实 JAR 继续做 ZIP 目录安全检查、成员 CRC 检查和 `fabric.mod.json` 检查；损坏压缩数据、CRC、JSON、路径越界、链接、哈希或文件大小均保持错误。缺少 Fabric 元数据仍报告既有 `NO_FABRIC_META`，后续 Fabric 闭包解析继续决定是否可构建。过滤不会将静态预检提升为运行兼容验证；声明的不兼容依赖和构建期转换失败仍会阻断。归档路径安全检查在过滤前保留，不以元数据名称绕过路径安全规则。

目录资源选择不受伴生文件增删影响。`.mrpack` 选择指纹使用过滤后的 manifest 和真实成员 CRC/大小，避免重新打包元数据造成失效；实际导入仍验证下载 SHA-1/SHA-512，最终内容和缓存仍验证 SHA-256。旧版本生成的 `.mrpack` 资源选择需要重新扫描；本次恢复只在原算法指纹仍与原任务匹配时迁移选择。已有构建输入不会被重写；策略源文件列入构建工具指纹，修复后的构建使用新输入，不能把旧检查点当作新工具链结果。

回归测试：`python3 -B -m unittest discover -s tests -p 'test_mod_file_policy.py'`，涵盖 CLI/GUI、本地/归档/远程导入、复制后生成伴生文件、损坏真实 JAR、Fabric 元数据错误、CRC、清理边界、资源选择和阶段缓存。桌面资源打包同时携带共享模块。

## 本次本地复核

- 分支：`integration/gl41-gui-ipa-20261115-appledouble`。
- 原失败任务：`ff517934cf18406586bbd5137e404a49`，Recollection3 导入后的 AppleDouble JAR 误报。
- 外接盘守卫通过后，清理原任务暂存树 232 个元数据项；192 个真实文件的 SHA-256 在清理前后完全相同。真实根 Mod 共 53 个，ZIP/Fabric 静态检查无 error。
- 原始证据：`artifacts/integration-20261115/appledouble-fix/cleanup.json`、`resumed-job.json`。原 pack、Mod、资源及日志保留本地。
- 自动化测试：407 项全部通过，含 11 项本次专项回归。完整日志：`artifacts/integration-20261115/appledouble-fix/unit-tests.log`。
- 继续任务：`b6112a911fd9421da10b7cf96e9695e0`，使用原资源选择并重新下载校验，导入与 doctor 通过。随后 Fabric 阶段的 sandbox-control 阻止外接盘工具链 Java 启动：`sandbox-exec: execvp() ... java failed: Operation not permitted`（控制子进程退出 71，构建退出 2）。保持该独立阻断，不放宽隔离、不跳过控制。真实 JAR 静态检查无 error；完整 Fabric 依赖/转换兼容性尚未执行，不能据此判定整个整合包兼容。最终复核：`artifacts/integration-20261115/appledouble-fix/result.json`；原始失败日志在继续任务 build 目录的 `fabric/*/product/sandbox-control/stderr.log`。
