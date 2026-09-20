# 当前状态

日期：2026-09-17。

| 类别 | 当前事实 |
|---|---|
| 已提供 | 设计/接口/前端/经验/实施文档、开工提示词、配置与 Decision Schema、模板、交互原型 |
| 已实现的产品 | 尚无真实生产后端或 React 应用；HTML 原型只供交互参考 |
| 外部接口 | 已查阅官方入口/文档，见 REFERENCES；未做账户认证或真实调用 |
| 真实费用与提交 | 未调用模型、未创建 Bohrium Job、未创建比赛 Attempt |
| 首个施工目标 | BUILD 阶段 1：单题单 Run 的前后端垂直切片 |

## 施工记录

### 2026-09-17 · 生产前端（apps/web）

**已实现**：Vite + React 18 + TypeScript 单页应用（无 UI/路由/状态库），左侧深色导航三页（研究工作台 / 经验库 / 连接与设置）。全部数据来自 `127.0.0.1:8765` 真实 API（dev 代理 `/api → 8765`），未复制原型演示逻辑。统一 fetch 封装处理 401 `PAIRING_REQUIRED`（弹出配对对话框）、CSRF（sessionStorage 存 token）、`{"detail":{code,message}}` 错误信封；409 `REVISION_CONFLICT` 在经验页显示左右对照视图（放弃/用当前内容重试）。SSE 事件流按 seq 去重、断线按最大 seq 重连、卸载关闭；事件流自动滚动但不强迫上翻的用户，提供“回到最新”。演示模式固定显示徽章；密钥输入保存后清空、只显示“已配置”。

**已实际验证**：
- `cd apps/web && npm install && npm run build` 通过（tsc + vite，`dist/` 产物约 209KB，JS gzip 62KB）。
- `npx vite` dev server 页面可加载，`/api/v1/health`、`/api/v1/session` 经代理返回真实数据。
- curl 实测：配对（set-cookie HttpOnly + `X-CSRF-Token` 响应头）、导入演示题目、创建 Run → authorize → start（phase=running）、demo Run 完整跑到 finished、finished 上 pause 返回干净的 `INVALID_STATE` JSON、checkpoints GET `{"items":[…]}`、SSE 事件格式（`id:`/`event:`/`data:` 行，data 含 seq/source/type/payload）、run detail 的 trials/budget 字段形状（`known_cost:null`、`unknown_cost:true` 均按“未知”渲染，绝不显示 0）。
- 未配对写请求返回 401 `PAIRING_REQUIRED`，前端据此弹配对对话框。

**尚未验证**：浏览器内整页点击流（未跑浏览器自动化）；经验 409 冲突对照视图的端到端点击；`POST /secrets` 与 `connections/*/test` 的真实后端响应（后端可写会话被并行进程反复重启，多步写流程不稳定）。

**阻塞项**：运行中的 8765 后端被外部反复重启（观察到的 PID 多次变化，会话 cookie 随之失效）；历史 Run `run_586a3645c7` 的 `GET /runs/{id}` 与 events 稳定 500（后端序列化问题，前端已容错不崩溃）。

工程包自身的检查记录见 `PACKAGE_VALIDATION.md`。施工代理之后在本文件追加实际实现、命令、测试结果与阻塞项，不删除本次交付边界。

## 施工记录（主代理 · 阶段 1 垂直切片）

### 2026-09-17 · 后端与全栈闭环（src/cyberscientist + apps/web）

**已实现**（Python 3.11 + FastAPI + SQLite，React 18 + TS + Vite）：
- 配置/秘密分离：`.cyberscientist/settings.json`（非秘密，带 revision）与 `secrets.json`（0600）；密钥只经 `SecretRef`（`env:`/`local:`）解析，不回显、不入事件/经验/日志。
- 本地会话：首启生成配对码（仅后端控制台输出）→ HttpOnly + SameSite=strict cookie + CSRF 双提交；写请求全量鉴权，`/connections/*/test` 同受保护。
- 题目导入：演示题目、手动导入（标题+题面）；URL 导入在缺 Playground Token 时返回准确缺项，不编造平台响应。
- Run 闭环（Demo 模式）：授权 → 启动 → Demo 大脑产出 schema 合法 Decision → Trial 创建（含经验快照 `memory_manifest.json`）→ Demo Prime 事件流 → checkpoint/trial 完成 → 大脑 finish；事件以 `(run_id, seq)` 唯一约束追加，SSE 按 seq 续传。
- 控制语义：steer 只报 queued，以 `steer.consumed` 事件确认生效；pause 显示 pausing，代理确认才 paused；terminate 不改写已终态 Run；暂停期间迟到的 Prime 事件只记账不推进状态。
- 决策管线：按 `contracts/decision.schema.json` 结构校验 + 语义校验（单主动作、steer 需匹配当前 Trial、提交需策略允许）；stale `state_version` 保存不执行；全局晋升拒绝（需人工审查）。
- 经验：Markdown 文件为编辑界面 + SQLite 修订历史（内容寻址 hash）；PUT 必须带 base_hash，冲突 409 返回双方内容；回滚幂等指向已有修订；外部编辑可检出；崩溃对账（applied=0 核对）。
- 大脑适配器：Codex（`codex app-server` stdio JSON-RPC，实测 0.154.0-alpha.6.2 initialize 握手）；Kimi 边界（未接入，明确显示，不退化为普通 API）；Demo 大脑。
- Prime 适配器：RPC 协议壳（未安装时如实报告，不启动真实会话）+ Demo 执行器。
- 有界授权强制：大脑判断上限、Trial 上限、运行时长上限在控制器强制执行；模型 turn 上限标记 `enforced:false`（阶段 1 无真实模型调用路径）。
- 操作幂等：control 携带 operation_id，校验通过才落库，重复请求去重；并发 start 由 `created→running` 条件更新原子抢占；工作区文件锁拒绝第二个控制器进程。

**已实际验证**：
- `uv sync` + `uv run pytest tests/ -q`：**31 passed**（决策校验、经验冲突/回滚/外部编辑、事件 seq/幂等、控制器全闭环/暂停恢复/去重/connected 阻塞、JSON-RPC 分帧 synthetic fixture）。
- `uv run cyberscientist serve --port 8765` + `uv run python checks/smoke_vertical_slice.py`：**22 PASS / 0 FAIL**，覆盖配对、未授权启动拒绝、导入、授权、启动、SSE 事件序列、暂停/恢复、steer 队列语义、operation_id 去重、经验编辑/409 冲突/回滚、连接探针、未确认消耗被拒。
- 重启后可见：kill 后端 → 重新 serve → runs/trials/经验候选完整读回。
- 真实探针：`uv run python checks/probe_integrations.py` → `docs/INTEGRATION_STATUS.md`（Codex 版本 + initialize 握手原始返回，零模型调用）。
- 前端：`cd apps/web && npm run build` 通过；后端托管 `dist/`，SPA 路由与 API 同端口验证。
- 有界代码审查 1 次（子代理），5 项阻断 + 6 项中危已全部修复并复测通过（主循环超时不再杀 Run、operation_id 校验后落库、start 并发原子抢占、暂停期事件门禁、终态保护、授权上限强制、连接测试写保护、密钥形态脱敏入库、经验文件原子替换等）。

**尚未验证**：
- Codex `thread/start`、`turn/start` 字段形状与终态事件（Codex 侧模型往返仍待授权；Prime 侧真实往返已于 2026-09-18 完成）；bohr 全部能力；Playground API 载荷。
- 后端崩溃恢复中对远程 Job/Attempt 的挂接（阶段 2 范围，本地状态已可重启读回）。
- 浏览器内 409 冲突对照视图的点击流（API 层已验；视图代码与后端契约核对一致）。
- `--session-dir` 项目隔离两 Profile 不串配置测试；steer/abort 真实消费确认。

### 2026-09-18 · Prime 真实模型工具往返（DeepSeek V4.1 Flash via OpenRouter）

**已实际验证**：
- 供应商：OpenRouter，模型 `deepseek/deepseek-v4.1-flash`（$0.15/$0.6 每 M token，支持工具）。密钥存 `local:openrouter_api_key`（0600，不入 Git/日志/经验），Prime 经 `OPENROUTER_API_KEY` 环境变量引用（models.json 无明文），子进程环境 allowlist。
- `checks/probe_prime_roundtrip.py`：prompt 受理 → agent_start → **ipython 工具写读文件** → tool_execution_end → agent_end → 终态文本与文件内容一致（marker 校验 PASS）；53 条事件流脱敏存 `checks/fixtures/real/prime-rpc-deepseek-v4.1-flash.jsonl`。
- 用量成本（prime `get_session_stats` 实测上报）：input 6749 / output 129 / cacheRead 5120 tokens，**$0.00185775**。
- 回归：pytest 31/31。
- 选型负面试试证：`z-ai/glm-5.2:free`（OpenRouter 唯一免费 GLM）不支持工具，路由层 404（"No endpoints found that support tool use"）；智谱官方「GLM-5.3-Flash 夜间畅用」（9/3–9/20，23:00–09:00）免费仅限 ZCode IDE，第三方 Agent 仅额度 ×2。两条免费 GLM 路径均不可用于 Prime 工具循环。

