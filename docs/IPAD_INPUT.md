# iPad 原生适配与妙控键盘触控板输入

最后复核：2026-11-13。本文记录 PR #2 真机失败的根因、修复、可复现构建/验证命令，以及真机验收步骤。**模拟器通过不代替真机验收。**

## 1. 真机失败根因

失败构建的实际设置与最终包：

- 实际构建使用 `/tmp/mcfao-pr2-review` 中的本地改动；其 `World Device` 目标配置没有 `TARGETED_DEVICE_FAMILY`，Xcode 采用默认值 `1`。
- 最终 `.app/Info.plist` 为 `UIDeviceFamily = [1]`，因此 iPad 以 iPhone 兼容模式运行，出现系统放大按钮，画面比例保持 iPhone。
- 该兼容模式场景不满足 iPadOS 指针锁定的“全屏场景”前提；`prefersPointerLocked` 请求未被系统批准，`UIPointerLockState.isLocked` 保持 `false`。
- 原输入桥只在 `captured && pointerIsLocked` 时转发 `GCMouse` 相对位移，所以触控板只能移动系统光标，不能转动视角。
- 原 `WorldDevice` 实际只做了 iPhone 尺寸窗口和 Drawable 的初始化同步；没有把最终包契约、场景全屏状态和指针锁状态记录为可核验证据。

证据：

- 失败包的 `Info.plist`：`UIDeviceFamily = [1]`
- 构建设置：`TARGETED_DEVICE_FAMILY = 1`
- 安装日志：免费开发者描述文件应用数量上限；这不是签名失败的证明，也不是真机功能通过的证明。

## 2. 修复

### 2.1 原生 iPad 包契约

- `ios/C0Harness/WorldDevice.xcconfig` 明确设置 `TARGETED_DEVICE_FAMILY = 1,2`。
- `ios/C0Harness/Info.WorldSimulator.plist` 与 `Info.plist`：
  - `UIRequiresFullScreen = true`
  - `UIApplicationSupportsIndirectInputEvents = true`
  - `UISupportedInterfaceOrientations~ipad` 包含左右横屏
  - 不再手写 `UIDeviceFamily`；该键由 Xcode 从 `TARGETED_DEVICE_FAMILY` 注入，手写副本会被覆盖并产生警告。
- `embed_graphics_libraries.sh` 在 `ProcessInfoPlistFile` 之后调用 `ios/C0Harness/verify_ipad_bundle.sh`；后者检查**实际最终** `Info.plist` 的 `UIDeviceFamily` 同时包含 1 和 2、全屏键、间接输入键、iPad 横屏和 iPhoneOS 平台。契约不满足时构建直接失败。
- `tools/verify_ipad_bundle.py` 对已构建的 `.app` 或导出的 `.ipa` 做同一契约检查，并检查 arm64 / IOS 平台；CI 在构建后运行。
- 移除 `FabricAOTWorld` 目标的“只允许模拟器”构建阶段拦截，避免设备构建在脚本阶段被误杀。

### 2.2 窗口、Drawable 与帧缓冲尺寸

`ios/glfw-lite/uikit_surface.m`：

- `UIWindow`/root view 使用当前 `UIWindowScene` 的 `effectiveGeometry.coordinateSpace.bounds`，设置 `autoresizingMask`。
- `layoutSubviews` 只在点尺寸或 Drawable 像素尺寸变化时更新 `CAMetalLayer.drawableSize` 并调用 `faot_glfw_resize`，同时把 `points/drawable/scale/sceneFullScreen` 写入输入日志。
- `faot_surface_screen` 报告当前场景尺寸而不是固定的 `UIScreen.bounds`，避免横屏下视频模式仍使用竖屏尺寸。
- 初始 `glfwGetWindowSize`/`glfwGetFramebufferSize` 与首帧前的 `layoutIfNeeded` 使用同一组点/像素尺寸。

### 2.3 指针锁定与触控板

- `FAOTGameController` 的 `prefersPointerLocked` 只在 `captured && active && sceneFillsScreen` 时为真；`UIPointerLockStateDidChangeNotification` 记录系统**实际**批准/撤销状态，而不仅是请求状态。
- `sceneFillsScreen` 比较场景坐标空间和屏幕尺寸（允许横竖旋转），因此 iPhone 兼容模式或 iPad 窗口化场景会明确记录 `fullScreen=0`。
- `GCMouse`：
  - 监听连接、断开、成为当前设备、停止成为当前设备；
  - 启动后 1s/3s 再枚举一次，覆盖妙控键盘较晚枚举的情况；
  - 相对位移通过 `mouseMovedHandler` 进入 `FAOT_EVENT_CURSOR_DELTA`；
  - 按键通过 `valueChangedHandler` 进入 `FAOT_EVENT_BUTTON`；
  - 滚动通过 `scroll.valueChangedHandler` 进入 `FAOT_EVENT_SCROLL`。
- 指针锁未获批准时仍转发相对位移（策略函数 `faot_pointer_should_forward_motion`），这是触控板/鼠标在窗口化场景下的保底相机控制；日志明确记录 `approved=0`。
- 若妙控键盘触控板不产生 `GCMouse`，`UIHoverGestureRecognizer` 的相对位移作为 fallback；`UIPointerInteraction` + `hiddenPointerStyle` 在 captured 时隐藏系统指针。二者均为公开 UIKit API。
- `UIPanGestureRecognizer.allowedScrollTypesMask = UIScrollTypeMaskAll` 接收触控板滚动事件；delegate 只接受 `UIEventTypeScroll`/`UIEventTypeTransform`，不会和手指拖动视角冲突。
- 进入世界（`GLFW_CURSOR_DISABLED`）请求锁定；打开菜单（`GLFW_CURSOR_NORMAL`）释放锁定并释放按键/鼠标按钮，避免卡键。
- 前后台切换更新 `active`、撤销/重申请求，并释放按住的输入。

