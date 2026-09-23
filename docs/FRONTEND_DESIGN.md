# Research Interface Language 接入记录

视觉基线来自本机提供的 `research-interface-language-v1.0.0.zip`，其解压内容保存在仓库的 `.design/research-interface-language/`。原始参考、token、来源及许可均随解压目录保留；原始 ZIP 只在本机归档，不纳入 Git。未执行全局技能安装。包内实际规范文件名为 `DESIGN.md`、`MOTION.md`、`IMPLEMENTATION.md`、`REFERENCE_MAP.md`、`CHECKLIST.md`，覆盖任务所指的设计、运动、专注和组件规范。

## 共享层

- `apps/web/src/design/tokens.css` 原样接入命名空间 token；`styles.css` 把旧页面使用的颜色别名映射到 token，并统一按钮、表单、面板、标签、状态、空态、加载态和原生 dialog。旧圆角、阴影和深蓝导航样式已移除。
- 日间为纸色；夜间主背景 `#17191A`、纸面 `#202223`。状态色作为少量语义扩展；观测图形通过颜色 uniform 适配主题。
- `PresentationProvider` 只持有主题、交互动效、环境动效、专注偏好；不读写业务配置。持久化键为 `cyberscientist.presentation.v1`。专注模式可由按钮或 Esc 退出，不卸载表单。
- App Shell 保留四个现有页面入口。研究意图、指导表单与活动记录位于阅读区；观测、监督在侧区；预算和配置快照在可展开摘要中。
- 中文/英文正文保持稳定，使用本机字体栈，不在浏览器运行时请求外部字体。无中文字库的最小 Linux 镜像需准备 Noto CJK；本次浏览器使用项目忽略目录中的临时字体，未修改系统配置。

## 已采用动效

| ID | 接入位置与触发条件 | 基线实现 |
|---|---|---|
| RB-01 Threads | 局部观测窗；当前 Run 为 running、SSE 连接且监督响应确认 brain_busy 或 executor_busy 时运动 | 原参考 GLSL 保留，独立 WebGL host；速率 0.8 |
| RB-08 Dot Grid | 同一观测窗；满足真实活动条件时响应邻域指针与点击冲击 | 原网格、邻域、速度脉冲及弹性积分公式 |
| RB-29 Target Cursor | 鼠标进入可操作控件，保留系统指针，编辑区及触屏不捕获 | 原四角几何，捕获 200ms、回收 300ms |
| RB-34 Pixel Transition | 用户切换线束/点阵 | 12×12 不透明格，300ms 遮挡、遮挡中切换、300ms 退去；快速切换以最新选择为准 |
| RB-35 Animated Content | 页面切换、dialog 首次打开 | 原位移/透明度关键帧，600ms、原参考 easing；正文更新不重播 |

图形表达活动存在，不表达科学计算进度；Demo 始终显示演示标记。未收到当前 Run 的监督确认、运行已结束、事件流断开时不播放活动动画。用户暂停画面、正在输入、系统减少动态、页面隐藏或图形离屏时停止绘制；卸载、主题/图形切换清理 RAF、Observer、监听器和 WebGL 资源。主题颜色在根元素主题属性生效后读取。

原始许可证和修改声明随构建进入 `public/legal/`，页脚提供访问入口。其余动效未强行加入业务页面；完整候选仍在原参考页。

## 接口与回归边界

没有替换真实数据或更改后端 API。新观测层拒绝旧 Run 的延迟监督响应；终态显示归档。浏览器验收发现同 Run 进入终态时 SSE effect 重置游标造成重复事件，现改为同 Run 保留订阅游标，并覆盖重连、终态、切 Run 和 StrictMode 的回归测试。

原生 Demo 验收还发现演示执行器缺少控制器现有的 `close(session_id)` 方法，现补齐脚本取消、队列释放、幂等关闭；未调整控制器、外部协议或真实代理实现。

可复验工具：`checks/serve_ui_demo.py` 使用全新独立目录启动原生 Demo 后端；`checks/ui_design_smoke.py` 只接受带隔离标记的服务，通过真实 UI/API 导入、授权零额度 Demo、检查动效和页面。`checks/ui_motion_smoke.py` 补查像素中间帧、快速连点、键盘焦点、真实网络延迟下的加载态与离屏/减少动态。报告及截图位于 `checks/shots/design-language/`；Demo 不能证明真实 Kimi/Codex/Bohrium/比赛接口可用。
