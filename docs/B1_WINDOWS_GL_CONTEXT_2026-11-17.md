# B1 · Windows：把崩溃缩小到 GL 上下文，尝试三条修复路径（2026-11-17 下午）

## 分段结论（未变）

| stage | 结果 |
|---|---|
| `bootstrap` | ✅ 1.6 s，1,060 方块 |
| `glfw` | ✅ `glfwInit=true`、窗口句柄有效 → ❌ `glfwMakeContextCurrent` 或其后第一个 GL 调用 segfault |
| 完整客户端 | ❌ `Main.main` 后静默退出（同一处） |

## 本轮三个尝试

| 尝试 | 目的 | 结果 |
|---|---|---|
| 给探针加 3.2 core / forward-compat hints | 复现 MC 真实上下文配置 | 仍在同一处 segfault |
| `--initialize-at-run-time=org.lwjgl` | 排除 LWJGL 静态字段被烘进镜像堆 | 无变化 |
| 用 native-image agent 采集 JNI/反射配置 | LWJGL 的原生方法可能需要显式 JNI 注册 | 采集未完成：agent 只在 JVM 正常退出时落盘，客户端被强杀导致只留下 `.lock` |

## 现在的判断

崩溃点在 **GL 上下文绑定之后的第一次 GL 调用**，属于 native-image 与 LWJGL 原生绑定的交界处，可能原因按概率排序：

1. **JNI 注册缺失**：LWJGL 的 `glfw*`/`gl*` 原生方法在镜像里没有走正常的 `RegisterNatives`，调用落到错误桩上；
2. **GL 函数解析路径**：`GL.create()` 的 FunctionProvider 在镜像里取到空指针后直接调用；
3. **上下文/驱动交互**：真实 GPU 驱动在镜像进程里初始化方式不同。

## 下一步（按成本排序）

1. **把 agent 跑完**：让客户端完整进主菜单后正常退出（或用 `jcmd` 触发 VM 退出），拿到 `jni-config.json` / `reflect-config.json`，加进构建；
2. 或用 `-H:+JNI` 相关选项 / `-H:JNIConfigurationFiles` 显式注册 `org.lwjgl.glfw.GLFW` 与 `org.lwjgl.opengl.GL` 的原生方法；
3. procdump + 符号化，确认具体 DLL 与偏移（image 未带 PDB，可加 `-g` 重新构建）。

## 工程资产（本轮产出）

| 资产 | 位置 |
|---|---|
| GitHub Actions 工作流（Windows，13 分钟出包） | `.github/workflows/b1-client-windows.yml` |
| 分阶段入口（`B1_STAGE=bootstrap|glfw`） | `b1/n05/ClientMain.java` |
| LWJGL 3.4.3 覆盖 + Windows natives 提取 | 同上工作流内 |
| 分段定位记录 | 本文件 |
