# AOT Classpath 资源

导出器对有标准资源 API 的方法执行 ASM 数据流分析。支持类字面量、根绝对路径、包相对路径、局部变量、同值分支、`String.concat`、全常量字符串拼接和已知应用 ClassLoader 的枚举。无法确定的值记为 `DYNAMIC_RESOURCE_UNRESOLVED`，自定义 ClassLoader 和一般动态拼接仍需运行证据。

`transform.resourceClosure` 记录 Mod、源归档/嵌套位置、原始路径、引用方法、冲突/缺失/预算状态、最终条目和 SHA-256。新 Classpath 资源限制为每项 1 MiB、每次导出 32 MiB。不同来源产生同名条目时记录冲突。单层合并仍无法重现一般 `getResources` 多 URL 语义。`META-INF/services` 保持导出遍历顺序与文件内声明顺序，按 provider 去重。Minecraft packs 及需真实文件的 Mod 容器路径继续使用各自路径，完整 pack 优先级和 reload 尚未功能复验。

原始日志 `logs/compat-20261121/phase2-fabric` 保留 41 个根 JAR、109 个解析后 Mod 的实跑：Sodium `config-icon.png` 为 1,832 字节，Iris 1.10.9 的 `centerDepth.fsh` 和 `centerDepth.vsh` 为 473 与 149 字节。三者在最终合并 JAR 中重新读取并核对 SHA-256。原始 Iris 字节码见 `iris-center-depth-bytecode.log`。`CenterDepthSampler.<init>` 对两次资源读取立即执行 `requireNonNull`。该结论针对两个具体调用点，后续 shader 初始化仍需要运行验证。

`test_resource_closure.py` 对照分支、拼接、包相对路径、枚举、缺失条目与损坏哈希。清单的 `aotReadable` 仍为 UNVERIFIED，直至取得对应 Native Image 运行证据。

COMPAT-r2 在固定 Fabric resource-loader 版本上执行 `FABRIC_LAYERS`。导出确认 Knot 仍将实际提供者挂入 `BuiltInPackSource` 后，按原 Fabric 排序逻辑从各 Mod 快照根加载 pack。合并后的原版层不再叠放相同的 Mod assets/data。隔离 JVM 实跑读取了 Sodium 的客户端资源及 Biomes O’ Plenty 的服务端数据，字节与各自的导出快照一致。启动中的 pack reload、选用内置包及世界行为尚待目标环境验收。

签名 COMPAT-r2 链接产物包含三项关键资源的完整对应字节，见 `r2-signed-linked-resources.json`。iOS 运行期实读仍待设备执行。

## COMPAT-r3 真机日志回归

COMPAT-r2 真机到达主菜单并开始进入世界，随后 Sodium 的 `ShaderLoader.getShaderSource` 抛出 `Shader not found: /assets/sodium/shaders/blocks/block_layer_opaque.vsh`。文件仍在它的 Fabric pack 层。这个方法根据标识符运行时构造路径，字面量扫描无法发现它。Iris 报错的 `ColorSpaceFragmentConverter.rebuildProgram:73` 则实际读取根目录的 `/colorSpace.csh`，原静态资源规则的后缀列表拒绝了它。

导出为唯一且不与原版重名的 `assets/` 和 `data/` 路径生成 `mcfao/classpath-pack-resources.tsv`。`Class.getResourceAsStream` 读取绝对 pack 路径时可以直接使用各 Mod 层的同一份字节。索引目标和条目数在最终合并 JAR 校验。43 个跨 Mod 同名路径记录在 `packClasspathConflicts`，继续由各自的 Fabric pack 提供。URL、枚举、自定义类加载器和跨来源的动态查找仍需单独验证。字面量规则改用安全路径校验、代码及原生库/归档排除和原有大小预算，覆盖新资源后缀。

在同一台 Mac 用相同输入运行实际 `ShaderLoader`，r2 重现异常，r3 返回字节 SHA-256 `933a0f411018946c411774b536609f13178524dad35701330a32945abf9b49dd`。隔离 JVM 中 Fabric 客户端和服务端 pack 读取也通过。严格模式的 macOS Native Image 探针实际读取地形着色器、Iris 三个内部 shader 及 Sodium 图标并比对 SHA-256。真实整包索引含 8,867 项，增加 1,280,940 字节索引，复用资源原字节。证据在 `logs/compat-r3-20261121`。iOS 游戏内的 shader 编译、渲染和世界重入仍需 r3 真机证据。
