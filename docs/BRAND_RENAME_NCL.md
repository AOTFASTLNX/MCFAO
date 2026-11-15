# Native Craft Launcher / NCL 品牌更名报告

日期：2026-11-15
分支：codex/ncl-brand-rename-20261115，基线 origin/main 的 41dd14c0d5b37738a763b73a95f07f49a6c309db。

## 更名范围

| 对象 | 新名称 |
| --- | --- |
| 正式产品名 | Native Craft Launcher |
| 简称 | NCL |
| iOS / iPadOS 应用显示名 | Native Craft |
| macOS GUI 构建工具 | NCL Builder |
| 当前无签名 / 开发签名 IPA 产物 | NCL-game.ipa、NCL-WorldDevice-unsigned.ipa |
| macOS 应用包 | NCL Builder.app |
| 导出报告与日志 | ncl-preflight.json、ncl-build-<id>.txt、ncl-workspace.json |

README.md、根 AGENTS.md、docs/PRODUCT.md、docs/TECHNICAL_GATES.md、docs/REVIEW_REPORT.md、docs/BUILDING.md、docs/DESKTOP.md、兼容矩阵标题和 GUI 构建指南中的当前产品称谓已更新。GUI 侧栏、窗口标题、浏览器标题、设置页新增「关于 NCL Builder」、版本 v0.2.6、日志导出名、项目目录标签、错误提示、Rust 宿主提示和 CLI 描述同步更新。iOS 四份 Info.plist 的显示名、A1/B1 状态文案、启动器标题、GLFW 版本串、Metal 后端诊断串更新。

## 明确保留的技术标识

以下内容均保持不变：

- Java 包名 fabricaot.*、mcfao.*，JNI 符号 fabricaot_a1_run，FabricAOTProbe.framework、@rpath/FabricAOTClient.dylib、fabricaot-present.metallib / fabricaot-shaders/。
- 全部 Bundle Identifier：org.fabricaot.research.c0.kexin、fab.aot.kexin、org.fabricaot.desktop、org.fabricaot.research.runtime 等；签名证书、Provisioning Profile、DEVELOPMENT_TEAM 解析和 ExportOptions.plist 不变。
- mcfao CLI、tools/mcfao.py 模块名、mcfao.local.json、artifacts/mcfao-local.json、artifacts/mcfao-gl41.json、artifacts/mcfao/ 与 /Volumes/K/MCFAO-data/。
- FAOT_* / FABRICAOT_SIMULATOR_* / MCFAO_* 环境变量、xcconfig 键、NSUserDefaults 键、Documents/game 与存档路径、任务目录和 result.json 字段。
- [MCFAO_ENTRYPOINT]、[MCFAO_SHADER]、[FAOT]、MCFAO_F1/F3_*_PASS 等门禁与日志标记。
- Xcode target / scheme / product name：C0Harness、FabricAOTWorld、WorldDevice、WorldSimulator、WorldUITests；这些名称绑定 xcodebuild -scheme 与测试目标。
- 渲染路线：ADR-009 的 GL41 / OSMesa-Zink / MoltenVK / CAMetalLayer 主路线不变；compiler/metal-backend 仍作为可选独立路径，没有重新引入或切换主渲染器。
- 带固定 SHA-256 的历史交付记录、CI 快照、历史日志和既有 result.json 证据原样保留；不通过改写证据来「完成」更名。

## 用户数据与配置连续性

桌面 GUI 的四个 localStorage key 改为 ncl.theme.v1、ncl.accent.v1、ncl.builder.v2、ncl.desktop.v1。新增 desktop/src/storage.ts 统一维护新旧 key，并在启动时把旧值复制到新 key；读取顺序为「新 key → 旧 key → 默认值」，旧值保留以支持回滚。重置界面记录会同时清除新旧两组 key。测试覆盖旧值读取、迁移和不覆盖现有新值。Tauri identifier 保持 org.fabricaot.desktop，因此 WebKit 存储 origin 不变。

实际启动的 GUI 显示 NCL Builder 与 v0.2.6 · 实验版，并保留了既有的 Recollection3 .mrpack 来源记录和表单，说明旧配置继续可用。

## 更名后验证

