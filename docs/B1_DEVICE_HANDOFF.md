# B1 真机结果与复现

日期：2026-11-08。**B1 PASS，仅第一方预转换夹具。** Mac脚本由助手执行，真机安装和运行由用户负责。

用户提供build 4两张PASS截图，并确认“一次连了Xcode一次没连”。两次启动分别为14:16:06.231和14:16:40.241，进程ID与日志名不同。原始日志只读采集至 artifacts/evidence/b1-user-device-run-01/，两次均包含：

```text
B0_BEHAVIOR mixed=42 widened=7 parent=1 nested=1
B0_REPLAY_PASS
B1_SEMANTICS_PASS
B1_NATIVE_FINISH create=0 run=0 teardown=0
```

不推断哪张截图对应连接状态；两次均通过，加上用户对独立启动条件的确认，构成B1独立执行证据。打包时创建的device-handoff/result.json保留当时deviceRun=NOT RUN，后续真机结论存独立记录，不改写历史。

## 输入与产物

B0来源 artifacts/b0/run-04/，源快照 artifacts/b0/source-snapshot-04/。真实Knot转换后第一方Target的SHA256为1e65478fcc10c5c8f0bc774fa8d68fcc1b258d8b8e30f1d6fe08e826c2b5b389，B1 input-chain.json确认该字节进入AOT；游戏JAR没有进入AOT classpath。

AOT记录 artifacts/b1/ios-probe-03/；119单元/6个iOS静态库在runtime-ios/；链接后的Framework在ios-framework/。固定源码与A1相同，不声称archive字节相同。iOS运行时采用256 MiB地址预留；没有运行时Java类转换。

可编辑工程为 ios/B1Harness/B1Harness.xcodeproj。App复用研究Bundle ID org.fabricaot.research.a1probe.kexin，build 4名为FabricAOT B1，旧A1 Documents保留。它是测试App，未验证Minecraft世界数据迁移。

签名IPA：artifacts/b1/device-handoff/export/FabricAOT B1.ipa，4787138字节，SHA256 df588c3fd34c67dd1a52857226f3a39f03cf105e5607e827818b91d9c1df31ff。嵌套签名与arm64 iPhoneOS平台核验通过；权限仅标准开发签名。描述文件到期2026-11-15 09:53:47（北京时间），动态有效性以设备和本地描述文件为准。

## 重新构建

先按[B0复现](B0_TEST_HANDOFF.md)生成新的PASS快照，然后：

```bash
python3 -B tools/build_b1_probe.py --b0 artifacts/b0/run-new --output artifacts/b1/probe-new
```

该命令校验B0结果与全部快照指纹，再通过沙盒拒绝控制，最后生成iOS AOT对象。它不会安装或启动手机App。按该次result.json找到work/native-tmp/SVM-*/a1probe.o，交给build_ios_runtime.py和link_a1_ios.py，方法见[BUILDING](BUILDING.md)。链接时--probe指向probe-new。

```bash
xcodebuild -project ios/B1Harness/B1Harness.xcodeproj -scheme B1Harness -configuration Release -destination 'generic/platform=iOS' -derivedDataPath artifacts/b1/xcode-new -archivePath artifacts/b1/handoff-new/B1Harness.xcarchive DEVELOPMENT_TEAM=P57SZ9Z7G2 -allowProvisioningUpdates archive
xcodebuild -exportArchive -archivePath artifacts/b1/handoff-new/B1Harness.xcarchive -exportPath artifacts/b1/handoff-new/export -exportOptionsPlist ios/B1Harness/ExportOptions.plist -allowProvisioningUpdates
```

新Framework目录需用FAOT_FRAMEWORK_DIR覆盖工程默认artifacts/b1/ios-framework；其他开发者使用自己的Team配置。本次已完成真机验证，无需为这两张截图重复测试。

B1不证明任意Fabric Mod、Fabric API、真实Minecraft渲染或世界行为；下一门槛为C0。未测的触摸、音频、持续游玩和性能不由夹具PASS推导。
