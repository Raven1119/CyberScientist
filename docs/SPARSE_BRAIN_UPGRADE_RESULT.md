# CS-SB-01 交付记录（2026-09-24）

独立判断为核心，轨迹按需读取，未增加主动核查流程。新建 Run 使用 `sparse_brain_version=1`；存量 Run 的快照与旧问答协议不被静默改写。

开工时实际 HEAD 为 `9b7fe6735732ec73bf7c908d6cb0b1ae61372b9f`；指定子目录当时不存在，任务卡和设计稿是仓库根目录的未跟踪 `CODEX_TASK.md`、`DESIGN.md`，已据此阅读并保留原文件。实现与测试阶段未启动或暂停已有科研 Run。

本次决策增量见 `docs/SPARSE_BRAIN_UPGRADE_DECISIONS.md`；原有历史决策日志不随本次升级重传。

## 位置与行为

- `controller.py`、`collab.py`、`decision_extraction.py`：执行器可经 `research_checkpoint.research_question` 迅速登记 async/blocking 问题；大脑以完整 `ResearchAnswer.answer_md` 判断，选项只用于原生可映射运输。答案连同 request_id 先事务化保存、生成一份指导，再在空闲/检查点自然边界投递；ACK 表示收到或异议，不代表已执行。过期、暂停、终止或额度不足时不能产生有效新行动。
- `research_trace.py`、`mcp_bridge.py`、`api.py`：大脑有独立角色令牌与单个只读 `research_trace` MCP，只有它主动 list/read 才查已保存的当前 Run 公开事件、检查点、可核实版本的冻结输入清单；按本次审阅 `through_seq`、范围、脱敏和额度限制，实际提供的片段记 `brain.trace_read`。执行器令牌不能读取，脑令牌不能写 Job/检查点。执行器重建只撤销执行器令牌，Run 结束撤销全部。
- `observation.py`、`controller.py`、`brains/{codex,kimi}.py`：长期研究会话默认接收高层研究状态、预算与未知，不再自动载入原始工具进展；研究级变化可稀疏唤醒，普通进度、活跃长 Job 和巡检不触发模型。维护整理使用单独会话，新脑会话不自动注入执行技能。
- `prime/kimi_acp.py`：已知 AskUserQuestion 表单可合法映射；自由答案不能映射时原生 decline/cancel，但全文仍经指导队列送达。非已知研究表单不代签。Codex 执行器通过共享 checkpoint 入口提问；没有凭空新增未验证的 Codex 原生 user-input 接口。
- `apps/web/src/pages/ResearchPage.tsx`：显示完整研究回答、原生映射/拒绝、正文投递与 ACK、最近唤醒原因及实际读取引用。

原来的 `answers` 非空、`options.const` 硬限制从**新 Run 内部研究回答**移至原生表单映射边界；500 字理由静默截断已移除。原生表单自身仍做 schema 校验。大脑可以同意，也可以否定前提、给第三路线或保留未知；没有强制反对、强制先读轨迹或二次审查。这些是传输与调度能力，真实模型是否独立判断尚未验证。

## 隔离回放与命令

使用 `tests/conftest.py` 的临时 SQLite/工作目录及 fake 原生会话，未触及本机历史科研 Run。`test_sparse_brain_open_answer_optional_read_and_delivery` 实际调用 checkpoint → 控制器审阅 → MCP HTTP → 指导 outbox → fake 执行器：第一次面对“是/否加倍内存”零读取，给出超过 500 字的第三路线，执行器收到全文并 ACK；第二次自行 list/read 一个未在问题中引用的失败回执，再收到并投递新判断。重复 checkpoint 只保留一份指导。另测角色/Run/未来序号/审阅状态隔离、冻结清单版本、长 Job 与研究级唤醒、Kimi 原生表单合法接受或拒绝。

