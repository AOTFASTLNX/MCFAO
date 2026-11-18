# NCL Builder IPA 构建工作台（实验版）

中文本地图形工具：选择游戏内容 → 构建环境 → 开发签名 → 构建 IPA。包含真实后台任务、阶段日志、取消、失败重试、任务恢复、IPA 校验和 Finder 定位。界面提供跟随系统、浅色和深色三种外观，选择保存在本机，并同步 macOS 窗口标题栏。

视觉体系采用 System Neutral：中性系统表面、macOS 原生强调色、独立的成功 / 警告 / 错误状态色。设置页可跟随系统强调色，或固定一个可读的交互色；状态色不会随强调色变化。日志使用等宽字体并按 INFO / WARN / ERROR 着色，同时保留文字标签。

## 启动

在 desktop 目录执行 npm ci，然后 npm run tauri dev。浏览器预览使用 npm run dev，地址 http://127.0.0.1:1420；预览可以导入报告、查看界面和配置表单，真实构建必须在桌面应用执行。

桌面开发需要 Node.js 22.12+、Rust / Tauri 开发依赖。完整 IPA 构建另需 macOS Apple Silicon、ARM64 Python 3.11+、Xcode、现有 AOT 前置配置和本机开发签名。详细输入准备见 docs/BUILDING.md。

来源卡片可勾选「强制编译（忽略 Loader 版本差异）」，使用内置 Loader 0.19.3 尝试构建；来源与实际版本保留在任务中。详细边界见 docs/DESKTOP.md。

## 本地打包

在 desktop 执行 npm run build:mac。脚本会先检查所选目录的剩余空间，再用 Xcode actool 把仓库根目录的 NCB.icon 编译为 Assets.car 与 NCB.icns，保留浅色、深色与透明图层；随后运行 Tauri 开发包构建，把这两个资源放入 Contents/Resources，并让 CFBundleIconFile 与 CFBundleIconName 指向 NCB。最终在所选产物根的 desktop/ncl-builder-<version>/ 生成经临时签名与严格验签的 NCL Builder.app 及同名 zip；已有同名交付时使用新的目录后缀。工作台附带受控源码树，分发应用默认使用包内源码，不包含游戏文件；首次准备与外部客户端输入见 docs/DESKTOP.md 和 docs/BUILDING.md。正式分发签名和公证尚未验收。

当前版本 0.2.7，界面、npm、Cargo 和 Tauri 版本号一致。交付位于 artifacts/desktop/ncl-builder-0.2.7/，保留旧版本目录；沿用已有配置迁移，并使用主项目已修复的沙盒路径解析和日志元数据过滤。

## 使用

- 选择 .mrpack 或 Prism 实例，或选择原版 26.1.2；选中后自动执行来源检查。Fabric 固定 Loader 0.19.3。整合包选择不跨页面或重启记忆，每次进入构建页都重新选择。
- 自动识别本机配置，或在高级资源配置中选择路径并保存。新机器需先准备 CLI 所需的合法游戏资源与原生输入。
- 使用 Xcode 已准备的证书和描述文件，Team ID 可留空。Fabric 来源的构建期转换在项目沙盒中执行，不再要求单独确认代码审计；选中整合包后直接构建 IPA。
- 构建记录显示持久任务与日志；可取消和重试。关闭应用不结束后台任务。
- 已有构建可从 result.json 所在目录直接重新导出 IPA。

来源的静态检查不证明 Mod 真机兼容。IPA 成功表示构建、签名和内容校验通过，真机安装、游玩及存档仍按独立验收标准验证。当前不自动操作任何设备。

## 外观与日志

- 外观默认跟随系统；设置页可固定浅色或深色，并切换交互强调色。
- 强调色默认读取 macOS 系统设置；浅色模式会自动调整填充色的明度，保证按钮文字可读。
- 状态色固定表示成功、警告和错误。构建日志使用等宽字体，并同时用文字标签与颜色区分等级。
- 动画由统一的 Motion System 管理：时长、缓动、位移与 Reduced Motion 共用同一组令牌；步骤、页面和侧边栏的选中层是单一测量图层。实现与覆盖清单见 [docs/DESKTOP_MOTION.md](../docs/DESKTOP_MOTION.md)。

## 磁盘空间

侧边栏「存储管理」集中展示各磁盘容量条、四类目录的占用分布、最大目录明细与 Finder 定位，并提供存储位置配置。清理默认不勾选，展开路径明细并选择后再二次确认；清理后重新扫描。旧构建与中间阶段分组互斥，保留交付产物、构建记录与顶层日志，运行任务期间禁用清理。自定义目录提供只读统计和 Finder 管理。

## 测试

- npm test
- npm run test:e2e
- npm run build
- cargo test --manifest-path src-tauri/Cargo.toml --lib
- CARGO_TARGET_DIR=/tmp/ncl-clippy-target cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings（外接盘目标目录可能带 `._` 元数据，改用本机临时目录）
- 仓库根执行 python3 -m unittest discover -s tests -p 'test_desktop_workbench.py'

## 实现

- src/App.tsx：Fabric 五步 / 原版四步的构建、环境、签名、任务和设置界面。
- src/system-neutral.css：System Neutral 语义令牌、控件、页面与响应式规则。
- src/theme.ts：外观与系统强调色偏好、可读性映射和原生窗口同步。
- src/LogView.tsx、src/log.ts：构建日志的等宽呈现与 INFO / WARN / ERROR 语义分级。
- src/motion.ts、src/MotionPrimitives.tsx：全局动画令牌、共享选中层、步骤过渡、数字与状态标记。
- src/workflow.ts：构建输入、持久化和前置约束。
- src/model.ts：静态报告校验与旧记录迁移。
- src-tauri/src/lib.rs：固定第一方操作桥接，ARM64 服务启动。
- ../tools/desktop_workbench.py：受控下载、暂存、持久任务、CLI 调度与恢复。
- scripts/package-macos.mjs：本地开发应用签名打包。

边界、详细验证与证据见 docs/DESKTOP.md。界面使用原创 SVG 插画；不是游戏截图。