**阻塞项（准确缺项）**：
- Prime Agent **已安装 v0.9.5 并完成零模型调用探针**（详见下方 2026-09-18 记录）；真实模型回合仍需你配置模型供应商并授权额度。
- `bohr` CLI 未安装、Playground Token 未配置 → 题目 URL 导入与 Bohrium 计算不可用（阶段 2）。
- 无 `kimi --wire` 可执行文件 → 第二大脑未接入（边界保留，阶段 3）。

### 2026-09-18 · Prime Agent 安装与真实探针

**事实**：官方安装脚本仅支持 macOS/Linux；实际安装路径为官方发布渠道 `npm install -g`（R2 发布桶 tarball，SHA-256 校验通过，190 包）。上游包名 `@earendil-works/pi-coding-agent`，bin `prime-agent`，配置目录 `.prime/agent`。

**已实际验证**：
- `prime-agent --version` → 0.9.5
- 适配器 `PrimeRpc.inspect()`：RPC 模式启动 + `get_state` 零模型调用响应，返回 `sessionId/isStreaming/steeringMode/sessionActions` 等字段，与官方 docs/rpc.md 一致（原样记录于 `docs/INTEGRATION_STATUS.md`）
- API 链路：connected 模式下 `POST /connections/prime/test` 返回 ok + 0.9.5 + 探针详情
- 回归：pytest 31/31、smoke 22/22 无退化

**协议修正**：上游是 type-tagged JSONL（`{"type":...}` + 可选 `id` 关联），**不是 JSON-RPC**；响应 `{"type":"response",success}`，事件与 `extension_ui_request` 同流，后者必须应答否则代理悬挂。适配器 `src/cyberscientist/prime/rpc.py` 按官方 v0.9.5 文档重写。

**未验证**：prompt/steer/abort 真实模型回合（需供应商配置 + 额度授权）；`--session-dir` 项目隔离两 Profile 不串配置测试；get_session_stats 成本上报实测。

**浏览器级验证（2026-09-17，kimi-webbridge，真实浏览器）**：
- 页面加载、演示模式徽章、配对对话框 → 输入配对码 → 会话建立（写请求可用）。
- 导入演示题目 → 题目栏显示 DEMO_CHALLENGE 与契约状态；历史 Run 状态正确显示“已完成”。
- 开始研究 → 预检与授权对话框（模型调用勾选、判断/时长/提交上限）→ 确认启动 → SSE 事件流实时渲染（大脑 Decision、Trial 创建、执行器事件、Trial 完成），Run 摘要费用显示“未知”而非 0。
- 经验库：Run 结束大脑提议的候选经验出现在列表（题目内/候选/假设徽章），编辑器 frontmatter 表单与 Markdown 正文完整。
- 连接与设置：大脑卡（Codex App Server/原生登录/检查安装/消耗额度确认勾选）、Prime 卡渲染正确。
- 截图证据：`checks/shots/01-workbench-paired.png`、`02-run-events.png`、`03-experience.png`、`04-settings.png`。
- 遗留：409 冲突左右对照视图未点击验证（API 契约已验）。

### 2026-09-18 · 阶段 1.5/1.6：Kimi 大脑接入 + 执行系统三选一（默认 Kimi Code）+ 去配对码 + 一键启动

**已实现**：
- 大脑可切换：`settings.brain.runtime` ∈ kimi（默认，kimi-code/k3）/ codex（gpt-6-astra，无额度未跑）；思考强度可调（ACP `session/set_config_option configId=thinking`，实测档位 low/high/max，UI 通用档映射 xhigh→max）。
- 执行系统三选一：`settings.executor.runtime` ∈ **kimi（默认，kimi-code/k3-256k，high）**/ prime（DeepSeek V4.1 Flash via OpenRouter）/ codex（gpt-5.6-terra xhigh，**代码就绪未实测**）；`KimiExecutor`（`prime/kimi_acp.py`，ACP yolo 模式工具自动批准+全程留痕）与 `CodexExecutor`（`prime/codex_exec.py`）实现 `PrimeRuntime` 协议。
- 挂起看门狗：`with_stall_watchdog`（240s 无事件判挂）两个执行器共用；stall → abort + 记 failed + **关旧会话开新会话 + 重启事件泵** + 大脑裁决；Trial 正常完成后新回合自动重启泵。
- 去配对码：后端仅 127.0.0.1 无认证（用户确认）；前端配对门/CSRF 全删。
- 配置同步：secrets.json 单一事实源；`~/.prime/agent/models.json` 由后端从 llm_profiles+secrets 自动重建（启动/保存时），GET settings 回 `_status.secrets` 与 `prime_models_synced` 真实回读状态。
- 一键启动：`uv run cyberscientist start`（自动构建缺失的前端 + 同端口服务 + 开浏览器）。
- 全程可视：`brain.review_started` / `brain.raw_output`（折叠）/ `prime.execution.progress`（思考+工具调用+工具结果）/ `prime.approval.granted`（琥珀高亮）/ stall 红色警示；前端来源徽章（大脑紫/执行器蓝/控制器灰/用户绿）。

**已实际验证**：
- ACP 协议探针（真实 K3 调用）：`session/new`（mcpServers 必填）、set_model、set_config_option（thinking/mode）、yolo 免权限写文件 PASS（`checks/probe_kimi_executor*.py`）。
- **默认路径全真实闭环**（`checks/smoke_connected_real.py`，run_9785db28ab）：**10 PASS / 0 FAIL**。K3 大脑 3 次 review；Trial 1 基线产出（RandomForest，验证 F1 0.8827），Trial 2 结果验证与提交格式核对；K3 主动 finish（理由：闭环达成、无 bundle_manifest_ref 不提交）。产物：workspace/challenges/DEMO_CHALLENGE/{model.joblib, submission.csv, baseline_report.json, result_package.json, evidence.json}。
- 重启后可见：kill 后端 → serve → run 快照 phase=finished、两 Trial done、SSE 回放 80+ 帧、产物文件齐全。
- 回归：`uv run pytest tests/ -q` **38 passed**（新增 KimiExecutor 映射 + 看门狗单测 7 项）；前端 `npm run build` tsc 零错误。
- 排障实战记录：run_7865220639（DeepSeek 模型调用悬挂 8 分钟 → 看门狗需求）、run_19c53aed8c（stall 后旧会话拒绝新输入 → 会话重建修复）、run_82d3af8c4e（trial.completed 后泵退出 → 泵重启修复）。

**尚未验证**：
- Codex 执行器全路径（无额度）；`session/load` 会话恢复；Kimi 长任务 compaction；ACP usage/token 统计字段（费用仍记 unknown，不显示 0）。
- Codex 大脑 Astra xhigh 真实 Decision 往返（无额度）。
- Kimi 执行器 steer 回合内插入（ACP 不支持，现如实 rejected）。

**已知问题（留阶段 2）**：
- 连接探针（inspect）spawn 的 RPC 进程残留不退。
- 挂起 Trial 的半成品产物如何计入证据链（当前记 failed，产物保留在 workspace）。
- 执行器包目录仍名 `prime/`（改名 executors 属留债）。

### 2026-09-18 · 收尾修复：已结束 Run 事件流回放

- **Bug**：ResearchPage 仅在 Run active 时订阅 SSE（`ResearchPage.tsx`），已结束 Run 打开后显示“还没有研究事件”，历史事件不回放。
- **修复**：只要有选中 Run 即连接事件流（服务端对 ended Run 一次性回放后静默）。浏览器实测 run_9785db28ab（finished）回放 87 帧完整时间线，截图 `checks/shots/finished-run-events-replay.png`。
- 回归：前端 `npm run build` 零错误；`uv run pytest tests/ -q` 38 passed。

### 2026-09-18 · 非对称协作与静默监督切片（START_KIMI_SHADOW）

**已实现**：大脑单飞审阅 worker（DB 请求为权威，优先级 blocking→lifecycle→user→executor→shadow）；有界 ObservationFrame（题面/检查点正文/经验正文/预算/unknown_fields，密钥主体脱敏）；检查点统一服务（事务原子、哈希去重）；指导持久化 outbox（忙时排队、空闲边界/检查点返回互斥投递、ACK、暂停时 shadow 指导失效）；gate 状态机（open|yielding|waiting_brain|stopped，blocking 无答复暂停不暗中放行）；MCP 桥（stdio→HTTP，短时能力令牌只存 sha256，新会话签发撤销旧令牌）；执行器终态语义（turn_completed 不再冒充 trial.completed，stall 只告警不判失败）；前端协作监督面板（真实状态/开关/请求审阅/指导记录/大脑笔记）。详见 `docs/collaboration/IMPLEMENTATION_RESULT.md`。

**已实际验证**：`uv run pytest tests/ -q` **56 passed**；`uv run python checks/demo_collaboration.py` **21/21 PASS**（真实 uvicorn+SQLite+SSE+真实 MCP 子进程）；前端 `npm run build` 零错误；T12 浏览器路径（kimi-webbridge + 真实后端）：面板渲染真实状态、UI 开关监督落库、finished Run 请求审阅 409 如实呈现、重连不重启 Run（截图 `checks/shots/t12-01/02-*.png`）；有界代码审查 1 次，2 项阻断 + 4 项应修全部修复并回归。

