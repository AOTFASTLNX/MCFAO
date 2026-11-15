# GL41 真机测试交接 — 2026-11-15

用户已指定自行进行真机测试。Agent 停止真机 UI、游戏与存档操作；以下项目等待用户实测，不授予 FUNCTION_PASS。

## 当前测试包

- 本地路径（相对于集成 worktree）：`artifacts/integration-20261115/output/signed-gl41-03/FabricAOT-GL41-development.ipa`。
- 467,492,792 字节；SHA-256：`7af7550bddb93eebd4e0e7bf6b0e0e378c68f941db54048888b849cbacb14803`。
- Minecraft Java 26.1.2 Vanilla；GL41 / OSMesa-Zink / MoltenVK；iOS ARM64 AOT。不是 Fabric 测试包。
- AOT 与运行时代码来自 `70d5cbe7fee35fa386302721edb5424f75181bce`；本次 Xcode 打包来自 `d1936f873081e299d8ab9e6096aa741806d233f0`，差异为文档和 CI 源文件列表。
- 已使用现有开发签名资源重签、校验、安装，并通过 devicectl 独立启动，无附加调试器。该成功仅证明应用进程启动，尚未确认真实 Minecraft 首帧。
- 新测试 Bundle ID 为 `fab.aot.kexin`，安装前确认该设备没有此标识；未覆盖原有 `org.fabricaot.research.c0.kexin` 应用及其存档。新旧应用可能均显示“FabricAOT World”，请用 Bundle ID 区分。
- 此包描述文件到期：2026-11-20 00:13:37（Asia/Shanghai）。过期后需重新使用有效的本地资源签名。旧 `signed-gl41-02` 描述文件已过期，不再用于本轮测试。

## 测试顺序

1. 在新安装的测试应用中启动游戏，确认真正的 Minecraft 主菜单；保留截图或视频。
2. 新建专用单人测试世界，确认地形、方块、实体与 GUI；不要导入或修改个人原有存档。
3. 测试移动、旋转视角、破坏与放置方块、背包和物品操作、音频。
4. 保存退出，关闭客户端，重新启动并进入同一测试世界，核对之前的修改。
5. 连续运行至少 30 分钟，记录开始/结束时间、崩溃与异常。FPS、帧时间、内存和热状态没有采集时写 NOT MEASURED。
6. 返回设备型号/iOS、以上步骤结果、截图/视频和 `Documents/c0-logs/run-*.log`；崩溃时同时保留系统 `.ips`。文件共享已启用，可从 Finder 的设备文件共享导出测试应用日志。日志分享前去除个人令牌、账户和服务器地址。

Fabric Loader、Fabric API、轻量功能 Mod、Sodium/Sodium Extra/Iris 与完整 Recollection3 仍未获得本轮 GL41 真机验证。Vanilla 通过后才能继续相应验收，不能由本 IPA 推断 Mod 兼容性。
