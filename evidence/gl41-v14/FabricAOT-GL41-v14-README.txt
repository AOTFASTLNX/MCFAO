FabricAOT GL41 v14 — 帧时间诊断版（未签名 + 已签名）
Minecraft Java 26.1.2 · GL41 / zink / MoltenVK · iPhone 16 Pro 实测

源提交：bb65fee（诊断计时）+ 509212c/e0cb34f（记录）
CircleCI 任务：119
未签名包：FabricAOT-GL41-v14-unsigned.ipa  466,753,894 字节
  SHA-256 E408DCE1DDFA21D15891602314F5DC47ACF7C0A57D0D986DF707F9A79ED7F9CE
已签名包：FabricAOT-GL41-v14-signed.ipa  483,562,228 字节
  Bundle app.perseus4004.sunset349，版本 7，已通过 USB 安装到手机
  SHA-256 DF79BFAFD6FDD09D4FCC8EF03D8995AD67DEA5835AE1B01864692B1DF46B4AA7

本版与 v13 的性能配置相同（80% 内部渲染、不额外限帧、按游戏内 FPS 设置），
新增每帧分段统计：
  finishP95        渲染提交到同步完成（GPU + 回读）的 95% 分位
  outsideSwapP95   上一帧呈现完成到进入本帧 swap 的 95% 分位
统计只记录，不增加 GPU 等待，也不改变画面元素与樱花背景。

实测（同一存档，地形加载稳定后 80 秒窗口）：
  默认 80% 比例      中位 71.3 FPS，最低 44.2，finishP95 13ms
  50% 比例           中位 65.0 FPS，finishP95 仍 13ms，说明瓶颈不是像素填充
  游戏内 60 FPS 限帧  中位 49.8 FPS，限帧等待本身就在拖慢每一帧
  ZINK_DESCRIPTORS=lazy/db、MVK 异步提交、MPS 深度模板、glthread 全部更慢

因此保留 120 档、80% 比例和现有等待策略。当前渲染上限约 70 FPS，
剩余提升需要把整帧 GPU→CPU 回读换成 Vulkan 交换链直出，属于渲染管线改造。

使用：保持游戏内帧率上限 120，进入世界后正常游玩。
日志中关键行示例：
  [GL41] first render size 2098x965
  [GL41] perf fps=71.2 finish=9.7ms present=1.1ms finishP95=13ms outsideSwapP95=7ms
  [GL41] display fps=71.6 p95=21ms long34=0 drops=0
