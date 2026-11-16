# B1 · 静态运行期跑通：Bootstrap 完成（2026-11-16）

## 结果

native-image 里**完整跑完了 Minecraft 的注册表初始化**，没有 JIT、没有 ModLauncher、没有模块层：

```
B1 static-runtime bootstrap smoke
seeded FMLPaths at /var/folders/.../b1-game
seeded configs: 630
seeded FMLLoader
[b1] ModList shim knows 400 mod ids
bootstrap ms=1243
blocks=1060
items=1333
entities=130
ok
```

1,060 个方块、1,333 个物品、130 个实体类型全部注册成功，用时 **1,243 ms**。
镜像 206 MB，构建 2 分 27 秒。

## 为了让封闭世界跑起来，一共补了这些环境

| 缺口 | 处理 | 形式 |
|---|---|---|
| `Bootstrap.bootStrap` 里的 ModernFix 钩子扫 jar 清单 | `ManifestCompactor.compactManifests()` 置空 | 类替换 |
| `FMLPaths.GAMEDIR` 为 null（ETF 读配置目录） | 启动前 `FMLPaths.loadAbsolutePaths(tmpGameDir)` | 运行时反射 |
| mod 查询 mod 列表 | `ModList` / `LoadingModList` 最小实现，400 个 mod id 来自 `b1-modids.txt` | 类替换 + 资源 |
| `FMLLoader.loadingModList` 为 null | 反射注入 shim、dist、gamePath | 运行时反射 |
| night-config 找不到 TOML/JSON/YAML 格式 | `FormatDetector` 按扩展名直接返回对应 parser | 类替换 |
| 630 个 mod 配置缺失 | 打包 1 MiB 文本配置，启动时铺到 gameDir | 资源 |
| `ServiceLoader` 什么都看不到 | 236 个 `META-INF/services` + 288 个 provider 反射注册 | 资源 + 反射配置 |
| `CommonHooks.overridesEqualsAndHashCode` 反射 | 3,467 个类的 equals/hashCode 反射注册（扫描图谱生成） | 反射配置 |
| `Class.forName` 找不到 mixin 插件 | 插件类反射注册 + 启动时实例化 | 反射配置 + 运行时 |
| ModernFix 插件构造崩溃 | `ModernFixMixinPlugin` 最小实现（所有选项 false） | 类替换 |
| ModernFix DFU 缓存反射 | `DFUBlaster` 置空 | 类替换 |
| ModernFix 平台钩子 `Class.forName` | 反射注册 `ModernFixPlatformHooksImpl` | 反射配置 |
| 镜像里带进来 5 个运行期代理包 | 构建前删掉 graph 里的 `jdk/proxy*` | 构建脚本 |
| 记录引起的 `getRecordComponents` 崩溃 | 反射配置跳过 record / 引用缺失类的条目 | 生成脚本 |
| `Language.loadFromJson` 没有语言文件 | 打包 `assets/minecraft/lang/en_us.json` | 资源 |

## 工件

| 工件 | 位置 |
|---|---|
| 图谱 v3 | 私有 release `b1-client-graph3`（111,452 类） |
| overrides 层 | 私有 release `b1-overrides`（约 400 KB） |
| CI | `zhangrongxue/mc-aot-ios` 分支 `build/b1-n0`，作业 **#214** |
| 冒烟源码 | `b1/n05/BootstrapSmoke.java` |

## 下一步

注册表能初始化 ⇒ 静态运行期的地基成立。下一关是**客户端入口**：
`net.minecraft.client.main.Main` 需要 GLFW/OpenGL 上下文，CI 的 macOS 虚拟机没有 GPU，
所以这一步要在有显卡的机器上验证（本机 Windows 或真机）。

顺序：

1. 在 Windows 本机用 GraalVM 构建同一份图谱的镜像，跑客户端入口到主菜单；
2. 把渲染接到已有的 GL41 栈（OSMesa → zink → MoltenVK），对齐 A1 线的做法；
3. 再谈 iOS 打包。
