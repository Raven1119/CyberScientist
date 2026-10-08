# CS-UP-16 验证记录

所有测试使用隔离临时账本；真实验证单列。原始日志和截图在本地忽略目录 `.package-checks/cs-night-1009/`，不提交原生会话、回执全文或凭据。

| 项 | 结果与证据 |
|---|---|
| W0 | D-75/D-80 已写入决定和升级计划。 |
| W1 | 方法关口持久化，审批与 PI 请求同事务；计算仍要求 open gate。8 项后端测试通过（cs16-w1-tests.log），4 项前端测试通过（cs16-w1-front.log），前端构建通过。真实 Chromium 140 按 aria-label 点击批准成功；HTTP 为明确的 synthetic fixture，实际渲染 MethodApproval 组件，cs16-method-playwright.json / cs16-method-approved.png。提示词附录原文加入 brain.md。 |
| W2 | 8 项闭环/早回执/账号测试通过（cs16-w2-tests.log）。fake 走实际 controller、提交和回执写路径：批准前无执行消息；批准后完整版本产物提交；等待期间新 Trial 可继续；final=false 的科学分唤醒 PI；第二完整版本轮换账号。提交路径未调用本地科学评分；现有轨迹诊断已为 advisory。没有真实计算或评分器探测。 |
