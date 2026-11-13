# 内容模组样本包

Last reviewed: 2026-11-13

目标：Minecraft 26.1.2 / Java 25 / Fabric Loader 0.19.3。仅本地研发输入，未认证 AOT 或真机玩法兼容。

[下载清单包](../artifacts/mcfao/content-samples-01/FabricAOT-Content-Samples-26.1.2.mrpack) · [版本与许可锁](../artifacts/mcfao/content-samples-01/pack-lock.json) · [本地说明](../artifacts/mcfao/content-samples-01/README.md)

| 模组 | 版本 | 官方发行页 |
|---|---|---|
| Tech Reborn | 6.0.5 | [来源](https://modrinth.com/mod/techreborn/version/odOcmoOg) |
| BetterEnd | 26.101.5 | [来源](https://modrinth.com/mod/betterend/version/Y493JLy6) |
| BetterNether | 26.101.5 | [来源](https://modrinth.com/mod/betternether/version/7CEc5wqL) |
| Biomes O' Plenty | 26.1.2.0.22 | [来源](https://modrinth.com/mod/biomes-o-plenty/version/8MVwdPgG) |
| YUNG's Better Dungeons | 26.1.2-Fabric-6.1.1 | [来源](https://modrinth.com/mod/yungs-better-dungeons/version/ZAy29qXU) |
| GlitchCore | 26.1.2.0.2 | [来源](https://modrinth.com/mod/glitchcore/version/WNtSATXw) |
| TerraBlender | 26.1.2.0.3 | [来源](https://modrinth.com/mod/terrablender/version/NIXt6lha) |
| Fabric API | 0.155.3+26.1.2 | [来源](https://modrinth.com/mod/fabric-api/version/3dM0X6ou) |
| BCLib | 26.101.5 | [来源](https://modrinth.com/mod/bclib/version/L2Um1lwa) |
| World Weaver | 26.101.5 | [来源](https://modrinth.com/mod/worldweaver/version/WKBeK6NA) |
| Cloth Config API | 26.1.154+fabric | [来源](https://modrinth.com/mod/cloth-config/version/GFM8zh9J) |
| YUNG's API | 26.1.2-Fabric-6.1.3 | [来源](https://modrinth.com/mod/yungs-api/version/lmLenYfY) |

12 个根 JAR、80 个嵌套 JAR；官方 SHA-1/SHA-512 校验通过。mrpack 只包含下载链接和哈希，不内嵌第三方游戏文件。metadata/ 留存 Modrinth API 响应。

`content-samples-preflight-01` 发现发布平台遗漏 GlitchCore 和 TerraBlender 依赖；补齐后 `content-samples-preflight-02` 真实 Fabric Loader 图解析为 RESOLVED（89 个选中 ID），元数据预检为 NO_METADATA_BLOCKERS。mrpack 静态预检 fatal=false。

未加入 AE2：官方 API 的 26.1.2 记录为 NeoForge，没有 Fabric 发行版。Create Fabric、Cobblemon、Ad Astra、Spectrum 没有匹配的 26.1.2 Fabric 发行版。不混入旧版本。

本轮未执行这批新下载模组的 Mixin 插件/构建期初始化/游戏代码。转换、AOT、进世界、玩法断言和真机均 NOT RUN；将它们作为下一轮逐项适配输入，不能称整包可玩。

同轮公共接口扩展的 287 项回归记录位于 `artifacts/mcfao/content-samples-01/regression-final.log`；这是第一方工具测试，不是本样本整包游戏运行结果。
