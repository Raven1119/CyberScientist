# CS-SB-01 稀疏输入与唤醒修复（2026-09-24）

任务开始时 `main` 为 `1d554be9e39be7ec61581459d67f281669da4586`，工作树干净。本轮只使用临时 SQLite 和 fake 大脑/执行器，没有启动真实科研、模型、Bohrium Job 或比赛提交。

## 已实现

- 检查点合约、MCP 工具、UI 手动检查点 API 和 SQLite 幂等迁移加入可选 `research_summary_md`（最多 1600 字）。完整 `report_md` 仍原样保存。稀疏帧只展示检查点 ID、阶段、来源、证据引用、是否有摘要，以及经过脱敏的显式摘要；旧检查点明确显示 `research_summary_available=false`，不会回退到报告前缀。`checkpoint.created` 的 `report_excerpt` 也不再进入稀疏帧。大脑仍可经 `research_trace` 按需读取完整报告。
- 新 Run 的 shadow 触发器排除普通 `checkpoint.created`、进度与普通 Job 轮询；显式 async/blocking 和 trial_complete 保持既有请求及门禁。评分、Trial 研究级事件、错误、Job unknown，以及 Job 首次进入 Failed/Stopped/Finished 可触发观察；同一 Job 或 Trial 的重复状态事件按 ID 和前一状态去重。没有新增时间停滞分类器。
- 旧 Run 仍走原有检查点报告投影和 shadow 触发词表。修改涉及 `db.py`、`collab.py`、`observation.py`、`controller.py`、`api.py`、`mcp_bridge.py`、协作合约及 `tests/test_collaboration.py`；未修改前端。

## 已实际验证

- `.venv/bin/python -m pytest -q tests/test_collaboration.py`：先出现一处旧断言与新语义冲突，随后在既有 asyncio 关闭路径停住；`timeout 120s` 以退出码 124 中止。已把依赖普通检查点唤醒的旧测试改为使用评分事件，并新增摘要、按需读取、单次显式审阅、普通 Job 轮询及终态去重的回归。
- 测试进程内临时以 0.05 秒定时唤醒 asyncio 事件循环（`/tmp/cs_pytest_pulse.py`，未改产品或仓库测试框架）后，`.venv/bin/python /tmp/cs_pytest_pulse.py -q tests/test_collaboration.py tests/test_codex_brain_environment.py tests/test_codex_runtime.py tests/test_kimi_executor.py tests/test_mcp_bridge.py tests/test_linux_codex_configuration.py tests/test_upgrade_regressions.py`：95 passed。相同包装执行 `-q tests --ignore=tests/test_cli_shutdown.py`：285 passed。包括开放 ResearchAnswer、zero/自主 trace read、全文指导及 ACK、角色与截止序号隔离、旧 Run 检查点投影和周期监督。
- 最终代码又执行 `.venv/bin/python /tmp/cs_pytest_pulse.py -q tests/test_collaboration.py`：59 passed；`.venv/bin/python -m compileall -q src/cyberscientist tests/test_collaboration.py` 和 `git diff --check` 均通过。

## 尚未验证与兼容边界

未运行未经包装的完整 pytest；上述 285 项排除了独立的 CLI 关闭测试，本轮未重跑该用例。未做真实 Kimi/Codex 原生双会话、真实科研、付费计算或提交，因此不据此声称模型更独立、迎合消失、科研能力提高，或原生工具已完全硬隔离。旧 Run 根据创建时的快照继续使用非稀疏行为；存量数据库通过幂等列迁移保留旧报告，旧检查点摘要列为 NULL。
