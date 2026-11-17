# B1 · JVM 对照台推进到"资源层"（2026-11-17 傍晚）

## 一句话

用 JVM 跑同一份 `ClientMain` 做快速迭代，已经把 BMC5 推到 **`Minecraft.<init>` 的渲染初始化**；
现在挡住去路的不是代码，而是**资源**：静态运行期只有类，没有 mod 的 `assets/`。

## JVM 对照台的价值

| 方式 | 一次迭代 |
|---|---|
| CI 编镜像再跑 | ~13 分钟 |
| **JVM 直接跑** | **~3 分钟** |

所以每修一个 shim，先在 JVM 上验证，再交给 CI 编镜像。

## 本轮修掉的 9 个缺口

| # | 现象 | 修法 |
|---|---|---|
| 1 | `LoadingModList.getModFileById(...).versionString()` NPE | 新增 `ModFileInfo` 最小实现 + `getModFileById` 返回带版本实例 |
| 2 | `IrisForgeHelpers.getVersion()` NPE | 替换 Iris 平台助手 |
| 3 | `GLFW error before init` | 删除看门线程（它在 MC 初始化 GLFW 前调用 GLFW） |
| 4 | `no OpenGL context current` | `setupMinecraftWindow` 真的创建窗口并 make current |
| 5 | `WGL.wglGetCurrentContext` 不存在 | LWJGL 换回官方 **3.3.3**（4.3.3 删了 sodium 用的方法） |
| 6 | `ImmediatelyFast.config` NPE | 补 config / runtimeConfig 两个最小实现 |
| 7 | `backgroundScanHandler` NPE | 补 `BackgroundScanHandler`（等待回调直接执行） |
| 8 | `ModList.gather(List)` 不存在 | 给 `ModList` 补 `gather` 与 `completableFutureFromExceptionList` |
| 9 | ModernFix 插件 instance 为 null | `ClientMain` 里按清单实例化 mixin 插件 |

## 现在停在哪

```
Minecraft.<init> → GameRenderer.preloadUiShader ✅（blit shader 已能加载）
Minecraft.<init> → Iris setupImages ❌ NPE: inputStream
```

Iris 要读它自己的图片资源，而我们的图谱只有类。**这就是"资源层"问题**。

## 下一步（资源层）

1. 把 mod jar 里的 `assets/**`（或至少 MC + Iris 需要的部分）打进静态运行期的资源根；
2. 资源规模要评估：BMC5 的 jar 里 assets 总量很大，可以按需切片（先只放 shaders/ + iris/）；
3. 资源通了之后，JVM 上应该能到主菜单，再把同一套东西放进镜像。

> 注：本轮结束后已把最新 overrides 与 `ClientMain`（含 mixin 插件实例化）推上去，
> CI 下次编出的镜像会带上这些 shim。