执行命令与实际结果：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_collaboration.py -k 'not test_t13b_submit_guidance_failure_marks_failed and not test_t13_submit_guidance_auto_submits_without_executor'` | 55 passed，2 deselected |
| `.venv/bin/python - <<'PY'`（以下事件循环唤醒包装，运行 `pytest.main(['-q','-k','not test_cli_sigterm_exits_with_sse_client_still_connected'])`） | 最终 283 passed，1 deselected，46.51s |
| 同一唤醒包装运行 `pytest.main(['-q','tests/test_collaboration.py','tests/test_kimi_executor.py','tests/test_codex_brain_environment.py'])`（最后一次原生表单身份收紧后） | 74 passed，18.95s |
| `.venv/bin/python -m pytest -q tests/test_cli_shutdown.py::test_cli_sigterm_exits_with_sse_client_still_connected`（允许本机回环监听） | 1 passed，5.60s |
| `.venv/bin/python -m pytest -q tests/test_codex_brain_environment.py`（Kimi 原生 MCP 接线测试加入后） | 11 passed |
| `.venv/bin/python checks/evaluate_sparse_brain.py` | 3 个固定事实/不同诱导选项样例加载，0 个真实模型调用；人审入口，不以反对次数或读取次数计分 |
| `PATH=.../node-v22.17.0-linux-x64/bin:$PATH npm --prefix apps/web test -- --run` | 10 passed |
| `PATH=.../node-v22.17.0-linux-x64/bin:$PATH npm --prefix apps/web run build` | TypeScript 与 Vite 构建通过 |
| `.venv/bin/python -m compileall -q src/cyberscientist tests/test_collaboration.py checks/evaluate_sparse_brain.py`；`git diff --check` | 均通过 |

本机 Python 3.12 的普通 `asyncio.run(asyncio.to_thread(lambda: 1))` 在线程工作完成后仍可能挂在事件循环等待；未修饰的全量 `.venv/bin/python -m pytest -q` 卡在 Bohrium 连接测试。上表完整回归使用**仅在测试进程内**的定时唤醒包装：保存 `asyncio.BaseEventLoop.run_forever`，每 0.05 秒 `call_later` 唤醒一次直到循环退出，再交由 `pytest.main(...)` 运行；未改产品代码或测试断言。单独 CLI 用例需要监听 `127.0.0.1`，普通沙箱拒绝 socket，故单独在允许本机回环监听后执行。测试结果不应误写成未经包装的默认命令通过。

2026-09-26 纠正：最小复现进一步证明是此沙箱拒绝 socketpair 的 `send(2)`、允许 `os.write(2)`，不是 Python 3.12 本身的已知缺陷。当前 `tests/conftest.py` 仅在该限制出现时替换测试进程的 asyncio 跨线程唤醒写入；下面的定时包装仅保留作历史验证记录。

完整回归的临时包装（从仓库根目录执行）：

```bash
.venv/bin/python - <<'PY'
import asyncio, pytest
original = asyncio.BaseEventLoop.run_forever
def run_with_wakeup(self):
    def pulse():
        if self.is_running():
            self.call_later(0.05, pulse)
    timer = self.call_later(0.05, pulse)
    try:
        return original(self)
    finally:
        timer.cancel()
asyncio.BaseEventLoop.run_forever = run_with_wakeup
raise SystemExit(pytest.main(['-q', '-k',
    'not test_cli_sigterm_exits_with_sse_client_still_connected']))
PY
```

## 未验证边界

本轮未启动真实 Kimi/Codex 大脑、真实科研、Bohrium Job 或比赛提交。Kimi form 的本地映射与已存真实协议 fixture 对齐，但升级后的原生双会话完整往返待授权验证。Codex 大脑使用原生只读沙箱和项目 MCP allowlist；Kimi/Codex 内建工具是否可由当前版本完全硬禁用未经本轮探针确认，因此不能把提示中的“勿用 Shell”宣称为硬隔离。`research_trace` 返回本地已保存材料，不代表外部平台原始日志完整。保存的 `checks/fixtures/sparse_brain_independence.json` 及离线入口只为以后同模型、同强度、同事实、同预算并计入读取成本的有界比较准备，不证明已消除迎合。
