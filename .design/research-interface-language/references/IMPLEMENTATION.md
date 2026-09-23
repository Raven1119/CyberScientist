# 移植到其他项目

## 先匹配项目，再选实现

已有 React/Vue/Svelte 项目：保留原框架、路由、表单与组件库。把 `--ril-*` 映射到项目现有的 theme token；新动效只接到需要的组件。新建无构建示例可从 `examples/starter.html` 起步。

模板导入：

```html
<link rel="stylesheet" href="path/to/assets/tokens.css">
<link rel="stylesheet" href="path/to/assets/primitives.css">
```

两个样式表都不做全局 body/reset。主题属性放在 `<html data-theme="night">`；字体回退取当前系统。`primitives.css` 使用 `ril-` 前缀，不覆盖项目原有类名。

参考应用内部使用无前缀 token 和样式；不要把整段参考 CSS 全局注入另一个项目。参考布局不是必须复制的页面骨架。

## 动效代码所在位置

见 `REFERENCE_MAP.md`。完整 HTML 的脚本按依赖顺序为：许可证 → shader 常量与 helpers → Motion 主机 → 演示业务。

`window.ResearchMotion` 只在完整演示加载后存在。它不是 npm 包，也不是独立 ESM；不要在新页面写一句 import 就假装已接入。

迁移原生效果时，把相关代码与依赖放到**目标应用内部**，明确 namespace、DOM 和生命周期。只抄单个函数常会漏掉闭包变量。优先直接使用记录的上游组件，或在目标应用内迁移 V9 主机；不要重新近似 shader 和像素算法。

| 迁移项 | 必要依赖／要点 |
|---|---|
| `Motion.field` | 所选 shader 常量与 helpers、Motion 的 canMove/live 状态、WebGL 主机；Dots 路径依赖 dotGrid。容器先有明确尺寸 |
| `Motion.pixelTransition` | `canMove`、对应像素 CSS、定位容器；保存并取消旧 job；swap 回调只执行一次有效更新 |
| 解码／打字 | textJobs、cancelText、动效状态；卸载和取消需结算最终文本 |
| 分字／进场 | WAAPI 主机、动效开关、split-char 样式；输入字段不分字 |
| Scrambled | pointer 事件和 timer 清理；V9 的函数没有公开 dispose，新项目在组件卸载时补清理 |
| ElasticSlider | `.slider-root/.slider-track/.slider-range/output` DOM、pointer capture、键盘、decay 函数；V9 只返回 set，组件化时补 destroy |
| Target Cursor | 位于演示业务脚本，依赖四角 DOM、Motion.wa、pointer/scroll 监听；不是 Motion 的公开方法 |
| Stepper | 演示里的 stepTo/syncWizard/wizardNext；迁移方向／高度切换，不迁移示例任务数组 |

不要将 `reference.html` 的所有应用逻辑贴进项目。尤其不能复制 `research-systems-upstream-v9` 存储键和样本任务。为实际产品定义自己的业务数据和命名空间。

## React 生命周期示意

下面的 `createField` 必须是已经在**当前应用**内完成移植并处理依赖的函数；这是接入方式，不是本包导出的现成方法。

```tsx
useEffect(() => {
  const host = hostRef.current;
  if (!host) return;
  const scene = createField(host, mode);
  return () => scene.dispose();
}, [mode]);
```

React Strict Mode 会重复挂载／卸载；canvas、监听器、timer、RAF 都要能清理。不要通过关闭 Strict Mode 掩盖泄漏。

## 数据与交互

假执行只留在参考演示里。目标页面由真实请求驱动 loading/success/error；事件动画不能伪造后端运行。像素替换的过渡期不锁死用户操作；快速点击应以最终选择为准。

浏览器不支持 WebGL 时，明确说明观测图未运行并保留主工作流。不要伪装成“已暂停”或把空白当正常结果。

## 第三方范围

本包提供完整应用示例与源码定位，而不分发 React Bits 的独立组件集合。来源许可证在 `licenses/`。需要原始 React 版本时从登记的官方源码获得，并保留项目中的版权／变更说明；本地 blob 记录不等同 package.json 锁版本。

起步页只包含自有视觉外壳，刻意不把所有动效或依赖预装到每个项目。
