# 可选：把大体积目录放到外接盘

> 2026-11-17：外接盘是本机可选的存储布局，不是仓库要求。默认克隆下来的项目使用项目内目录，任何一块空间足够的盘都能构建。本文描述的是把缓存与产物通过符号链接放到外接盘的配置方式，只对声明了这份映射的本机生效。

## 默认行为

仓库不含挂载清单。`external-storage.json` 属于本机个人配置，已在 `.gitignore` 中排除；没有这份文件时，`tools/external_storage.py` 报告 `available: true`，构建只受所选目录的空间预检约束。

当仓库根存在这份清单时（例如为释放内置盘空间，把体积大、可由本地重建或保留为历史证据的目录移到外接盘，原位置改为符号链接），守卫才会启用：

```bash
python3 -B tools/external_storage.py --json
```

返回 available: true 才能构建。返回 volume-not-mounted 时请插入硬盘；返回 data-directory-missing 或 missing-links 时先按下面的映射表修复。启用了守卫就不要绕过它。

## 本机示例配置

按需创建 `external-storage.json`（不要提交），并建立对应的符号链接：

```json
{
  "volume": "/Volumes/K",
  "data": "/Volumes/K/MCFAO-data",
  "directories": [
    {"link": "artifacts/mcfao", "external": "artifacts/mcfao"},
    {"link": "artifacts/graphics", "external": "artifacts/graphics"},
    {"link": "artifacts/desktop-jobs", "external": "artifacts/desktop-jobs"},
    {"link": "desktop/src-tauri/target", "external": "desktop/src-tauri/target"},
    {"link": ".cache", "external": "cache"}
  ]
}
```

## 目录映射

映射条目完全由本机清单决定，下面只是上述示例的展开。

| 项目内路径（符号链接） | 外接盘实际路径 | 内容 |
| --- | --- | --- |
| artifacts/mcfao | MCFAO-data/artifacts/mcfao | 历轮 AOT 构建、整合包、签名产物与逐阶段日志（Gate 证据） |
| artifacts/graphics | MCFAO-data/artifacts/graphics | 图形/音频/着色器输入、模拟器世界与世界设备包 |
| artifacts/desktop-jobs | MCFAO-data/artifacts/desktop-jobs | 桌面工作台任务、Xcode DerivedData |
| desktop/src-tauri/target | MCFAO-data/desktop/src-tauri/target | Rust 构建缓存，可重建 |
| .cache | MCFAO-data/cache | GraalVM/JDK、upstream 源码、GLFW/LWJGL/Apple Metal 缓存，可重建 |

artifacts/desktop 内是已跟踪的界面截图证据，保持在主仓库不动。外接盘常用 ExFAT：权限位和扩展属性不保真，复制时用 rsync -rlpt 并清理 ._* 伴生文件；符号链接虽然能创建，但只让主仓库这一侧持有链接。

## 守卫实现

- tools/external_storage.py 在清单缺失时直接返回可用，并按 tools/storage_config.py 做空间报告；清单存在时读取 volume / data，检查卷是否为挂载点、数据目录是否存在、每条链接是否都指向对应目录。只读，不创建任何东西。
- tools/mcfao.py 在参数解析之后、创建输出之前调用 require_mount；doctor/build/verify/export 在有清单时全部受保护。
- tools/desktop_workbench.py 在 start 和 retry 前调用，GUI 里会显示「暂停」错误而不是排队跑一个注定失败的构建。
- 退出码 3 表示因清单声明的卷缺失暂停，和普通的失败 2 区分。分发应用不包含个人挂载清单，改为检查所选卷与悬空链接。
- 回归测试：tests/test_external_storage.py 覆盖未挂载、缺数据目录、链接缺失、链接被普通目录替换，以及清单缺失时不做挂载限制等情形。

## 断盘时的表现与恢复

启用了清单时，断盘会让符号链接变成悬空链接：浏览源码、读文档、运行 Python 单元测试仍然可用，但依赖这些目录的构建会在第一阶段暂停。重新插盘后 macOS 会挂载回原路径，无需重建链接；再跑一次检查命令确认 available: true 即可继续。

