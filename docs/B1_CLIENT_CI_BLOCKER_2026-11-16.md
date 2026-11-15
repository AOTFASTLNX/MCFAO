# B1 · 客户端图谱：CI 环境的硬限制（2026-11-16 凌晨）

## 1. 客户端启动链路已经打通

`launch_client.py` 这一轮把 NeoForge **客户端**的启动链路全部拼对了：

| 问题 | 修法 | 结果 |
|---|---|---|
| 客户端没有 `run.sh` | 从 `versions/<id>/<id>.json` 展开 `arguments.jvm/game` | ✅ |
| json 是 `inheritsFrom: 1.21.1` | 合并父版本 json，缺则从 Mojang manifest 下载 | ✅ jvm 24 / game 45 |
| 51 个库不存在 | 按 json 里的 artifact URL 下载 | ✅ downloaded 51, failed 0 |
| `Duplicate key` 崩溃 | classpath 去重（gson 在父子 json 里各出现一次） | ✅ |
| `Invalid window size -1x-1` | 宽高默认 1280×720 | ✅ |

## 2. 真正的阻塞：CircleCI 的 macOS runner 没有 OpenGL

```
[EARLYDISPLAY]: Trying GL version 4.6 … 3.2
[EARLYDISPLAY]: Failed to find any valid GLFW profile.
  GLFW error: [0x10009] NSGL: Failed to find a suitable pixel format
Failed to initialize the mod loading system and display.
```

runner 是虚拟机，没有可用的 NSGL 像素格式——Minecraft 客户端在它上面**根本起不来**。
这跟参数无关，是硬件/会话限制。所以「在 CI 上跑客户端来 dump 客户端类」这条路走不通。

## 3. 三条可行路径

| 路径 | 做法 | 成本 | 风险 |
|---|---|---|---|
| **A. 本地跑 client dump** | 在你自己的 PC（有 GPU）上用 PCL 的 BMC5 实例启动，JVM 参数挂 agent，dump 完把目录打包 | 几分钟手工 + 一次上传 | 低；需要你配合点一下 |
| **B. 带 GPU 的 macOS runner** | CircleCI 的 GPU 机型（付费） | 钱 | 中 |
| **C. 无窗口的客户端图谱** | 跳过 early display 与 GLFW，直接让 FML 加载 client 模块并强制定义 | 1–2 天开发 | 中高；FML 的启动顺序依赖显示初始化 |

**建议 A**：本地客户端本来就要跑（整合包在 PCL 里），只需把它跑一次并挂上 agent。

## 4. 本地路径的具体操作（准备中）

1. 我编译 `dumpagent.jar`（JDK 17 目标，可被 Java 21 加载）并生成 `jars.txt`（实例 `libraries` 下所有 jar）
2. PCL → 版本设置 → 高级 → JVM 参数追加：
   `-javaagent:<路径>\dumpagent.jar=<dump目录>|<jars.txt>|120000`
3. 启动 BMC5，等 2 分钟后关闭；`<dump目录>` 里就是完整的客户端类图谱
4. 打包该目录（zip），我接着做 native-image 冒烟

这样得到的图谱和 B0 的服务端图谱同源（同一套 FML 转换），可以直接对接 A1 的 AOT 工具链。
