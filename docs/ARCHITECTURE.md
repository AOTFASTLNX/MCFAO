# 技术架构与关键事实

## 已确认的基本事实

- Minecraft Java 26.1.2 最低 Java 25；26.1 起游戏发布时不再混淆字节码。
- Fabric Loader 支持编织/转换类，包括 Mixin；常规的运行时加载机制与 AOT 静态闭包存在实质冲突。
- GraalVM Native Image 的 closed-world 假设要求动态类/资源/反射在构建时尽可能可知。仅增加 reflection-config 并不能解决任意 ASM 动态 defineClass。
- Gluon 项目有 iOS Native Image 技术路线，但 **Java 25 + 本项目真实代码 + 当前 iOS 工具链是否可用需要单独实证**。
- Minecraft 桌面 LWJGL/OpenGL 不能假定直接在 iOS Metal 中执行；必须验证具体 GL 特性并实现语义兼容。优先研究有源码、有许可的绑定/渲染技术，不得假称已兼容。

## 已识别但尚未实现的关键约束

- 26.1 需按 **official/unobfuscated** Minecraft 和对应 Fabric Loader 版本处理，不可以默认复用旧 Intermediary/Yarn 的 JAR。Mod 适配须核验 Fabric API 与 Class Tweaker。
- 执行 Mixin 前的加载图解析必须覆盖 `depends/breaks/conflicts/provides`、Entrypoint、Language Adapter、Jar-in-Jar、side stripping 和实际版本选择；正确处理 class initialization build-time vs run-time。
- 需要被完整识别的客户端原生依赖不止 OpenGL：LWJGL/GLFW、OpenAL、STB、JNI、线程、资源/字体/着色器/窗口事件、iOS 应用生命周期。
- 预检只是静态读取；远程 Mod 与真正 Minecraft 客户端获取必须单独有安全下载+哈希核验服务，第三方构建代码必须先在隔离环境处理。
- AOT 后含 Minecraft 代码的 IPA 不得公开再分发；无 Apple Developer Program 的签名/安装必须按 7 天有效期实证。
- 参考 `TECHNICAL_GATES.md`、`SECURITY_AND_DISTRIBUTION.md`、`REVIEW_REPORT.md`，以逐步 Gate 判断是否真实可行。

## 建议流水线

```
.mrpack / Prism Instance
   -> manifest verification + secure asset acquisition
   -> dependency resolution + license-aware local assets
   -> verified Fabric dependency graph + isolated deterministic Mixin / Class Tweaker transformation
   -> AOT reachability / resource / reflection metadata
   -> Java25-compatible native image (iOS arm64)
   -> Cocoa / Swift + Java native interop + LWJGL/GLFW/OpenAL compatibility + Metal graphics bridge
   -> Xcode codesign + IPA
   -> physical iPhone smoke / perf / longevity tests
```

## 必须产生的 ADR

- `ADR-001` Java25 iOS AOT 实际工具链版本、补丁、复现过程（包括失败日志）。
- `ADR-002` 构建期 Fabric Loader / Mixin 的设计与可支持范围，单独明确 Mixin 在加载期修改目标类的语义。
- `ADR-003` Minecraft 26.1.2 LWJGL/OpenGL 适配路线、Metal 渲染方案和测试用例。
- `ADR-004` Microsoft / Minecraft 合法授权流程，资产来源与分发隔离。
- `ADR-005` 用户本地 IPA 签名、free provisioning、bundleID 与更新/存档保留行为。
- `ADR-006` 性能调优方法：baseline vs 优化后数据、设备配置与功耗限制。

## 风险登记（重要）

- **R1 工具链不兼容：** GraalVM 25 社区版 Native Image ≠ 完成 iOS cross compile。需先完成 iPhone 真机 AOT smoke test。
- **R2 类转换：** Mixin 的装配时机与 AOT 需要的静态化可能冲突；构建期转换可能影响 Mod 副作用与初始化顺序。
- **R3 图形：** OpenGL context、着色器、驱动相关行为与 iOS Metal 不等价。
- **R4 许可证：** 不得把 Minecraft 专有 JAR 或未经授权资源上传到公开仓库/发布包。
- **R5 运行时内存：** 高分辨率纹理、Java 堆/Native Image 内存行为、iOS Jetsam，均须在真机测试。

## 参考资料

- https://www.minecraft.net/en-us/article/minecraft-java-edition-26-1
- https://www.minecraft.net/en-us/article/removing-obfuscation-in-java-edition
- https://docs.fabricmc.net/develop/loader/
- https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- https://docs.gluonhq.com/
- https://www.minecraft.net/en-us/usage-guidelines
