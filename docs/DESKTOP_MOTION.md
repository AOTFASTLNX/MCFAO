# NCL Builder 动画系统

2026-11-17。适用范围：`desktop/` 的 Tauri 2 + React 19 工作台。本文记录动画令牌、复用组件、接入位置和验证边界；动画只描述真实状态，不生成构建进度。

## 架构

- `desktop/src/motion.ts`：全局时长、缓动、位移和缩放令牌；`useSlidingIndicator`、`useStepContent`、`usePageEnter`、`useSelectionPulse`、`useAnimatedNumber`、`useReducedMotion`。
- `desktop/src/MotionPrimitives.tsx`：`MotionIndicator`、`StepBody`、`AnimatedNumber`、`StatusMark`、`Reveal`。
- `desktop/src/system-neutral.css`：`--motion-*` CSS 变量与组件规则；`prefers-reduced-motion` 在这里统一关闭位移和装饰动画。
- `desktop/src/dropTarget.ts`：拖放路径分类和提示文案，纯函数可单测。

令牌：instant 100 ms、fast 160 ms、normal 240 ms、smooth 320 ms、expand 360 ms、completion 480 ms；位移 4 / 16 px；按下 0.985、进入 0.96。缓动分为 out、spring、standard、in 四档，避免每个组件自定义曲线。

共享元素的做法是“一个测量层就是选中面”：`useSlidingIndicator` 读取每个 `[data-motion-item]` 的实际矩形，把唯一的 `.motion-indicator` 从当前项连续移到目标项，并同步宽高；选中行本身保持透明，所以切换时看到的是同一块色板在移动，而不是旧背景消失、新背景出现。快速切换只是重定向这个图层，不会叠加多个指示器。

## 接入位置

- 五步向导：选中胶囊连续移动；数字 / 对勾按真实完成门槛切换；前进向右、后退向左的 16 px 内容过渡；高度交接；底部计数数字过渡；按钮悬停箭头位移、按下缩放。
- 侧边栏：导航选中块连续滑动；页面切换先淡出再淡入（不横向位移）；构建记录计数使用数字过渡；运行中任务在顶栏显示真实阶段。
- 游戏内容：Fabric / 原版单选底板滑动；拖拽悬停、拒绝、离开反馈；报告卡片和统计数字进入；诊断详情展开。
- 资源与依赖：资源列表进入、勾选反馈、数字统计；原生依赖状态标记、真实 `dependencyProgress` 计数。
- 构建：阶段图标只在任务运行中活动；失败或取消停止动画并显示停止标记；日志追加不再强制拉回底部；错误 / 警告行短暂高亮；任务已用时按真实时间更新。
- 产物：仅当任务状态为 succeeded 时播放 IPA 完成反馈；安装、上传和游戏启动仍是独立状态，不使用成功动画代替。
- 通用控件：下拉、弹窗、Toast、横幅、输入聚焦、Checkbox、详情展开、列表进入；主题切换不参与动画，避免颜色过渡期间读到中间色。

## 无障碍与性能

- `prefers-reduced-motion: reduce` 时取消位移、缩放、旋转和装饰动画；步骤、进度、错误和完成状态仍完整可见。
- 页面切换只动画入场的现有内容，不保留两个活动页面；步骤内容始终挂载，表单输入和滚动位置不丢失。
- 日志面板只渲染实际日志行，自动跟随在用户滚动离开底部后暂停；`LogView` 使用 `memo` 避免无关父级重渲染。
- 动画只改 `transform`、`opacity` 和受控高度；不存在常驻的无限装饰动画。唯一循环活动是正在运行任务的加载指示和当前阶段呼吸，任务停止即结束。

## 验证

- `npm test`：Motion 令牌、方向、缓动、计数、拖放分类和 Reduced Motion 媒体查询单测。
- `npm run test:e2e`：`tests/motion.spec.ts` 覆盖步骤胶囊定位、快速切换、前后方向、计数稳定、侧边栏层、Reduce Motion、快捷键、Fabric / 原版底板、拖放提示、日志阅读位置。
- `npm run build`：TypeScript 与 Vite 生产构建。
- 浏览器预览只能验证 DOM 状态与布局；原生拖放事件、窗口后台节流、真实构建阶段和 IPA 完成状态需要在桌面应用和真实任务中确认。

## 未接入

- 云端构建：当前工作台没有云构建 API，未添加云端状态动画。
- 自动修复 Mod：当前流程只有静态检查与排除确认，没有修复动作，未伪造“已修复”状态。
- 设备安装：当前不自动操作设备，只显示构建 / 签名 / 导出状态。
