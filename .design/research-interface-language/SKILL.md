---
name: research-interface-language
description: >-
  Apply Raven's shared frontend design language to application UI, research tools,
  agent workspaces, dashboards and settings. Use when implementing or reviewing
  frontend visuals or interaction, especially when the user references the shared
  design language, Research Systems, 雨世界, 尼尔机械纪元 or 莱茵生命.
compatibility: >-
  File-reading coding agents. Reference and starter run offline in a modern browser;
  observation shaders need WebGL/WebGL2. Optional installer requires Python 3.9+.
metadata:
  version: "1.0.0"
  baseline: "V9 upstream-motion application; cool-graphite night palette"
---

# Research Interface Language

所有相对路径以本 SKILL.md 所在目录为基准。当前任务和项目约束优先；本 Skill 仅约束前端设计，不改变项目后端架构。

## 开始前

1. 读 `references/DESIGN.md` 和 `references/MOTION.md`，查看 `assets/screenshots/` 的日间、夜间截图。
2. 用可用浏览器打开 `assets/reference.html`：观察一次观测模式切换、样本室像素翻面和夜间模式。只有截图时不能声称验证过运动。
3. 读 `references/IMPLEMENTATION.md`，审计目标项目现有技术栈与组件；按需查 `references/REFERENCE_MAP.md` 和 `assets/motion-map.json`。

## 固定基线

基准是包内 **V9 冷石墨夜间版**，不能回到 V7/V8 的半透明遮罩、全屏扫描或几乎不可见的观测场。
主题是“仍由人维护的研究机构”：暖纸面或冷石墨阅读面、严格排版、克制刻线、有真实用途的编号，以及有清楚辨识度的局部动效。
不要仅凭“雨世界／尼尔／莱茵生命”重新脑补一个风格。不得重新引入墨绿色夜间主界面、通用紫蓝渐变或发光 HUD。

## 实现

使用 `assets/tokens.css` 的 `--ril-*` 变量；JSON 是相同数值的机器可读副本。`assets/primitives.css` 和 `examples/starter.html` 是无构建的基础外壳，可映射到现有组件，不必换框架。

动效从已选来源和实际 V9 应用代码迁移，不能用自制的“类似动画”替换。观测窗一次展示一种清楚可见的效果；正文保持稳定。不是每页必须塞满十五项：按功能使用，完整候选在样本室保留。

像素切换必须是：**不透明方块填满 → 遮挡中替换 → 方块退去**；局部容器内完成，不用全屏扫光代替。

业务行为先由真实数据决定。不要复制演示里的任务、假执行记录、全局变量、localStorage 键或“研究阶段”来冒充真实工作流。页面布局可变，视觉与动作语法不随项目任意变。

## 最小交付

先做目标项目中一条完整、可操作的工作流。复用现有组件，按需迁移效果。不预建通用引擎、不强制所有页面采用三栏布局，也不扩成全量组件平台。

## 验收

对照 `references/CHECKLIST.md` 验证：日／夜、桌面／窄屏、开关动效、减少动态、键盘、实际任务操作。动态验收录屏或至少比较两个不同时刻，不拿静态截图证明动画正常。

交付说明列出已采用的 token、动效 ID、实际验证结果与未验证项。参考应用可运行不等于目标项目已适配完毕。

## 来源与授权

`assets/reference.html` 保留完整应用及许可证。`licenses/THIRD_PARTY_NOTICES.txt`、`licenses/PACKAGE_SCOPE.md` 必须随相关使用保留。React Bits 组件不在本包中另行拆成通用组件发行物；在目标应用内使用时按原授权处理。