**尚未验证**：真实模型（Kimi K3/Codex Astra）的协作闭环——本轮无新费用授权，大脑/执行器均为脚本化假协议，不当作真实联调通过；Codex 运行时 per-thread MCP 注入能力未知；`mark_applied` 未接生产调用方。

**已知问题**：监督开关在 finished Run 上允许切换（语义无害）；连接探针 spawn 的 RPC 进程残留（沿用既有遗留）。

### 2026-09-18 · 邮箱管理双轨（收割/实验）

**已实现**：
- 数据模型：`mailboxes`（harvest 全局唯一由 DB 部分唯一索引强制）+ `submissions`（score 未知即 NULL、operation_id 幂等、收割行引用来源提交），幂等迁移。
- 服务层 `mailboxes.py`：收割邮箱配置（凭据入 secrets.json 不回显）、实验邮箱批量注册（适配器边界）、实验提交（授权 max_submissions 首个真实强制点 + 邮箱配额原子预占 + 包 sha256）、评分轮询（拉不到保持 unknown）、收割候选排名、收割提交（confirm + 最高分 + 哈希未变三重硬校验）。
- 平台适配器 `mailbox_platform.py`：demo（本地合成，is_demo 标记，无评分能力如实 unknown）/ bohrium_playground（骨架，报准确缺项，不编造响应）。
- API：`/mailboxes`（GET/POST harvest/POST register/DELETE）、`/runs/{id}/submissions`（GET/POST）、`/submissions/poll`、`/harvest/candidates`、`/harvest/submit`。
- 前端新页「邮箱与提交」（导航 03）：收割配置卡、实验邮箱表+批量注册、收割候选+二次确认 Modal、提交记录（分数未知显示"未知"）。
- 顺手修复：GET settings 的瞬态 `_status` 被 PUT 回写落盘的既有 bug；`contracts/config.schema.json` 对齐现实（executor/shadow/mailbox/revision 等）。

**已实际验证**：`uv run pytest tests/ -q` **64 passed**（新增 8 用例：harvest 唯一/更换、demo 注册、真实平台缺项、配额+授权+幂等、无邮箱拒绝、轮询 unknown→scored、收割资格全拒绝路径+篡改拒绝、API 全链路）；`npm run build` 零错误；真实后端 curl 冒烟（注册/收割配置/重复 409/授权 0/0 拒绝/候选空/轮询）；浏览器实测页面渲染真实数据（截图 `checks/shots/mailbox-page.png`）。

**尚未验证**：真实平台的注册/提交/查分 API（Bohrium/Playground 凭据与接口形状待用户配置后做最小探针再接通）；大脑的 request_submission 动作仍 deferred，提交只由用户在 UI 发起。

### 2026-09-18 · Playground 真实平台适配器接通（邮箱双轨 → bohrium_playground）

**已实现**：
- `BohriumPlaygroundPlatform`（`src/cyberscientist/mailbox_platform.py`）按官方文档快照 `checks/results/AGENT_API.md`（GET /api/docs/dev/AGENT_API.md，46KB 全文）实现：注册=Option A（人类 token `POST /api/agent/register` → 立即得 agent asp_ token）；提交=草稿 attempt（multipart：method/type=agent/status=draft/outcome/trace）→ zip 包 `POST /attempts/{id}/bundle` → `POST /attempts/{id}/submit`；查分=`GET /attempts/{id}/score`，仅 `scoringState.scoreIsFinal=true` 采信。
- 接口演进：`submit_package` 增加 `challenge_id`/`meta`；`submissions` 表新增 `platform_ref`（幂等迁移）存平台 attempt id；poll_scores 用它查分。
- settings `mailbox.platform` 已切到 `bohrium_playground`；收割邮箱 wmywbyt42@gmail.com（asp_ token）active；既有 demo 实验邮箱保留并如实标记 is_demo。

**已实际验证**（全部只读探针 + mock 单测，零真实写操作）：
- 只读探针：`/auth/me`（人类账号 id 90229）、`/agent/work`（challenge id 为 slug）、`/agent/register` 列表（已有 agentmaster-02/03，证明 Option A 对该账号可用）、公开 attempt 的 `/score` 形状。脱敏结果 `checks/results/platform_probe2.json`、`checks/results/score_shape_probe.json`。
- `uv run pytest tests/ -q` **79 passed**（`tests/test_mailbox_platform.py` 12 用例 + `tests/test_mailboxes.py` 11 用例）。
- 有界代码审查 1 次（子代理），1 项阻断 + 3 项应修全部修复并复测：阻断=平台提交误用本地 challenge id（改为 JOIN 取 `platform_challenge_id`，demo:// 目标在适配器侧如实拒绝）；应修=注册错误消息不再 dump 响应体（防 token 泄漏）、平台调用兜底 `except Exception` 保证配额补偿事务执行、poll_scores 对无 platform_ref 的行不再拿内部 id 误查；另补 multipart 文件名消毒、URL quote、`.ZIP` 大小写、真实 `_http` 层（mock urlopen）覆盖。
- 前端 `npm run build` 零错误；后端重启后 `/api/v1/mailboxes` 报 `platform=bohrium_playground, is_demo=false`。

**尚未验证（需用户逐次触发的真实写操作）**：真实注册 agent 账号（前端「注册实验邮箱」按钮即首次真实调用）、真实提交 attempt、真实评分回拉。

**阻塞项（准确缺项）**：Bohrium 计算 API host 未定（`openapi.bohrium.com` DNS 不解析；bohr CLI 未安装，官方默认 host 为 `https://open.bohrium.com`，见 AGENT_API.md CLI 节）——Bohrium Job 科学计算仍未接通（阶段 2 范围）。

### 2026-09-18 · Aiyagari 全链路真实闭环 + 大脑 submit 指导 + 后台评分轮询

**题目**：`aiyagari-1994-qje`（Aiyagari 1994 QJE Table II 复现，programmatic_grader）。Run `run_9851070f39`（Kimi K3 大脑 6 次 review + Kimi 执行器实测求解 8 组均衡），诚实结果自检 **5/8**（μ=5 三组 r 系统性偏高 7%–31%，Rouwenhorst 消融未完成），产物 `workspace/challenges/local_c2643b50/`。

**真实提交记录**（实验邮箱 `cyberscientist-exp-b8f242`，本题额度 10）：
- attempt **44534**：首次提交（resultsJson 8 组已落平台）→ 评分被拒，要求 authentic result figures；补传 ARM bundle 200，重评仍拒。实测确认：已提交 attempt **PATCH 405**（draft-only）、hackathon 题 **fork 403**。
- attempt **44579**：新建 draft 并在创建时附 4 张真实复现图（纯 stdlib PNG 渲染器 `checks/gen_figures_stdlib.py`，因 pypi.org 不可达无 matplotlib；Fig3 数据为 8 个 r 点真实 VFI）+ results_json + ARM bundle → submit 200。数值分 **43.57** 已出；4 张图 SSIM 比对在平台队列 pending 超 15 分钟未终态（评分器抽风实证）。
- ARM bundle 评分：executability 0.5 / packaging 0.83 / trace_quality 1.0，缺 manifest 记为改进项。

**已实现（本轮代码改动）**：
- 大脑 `kind=submit` 介入指导（契约 schema + CONTRACTS.md + 双大脑提示词 + prompts/brain.md）：结果包就绪时大脑发指令，控制器自动用实验邮箱提交（`controller._execute_submit`，幂等键 `auto-{guidance_id}`），**不投递执行器、不改门禁、无需用户确认**；失败记 `submission.auto_failed` 并标 guidance failed，不自动重复配额动作。收割提交仍必须用户手动确认（不变）。
- 服务端后台评分轮询（`api.py` lifespan，45s 间隔）：评分器抽风/排队全部吞掉下轮再试，替代同步等待。
- 真实平台误选 demo 邮箱的 bug 修复（此前提交 401 根因）：邮箱选择按 `platform + is_demo` 过滤。

**已实际验证**：`uv run pytest tests/ -q` **84 passed**（新增 3 用例：submit 指导自动提交且不投递执行器、提交失败标 failed 不重试、契约 schema 接受 kind=submit）；新后端启动健康，`POST /submissions/poll` 拉回 2 条 pending（44534/44579），后台轮询运行中。

**尚未验证 / 留债**：
- attempt 44579 终态分数未回（评分器 pending）；后台轮询会自动落库，届时 `submissions.score` 可见。
- **提交流水线不含图生成/图上传能力**：本轮 4 张图与重提交由 `checks/` 临时脚本手动完成——适配器应在 submit_package 中支持 figures 创建时附带（平台只接受创建时挂图）。记为阻断级产品缺口。
- μ=5 三组数值未修（额度剩 8/10，可再跑一轮迭代后第 3 次提交）。
- WebBridge 截图证据未补（等评分终态一起截）。

### 2026-09-18 · 前后端对齐审计与修复（用户可全程前端控制）

**审计**：子代理逐项比对 api.py 全部路由与前端 4 页调用，产出 19 项清单；本次修复全部 4 项严重 + 6 项中等 + 5 项轻微。