需要迁移时，先只读统计并列明源目录、目标目录、空间预算、复制与哈希复核步骤，经用户确认后再操作；保留现有 external-storage.json 与链接直到复制完成并再次确认，不要在断盘状态下删除悬空链接后直接新建目录，那会让本地与外接盘产生两份分叉的证据。

## 隔离授权与日志（2026-11-16）

`tools/run_b0_reference.py::sandbox_policy` 在生成规则时解析全部路径的符号链接。Java Home 和工作目录授权到真实目录，Java 可执行文件与输入 JAR 授权到真实文件；外接盘上的工具链、工作目录及单独链接的依赖均按原有范围授权。目录外读写、网络访问和启动其他程序仍默认拒绝；挂载守卫和 Fabric 转换前的第一方拒绝控制继续强制执行。失败信息同时带上 stderr 末尾，避免界面只显示 `Stage failed`。

桌面任务日志在选取最近六个文件前，通过共享元数据规则排除 `._*`、`.DS_Store`、`__MACOSX` 路径；不删除原日志或元数据文件。

复验记录：`artifacts/evidence/external-sandbox-20261116-075ab1794e86/`。相同工具链通过旧链接路径规则复现退出 71 / `Operation not permitted`；新规则运行原第一方 `SandboxProbe` 返回 `B0_SANDBOX_PASS`，目录外读取、写入和本地连接均被拒绝。额外第一方 Java 程序在真实外接盘工作目录读写成功（`EXTERNAL_STORAGE_PASS`）；未执行第三方 Mod、游戏、模拟器或真机。`result.json` 保存工具链路径与修复源文件摘要，`verify.py` 是本次复验脚本。

自动化回归命令：`python3 -B -m unittest discover -s tests`，本次 410 项全部通过（39.575 秒）。专项覆盖见 `tests/test_b0_preparation.py` 与 `tests/test_desktop_workbench.py`：链接目录、链接 JAR、错误详情、元数据过滤和日志限额。原失败任务的只读日志快照已复核，无 AppleDouble 内容，见证据目录的 `original-job-snapshot.json`。

GUI 调用所选源码目录内的工作台脚本，本次修改主项目即可生效，无需重装桌面壳。修改构建工具后输入指纹会改变；原任务和构建输入保持历史证据，使用「新建构建」重新编译，避免复用旧输入目录导致 `Build inputs changed`。本次控制通过仅解除 Java 启动阻断，不代表整合包的 Fabric 转换、IPA 或游戏验收通过。

## 四类可配置目录（2026-11-16）

设置页可独立选择编译缓存、构建产物根、任务记录和 Rust target；实现为 tools/storage_config.py。默认沿用当前目录与链接，现有 external-storage.json 不做修改。路径配置位于用户 Application Support，保存操作没有数据迁移或清理。旧任务目录保留在 previousJobRoots，旧任务及重试继续可查。环境变量与预算详见 DESKTOP.md。

空间预检会解析目标路径的最近存在父目录，对同一磁盘累计四类预算；断开的符号链接与未挂载的 /Volumes/<卷名> 均拒绝，且不创建替代目录。最低预留分别为 8 / 24 / 4 / 4 GiB，同盘总计 40 GiB。

本轮只读 du 分配占用：

| 既有目录 | KiB | 约 GiB |
| --- | ---: | ---: |
| .cache | 20,303,232 | 19.4 |
| artifacts/mcfao | 64,794,752 | 61.8 |
| artifacts/graphics | 11,546,624 | 11.0 |
| artifacts/desktop-jobs | 28,162,688 | 26.9 |
| desktop/src-tauri/target | 21,373,824 | 20.4 |

统计时外接盘剩余约 538 GiB；这些是现存占用，**不是可删除容量**，其中包含历史证据与任务数据。后续测试和桌面打包会增加新产物。

待用户确认的迁移计划：先确定四个目标目录；重新计算目标盘空间（复制期间须同时容纳旧、新两份数据）；停止相关任务；生成精确文件清单并复制到新目录；复核数量、大小与内容 SHA-256；最后更新配置并验证旧任务查找。原目录、个人挂载清单与五条链接继续保留；删除旧副本或替换链接需要独立确认。本轮未执行迁移、链接替换或清理。
