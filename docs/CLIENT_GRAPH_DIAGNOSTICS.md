# 真实客户端AOT分析诊断

Last reviewed: 2026-11-08。C0 BLOCKED，C1/C2 NOT RUN。本轮没有游戏启动、目标代码生成或手机执行。Mac脚本由助手操作，真机由用户负责。

## 有界对照结果

固定26.1.2客户端SHA256 b1b3158572666445eff01e82fad8c7de2e4953db6d354f311730d77a8359d0b0；同一Java25.0.2、classpath指纹、iOS静态库和CAP数据。四分析线程，墙钟600秒/CPU1800秒，日志16 MiB、单文件64 MiB、FD512，默认拒绝沙盒控制每轮先通过。主机约18 GiB物理内存；堆不超过45%，启动可用比例阈值为6 GiB时35%、8 GiB时45%，磁盘余量至少8 GiB。这是预检和Java堆上限，不是整个进程组RSS硬上限或完整D0认证。

| 轮次 | 构建堆/GC | 墙钟 | GC累计暂停 | Full GC | 最后GC后堆占用 | 结果 |
|---|---|---:|---:|---:|---:|---|
| 09 | 6 GiB / Parallel | 91.0s | 73.33s | 49 | 4.50 GiB | Java heap OOM，退出3 |
| 10 | 8 GiB / Parallel | 127.6s | 110.51s | 50 | 5.78 GiB | Java heap OOM，退出3 |
| 11 | 8 GiB / G1 | 119.4s | 95.04s | 22 | 7.99 GiB | Java heap OOM，退出3 |

以上均未超时或耗尽CPU预算。GC数值来自保留的HotSpot日志，带大小取整；暂停统计仅计算已结束事件，不包含全部并发GC工作。Native Image分析线程为4，构建HotSpot记录的Parallel GC Workers为9；不要把--parallelism误当作全部JVM线程数量。Safepoint采样最大线程数为17/18/18，不是完整线程峰值普查。

Darwin time报告的maximum resident set size分别为4548132864、4599791616、4770480128字节，另有CPU秒494.1/680.4/578.1；这与Java逻辑堆占用是不同指标。本轮不将它推导为iOS内存预算或整个进程树的持续监控。

完整分析统计均未生成，可达类型/方法数量保持UNKNOWN；build-output JSON也不存在，官方文档说明其成功构建生成条件。不能把缺失文件当作零可达对象。诊断target_info显示IOS_AARCH64，但clang版本/架构为空；关闭工具链探测的分析配置不能证明完整交叉编译链成立。

## 元数据与观察影响

各轮metadata-audit.json只读核查25个classpath内META-INF/native-image文件（124655字节）：542条反射声明（336条无条件）、26条JNI声明（1条无条件）、4条资源声明。216个反射批量成员标志是按类型声明的候选，不是成员总数或完整可达性覆盖；没有发现Preserve=all或全资源通配。SDK默认、Feature注册与推导反射尚未穷尽，不能排除元数据带来的闭包膨胀。

第08轮构建JFR自动开启目标JFR，因缺少LibMDependencies.cap提前失败，保留独立证据与当轮源快照。09至11使用GC日志、诊断模式、分析统计选项和外部time；不启用构建JFR，避免这一观察影响。不能伪造空CAP或用macOS库替代iOS库绕过该错误。

原始07未覆盖。09/10命令、classpath、CAP、沙盒策略和源码指纹对照通过；10/11只改变构建GC参数，新增参数分支造成构建器源码SHA不同，差异明确保留。两组主机负载/内存压力不是受控变量，所以不是严密性能基准。

## 复现与证据

使用未存在的新输出目录，顺序运行，不并行争用内存：

```bash
python3 -B tools/probe_client_graph.py --heap-gib 6 --output artifacts/c0/client-graph-new-6g
python3 -B tools/probe_client_graph.py --heap-gib 8 --output artifacts/c0/client-graph-new-8g
python3 -B tools/probe_client_graph.py --heap-gib 8 --builder-gc g1 --output artifacts/c0/client-graph-new-g1
python3 -B tools/compare_client_graph_runs.py --left artifacts/c0/client-graph-new-6g --right artifacts/c0/client-graph-new-8g --output artifacts/c0/heap-comparison-new.json
python3 -B tools/compare_client_graph_runs.py --left artifacts/c0/client-graph-new-8g --right artifacts/c0/client-graph-new-g1 --vary builder-gc --output artifacts/c0/gc-comparison-new.json
```

若主机余量不足，运行器保留BLOCKED并停止于分析前。每轮保存source/、policy.sb、metadata-audit.json、host-memory-before.log、analysis/{command.json,stdout.log,stderr.log}、work/gc.log、work/reports/和result.json。当前对照为artifacts/c0/heap-comparison-verified.json与gc-comparison-verified.json。比较脚本不会提升C0，即使未来分析完成，也必须另证目标对象、链接与真实引导。

当前没有对象直方图或保留链，仍不知道具体内存持有者。下一步先取得这类证据；全客户端Fabric静态转换、反射/资源/JNI闭包和真实iOS引导验收仍未完成。详见[ADR-003](evidence/ADR-003.md)。