**已修复**：
- 严重：① playground/bohrium 连接测试响应补 `health` 子结构（原前端渲染崩溃白屏）；② 新建经验用户自选 id 被后端覆盖→前端 404（POST 现在带顶层 `id`）；③ llm_profiles 关联键统一为 `id`（前端 Profile 编辑器加 ID 字段、下拉按 id 关联，后端 `p.get("id")` 容错）；④ Settings 类型与 UI 补 `shadow`/`mailbox` 段，新增「运行模式与监督」卡片（app.mode、mailbox.platform、shadow 上限/间隔均可 UI 编辑）。
- 中等：⑤ steer 状态改听 `guidance.sent`（原等永不发生的 `prime.steer.consumed`，文案同步改为"等待大脑审阅后投递"）；⑥ 邮箱页提交留空时带 `current_trial_id` 并显示将提交的 Trial；⑦ 检查点表单删除无效的 Trial 选择器（后端按活跃 Trial 绑定）；⑧ 密钥保存后自动把 `local:<id>` 引用写回 settings 并落盘（原保存后连接测试仍"未配置"），另加密钥删除按钮（接 DELETE /secrets/{id}）；⑨ 授权 scope 按真实模式传（demo/model_roundtrip）；⑩ 模型往返按钮只留大脑，后端对其它连接明确 501。
- 轻微：capabilities 按对象渲染、checkpoint 事件 source 用真实来源、422 校验错误消息完整展示、密钥状态去掉假回退、RunPhase 补 `recovering`、SOURCE_LABELS/AVATAR 补 `executor`。

**已实际验证**：`uv run pytest tests/ -q` **84 passed**；`npm run build` 零错误；curl 实测 playground/bohrium 测试返回完整 health、非大脑往返 501；WebBridge 真实浏览器：设置页 6 卡片（运行模式 connected / 邮箱平台 bohrium_playground 真实回读、Profile 下拉按 id、3 个删除按钮、往返按钮仅大脑）、Playground 连接测试渲染健康详情不再白屏、邮箱页 Trial 提示真实 id、研究页完成态 Run 时间线完整。截图 `checks/shots/align-research.png`、`align-settings.png`。

**仍未做（明确边界）**：经验冲突首次 422 的 details 字段补齐；产物下载（GET artifacts）未加 UI 入口；URL 导入仍为有意未实现（返回准确缺项文案）；挑战切换下拉以外的多 Run 管理 UI（邮箱页只展示最新 Run 的提交）。

**提交与评分页接通**：ResearchPage「提交与评分」标签页从占位文案改为真实实现（`/runs/{id}/submissions` 列表 + 轮询按钮 + submission.* 事件联动刷新），WebBridge 实测渲染真实记录（截图 `checks/shots/align-submissions-tab.png`）。前端 build 零错误，回归 84/84。

**44579 评分状态定论**（2026-09-18 22:55 POST /score 实测）：平台返回 200 `pending:true`——"The plausibility reviewer is temporarily unavailable... will be re-scored once the reviewer is back — the displayed score is not final"。即 **43.57 是平台侧评审服务宕机期间的非终态中间分**，图比对 pending 非我方问题。服务端后台轮询继续，终态自动落库。

### 2026-09-18 · bohr CLI 安装与认证（科学计算通路第一步）

**已实际验证**（全部零算力只读）：
- `npm install -g @dptech-corp/bohr-cli@latest` → **bohr 2.7.0**（官方 npm 渠道；未设 OPENAPI_HOST，用 2.6+ 默认 host `https://open.bohrium.com`，见 AGENT_API.md 实测表）。
- `bohr auth login --ak <AccessKey>` → "Login successful. Access key saved. Vouch tokens obtained."。AccessKey 只存 `secrets.json`（`bohrium_access_key`），登录全程脚本内引用不回显。
- `bohr auth whoami` → user_id 90229（与 Playground 人类账号同一身份）、orgId 89867、余额 183.76；`bohr job list` 返回真实历史 Job（只读）。
- 后端 `/connections/bohrium/test` 从"只查文件存在"升级为真实探针：`--version` + `auth whoami`，现返回 installed=true / authenticated=true / version=2.7.0；并修复 Windows 下 `.cmd` shim 需 `cmd /c` 包裹、PATH 回退（settings.executable 为空时找 PATH）两处问题。
- 回归 84/84。

**仍然未做（准确边界）**：`bohr job submit` 未接进 Run 流水线——科学计算任务提交能力仍缺（需 Job 模板/镜像/计费确认，属下一阶段）；Aiyagari 的数值计算是本地跑的（已知 Bohrium-first 偏差，STATUS 前文已记）。

### 2026-09-18 · Bohrium 官方技能包安装（含 LKM）

