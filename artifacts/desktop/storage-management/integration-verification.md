# 存储管理集成验证（2026-11-17）

入口为侧边栏「存储管理」及设置页「本地记录」上方的「储存目录」。包含分类/磁盘图形统计、目录明细、快速选总目录、迁移/删除/保留策略及恢复默认目录。

验证在独立工作区进行，依赖现有 node_modules、B0 本地参考输入与已生成的 NCB 图标资源；未把这些本地依赖、游戏文件、App 或 ZIP 加入提交。

- `npm run build`：通过。
- `npm test`：72 项通过。
- `npm run test:e2e`：52 项通过，包含目录重置、确认/取消、处理策略与现有导航布局。
- `MCFAO_STORAGE_CONFIG=<临时设置文件> python3 -B -m unittest discover -s tests -p 'test_*.py'`：530 项，6 项跳过，其余通过。隔离工作区没有完整的本机研发产物。
- `CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=<现有缓存> cargo test --manifest-path desktop/src-tauri/Cargo.toml --lib`：11 项通过。
- `git diff --check`：通过。

迁移与删除仅在临时夹具验证，浏览器中的原生文件选择使用模拟 IPC；未实际迁移或删除用户文件，不改变 Minecraft/设备 Gate。目录重置只更新配置，保留旧文件和历史任务发现路径。