### 2.4 诊断证据

每次输入状态变化写入 `Documents/c0-logs/input-*.log`，字段包括：

```
state reason=... captured=... active=... fullScreen=... locked=... lockRequested=...
gcmouse=... gcmouseCount=... mouseName=... scene=WxH screen=WxH drawable=WxH scale=...
firstResponder=... lockRequests=... motionForwarded=... motionDropped=...
geometry points=... drawable=... sceneFullScreen=...
motion source=gcmouse|hover|touch-drag ...
scroll source=gcmouse|trackpad-pan ...
```

iPad 上启动和进入世界后还会短暂显示两行屏幕 HUD，包含场景点尺寸、Drawable 像素尺寸、指针锁状态和 GCMouse 名称，便于截图取证。

## 3. 可复现构建与验证

以下命令在仓库根执行。图形/AOT 输入由用户本地合法资产生成，不进入仓库。

```bash
g=artifacts/graphics
# 1. 编译当前指针桥（真机）
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 \
  -std=c11 -fobjc-arc -O2 -Wall -Wextra -Werror -Wno-deprecated-declarations \
  -dynamiclib ios/glfw-lite/glfw_lite.c ios/glfw-lite/pointer_state.c \
  ios/glfw-lite/uikit_surface.m \
  -framework UIKit -framework QuartzCore -framework CoreGraphics -framework Metal \
  -framework GameController -install_name @rpath/libglfw.dylib \
  -o artifacts/ipad-fix/input/libglfw.dylib

# 2. 用新库替换已核验的 WorldDevice 输入目录中的 libglfw.dylib
#    其余文件沿用 world-device-input-02 的哈希核验结果。

# 3. 构建（无签名先用 0；正式包由本机 Team 签名）
xcodebuild -project ios/C0Harness/C0Harness.xcodeproj -scheme WorldDevice \
  -configuration 'World Device' -destination 'generic/platform=iOS' \
  -derivedDataPath artifacts/ipad-fix/DerivedData \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  FAOT_GRAPHICS_NATIVE_DIR="$PWD/artifacts/ipad-fix/input" \
  FAOT_CLIENT_LIBRARY="$PWD/artifacts/ipad-fix/input/client-graph.dylib" \
  FAOT_GAME_ASSETS_DIR="$PWD/artifacts/graphics/game-assets-01/assets" \
  build

# 4. 最终包契约（构建阶段已自动执行；此处独立复核）
python3 tools/verify_ipad_bundle.py \
  --app artifacts/ipad-fix/DerivedData/Build/Products/'World Device-iphoneos'/C0Harness.app

# 5. 安装到已解锁、已配对的 iPad Pro
xcrun devicectl device install app --device <iPad-UDID> \
  artifacts/ipad-fix/DerivedData/Build/Products/'World Device-iphoneos'/C0Harness.app
xcrun devicectl device process launch --device <iPad-UDID> --console \
  org.fabricaot.research.c0.kexin
```

本机 2026-11-13 的实测：

- 构建：`BUILD SUCCEEDED`
- 构建阶段：`iPad bundle contract PASS: UIDeviceFamily=[1,2] TARGETED_DEVICE_FAMILY=1,2 fullScreen=true indirectInput=true`
- 独立 `verify_ipad_bundle.py`：`IPAD_BUNDLE_CONTRACT_PASS`
- iPad Pro 11-inch (M4) / iPadOS 27.2 模拟器：场景 `1210x834 pt`、Drawable `2420x1668 px`、`sceneFullScreen=1`，真实 Minecraft 主菜单铺满屏幕；日志无 iPhone 兼容模式。
- 真机安装：**未完成**。2026-11-13 的两次安装均因 iPad 锁屏被 CoreDevice 拒绝（`The device is still locked`），不是构建或签名失败。真机指针锁定、触控板视角、菜单点击/滚动/键盘仍为 **NOT RUN**。

## 4. 真机验收步骤

1. 解锁 iPad，保持妙控键盘连接，关闭分屏/台前调度，让 App 全屏。
2. 安装上述 `.app`（同一 bundle ID `org.fabricaot.research.c0.kexin` 会替换旧测试包并保留同 ID 存档）。
3. 启动后确认主菜单铺满屏幕，没有系统放大按钮。
4. 进入一个测试世界，检查屏幕 HUD/日志：
   - `scene=... screen=...` 两值相同（或横竖互换）
   - `fullScreen=1`
   - `locked=1`（若系统拒绝，记录 `approved=0` 与 `fullScreen` 值）
   - `gcmouse=1` 或记录 `gcmouse=0` 并确认 hover fallback
5. 触控板向左/右、上/下移动，确认两个方向视角都变化。
6. 打开菜单，确认指针释放、可点击/滚动、WASD/E/Esc 正常；回到游戏再次锁定。
7. 收集 `Documents/c0-logs/input-*.log` 与运行日志，连同屏幕截图/录屏归档到 `artifacts/evidence/ipad-pointer-pr2-<date>/`。

只有第 1–6 步在真实 iPad Pro 上通过，才能把 PR #2 的真机测试标记为 PASS；在此之前保持 `NOT RUN`，不得合并 main。
