# P0 Metal 图形内存持续增长修复（2026-11-14）

## 证据与根因

真机 Apple A20 Pro GPU 的三份日志（`~/Downloads/run-1794621137926.log`、
`run-1794621651389.log`、`run-1794622357714.log`）显示 `metal-HUD` 的图形内存
在 95–176 秒内从约 232–302 MB 单调增长到 1711–1850 MB，随后
`cloneBuffer` 或 `bindTexelBuffer` 中的 `newBufferWithLength` 返回 nil。
`[MetalPerf]` 同时给出每 300 帧约 8.6–16.1 次 `buffer_snapshots` 与
1.00 次 `texel_shared`，说明每帧都在新建 Metal 缓冲区。

根因是**每帧瞬态 Metal 对象没有明确的释放时点，也没有并发上限**：

- `ios/metal-bridge/metal_bridge.m` 的 `bindTexelBuffer` 每次绑定都
  `newBufferWithLength` 创建 staging `MTLBuffer`，再
  `newTextureWithDescriptor:offset:bytesPerRow:` 创建共享存储的
  `MTLTexture` 视图。两者只在 `@autoreleasepool` 和命令缓冲区的隐式资源
  表里持有；JNI 返回后没有任何强引用，也没有 GPU 完成后的显式回收。
- `cloneBuffer`（由 `MetalCommandEncoder.prepareCpuWrite` 每次 CPU 写调用）
  每帧新建快照 `MTLBuffer`，Java 侧 `MetalNative.release(previous)` 立即
  `__bridge_transfer` 丢弃旧 handle，同样没有等待 GPU 完成。
- `writeTexture` / `readTexture` / `fan` 的 staging 也是同类模式。
- `commands(ctx)` 把 `ctx` 强捕获进命令缓冲区的 completion handler，而
  `ctx` 又强持有 `pending` 命令缓冲区，形成编译器用
  `-Warc-retain-cycles` 报出的循环引用（本次编译前确实报错）。

这些对象被未完成命令缓冲区及其回调图隐式保留，在 iOS 上随帧数累积；
`MTLCommandQueue` 文档说明普通 `commandBuffer` 会强引用其执行所需资源。
`resourceBudgetMiB=1024` 只约束 Java 侧逻辑字节，管不到这些没有 Java owner
的原生分配，所以调大它或 Java 堆都无法解决。

## 完整持有与释放链（修复前）

```
Java GpuBuffer / RenderPass.prepare
  -> MetalNative.cloneBuffer / bindTexelBuffer
  -> [MTLDevice newBufferWithLength] (+1, __bridge_retained 或 autorelease)
  -> [renderEncoder setVertexBuffer/setFragmentTexture] (命令缓冲区隐式持有)
  -> [commandBuffer commit]
  -> GPU 执行中：命令缓冲区/回调图持有对象，回收时点不可观测
  -> JNI 返回，@autoreleasepool 排空 / Java release 丢弃 handle
  -> completion handler 释放命令缓冲区
  -> 资源最终才可能释放；累计在途帧数不受约束，真机上表现为单调增长
```

## 修复

新增 `ios/metal-bridge/metal_resources.{h,m}`：`FAOTResourceTracker`。

1. **显式 GPU 完成后回收**：`deferUntilCompleted:` 把对象的唯一 owning
   reference 放进对应命令缓冲区的 completion handler，GPU 完成时置空。
   `recycleTransientBuffer:` 在完成时把共享缓冲区放回池，
   `recycleOwnedBuffer:` 处理 Java 已释放的快照 handle。
   不提前释放仍在 GPU 使用的资源，不引入每帧同步等待。
2. **有界瞬态池**：`acquireTransientBufferOfLength:` 优先复用池中同长度
   缓冲区；池上限 64 项，总瞬态字节上限 64 MiB。超限时只做一次有上限的
   dispatch group 等待，仍超限则明确失败并打印内存快照，不无限重试。
3. **修复循环引用**：`commands(ctx)` 的 completion handler 改用
   `__weak FAOTMetalContext`。
4. **统一提交入口**：`commit(ctx, cb)` 记录 in-flight 数量并每 5 秒输出
   一次 `[MetalMemory]` 摘要。
5. **Java handle 单点释放**：`keepTracked` 记录 handle 的字节数与类别；
   `MetalNative.release` 是唯一 `__bridge_transfer` 点。快照 handle 的
   +1 retain 被转移到完成回调，再回池，不会 use-after-free。

## 可复核统计

`[MetalMemory]` 每 5 秒输出一次（低频）：`live_bytes`、`peak_live_bytes`、
`device_bytes`（`MTLDevice.currentAllocatedSize`）、`in_flight`、
`peak_in_flight`、`alloc_failures`，以及 snapshot / texel_buffer /
texel_view / texture / buffer / staging / pool 各自的
`alloc_count` / `alloc_bytes` / `free_count` / `free_bytes` /
`live_bytes`，还有 `pool_entries` / `pool_bytes` / `transient_budget_bytes`。
分配失败时 `[MetalAllocFailure]` 立即打印 `category`、`requested_bytes`
和完整内存快照。统计只保存 NSUInteger 计数，不额外持有 Metal 对象；
唯一的 Metal 容器是那 64 项有界池。

修复前后趋势可用同一方法比较：读日志中 `metal-HUD` 的图形内存列，或读
`[MetalMemory] device_bytes` / `live_bytes`。真机复测前不得把主机夹具当作
真机结论。

## 验证

- `tests/metal_resource_lifetime_test.m`：1200 帧真实命令缓冲区 + 真实
  Metal 分配，断言 `device_bytes` 与 `peak_live` 在预热后稳定、
  `in_flight<=2`、分配失败为 0。ASan/UBSan 通过。
- `tests/test_metal_resource_lifetime.py`：6 项源码/构建契约。
- `tools/build_metal_backend.py --test-host` 新增编译 `metal_resources.m`
  并运行生命周期夹具。
- 全量 `python3 -B -m unittest discover -s tests -p 'test_*.py'`：
  312 项通过（5 项按环境跳过）。
- `arm64-apple-ios17.0` 与 macOS 双 SDK、`-Wall -Wextra -Werror` 编译通过；
  `build_metal_backend.py --sdk iphoneos --test-host` 的 javac / native /
  metal / metallib / 生命周期夹具全部 exit 0。

未完成：真机 5/5/5/10 分钟矩阵、主菜单/暂停/移动场景、修复前后真机
`[MetalMemory]` 对比。Gate E 仍为 BLOCKED。
