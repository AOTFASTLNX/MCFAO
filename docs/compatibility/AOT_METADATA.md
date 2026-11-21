# AOT 动态元数据

最终类路径扫描直接识别 Gson 和 Jankson 的已知 `fromJson` 签名接收本地 Class 字面量的场景，并复用原有配置类型闭包。现有字段传递、配置构建器、Mixin 及人工根继续进入同一合并流程。统一格式中的条目按类型和条件合并，方法按名称、参数列表和条件识别。成员校验遵守最终类路径的顺序及 Java 25 multi-release 规则。报告标明维护项、静态推断及 Tracing Agent 的来源，发现签名不匹配时保留诊断。

`./mcfao build --exact-reachability-metadata …` 启用 GraalVM 诊断模式，并纳入 AOT 缓存指纹。测试运行镜像可使用 `-XX:MissingRegistrationReportingMode=Exit`。最终扫描标记 `<clinit>` 的文件、资源、注册表与 native 加载等直接副作用。现有运行期初始化策略不因标记而变更。调用链深处的副作用仍需运行证据。

`ResourceMetadataProbe` 在 Java 25 和 macOS Native Image 中使用实际 Gson 和扫描器生成的配置，验证默认配置、继承字段、EnumMap、保存重读和损坏 JSON。读取来自实际合并 JAR 的三个资源并核对哈希。日志在 `logs/compat-20261121/native-mechanism`。构建约 31.7 秒，峰值 RSS 1.27 GB。执行输出 `RESOURCE_METADATA_RUNTIME_PASS`。这组证据覆盖 macOS 的机制夹具。FancyMenu 的反射分配、Jankson 功能往返、Java 对象序列化、任意代理、Android/桌面 JNI 实现和 iOS 行为继续等待运行验证。

COMPAT-r2 真机日志中的 FancyMenu `MusicTrackInfo` 有公开无参构造器，但出货反射配置中缺少该类。字节码显示 Gson 收到的是私有静态 final `Type` 字段，值来自 `TypeToken<List<MusicTrackInfo>>`。COMPAT-r3 的扫描追踪 Gson 实际消费的内联 token 或同类不可变字段，解析 token 泛型签名并注册具体 DTO。动态字段和未消费的 token 不加入闭包。真实 r3 反射配置已含该类的构造器及字段。第一方无无参构造器 DTO 经相同扫描自动生成 `unsafeAllocated`，真实 Gson 在 JVM 和严格模式的 macOS Native Image 中通过泛型列表往返。日志见 `logs/compat-r3-20261121/probe-native-run.log`，FancyMenu 游戏内音乐列表仍需目标设备复验。
