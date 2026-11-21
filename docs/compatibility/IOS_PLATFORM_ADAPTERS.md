# Java 平台适配

| 能力 | 状态 | 证据及边界 |
| --- | --- | --- |
| 地图纹理 PNG 采样 | ADAPTED | 复用 `ios.texture.png-native-image.v1`，JVM 实际对照 RGBA、灰度、灰度 Alpha、调色板、透明及边界像素。损坏流关闭，超尺寸解析拒绝。Xaero 真机功能仍待测。 |
| 桌面图像导出、AWT 绘图和字体 | UNSUPPORTED 或 UNVERIFIED | 分别记录 ImageIO 和绘图 API 调用。匹配到原调用的调用点由预检保留。 |
| 沙盒 Mod 资源目录 | ADAPTED | `ModCatalog` 仅发布完整提取目录。失败回收部分文件、重试重新提取。绝对路径和目录穿越负例通过。 |
| IAS 的真实路径 | UNVERIFIED | `Path.toRealPath` 记录具体调用。没有改变 NOFOLLOW_LINKS 的语义。需要真机容器内复验。 |
| OSHI、桌面剪贴板、文件选择器 | UNSUPPORTED 或 UNVERIFIED | 独立报告调用面，功能和可选性取决于使用路径。 |
| OpenAL EFX 和 JNI | UNVERIFIED | 区分扩展调用、系统库加载及 native 声明。真实对象创建、错误码和清理需要目标环境探针。 |

测试参见 `test_runtime_lowering.py`、`test_mod_catalog.py`、`test_aot_compatibility.py`。默认 GL41 渲染栈沿用原有实现。
