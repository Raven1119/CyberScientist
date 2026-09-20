# 非对称协作与静默监督 — 实施结果

日期：2026-09-18。对应任务卡 `START_KIMI_SHADOW.md`。交付工作树（未 commit/push）。

## 1. 审计复核（A1–A10 逐项）

复核基准为当前工作树（非远端 main）。结论：**A1–A10 全部仍存在，且已在本次施工中修复**。

| 编号 | 复核结论 | 修复位置 |
|---|---|---|
| A1 主循环 await 审阅阻塞事件处理 | 存在 | `controller.py::_review_worker` 单飞审阅 worker（DB 审阅请求为权威 + asyncio.Event 唤醒 + 稀疏兜底），结果由控制器短事务单点接受 |
| A2 审阅帧无科学证据 | 存在 | `observation.py::build_frame`：有界 ObservationFrame（题面/Trial/检查点正文带来源/事件摘要/经验正文/预算/quality.unknown_fields） |
| A3 检查点保存非原子、不能唤起大脑 | 存在 | `collab.py::submit_checkpoint`：单事务写 checkpoint+事件+审阅请求，内容哈希去重/冲突；MCP 与 UI 共用该服务 |
| A4 回合结束冒充 Trial 完成 | 存在 | `prime/kimi_acp.py` / `prime/codex_exec.py`：end_turn → `executor.turn_completed`；未知终态记 unknown，不再映射 trial.completed |
| A5 指导无可靠排队/确认 | 存在 | guidance 表持久化 outbox + 检查点工具返回/空闲边界双渠道互斥投递 + `ack_guidance` |
| A6 同会话重复 pump | 存在 | `start_pump` 单消费者守卫（同会话只允许一个消费者） |
| A7 多步写入各自 commit | 存在 | `db.transaction()`（BEGIN IMMEDIATE，事务内禁用旧 commit helper）+ `append_event_tx`；shadow 额度耗尽只降级监督不暂停 Run |
| A8 stderr 管道阻塞 | 存在 | `jsonrpc_stdio.py`：stderr 持续 drain（有界尾窗 20 行） |
| A9 stall 误判失败 | 存在 | 看门狗改为 stalled 告警一次后流保持开放；stall 只标 Trial 保留现场 + 生命周期审阅，不 abort 不判失败 |
| A10 大脑无独立视图/指令过期 | 存在 | 大脑 cwd=workspace/runs/{id}/brain_view；根 AGENTS.md 本次更新 |

**审计未列出、本次新发现并已修复**：
- N1：`prime/__init__.py::with_stall_watchdog` 用 `asyncio.wait_for` 直接包裹常驻 `__anext__`，超时 cancel 会污染异步生成器（后续迭代崩坏）。已改为 `asyncio.shield` 包裹常驻任务。
- N2（仅测试基建）：演示脚本曾在异步 main 中直接调用阻塞 urllib，uvicorn 与演示同循环导致全部超时；已全部改 `asyncio.to_thread`。
- N3（仅测试基建）：演示 `scripted_call` 的"调用计数 > 捕获基线"存在触发快于捕获的竞态；改为触发前捕获基线 + 按 frame_id 精确匹配。

## 2. 本次实现（已存在 / 缺口 / 最小修改）

**新增**：`collab.py`（契约校验、检查点、指导、ACK、能力令牌）；`observation.py`（观察帧 + 脱敏）；`mcp_bridge.py`（stdio MCP server → HTTP，Bearer 令牌走 env）；`prompts/collaboration/brain.md`（审阅提示词）；`db.py` 四张新表（supervision/review_requests/guidance/capability_tokens）+ checkpoints/runs 增列，全部幂等迁移；`tests/test_collaboration.py`（18 用例）；`checks/demo_collaboration.py`（21 项确定性演示）。

**修改**：`controller.py`（单飞审阅调度、优先级 blocking→lifecycle→user→executor→shadow、shadow 合并/节流/降级、gate 状态机 open|yielding|waiting_brain|stopped、stop 先关门等原生终态、重启对账）；`api.py`（supervision/review_requests/tools 端点，checkpoints 走 collab 服务）；两个执行器适配器（终态语义 + MCP 注入）；两个大脑适配器（review_result 协议）；`decision_extraction.py`（extract_review_result）；前端 ResearchPage 协作监督面板（真实 supervision 状态、开关、请求审阅、指导记录、大脑笔记）。

**设计修正（相对 SPEC/CONTRACTS 的最小偏差）**：
1. Codex 运行时的 per-thread MCP 注入能力本机未核实：该运行时暂缺检查点工具注入，指导仍经空闲边界 prompt 投递；能力矩阵如实标注，不假装已送达。
2. `ack_guidance` 原设计带 generation 参数但未校验（审查 S3）：改为签发新会话令牌前撤销本 Run 旧令牌（`controller.py::_prime_spec`），会话绑定在令牌鉴权层成立；移除死参数。
3. blocking 审阅无有效答复（失败/超额度/重启中断）：原语义"保持等待"会使 gate 永久卡死；审查后改为暂停 Run + block_reason，等用户处理，不自动放行（`_blocking_dead_end`）。

## 3. 有界代码审查结论（本轮已修复）

审查范围：collab/observation/controller 协作部分/mcp_bridge/api 端点/db 事务。发现与处置：

