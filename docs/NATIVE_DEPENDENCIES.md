# 桌面原生依赖库管理

Last reviewed: 2026-11-17

「环境与资源」按实际构建依赖顺序展示 GLFW-lite、LWJGL-lite、OSMesa / MoltenVK、LWJGL OpenGL shim、Metal 后端、OpenAL Soft、着色器。shim 生成 JNI 时需要读取 OSMesa 的导出符号，因此 OSMesa 位于 shim 之前。Metal 和预编译 Metal 着色器在当前 GL41 向导中为可选项，整体重建仍包含它们。

每项显示配置中的路径、构建时间、目标架构及「一致 / 已过期 / 缺失 / 校验失败」。历史产物使用 result.json 的修改时间，界面明确标作「构建记录时间」；新产物记录真正构建完成时间。历史源码对比使用其已有 sourcesSHA256，并检查已记录源码目录中的新增文件；新产物使用完整的管理清单，对新增、删除和修改逐文件比对。OSMesa / MoltenVK 当前复用固定版本预编译库的获取及校验流程，界面明确标注这一点。

## 任务和事务

- Rust 和 Python 仅接受固定工作台动作。新增只读 `dependencies`；重建请求使用原有 `start`，请求增加 `kind: "dependencies"`、`dependencyKeys`。查询和取消仍使用 `status` / `cancel`。
- `tools/native_dependencies.py` 定义固定依赖图及构建命令；不接受脚本名或自定义命令。前置依赖未就绪时，单独重建会报告应先重建哪一库。
- 新任务输出位于所选构建产物根目录下的 `native-dependencies/dependencies-<UTC时间>-<随机任务号>/<库名>`，随储存设置切换；历史任务保留原路径。启动与 worker 均执行存储守卫，复用空间预算、全局任务锁、持久 job.json、子进程日志与取消机制。
- 每份新产物保存 `dependency-manifest.json`，包括源码哈希、产物哈希、目标、构建时间和依赖产物哈希，并纳入中央 AAR。二进制还核验实际 Mach-O iOS arm64 平台，着色器复用原有 bundle 校验。
- LWJGL 自身 result.json 的 `glfwLibrarySHA256` 必须等于所选 GLFW 实际哈希；管理清单另记录依赖哈希。GLFW 源码过期会传导到 LWJGL；GLFW 重建后如二进制哈希变化，旧 LWJGL 自动显示待重建。哈希相同的可重现构建保持有效。
- 选定库全部成功、提交前复核通过且未取消时，才原子更新所选配置中的对应路径。任何编译失败、产物校验失败、源码中途变更、取消或配置并发修改都会保留原配置和全部旧产物。部分新输出和日志也保留用于诊断。
- 当前构建器仍使用各第一方构建工具既有的固定宿主输入：LWJGL 使用 prepared-04 参考库，着色器使用 shader-catalog-03 / shader-toolchain-03。宿主缓存或参考输入不齐全时会明确失败；这不是任意宿主工具链的下载管理器。
- GL41 获取复用 `verified_download` 的固定 HTTPS 来源、系统 CA、下载大小及哈希校验。着色器校验忽略 exFAT 生成的 AppleDouble / Finder 元数据，继续拒绝真实文件的修改、缺失、多余项及符号链接。

## 构建前检查

向导在环境与确认步骤展示依赖预检，提供「一键重建所需依赖」。点击构建时先刷新依赖清单；发现异常时打开依赖管理页，不提交 IPA 任务。后端 validate_request 与 worker 环境检查再次执行同一预检，阻止绕过页面以及检查后源码变更。原 CLI 的 AOT 输入哈希检查继续保留。

只读检查示例：

```sh
python3 -B tools/desktop_workbench.py dependencies \
  --request '{"config":"/absolute/path/config.json"}'
```

## 验证与边界

- Python 测试：`tests/test_native_dependencies.py`，覆盖状态、具体源码差异、动作白名单、拓扑顺序、工作台分派、失败 / 取消 / 并发配置修改、成功切换，以及 GLFW 更新但 LWJGL 未跟随时拒绝预检。
- Rust：`dependency_actions_use_the_fixed_workbench_allowlist`。
- Playwright：`desktop/tests/native-dependencies.spec.ts`，覆盖七项依赖、四类状态、变更文件、浅深主题、单库 / 整体任务、日志、取消、失败保留路径与向导提前阻断。
- 本轮自动化结果：500 项 Python、69 项前端单测、10 项 Rust、44 项 Playwright 全部通过，TypeScript / Vite 生产构建通过。
- 2026-11-17 真实任务 `dcf3ec92611b46a38655af1c3f1a1a2f` 已成功构建 GLFW、LWJGL、OpenGL shim。输出 `artifacts/graphics/dependencies-20261116T232838Z-dcf3ec92/`；只修改 `/private/tmp/ncl-dependency-verification-20261117/config.json` 验证副本。第一轮任务 `e34119a9cf0649b5b29db089b45524e5` 因宿主缺少 ASM 依赖失败，保留旧配置；补齐固定哈希依赖后使用新目录重试。
- 最终整体任务 `835543a7b96f454eafb0ec186f8966df` 成功，七项状态全部为「一致」，60 组着色器完成翻译 / Metal 编译 / bundle 校验。输出 `artifacts/graphics/dependencies-20261116T233734Z-835543a7/`，仍只切换上述独立验证配置。中途的 TLS 来源证书问题和 exFAT 着色器元数据问题及其失败任务均保留；修复未关闭证书、真实文件或哈希验证。
- 本次没有执行新 AOT、导出 IPA、模拟器或真机游戏验收，不改变产品 Gate 状态。验证摘要和原始测试日志位于 `artifacts/evidence/native-dependencies-20261117/`。
