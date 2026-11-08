# 安全、授权、签名边界

## 构建输入不可信

`.mrpack`、Prism 实例、jar、fabric.mod.json、Gradle build scripts、Mixin plugins、远程资源都可能不可信。静态扫描应限制 ZIP 成员数量/路径/总展开量、禁止 symlink 和目录穿越，检测大小写路径冲突、下载指向本地网络/HTTP、损坏/缺失 SHA-1 与 SHA-512。下载器还应验证 DNS 解析、HTTPS 重定向、host allowlist、总下载量和最终实际 hash；**仅有 URL 字符串检查不够**。

不得直接执行未经隔离的 Gradle、Mod 类/插件、build-time initializer。先定义受控的独立构建用户/沙盒、最小目录权限、离线默认、只读工具链、禁用敏感主目录访问和进程资源上限。Mac 的各类“沙盒”对 Java/Gradle 是否适用须实测；无安全隔离则采用阻断/手动审计，不能声称安全。

## Auth 与资源

仅从用户授权的官方渠道取得 Minecraft 资源。合法验证流程需覆盖 Microsoft 身份认证/游戏所有权和 Token 生命周期，并让用户控制是否登录。任何 Token/密码都不得写入日志、Mod/Native Image 构建缓存、公开 issue 或 IPA 明文；应在系统 Keychain 中保存用户会话（若运行时需要）。没有官方凭据时，不得伪造/绕过账号认证；离线功能边界须按授权条件核定。

## 私人构建与再分发是两个问题

即使用户合法拥有游戏，AOT 编译后的 iOS 二进制可能包含 Minecraft 游戏代码或资源；不允许把含 Mojang/Microsoft 专有代码的 IPA 作为公开 GitHub Release 或通用 App 直接分发。官方 Minecraft EULA 明确禁止分发修改后的游戏本体。源码、构建器、补丁、第三方开源适配层和生成说明可以单独提供，具体授权按各自许可核验。私人本地生成不构成任何法律保证。

## Xcode Personal Team

Apple 官方文档：个人免费 Team 可在个人设备上开发安装，但相关 provisioning profile **7 天过期**；设备数、App 数也有限制。须分别测试 (1) Xcode 安装；(2) 真正导出 IPA；(3) 7 天到期后的重新签名安装；(4) 不卸载原 Bundle ID 的存档保留。工具不得存储个人签名证书或索要私密密钥。

## UI 与产品宣传

避免让用户误以为 Mojang/Microsoft 官方产品。明确：独立、非官方、未经认可/关联。AOT 工具和兼容清单不是 Minecraft 游戏本体；仅在通过真机 Gate 后才能宣称“可玩”。