| 验证 | 结果 |
| --- | --- |
| 外接盘挂载守卫 | python3 -B tools/external_storage.py --json 返回 available: true |
| Python 全量回归 | 396 项 PASS，13 项按既有条件跳过 |
| Mod 导入 / 元数据 / 转换 / 矩阵定向回归 | 108 项 PASS（import 9、mod catalog 3、matrix 5、scan evidence 8、runtime lowering 11、desktop workbench 35、mcfao 37） |
| 前端单元测试 | 59 项 PASS，含新增旧 key 迁移测试 |
| 前端生产构建 | tsc -b && vite build PASS |
| 浏览器交互测试 | 37 项 PASS |
| Rust 桥接测试 | 8 项 PASS |
| Tauri macOS 打包 | NCL Builder.app 生成成功；CFBundleDisplayName / CFBundleName 为 NCL Builder，CFBundleIdentifier 仍为 org.fabricaot.desktop |
| 原生 GUI 启动 | 从本地签名副本启动成功，截图确认菜单栏与侧栏显示 NCL Builder，已有导入记录保留 |
| CLI / 配置语法 | mcfao、preflight、desktop_workbench help，4 份 Info.plist，3 个 shell 脚本，6 份 YAML 均通过 |
| 真实 Mod 预检 | tools/preflight.py /Users/kexin/Downloads/Recollection3.mrpack 返回 STATIC_PREFLIGHT_ONLY，解析出真实 Mod 元数据 |
| AOT 前置检查 | mcfao doctor --config artifacts/mcfao-gl41.json --renderer gl41 返回 INPUTS_VERIFIED，核验 4229 个输入与 Java/GraalVM 25.0.2、Xcode 27.2 |

完整原版 GL41 AOT 构建在更名分支上执行到 aot 阶段：首次因独立 worktree 的 .cache 符号链接与沙盒策略路径不一致，sandbox-exec 探针报 Operation not permitted；将探针改用外接盘规范路径后 B0_SANDBOX_PASS。随后构建被既有的主机内存守卫阻断：Host memory headroom below bounded experiment threshold（当时可用内存约 33%，构建要求 9 GiB 堆）。这是环境资源门槛，不是名称或路径回归；没有生成新的可安装 IPA，也没有把构建成功冒充为真机可玩证据。已有历史开发签名 IPA 与真机 Gate 状态仍按原证据保留，C0 / C0a / C0b / C0c / D1 / E 的真机验收继续为 BLOCKED。

## CI / GitHub 仓库重命名迁移方案（远端状态补充）

本 PR 不执行 GitHub 仓库 rename、不修改 main、不启用新签名 workflow。推送本分支时，远端返回 This repository moved ... https://github.com/AOTFASTLNX/NativeCraftLauncher.git；只读 gh repo view 确认 AOTFASTLNX/MCFAO 已重定向到 AOTFASTLNX/NativeCraftLauncher，默认分支仍是 main。也就是说，rename 已由仓库管理员在本任务之外完成，旧 UPSTREAM / clone URL 当前依赖 GitHub 重定向继续工作。本 PR 保持这些旧地址不变，避免把尚未验证的新 slug 写进活跃 CI；后续按下面的双跑窗口验证后再切换。

### 当前活跃硬编码

| 位置 | 性质 |
| --- | --- |
| .circleci/config.yml:157 UPSTREAM="https://github.com/AOTFASTLNX/MCFAO" | 当前 CircleCI integration-game-ipa 的源码地址 |
| ci/build_mac.sh:11-12 CI_REPO / UPSTREAM | 完整 AOT 构建脚本默认 clone 目标 |
| ci/build_sim.sh:9 UPSTREAM | 模拟器构建脚本默认源码地址 |
| ci/native-refresh-sign.yml:25 repository: AOTFASTLNX/MCFAO | 显式 checkout 目标；文件当前位于 ci/，不是活跃 Actions workflow |
| ci/circleci/config.yml:11 UPSTREAM | 外部 CircleCI 项目配置模板 |
| README.md:91 git clone https://github.com/AOTFASTLNX/MCFAO.git | 用户可见且会实际执行的 clone 命令 |

