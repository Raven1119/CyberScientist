# 当前状态（2026-09-24）

## 已实现

- Linux 工作台已接入 Kimi、Codex 和 Prime 的可选大脑/执行器路径，提供运行控制、技能、经验、提交和可审计的事件记录。
- Bohrium 计算由后端网关准入和对账；创建结果不明时保留占位，不盲目重试。
- 前端已连接真实后端，提供运行监督、设置、经验管理与操作界面。
- TBMA 运行后的准入、恢复、审阅和经验整理改动已纳入本次代码更新；含账户和实际任务标识的运行记录保留在本机忽略目录。
- CS-SB-01 新 Run 稀疏研究大脑已实现：开放研究回答、按需只读轨迹、研究级唤醒、自然边界全文投递与 ACK；前端显示回答、交付和读取。旧 Run 保留原协议。详见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。

## 已实际验证

- 本次 Linux 项目虚拟环境执行 `.venv/bin/python -m pytest -q tests/test_collaboration.py -k 'not test_t13b_submit_guidance_failure_marks_failed and not test_t13_submit_guidance_auto_submits_without_executor'`：55 passed、2 deselected；其中 fake runtime + HTTP MCP + outbox 闭环证明零读取第三路线、可选读取、全文交付和 ACK。
- 本次在测试进程临时增加事件循环定时唤醒、未改产品代码或断言后，Python 全套除本机回环监听用例外 283 passed、1 deselected；回环 CLI 关闭用例单独获准本机监听后 1 passed。确切入口与局限见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。
- 本次执行 `.venv/bin/python checks/evaluate_sparse_brain.py`：3 个离线样例加载，0 次真实模型调用。
- 本次 `apps/web` 执行 `npm test -- --run`：10 passed；`npm run build` 成功。
- 代码与资源提交前已核查大文件、归档、数据库和已知密钥；本次公开提交不包含实际运行状态文件。

## 尚未验证

- 本次改动后的新一轮 Linux 原生模型完整往返、Bohrium 真实任务和比赛提交尚未执行。
- 经验改动对科研结果的因果效果尚未证明。
- CS-SB-01 的真实 Kimi/Codex 双会话往返、模型独立判断效果和原生内建工具完全禁用能力尚未验证；本轮按要求未启动真实模型或科研。

## 阻塞项

- 未修饰的全量 Python pytest 被现有 Linux Python 3.12 异步线程唤醒问题阻塞：独立最小脚本在线程工作完成后也可能无法退出。默认沙箱还禁止 CLI 测试所需的回环 socket；已分别用测试进程临时唤醒和单独本机回环测试验证，但未声称默认命令可直接通过。
