# 外接盘与本地构建守卫

> 2026-11-15：为释放内置盘空间，仓库里体积大、可由本地重建或保留为历史证据的目录已移到外接盘 /Volumes/K/MCFAO-data/，原位置改为符号链接。主仓库仍在 /Users/kexin/Documents/ChatGPT/MCFAO，git、worktree、Codex 项目登记都不变。

## 硬性要求

执行任何本地构建（mcfao doctor/build/export、desktop 工作台的启动/重试、Tauri 桌面应用构建）前，必须先接上并挂载卷标为 K 的外接盘。没有挂载时，构建命令会暂停并报错，不会创建输出目录、不会跑 AOT、不会把文件写回内置盘。

```bash
python3 -B tools/external_storage.py --json
```

返回 available: true 才能构建。返回 volume-not-mounted 时请插入硬盘；返回 data-directory-missing 或 missing-links 时先按下面的映射表修复，不要绕过守卫。

## 目录映射

映射清单见仓库根的 external-storage.json。

| 项目内路径（符号链接） | 外接盘实际路径 | 内容 |
| --- | --- | --- |
| artifacts/mcfao | MCFAO-data/artifacts/mcfao | 历轮 AOT 构建、整合包、签名产物与逐阶段日志（Gate 证据） |
| artifacts/graphics | MCFAO-data/artifacts/graphics | 图形/音频/着色器输入、模拟器世界与世界设备包 |
| artifacts/desktop-jobs | MCFAO-data/artifacts/desktop-jobs | 桌面工作台任务、Xcode DerivedData |
| desktop/src-tauri/target | MCFAO-data/desktop/src-tauri/target | Rust 构建缓存，可重建 |
| .cache | MCFAO-data/cache | GraalVM/JDK、upstream 源码、GLFW/LWJGL/Apple Metal 缓存，可重建 |

artifacts/desktop 内是已跟踪的界面截图证据，保持在主仓库不动。外接盘是 ExFAT：权限位和扩展属性不保真，复制时用 rsync -rlpt 并清理 ._* 伴生文件；符号链接虽然能创建，但只让主仓库这一侧持有链接。

## 守卫实现

- tools/external_storage.py 检查 /Volumes/K 是否为挂载点、MCFAO-data 是否存在、五条链接是否都指向外接盘对应目录；只读，不创建任何东西。
- tools/mcfao.py 在参数解析之后、创建输出之前调用 require_mount；doctor/build/verify/export 全部受保护。
- tools/desktop_workbench.py 在 start 和 retry 前调用，GUI 里会显示「暂停」错误而不是排队跑一个注定失败的构建。
- 退出码 3 表示因外接盘缺失暂停，和普通的失败 2 区分。CI 在独立克隆里构建，不使用本机外接盘，也不受此守卫影响。
- 回归测试：tests/test_external_storage.py 覆盖未挂载、缺数据目录、链接缺失和链接被普通目录替换等情形。

## 断盘时的表现与恢复

符号链接会变成悬空链接：浏览源码、读文档、运行 Python 单元测试仍然可用，但依赖这些目录的构建会在第一阶段暂停。重新插盘后 macOS 会挂载到 /Volumes/K，无需重建链接；再跑一次检查命令确认 available: true 即可继续。

需要把目录搬回内置盘时，先停用守卫路径或调整 external-storage.json，用 rsync -rlpt 反向复制并逐项校验后再替换链接；不要在断盘状态下删除悬空链接后直接新建目录，那会让本地与外接盘产生两份分叉的证据。