.circleci/config.yml 还显式依赖 CIRCLE_BRANCH = "main" 和工作流分支过滤 only: main；.github/workflows/*.yml 为无分支过滤的 push:。ci/snapshots/*、历史 Actions 运行 URL、v14 操作记录和带固定 SHA 的 raw URL 都是历史证据，保持原样。

### 分阶段安全迁移

1. 当前状态：本 PR 中所有旧远端地址保持不变，依赖已生效的重定向；同时把上述活跃地址收敛为可由环境变量覆盖的默认值，保留旧值。此阶段只做配置参数化，不触发 AOT，也不改历史证据。
2. 管理员核对：确认新 owner/repo 为 AOTFASTLNX/NativeCraftLauncher、是否保留 AOTFASTLNX org、是否同时改默认分支、是否保留旧名重定向窗口。GitHub rename 后旧 git/web/raw URL 会重定向，但这是兼容层，不是永久契约。
3. 双跑窗口：用旧 UPSTREAM 与新 UPSTREAM 分别触发 CircleCI build-game-ipa 和两个 GitHub Actions workflow；比较 CIRCLE_SHA1 / SOURCE_SHA、source-sha.txt、IPA SHA-256 与 artifact 名称。若 CircleCI 新项目未自动跟随，由管理员重新 Follow / Set Up Project 并手动触发。
4. 切换与清理：双跑一致后更新本地 origin 与所有 worktree 的 remote 到 AOTFASTLNX/NativeCraftLauncher、CircleCI 项目变量 / contexts / checkout key / webhook / required status checks、分支保护、ci/native-refresh-sign.yml:25 与 README clone 命令。保留 ci/snapshots/* 和历史文档。
5. 回滚：若新 slug 验证失败，管理员可 revert 配置 PR、把本地 remote 恢复为旧 URL（仍走重定向）、重新 Follow 旧 CircleCI 项目并复核 secrets / branch protection。旧名若在窗口内被第三方占用，则无法完整回滚到旧名。

### 需要管理员权限或单独确认

GitHub 仓库 rename / org 变更、默认分支改名、分支保护、environments、secrets、GitHub App、Pages；CircleCI 项目 Follow、项目变量、contexts、webhook 与 required status checks；外部历史构建项目 zhangrongxue/mc-aot-ios 和私有签名项目 zhangrongxue/mc-aot-sign 的迁移；把 ci/native-refresh-sign.yml 移入 .github/workflows/ 会启用涉及 P12_PASSWORD 与签名材料的流程，必须单独确认。Modrinth CDN、Mojang metadata 和 GraalVM 下载按固定主机白名单工作，不受本仓库名影响。

建议的只读盘点命令见本报告末尾「验证命令」；这些命令不会改变远端状态。

## 已知限制

- 本次是品牌与用户可见名称更名，不改变技术 Gate 状态；没有新增真机安装、进入世界、性能或存档保留证据。
- 完整 AOT / IPA 因当前主机可用内存低于构建门槛而未完成；doctor、静态预检、导入/转换回归、GUI 打包与启动均已通过。
- Tauri 打包脚本在外接盘 exFAT 产物上执行 ad-hoc 签名时会遇到 ._* 伴生文件；本次从本地副本完成签名和启动验证，外接盘上的原产物未被改写。
- 远端仓库已由管理员重命名为 AOTFASTLNX/NativeCraftLauncher，但本仓库内活跃 CI 地址与本地 remote 仍使用旧 URL 并依赖重定向；CI 项目 slug 与历史证据保持当前值，待按方案双跑验证后切换。

## 验证命令

```bash
python3 -B tools/external_storage.py --json
python3 -B -m unittest discover -s tests -v
cd desktop && npm test && npm run build && npm run test:e2e
cd .. && cargo test --manifest-path desktop/src-tauri/Cargo.toml --lib
python3 -B tools/preflight.py /Users/kexin/Downloads/Recollection3.mrpack
python3 -B tools/mcfao.py doctor --config artifacts/mcfao-gl41.json --renderer gl41
bash -n ci/build_mac.sh ci/build_sim.sh ci/refresh_launcher.sh
rg -n 'AOTFASTLNX|raw.githubusercontent.com/AOTFASTLNX' .circleci ci README.md
```