| 级别 | 问题 | 处置 |
|---|---|---|
| B1 | shadow_epoch 失效检查用 pending 快照行，恒不触发；在途 shadow 结果在监督关闭后仍生效 | 事务内重查请求行再比对 epoch；回归 test_b1 |
| B2 | `_strip_secrets`/`_redact` 只遮前缀，密钥主体（如 `sk-abc123` 的 `abc123`）照样进大脑 | 正则吞掉令牌主体 + 密钥块整体遮蔽；T10 断言加严为主体不残留 |
| S1 | 审阅完成时的投递旁路 phase/gate 检查，暂停期间可唤醒执行器 | `_deliver_queued_guidance` 入口校验 phase==running 且 gate==open；回归 test_s1 |
| S2 | blocking 请求终态化后 gate 永久卡死 | `_blocking_dead_end`：无其他在途 blocking 则暂停+原因；接额度耗尽/审阅失败/重启对账三处；回归 test_s2 |
| S3 | ack generation 参数死代码 | 签发前撤销旧令牌 + 删参数；回归 test_s3 |
| S4 | wake.clear() 与 _wake() 间丢失唤醒窗口 | clear 后重查请求队列（两处分支） |
| NOTE | 经验正文/题面未过脱敏（用户自有文本，风险低）；SSE 生成器无终态退出（客户端断开即清理，无泄漏）；shadow 额度在调用前扣减（记账诚实，失败也烧额度，属预期） | 记录在案，本轮不改 |

## 4. 验证证据（实际执行）

| 验证 | 命令 | 结果 |
|---|---|---|
| 全量回归 | `uv run pytest tests/ -q` | **56 passed**（38 旧 + 14 协作 + 4 审查回归） |
| 确定性演示（真实 uvicorn+SQLite+SSE+真实 MCP 桥子进程，合成证据已标记） | `uv run python checks/demo_collaboration.py` | **21/21 PASS**，时间线 `checks/results/collaboration_demo_timeline.txt` |
| 前端构建 | `cd apps/web && npm run build` | tsc 零错误，dist 含协作面板 |
| T12 浏览器路径（kimi-webbridge 驱动真实浏览器，真实后端 :8765 + 真实工作区 finished Run） | 见下 | 面板渲染真实监督状态；UI 开关监督落库（enabled 0→1→0，epoch 2）；finished Run 上"请大脑现在审阅"被后端 409 拒绝且 UI toast 如实呈现；页面重连后 phase/started_at 不变、无新 Run、面板仍在 |

T12 截图证据：`checks/shots/t12-01-supervision-panel-off.png`、`t12-02-supervision-panel-on.png`。

演示覆盖的验收语义：run_start 生命周期审阅→start_trial；SSE 实时推送；MCP initialize/tools/list/research_checkpoint/ack_guidance 真实子进程往返；SILENT 对执行器零打扰；忙时指导持久排队、空闲边界恰好投递一次、ACK；补报沿同一 Trial；shadow 指导在暂停时失效（invalidated 非删除）；重启后审阅/ACK/指导记录在、无重复外部操作、迁移幂等。

## 5. 尚未验证 / 阻塞项（准确清单）

- **真实模型的协作闭环未跑**：本轮无新费用授权，全部大脑/执行器为脚本化假协议实现；假协议不代表模型判断能力。真实联调（Kimi K3 / Codex Astra 大脑 + Kimi/Codex 执行器的 review_result 协议往返）标记**未验证**。
- Codex 运行时 per-thread MCP 注入能力未知（设计修正 1）；Codex 大脑/执行器全路径无额度未测。
- T12 的"请求审阅"正向路径（非 finished Run 上触发真实大脑审阅）因涉及模型调用未在浏览器路径执行；负向路径（finished→409）已验。
- `mark_applied` 尚无生产调用方（仅测试覆盖）：applied_reported 语义未接入检查点自动关联，属未接线而非错误。
- 监督开关在 finished Run 上允许切换（语义无害：只影响观察 epoch；如需严格可在后续限制阶段）。
- 启动命令：`uv run cyberscientist start`（自动构建前端 + 同端口服务 + 开浏览器）；仅后端：`uv run cyberscientist serve --port 8765`。

## 6. 增量：大脑 submit 指导 + 后台评分轮询（2026-09-18）

**需求**：只有收割提交需要用户手动确认；实验邮箱提交 = 大脑向控制器发指令 → 系统自动提交 → 异步评分等待。

**实现**：
- `docs/collaboration/contract.schema.json` Guidance.kind 枚举增加 `submit`；CONTRACTS.md 记录语义（系统级动作、非执行器文本、幂等、失败不自动重试）。
- `controller._apply_review_result`：kind=submit 的 guidance 创建即标 `sent/system_action`（投递循环永不拾取），事务外 `asyncio` 调度 `_execute_submit` → `mailboxes.submit_experiment`（幂等键 `auto-{guidance_id}`）；成功标 `applied` + 记 `submission.auto_done`，失败标 `failed` + 记 `submission.auto_failed`（含平台错误码）。
- `api.py` lifespan 后台评分轮询（45s）：`poll_scores` 在线程中执行，评分器排队/409/5xx 全部容忍下轮重试；替代任何同步等分路径。
- 双大脑提示词（kimi.py/codex.py）与 `prompts/brain.md` 告知 submit 语义与使用时机（结果包就绪 + 诚实性自检通过；收割永不由大脑发起）。

**验证**：`uv run pytest tests/ -q` **84 passed**（新增 T13/T13b/schema 3 用例：自动提交不投递执行器不改门禁、幂等键绑定、失败标 failed 不重试、schema 接受 submit）。

**背景实测（促成该改动的全链路）**：Aiyagari 题 attempt 44534（缺图被拒）→ 44579（创建时挂 4 图 + ARM bundle，submit 200，数值分 43.57 已出，图比对平台 pending）；详见 STATUS.md 与 DECISIONS.md 对应条目。
