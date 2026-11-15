# FabricAOT A1 · 重发布（无游戏本体）

版本：**A1 / Minecraft Java 26.1.2 / GL41 v14**
发布日期：2026-11-16
发布类型：**无游戏本体重打包**（slim）

## 与上一版 A1 的差异

| 项 | 上一版 | 本版 |
|---|---|---|
| 文件 | `FabricAOT-A1-MC26.1.2-v14-unsigned.ipa` | `FabricAOT-A1-MC26.1.2-v14-nogame-unsigned.ipa` |
| 大小 | 466,753,894 字节 | **91,446,850 字节** |
| SHA-256 | `e408dce1…ed7f9ce` | `024f40d4a6cd79cbf3039f5f1518568489be941b05e58ca83a6568943b24e0b4` |
| 游戏资源 | 打包在 `Payload/C0Harness.app/assets`（5,012 个文件 / 439 MiB 未压缩） | **已移除** |

**功能代码完全未改动**：启动器、AOT 客户端（`Frameworks/client-graph.dylib`）、GL41 渲染栈
（`libOSMesa` / `libMoltenVK` / `libglfw` / `liblwjgl` / `libopenal`）、着色器索引都在。

## 为什么移除

按 `docs/SECURITY_AND_DISTRIBUTION.md`：Minecraft 客户端与授权资源不得进入公开分发包。
本版只带我们自己构建的可执行文件，资源由使用者从自己合法拥有的客户端导入。

## 使用前必须做的一步

应用在启动时按以下顺序找资源（见 `ios/C0Harness/main.m`）：

1. App 包内 `assets/`（本版没有）
2. **应用沙盒 `Documents/assets/`** ← 本版走这条

所以安装后需要把 1.21.2 的资源放到应用的 `Documents/assets/`，结构为：

```
Documents/assets/
├── indexes/30.json
└── objects/…（按 30.json 的哈希分目录）
```

可以用「文件」App 的“我的 iPhone → FabricAOT → assets”，或用 `pymobiledevice3` 的
house_arrest 推入。**没有资源时客户端会在进入世界前报资源缺失，这是预期行为，不是包损坏。**

## 除资源外的完整性

| 检查 | 结果 |
|---|---|
| zip 完整性 | 通过（77 个条目） |
| `Frameworks/client-graph.dylib` | 存在（AOT 客户端） |
| `assets/` 条目 | 0（预期） |
| 与 v14 相同源码 | `bb65fee` + 记录 `509212c` / `e0cb34f` |
| 原构建作业 | CircleCI 119（2026-11-14 20:47→21:04） |

## 已知局限（与上一版一致）

- 帧率在 46–86 之间浮动（120 Hz 目标不可达，限速器未生效）
- 每帧成本集中在 zink 命令提交（约 10.7 ms），GPU 计算占比极小
- 进世界第一分钟有 100–250 ms 长帧（区块上传）

## 文件

| 文件 | SHA-256 |
|---|---|
| `FabricAOT-A1-MC26.1.2-v14-nogame-unsigned.ipa` | `024f40d4a6cd79cbf3039f5f1518568489be941b05e58ca83a6568943b24e0b4` |
| `FabricAOT-A1-MC26.1.2-v14-unsigned.ipa`（含资源，仅供本地自用） | `e408dce1ddfa21d15891602314f5dc47acf7c0a57d0d986df707f9a79ed7f9ce` |