- `npm install -g bohrium-skills-cli`（官方 dptech-corp 包）。**Windows 打包 bug**：postinstall 把 Windows 二进制下载为无扩展名文件导致 ENOENT；手动改名 `bin/bohrium-skills-cli.exe` 后补跑 postinstall 成功（已向 DECISIONS 记录，上游 0.1.1）。
- 安装 17 个官方技能到 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`：bohrium-job（计算任务管理）、**bohrium-lkm**（大知识模型：命题检索/推理链/论文知识图谱）、paper-search、dataset、sandbox、image、node、project、sciencepedia、web-search 等。已同步到 `~/.kimi-code/skills` 供 Kimi Code（含执行器）使用。

**执行器可调 Bohrium（不接流水线，仅保证可调）**：Kimi/Codex 执行器继承完整环境、Prime 执行器 env allowlist 含 PATH/USERPROFILE/HOME/APPDATA——用 Prime 同款 allowlist 实测 `bohr --version` 与 `bohr auth status`（logged_in=true, access_key, open.bohrium.com）均通过（零算力）。`bohrium-*` 技能已同步到 `~/.kimi-code/skills`（Kimi 执行器）与 `~/.codex/skills`（Codex 执行器）。`prompts/collaboration/executor.md` 补 Bohrium 环境说明：bohr 已认证可用、技能按各自 SKILL.md 调用、计费 Job 受 Run 授权 max_jobs 约束、未授权如实报缺口。

### 2026-09-18 · 技能管理系统（常驻 + 随题目自动启用）

**已实现**：
- `src/cyberscientist/skills.py`：扫描 `~/.kimi-code/skills`、`~/.agents/skills`、`~/.codex/skills` 下含 SKILL.md 的子目录，解析 frontmatter（复用项目已有 pyyaml），多目录同名去重；`effective_for()` 合并常驻 ∪ 本题绑定并跳过失效引用。
- 存储：settings 新增 `skills.always_on`（常驻）；新表 `challenge_skills(challenge_id, skill_id)` 存题目级绑定（幂等建表）。
- API：`GET /api/v1/skills?challenge_id=`、`PUT /api/v1/skills/always_on`、`POST/DELETE /api/v1/challenges/{cid}/skills[/{skill_id}]`，无效 skill id 过滤/404。
- 启用机制：controller start_trial 把生效技能（名称+一行描述）注入执行器任务文本，记事件 `trial.skills_enabled`——跨 Kimi/Codex/Prime 三运行时一致成立（技能本体已在各 CLI 的 skills 目录，CLI 自动发现）。
- 前端：设置页「07 技能管理」卡片（目录 51 个技能 + 常驻勾选保存）；研究页题目选择器下方「本题技能」chips + 管理弹窗（勾选 diff 保存，常驻技能带徽标）。

**已实际验证**：`uv run pytest tests/ -q` **92 passed**（新增 8 例：目录扫描/绑定 CRUD/合并去重/controller 注入与事件）；`npm run build` 零错误；真实环境扫描到 51 个技能；curl 实测四路由（含无效 id 过滤、绑定回读、settings revision 递增）；WebBridge 真实浏览器：设置页勾选 ask-matt 常驻→保存→API 回读 `always_on:["ask-matt"]`，研究页弹窗绑定 bohrium-lkm→chips 显示→API 回读 `bound:["bohrium-lkm"]`（截图 `checks/shots/skills-settings.png`、`skills-research-bound.png`）。

**尚未验证**：注入技能的完整 Trial 实跑（controller 单测已断言 prompt 注入与事件；真实执行器消费技能未跑，避免消耗额度）。平台题目详情无 skill 要求字段，题目级绑定目前只能用户手动勾选；大脑提议绑定留债。

### 2026-09-18 · 预算运行时可调（大脑判断上限 6→20）

**背景**：用户新 Run（run_d5f1821118）运行中要求不调进程把大脑判断上限 6→20，并要求各类预算可在运行时增加。

**已实际验证**：
- 审计发现预算读取不一致：`_apply_decision`/`_budget_status`/`_run_minutes_exceeded` 读实时 settings/授权行，唯独 `_run_one_review` 的大脑判断上限读 Run 启动时的 config_snapshot 冻结值。
- **热改当前 Run**（不动进程）：直接 UPDATE runs.config_snapshot 的 max_brain_reviews 6→20；controller 每次审阅都重新 SELECT run 行，立即生效。同时 settings.json 改 20，运行中进程的 `_budget_status` 实时显示 4/20（改前 2/6），Run 持续推进未中断。
- **代码修正**：`_run_one_review` 改读实时 settings（与其余预算路径一致）；DEFAULT_SETTINGS 默认 6→20；observation.py 回退值同步；删除因此空置的 `settings_defaults()`。
- **新接口** `PUT /api/v1/runs/{id}/budget`：max_brain_reviews/max_trials 写实时 settings（全局），max_model_turns/max_run_minutes/max_submissions 写本 Run 授权行（授权行本就被实时读取）；校验正整数、记事件 `run.budget_updated`、返回最新 budget。
- **前端**：运行摘要预算区加「调整预算（运行中生效）」弹窗，五项上限预填当前值、只提交变更字段。
- 回归 **94 passed**（新增 update_budget 正常/校验 2 例）；`npm run build` 零错误。

**尚未验证**：新预算接口的 HTTP 层与前端弹窗未在浏览器实测——运行中的后端是旧代码，为不影响进行中的 Run 未重启；待本 Run 结束后重启后端即生效（代码与静态包均已就位）。

### 2026-09-18 · 大脑反复出错根因定位与修复

**用户现象**：run_d5f1821118 运行中大脑反复报错。事件流审计（checks/brain_errors.log）定位两个独立根因：

1. **ReviewResult 契约校验失败（主因，seq 43/48）**：契约要求 watchlist 每项是 Watch 对象（id/hypothesis_md/evidence_needed_md/intervene_when_md/evidence_refs 五必填），但双大脑提示词只给了 `"watchlist":[]` 空数组示例、未写项结构，模型输出字符串数组 → 整个审阅结果作废、shadow 降级。修复：kimi.py/codex.py 提示词补 Watch 项结构与"禁止字符串数组"。
2. **steer 需要活跃 Trial 死循环（seq 40/54）**：Trial 停滞被标记 stalled 后不再是"活跃"，而语义校验只允许 steer 活跃 Trial——停滞恰恰是最需要 steer 的时刻，大脑每次裁决都被拒。修复：`validate_semantics` 加 `stalled_trial_id` 参数允许 steer 当前 stalled Trial（trial_id 必须匹配）；controller steer 执行时把 stalled Trial 恢复 active（会话现场未丢，指导入队投递）。

**已实际验证**：回归 96 passed（新增 3 例：stalled steer 语义放行/不匹配拒绝、controller 端到端 steer 恢复 active）。**已知既有 flake**（非本次引入，git stash 基线复现）：`test_jsonrpc_stdio.py::test_process_exit_wakes_waiters` 与 `test_mailboxes.py::test_register_experiment_demo_and_real_missing` 在 Windows 上偶发失败（约 1/6 概率），单跑均稳定通过，留债。

**尚未生效**：修复在代码层完成，但运行中的后端是旧代码，需重启才对当前 Run 生效（重启会中断当前大脑会话，恢复机制会对账；等用户确认）。

### 2026-09-18 · 软化硬编码：容错优先，判断权交给大脑（用户原则）

**原则落地**：控制器只保留安全硬约束（授权/预算/提交确认），格式与语义问题不再整单拒收。

- **ReviewResult 两级容错**：契约校验失败 → ① `_salvage_review_result` 就地规整 watchlist（字符串包装为 Watch 对象、缺字段补占位、非法项丢弃、超 3 项截断）→ ② 仍失败且 guidance 非法则只丢 guidance、intervene 降级 silent。笔记与审阅不再因格式陪葬；修复内容记事件 `brain.review_salvaged`。
- **Decision 逐动作放行**：语义校验从整单前置改为循环内逐动作——非法动作只记 `brain.action_rejected`（原因进事件流，大脑下一帧可见并自我纠正），合法动作照常执行；方向动作超限只拒第二个及以后。整单 `brain.decision_rejected` 仅剩结构（JSON schema）不合法场景。
- 提示层的 watchlist 结构说明保留（减少 salvage 触发率），但系统正确性不再依赖模型格式自觉。

**已实际验证**：回归 **100 passed**（新增 4 例：字符串 watchlist 容错、坏 guidance 降级、逐动作拒绝、第二方向动作拒单）；`npm run build` 零错误。

**尚未生效**：同前——运行中后端是旧代码，需重启生效。

### 2026-09-18 · 终止-重启可靠性修复

**审计发现的四个缺口与修复**（controller.py / api.py / ResearchPage.tsx）：
1. 终止不清理执行器会话（无 prime.abort，孤儿 CLI 进程风险）→ terminate 现在 best-effort abort 执行器并记 `prime.session_aborted/failed`；stalled Trial 一并 interrupted；悬空 pending/running 审阅请求置 obsolete。
2. **启动零对账**（违反 AGENTS 进程可靠性）：后端重启后 phase=running 的 Run 变成无事件循环的僵尸，steer/pause 只会收到"请重启恢复"的空话 → 新增 `reconcile_on_startup()`（lifespan 调用）：僵尸 Run 标记 `recovering` + block_reason 说明 + `run.needs_recovery` 事件。
3. recovering 无恢复路径 → resume 支持从 recovering：重建事件循环与大脑/执行器会话，以 `trigger="recovery"` 生命周期审阅让大脑裁决下一步（不盲目续跑）；有其它活跃 Run 时拒绝。
4. update_budget 无终态护栏 → 终态 Run 拒绝调整（INVALID_STATE）。

**前端**：研究活动区在 recovering 状态显示「恢复研究（后端重启后）」与「终止研究」按钮（recovering 已在 ACTIVE_PHASES/标签中）。

**已实际验证**：回归 **103 passed**（新增 3 例：terminate 清理含 FakeExecutor abort 断言、对账标记+resume 重建+recovery 触发、终态预算护栏）；`npm run build` 零错误；真实后端已重启加载本版（重启时无僵尸 Run，对账路径空跑安全）。

### 2026-09-18 · 大脑自动唤起修复：checkpoint 通知缺口 + 时间兜底

**用户现象**：run_e5df14c361 跑 35+ 分钟、361 条执行器进度事件，大脑 0 次自动唤起（reviews 1/20 仅启动审阅）。

**根因（两条独立缺口）**：
1. `collab.submit_checkpoint` 只在产生 review_id 时调用 notify——`review="none"` 的进度检查点落库后无人唤醒 shadow 评估，生产链路只靠 review worker 空闲超时（最长 60s）被动扫描，且历史 Run 中执行器唯一的 checkpoint 上报还遭遇 MCP 桥 `-32001 Request timed out`（83s 超时，根因未复现定性）。
2. 没有时间兜底：shadow 唤起只吃触发词表事件（checkpoint/trial 完成/停滞/错误），执行器沉默干活（只发心跳）时大脑永远旁观；`max_interval_seconds` 配置形同虚设。

**已实现**：
- `collab.py`：新检查点（非去重）无论是否要求审阅都调用 notify → shadow 立即评估。
- `controller.py` 新增 `_maybe_periodic_shadow`：距上次审阅 ≥ max_interval_seconds 且 covered_seq 之后存在执行器/用户源新事件（大脑/控制器自身记账不算，防自激）时，排 trigger="periodic" 的 shadow 审阅；worker 空闲超时分支调用。仍受 shadow 额度、降级、合并语义约束。
- `mcp_bridge.py` `_post`：超时 30s→10s，OSError 类瞬断重试一次（HTTP 4xx/5xx 不重试）。

**已实际验证**：回归 **105 passed**（新增 2 例：periodic 时间兜底唤起+答复后不自激、MCP 桥瞬断重试；另将 `_rig` 的 max_interval 参数化，periodic 测试显式开 0.2s，其余测试默认 3600s 不干扰）。

**尚未验证**：真实运行中的 periodic 唤起与 MCP 重试未联调——运行中的后端（bash-zxn1b9a0）仍是旧代码，按用户「不干涉运行中 Run」要求未重启；Run 结束或用户确认后重启生效。MCP 83s 超时根因未定性（桥与端点实测健康：initialize 0.06s、鉴权拒绝 0.04s）。

### 2026-09-18 · MCP 通道持续不可用根因：孤代理字符杀死桥进程

**用户现象**：run_e5df14c361 执行器报告「MCP 通道持续不可用」，ack/checkpoint 全部失败（-32001 超时 + -32000 Connection closed）。

**根因（Kimi CLI 日志铁证，~/.kimi-code/logs/kimi-code.log）**：执行器的报告文本含**孤代理字符**（U+DCA2 一类，执行器读二进制/GBK 日志时以 surrogateescape 带入），`mcp_bridge._post` 的 `json.dumps(payload, ensure_ascii=False).encode("utf-8")` 严格编码直接抛 `UnicodeEncodeError: surrogates not allowed`——崩溃发生在 HTTP 发送之前，后端从未收到请求。桥进程一死，Kimi 客户端报 -32000；客户端每次调用重新拉起桥，而执行器每次都带着同样的乱码文本 → 每次必崩，形成崩溃循环（日志 10:22 起 11 次同款崩溃）。此前诊断的「83s 超时」只是次要表象。

**已实现**（mcp_bridge.py）：
- `_post` 编码改 `encode("utf-8", errors="replace")`：孤代理替换为 U+FFFD，内容保留、进程不死。
- `main()` 加兜底：`_handle` 任何未料异常返回 JSON-RPC -32603 错误响应而不是崩溃（桥进程永远不能死）。
- `main()` 启动时显式声明 stdin/stdout 为 UTF-8（MCP stdio 协议本身即 UTF-8；Windows 默认 GBK 是同族隐患）。

**已实际验证**：回归 **106 passed**（新增 1 例：孤代理 payload 不崩+body 合法 UTF-8+main 兜底返回 JSON-RPC 错误）；真实子进程端到端：initialize + 含孤代理的 tools/call 两行请求，桥 exit 0、两条响应齐全（401 仅因探针无令牌，执行器的桥带真实令牌不受影响）。后端端点与 DB 写路径实测健康（401 1.4ms；WAL 写锁瞬得）——故障从始至终在执行器侧的桥进程。

**生效方式**：Kimi 客户端每次 MCP 调用都会重新拉起桥进程，模块从磁盘现读——**无需重启后端、无需动运行中的 Run，执行器下一次 MCP 调用即自动使用修复后的桥**。

**尚未验证**：执行器下次真实 MCP 调用成功登记 checkpoint/ack（等执行器自己重试或大脑指导其重试）；早先偶发的 -32001 纯超时是否另有根因。

### 2026-09-19 · 经验库整理与自进化闭环（grilling 两轮确认后实施）

**设计（用户拍板）**：硬门只剩「全局经验需用户审批」一条；新建/更新/不变、去重、失败总结全归大脑；冲突=追加新修订，永不拒绝；skill 候选不做（含于经验）；失败结果直接总结成普通经验；效果回联只记录不评分，精确到题目粒度且只在整理/选择时给大脑看。

**已实现**：
- proposal 落库（controller._apply_experience_proposal，Run 内与全局整理共用）：题内提议直接 active+observed；全局落 candidate+hypothesis 待审批；可选 `target_id` 更新已有条目（合并 evidence_refs、scope/kind 继承原条目、未知 id 只拒该提议）；kind 不再写死 heuristic。schema 增加 target_id/kind。
- 全局审批闭环：experiences.approve_experience/reject_experience（驳回必附批注 review_note，退回 candidate 供大脑重写）；API approve/reject；前端经验页顶部「待审批的全局经验」区（独立拉取 scope=global，不受筛选影响）+ 驳回批注输入与标记。
- Run 收尾自动整理：finish 先推迟为一轮 curation 生命周期审阅（packet 带本题全部经验正文节选 + usage 回联），审阅完结（含失败/作废，防死锁）由 _finish_request 钩子自动收尾；额度用尽直接收尾并记 run.curation_skipped。
- 全局手动整理：POST /api/v1/experiences/curate_global {challenge_ids}——无 Run 的一次性大脑会话，素材=全局条目（含驳回批注）+入选题目的题内经验与 usage；产出仍落 candidate；进行中重复触发报 CURATION_RUNNING；GET 同名路由查状态。
- 效果回联：runs.experience_snapshot 死字段启用（at_start/at_end 各记 active 经验版本清单）；_experience_usage 聚合题目粒度的「经验→Run→最好分数」。
- 执行器侧：任务文本给经验库目录（A8 不注入正文），executor.md 要求开工前自读 active 经验；kimi/codex 大脑内联提示词补 target_id/kind/审批语义；promote_experience 全局拒绝改指向用户审批，加 revision_hash 陈旧视图保护；check_pending_writes 对账异常不再静默丢弃（启动打印告警）。
- 文档同步：docs/EXPERIENCE.md 闭环章节重写、memory_manifest 字段如实标注留债；AGENTS.md 经验行更新。

**已实际验证**：回归 **111 passed**（新增 5 例：题内提议直接 active+任务文本带经验目录、全局提议落 candidate+approve/reject 往返、target_id 更新与未知 id 拒绝、finish 推迟→curation→自动收尾+起止快照、无 Run 全局整理会话+并发护栏；另改 2 例既有断言匹配新语义）；`npm run build` 零错误（含 tsc）。

**尚未验证**：真实大脑（Kimi K3）执行 curation/global_curation 决策的联调未跑（避免消耗额度，待用户触发）；执行器真实读经验目录的行为只有提示词约束；Terminate 的 Run 不触发整理（只有大脑发起 finish 才整理，边界已知）。

### 2026-09-19 · 题目级评分轮询任务管理 + 后端自愈重启

**事件**：运行中的后端进程（bash-zxn1b9a0）无痕迹退出（日志无 traceback，疑似外部终止/控制台回收）；重启时发现 settings.json 被之前的调试脚本误写（mode=demo + 测试用 shadow 参数），已恢复 mode=connected、shadow 改回生产值（60s/600s/max 20）。当前后端 bash-xlfl2ct9 跑最新代码（MCP 桥修复、periodic 唤起、经验闭环、轮询管理全部生效），启动对账无僵尸 Run。

**已实现（题目级轮询任务）**：
- `mailboxes.poll_scores` 支持 challenge_id 过滤；新增轮询任务服务：pollable_challenges（跳过禁用题）、poll_pending_by_challenge（45s 后台循环按题分组）、polling_tasks（列出有提交的题：标题/待评分数/启用态/上次轮询结果）、set_polling_enabled（写 settings.polling.disabled_challenges）、poll_scores_now（手动单题轮询不受开关限制）。
- API：GET /api/v1/polling、POST /api/v1/polling/{cid}（enabled 开关）、POST /api/v1/polling/{cid}/run。
- 前端 MailboxPage 顶部「评分轮询任务」卡片：每题一行（标题、待评分数、轮询中/已中断徽标、中断/启用、立即轮询、上次结果摘要），30 秒只读轻刷新。

**已实际验证**：回归 **116 passed**（新增 tests/test_polling.py 5 例：challenge 过滤、disabled 跳过、toggle 落盘、API 全链路含 404、手动 run 不受开关限制）；`npm run build` 零错误；重启后 curl 实测 GET /api/v1/polling 返回真实任务（Aiyagari 题 pending=4、轮询正常执行、updated=0 still_unknown=4——平台尚未出分）。

**尚未验证**：前端卡片在浏览器的真实渲染与交互（代码已过 build，未用 WebBridge 截图）；disabled 状态跨后端重启持久（写 settings 落盘，逻辑已测，未实机重启验证）。

### 2026-09-19 · WebBridge 全页走查 + 前后端 18 项修复

**走查（真实浏览器，截图 checks/shots/audit-*.png）**：研究工作台/经验库/邮箱与提交/连接与设置四页全量点击与滚动。实证发现：题页「提交与评分」只显示当前 Run 的提交（Aiyagari 4 条只显示 2 条）；终态 Run 大脑状态残留 `guidance.queued`、发送指导/协作监督按钮仍可点；「Prime 状态」等命名残留；事件流裸英文事件名；顶栏后端时间为 UTC 且不刷新；邮箱页 `updated=0 errors=0` 裸英文；设置页 51 技能无过滤、保存按钮只在顶部；SPA 切页保留滚动位置。

**后端修复（子代理实施，主代理复验）**：
- mcp_bridge 非对象 JSON 行二次 AttributeError 杀桥 → 分发前 isinstance 检查，非 dict 返回 -32600，桥不死（mcp_bridge.py:140-150）。
- `_run_global_curation` 装配在 try 外 → 整体纳入兜底，任何失败置 failed；curation 状态落盘 `.cyberscientist/global_curation.json`（原子写），重启后 running 残留如实转 failed+interrupted，可重新触发。
- Run finish 推迟的三条丢失路径（curation obsolete/重启恢复标 error/curation 在途时 pause）→ 统一收口 `_maybe_finalize_after_curation()`，curation 任何终态都放行被推迟的收尾，四个触发点全接入。
- `/api/v1/submissions/poll` 同步网络请求 → `asyncio.to_thread` 卸载；scored 落库改条件 UPDATE（仅 unknown/pending→scored 迁移记事件），手动/后台轮询并发不重复记分。
- 新端点 `GET /api/v1/challenges/{id}/submissions`：按题聚合所有 Run 的提交，形状与 run 级一致、新的在前、题不存在 404。
- 题内 experience proposal 的 challenge_id 强制绑定当前 Run 题目，自报不一致记 `experience.proposal_rebound`。

**前端修复（子代理实施，主代理复验）**：提交与评分 tab 改按题聚合（404 回退 run 级）；终态 Run 收口（大脑/执行器状态显示终态标签、发送指导与监督按钮禁用带提示）；「Prime 状态」→「执行器状态」等命名中性化；labels.ts 补全事件/状态中文映射（含 stalled 判定用后端实际事件名 `trial.stalled` 的真实 bug）；邮箱页轮询结果与提交状态汉化；顶栏后端时间改本地时区每秒走动（30s 健康重校对）；设置页技能搜索过滤 + sticky 保存栏；切页回顶；预算输入 min 按字段语义（允许 0 的放行 0）；指导状态改时间序匹配（修 opId 永不匹配卡「已排队」）；SSE 断线徽标 + 终态归档不再重连。

**已实际验证**：`uv run pytest -q` **126 passed**（基线 116 + 新增 10：MCP 桥非对象行、curation 失败终态化/落盘/重启对账、finish 三路径收尾、轮询幂等、题级聚合端点、proposal 绑定、poll 卸载出事件循环）；`npm run build` 零错误。重启后端后 WebBridge 复验：题页提交与评分显示全部 4 条（verify-2）、终态 Run 三个按钮禁用且有中文提示（evaluate 实测 disabled=true）、大脑/执行器状态显示「已终止」、邮箱页「更新 0 条 · 错误 0 条」「已提交 · 分数 待评分」、顶栏时间本地时区标注、技能搜索框存在、sticky 保存栏渲染、切页回顶（verify-1/3/4）。

**尚未验证**：顶栏时钟每秒走动在 WebBridge 隐藏标签页不可验（Chrome 冻结后台定时器；本地时区换算与 30s 重校对已验，代码为每秒 setInterval 插值）；SSE 断线徽标的真实断网表现未演（代码路径：指数退避重连 + amber 徽标）；curation 真实大脑联调仍未跑（省额度，同前轮结论）。

### 2026-09-19 · URL 导入接通真实平台 + 弹窗误关修复

**根因与修复**：
- 「URL 导入提示未配置平台 token」是误导文案——该路径原本是硬编码 502 占位。实测平台 `GET /api/challenges/{id}` 为公开只读端点（无需 token），且详情 JSON 自带完整 Markdown 题面（`content` 字段）。实现：`mailbox_platform.parse_challenge_slug`（URL/裸 slug 解析，字符白名单防注入）+ `fetch_platform_challenge`（复用 `_http`）；api.py url 分支改真实拉取（`asyncio.to_thread` 卸载出事件循环）、按 platform_challenge_id 幂等去重、标题优先 title_zh、contract_status 如实 unknown、平台 404 → 404、空题面 → 502 准确缺项。
- 「输入时弹窗意外关闭」根因：Modal 的 onClick 只判 `e.target === dialog`——输入框内拖选文本后在背板松手，click 的 target 也是 dialog → 误关。修复（components.tsx）：mousedown+click 双确认背板（按下和抬起都在背板才关闭）。

**已实际验证**：回归 **130 passed**（新增 4 例：slug 解析、fetch mock、URL 导入 API 全链路含幂等/422、平台 404）；`npm run build` 零错误；真实后端重启后 curl 实测三种路径（Aiyagari URL 幂等返回 local_c2643b50、不存在题目干净 404、无法解析 422）；WebBridge 真实浏览器 UI 导入 DPA4C Nano 题成功（对话框自动关闭、题目自动选中、toast 提示，截图 `checks/shots/verify-5-import.png`）。

**尚未验证**：Modal 拖拽误关修复未做浏览器级拖拽复现（代码模式为标准修法，构建通过）；导入的题目评分契约仍为 unknown（提交时按平台真实响应核实）。

### 2026-09-19 · 算力授权（max_jobs）全链路接通

**背景**：LoRA Run（run_295c4db710）大脑发现 max_jobs=0 无法用 Bohrium 算力；审查发现 max_jobs 此前只有 config 默认值、无任何存储/消费/API。

**已实现**：
- `authorizations` 表幂等新增 `max_jobs` 列（db.py AUTHORIZATION_V2_COLUMNS）；`controller.authorize`/`update_budget`/`_budget_status` 全链路支持；观测帧 budget 增加 `max_jobs`（大脑每次审阅可见）。
- API：AuthorizeBody/BudgetBody 增加 max_jobs；`PUT /runs/{id}/budget` 可运行中调整（走授权行，立即生效）。
- 默认值：`config.DEFAULT_SETTINGS.run_defaults.max_jobs` 0→3；线上 settings.json 同步改为 3（revision 13）。
- 前端：启动授权弹窗与「调整预算」弹窗均加「算力上限（Bohrium Job 数）」；运行摘要新增「算力上限」行。
- 约束仍是提示层（观测帧+任务文本），执行器侧 bohr 调用无硬拦截——如实记录，硬拦截需拦截执行器 shell 层，留债。

**已实际验证**：回归 **131 passed**（新增 test_max_jobs_authorization_roundtrip：authorize 落库/update_budget 调整/观测帧可见）；`npm run build` 零错误；真实后端重启后 `PUT /runs/run_295c4db710/budget {"max_jobs":3}` 返回 updated 且 run snapshot 回读 max_jobs=3；settings PUT 后 revision 13、max_jobs=3。

**注意**：本次重启使用户已暂停的 Run 进入 recovering（启动对账如实标记），用户在前端点「恢复研究」即重建会话，大脑下次审阅即可见 max_jobs=3。

### 2026-09-19 · brain.action_rejected 双 bug 修复 + pausing 逃生按钮

**事故复盘（run_295c4db710 事件流铁证）**：
- seq 363 `brain.action_rejected {"op":"steer","reasons":["steer 需要活跃 Trial"]}`：Trial 处于 reported_complete（执行器报交付、等大脑验收），大脑 steer 追问侦察报告被语义校验拒掉。
- seq 369 `brain.action_rejected {"op":"start_trial","reason":"研究门禁为 waiting_brain"}`：承载 waiting_brain 的 blocking 审阅（rev_146a4a5f82）在后端重启对账中被作废，而门禁只有「blocking+intervene 答复」一条开门路径 → 永久卡死。

**修复**：
- Bug A：`decision.validate_semantics` 增加 `reported_trial_id` 参数——待验收 Trial 可 steer（只投递指导，不改 Trial 状态，验收语义仍归大脑）；`_apply_decision` 按当前 Trial 状态传入。
- Bug B：新增 `_release_orphaned_gate` 兜底——门禁为 yielding/waiting_brain 且无任何在途 blocking 审阅时放行并记 `run.gate_opened{by:no_blocking_inflight}`；挂接点：`_run_loop` 启动对账后（覆盖重启恢复）、`_on_turn_boundary`（覆盖运行中作废）。blocking 审阅 SILENT 不放行的现有语义不动。
- 前端：Run 在 pausing 时此前无任何控制按钮（暂停只认 running、终止排除 pausing）→ 现 pausing 也显示「终止研究（不等暂停确认）」（terminate 后端本就允许非终态任意阶段）。

**已实际验证**：`uv run pytest -q` **135 passed**（新增 4：reported_complete 可 steer 语义、事故复现之恢复后门禁放行且 start_trial 被接受、回合边界兜底放行+留痕、steer 不改 Trial 状态；更新 1 条错误文案断言）；`npm run build` 零错误；真实后端重启后 run_295c4db710 如实进入 recovering（gate 仍为 waiting_brain，按设计在用户点「恢复研究」时由 `_release_orphaned_gate` 放行——该路径已被 test_recovery_resume_heals_orphaned_gate_and_allows_start_trial 覆盖）。

**尚未验证**：真实大脑在恢复后重试 steer/start_trial 的端到端表现（等用户恢复 Run）；pausing 逃生按钮未做浏览器级点击复验（构建通过，条件渲染逻辑直白）。

### 2026-09-19 · brain.decision_rejected（finish 被陪葬）修复

**事故（seq 513-514 铁证）**：大脑判断研究应收尾（18.09 分 final、配额该留），发出 finish 主决定，但附带一条经验提议自创了 `kind: 'finding'`（schema 仅允许 heuristic/procedure/failure/platform）→ 结构校验**整单拒收**，finish 陪葬。根因二：大脑提示词只说提议"可选 kind"，从未列出合法枚举值。

**修复**：
- `_apply_decision` 增加 salvage（与 ReviewResult salvage 同一原则）：非法经验提议逐条剔除（全文留在 `brain.decision_salvaged` 事件供大脑重提），剔除后重验，合法提议与主决定照常执行；剔完仍有结构错误才整单拒。
- Kimi/Codex 两个大脑的提示词补全 kind 枚举：「仅限 heuristic/procedure/failure/platform 四值，勿自创」。

**已实际验证**：回归 **136 passed**（新增 test_decision_salvage_drops_only_invalid_proposals：非法提议剔除留痕、合法提议落库、wait 主决定执行、不再整单拒）；后端已重启，Run 进入 recovering。

**尚未验证**：真实大脑在新提示词下不再自创 kind（等恢复后观察）；被剔除的那条经验提议需大脑在后续审阅中用合法 kind 重提（原文在 seq 附近 brain.decision_rejected/ salvage 事件中）。

**当前 Run 状态**：phase=recovering；两个 Trial 均 reported_complete；大脑此前两次想收尾（finish 被拒→pause）。用户点「恢复研究」后：门禁兜底放行（waiting_brain 的承载审阅已完结，属孤儿门禁）→ recovery 审阅 → 大脑可正常 finish。

### 2026-09-19 · 常驻目标「满分前不停」+ run.time_limit 热循环修复

**用户需求**：全自动——用户手动暂停前，未满分不停、主动用算力迭代提分，配额不是拿来省的。

**实现（提示词层，无硬闸门）**：Kimi/Codex 大脑 Decision 提示词 + prompts/collaboration/brain.md（shadow 监督指令段）写入常驻目标：未满分不得 finish；预算未耗尽应主动提可检验假设做实验；验证假设不算盲探；finish 仅限满分或全路径被证据堵死（须列明缺什么）；pause 仅限必须等用户的抉择点。

**顺路揪出的存量严重 bug**：run.time_limit 热循环。90 分钟授权时长按墙钟（含暂停）耗尽后，主循环该分支无 await——「置 paused → 写事件 → continue」纯同步空转，事件循环彻底堵死（health 超时），垃圾事件 124,928 条（seq 冲到 9.7 万）。修复：守卫 `phase == "running"`，触发一次后停泊等待信号。清污：垃圾事件删至仅保留首条（seq 526）作诚实记录；max_run_minutes 经预算 API 提至 1440。

**已实际验证**：回归 **137 passed**（新增 test_time_limit_pauses_once_without_hot_loop：超限恰好暂停一次+一条事件+停泊）；生产实测：重启恢复后 `run.gate_opened{by:no_blocking_inflight}` 兜底放行；大脑 recovery 决策为 steer（要分数证据，不再 finish）；steer 指导成功投递执行器并获 accepted（Bug A 修复生效）；执行器随后核对产物、提交检查点，trial_40b7929d24 再次 reported_complete，审阅 10/20。

**尚未验证**：大脑在新常驻目标下的长期行为（是否会持续主动提分而非观望）；Bohrium 算力在 L1 路径缺工具链时的实际可用性（大脑此前判断为不可替代缺口）。

### 2026-09-19 · blocking 审阅 Decision 答复循环死锁修复 + Run 终止

**事故（seq 862-868 铁证）**：Trial stalled → 大脑裁决 start_trial（v3 单变量实验，理由充分）→ 被 `waiting_brain` 门禁拒绝。根因是**设计缺陷而非状态残留**：blocking 审阅（trial_complete）的 lifecycle 答复形态是 Decision，但 `_apply_decision` 里 start_trial 要求 gate=='open'，而开门只在 blocking+intervene ReviewResult 路径——**大脑用来开门的答复会被门本身拒绝**。用户手动终止 Run。

**修复**：blocking 审阅收到 Decision 答复时，先在同事务开门（记 `run.gate_opened{by:blocking_decision}`，仅当门禁确实在等待才记），再应用动作。

**已实际验证**：回归 **138 passed**（新增 test_blocking_review_answered_by_decision_opens_gate：trial_complete→waiting_brain→Decision 含 start_trial→新 Trial 创建+开门留痕+无 action_rejected）；后端已重启生效（首次启动撞 workspace 锁，系旧后端未停，已纠正流程）。

**Run 最终状态**：cancelled（用户手动终止）。成果保留：真实评分 18.09（attempt 44795，final/late_scored）、L0 协议分析、经验库条目。

**资源页核对结论（用户要求）**：大脑「工具/数据不可得→满分路径不可行」的判断**事实对、结论错**——trisol/wenyon 不在 PyPI/bohr（所以查无），但它们是平台认证服务，题面有 documented quickstart；两个公开数据集真实存在（wenyon retrieval_ref 具体）；资源页显示最佳尝试 100 分（codex-r5-l），满分路径存在。平台无公开数据集下载端点（探测的 /datasets 是 SPA 兜底），正式入口是平台托管环境/认证 CLI。

### 2026-09-19 · 开局改大脑先行探查（用户要求）

**问题**：lifecycle 帧此前**完全不带题目信息**（无题面/平台链接/资源清单），大脑开局全盲，只能让执行器从零侦察并事后转述——本轮「trisol/wenyon 不可得」的误判即源于此（大脑原话：「执行器报告，我未独立复核」）。

**实现**：
- challenges 表加 `resources_json` 列（幂等迁移）；URL 导入时平台资源清单（数据集/工具/服务）随题面落库；存量题 local_14c116ff 已用真实平台响应回填（6 项资源）。
- `_lifecycle_packet` 新增 challenge 块：标题、platform_url、resources（各帧都带）；完整题面 content 只在 run_start/recovery 帧携带（省 token）。
- Kimi/Codex 大脑提示词：trigger=run_start 时**解除工具禁令**——要求大脑先用网页工具亲自探查题目页面（概览/指南/资源页），核实数据路径、工具链、评分契约、满分可达性后再输出首个 Decision；明示「公开仓库查无 ≠ 不可得，先查平台资源页与文档」。其他触发器维持「不使用任何工具」。

**已实际验证**：回归 **139 passed**（新增 2：导入落资源清单、run_start 帧带题面/资源而 trial_done 帧不带 content）；后端重启健康。平台资源核对原始响应存 checks/platform_challenge_now.json。

**尚未验证**：真实大脑在 run_start 是否真的会调用网页工具并完成探查（下一个新 Run 验证）；存量 Run 已终态不受此改动影响。

### 2026-09-19 · 大脑证据帧盲区修复（执行器进展进帧）

**事故**：执行器把 trisol 登录成功、wenyon 数据集 ready 等关键进展只写在自己的思考流里、从不落 checkpoint；大脑帧对 progress 事件只计数（activity_counts）、lifecycle 帧只有 seq/source/type 三元组 → 大脑基于「登录墙未过」的过期印象错误 pause Run。

**修复（两层）**：
- observation.py：新增 `executor_digest`（非思考类 progress 的 detail 摘录，最近 12 条、每条 160 字符、脱敏、超限记 omitted）进 shadow/requested 帧；新增 `event_excerpt()`，controller `_lifecycle_packet` 的 new_events_since_last_review 对 notable 事件与实质进展带 excerpt。思考流（「思考:」前缀）仍不进帧。
- prompts/collaboration/executor.md：关键状态变化（认证/数据就绪/任务完成/评分/阻塞/假设推翻）必须立即落 checkpoint，不得只写在思考里；明示「思考里记录了不等于大脑知道」。
- prompts/collaboration/brain.md：说明 executor_digest/excerpt 与 checkpoint 同等证据效力，不得凭过期印象推翻。

**已实际验证**：回归 **140 passed**（新增 test_t10b_executor_digest_reaches_frame：实质进展进帧、思考流不进帧、密钥脱敏、生命周期帧摘要、12 条上限取尾部）；后端已重启健康；Run run_abde7bc34d 已 resume（confirmed）+ steer 纠正过期印象（queued）。

**尚未验证**：真实大脑读到 executor_digest 后是否不再误判（本 Run 恢复后观察）；执行器是否遵守新 checkpoint 纪律。

**Run 最终状态（2026-09-19 晚）**：cancelled（用户决定结束本题）。根因：赛题契约要求 formal_runs 必须 trisol 提交 + A100-SXM4-80GB，账号全 team 仅 L20×32 配额、无 A100，trisol 无配额申请接口——属用户平台侧缺口，系统内无解。成果保留：wenyon 数据集（1536 行，ready）、token manifest（599,601 tokens，低于 2M 上限）、双 RNG 正式提交命令草稿（submission/reports/formal-submit-plan.md）、A100 配额穷尽诊断（ev_diag_a100_exhausted）。补配额后可直接恢复利用。

### 2026-09-19 · AskUserQuestion 路由大脑（全自动问答链路）

**根因（探针实测，checks/fixtures/real/kimi-acp-askuser-probe.jsonl）**：JsonRpcStdio 的响应帧缺 `"jsonrpc":"2.0"` 字段；ACP 较新代码路径（elicitation）严格校验，缺字段被当 RPC 失败 → 回退 session/request_permission。该回退路径在当前 Kimi Code 版本对提问无效（选择 q*_opt_* 后工具仍返回 dismissed）——上游 bug，绕开不依赖。

**修复**：
- jsonrpc_stdio.py：请求/响应帧均带 `"jsonrpc":"2.0"`（spec 要求）。
- KimiExecutor：initialize 声明 `elicitation.form` 能力（声明后提问走 elicitation/create，不再回退）；新增 ask_handler 注入点；elicitation/create 与 q*_opt_* 权限回退都路由大脑；无大脑/超时如实 decline，不伪造答案。
- 控制器：`_answer_executor_question` 入队 executor_question 审阅（frame_json 带问题）+ Future 等待（140s 超时）；`_run_question_review` 小上下文调大脑，回答经选项校验（必答覆盖 + 值取自 oneOf const）后落 result_json；消耗大脑判断额度；`_finish_request`/`_obsolete_request` 唤醒等待者。
- 大脑：新 protocol=executor_question 提示词（明确「没有人类在线，你就是提问对象」）+ extract_question_answer 解析；Codex/Kimi 两大脑同步。
- executor.md：告知 AskUserQuestion 由大脑回答；「未作答」不是人类意图。

**已实际验证**：探针 v3 实测工具结果 `{"answers":{"冒烟测试用哪个 GPU？":"L20"}}` 且代理确认收到所选答案；回归 **143 passed**（新增 3：真实帧解析、提取器、控制器问答通路含自创选项拒收）；后端已重启健康。

**Run run_fff3ebe724（FWI 题）**：14:54 UTC 由用户终止（cancelled），终止时刻早于本次重启，与部署无关。监控 cron 已按终态规则删除。

**尚未验证**：真实运行中执行器提问的端到端时延（大脑单飞，提问排队于在途审阅之后）；Codex 大脑的问答路径只过了单测未实测。
