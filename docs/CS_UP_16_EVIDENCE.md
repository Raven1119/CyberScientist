# CS-UP-16 验证记录

所有测试使用隔离临时账本；真实验证单列。原始日志和截图在本地忽略目录 `.package-checks/cs-night-1009/`，不提交原生会话、回执全文或凭据。

| 项 | 结果与证据 |
|---|---|
| W0 | D-75/D-80 已写入决定和升级计划。 |
| W1 | 方法关口持久化，审批与 PI 请求同事务；计算仍要求 open gate。8 项后端测试通过（cs16-w1-tests.log），4 项前端测试通过（cs16-w1-front.log），前端构建通过。真实 Chromium 140 按 aria-label 点击批准成功；HTTP 为明确的 synthetic fixture，实际渲染 MethodApproval 组件，cs16-method-playwright.json / cs16-method-approved.png。提示词附录原文加入 brain.md。 |
| W2 | 8 项闭环/早回执/账号测试通过（cs16-w2-tests.log）。fake 走实际 controller、提交和回执写路径：批准前无执行消息；批准后完整版本产物提交；等待期间新 Trial 可继续；final=false 的科学分唤醒 PI；第二完整版本轮换账号。提交路径未调用本地科学评分；现有轨迹诊断已为 advisory。没有真实计算或评分器探测。 |
| W3 | 14 项回归通过（cs16-w3-tests.log）；等待空闲、不 resume、旧日志不改、交接不含探索目标、封包只含新线程。已结束 LiSi 旧题账本副本真实最小 Trial trial_f694ba14df，新 Terra xhigh priority 线程 01a11cb8-50b5-7640-a467-6631a741406a 完成；169820 字节原生日志封包逐字节相等（clean-native/result.json）。无 Job/沙箱/提交。此绑定专用验证未接 MCP；旧 idle 线程未曾生成日志，旧日志保留由 fake 不变性测试覆盖。原生完成后验证消费者误等旧事件名，已停止并按真实 task_complete 及回执文本判定、封包；不把测试程序中断记作完整脚本通过。 |
| W4 | 实时逐题面板及全部控制接入真实接口并留审计；暂缓提交为持久门禁；档位覆盖保存在独立运行控制记录，冻结快照不改，仅新会话生效。19 项后端测试、34 项前端控制/审批/账号/旧页面测试通过，构建通过；真实 Chromium 截图 cs16-competition-panel.png（实际组件、明确 synthetic HTTP，page_errors=[]）。 |
