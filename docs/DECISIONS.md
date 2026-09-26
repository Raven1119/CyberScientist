# 设计调整记录

以下是相对最初“大脑监督 Prime + 双层经验”想法作出的选择。它们以更快获得可信成绩为目标，未证明会提高分数的部分保留可关闭开关。

| 决策 | 替换的设计 | 原因与影响 |
|---|---|---|
| 三类连接分别建模 | 把 Codex/Kimi、Prime LLM、Bohrium 都放进万能模型接口 | 原生代理有会话/认证/审批，模型有供应商协议，平台有 Job/提交；保留各自语义，避免错误抽象 |
| 控制器处理轮询，大脑事件驱动 | 大脑持续读全量 Trace、询问评分器 | 将模型调用集中在需要判断的变化，普通状态轮询不花推理预算 |
| Prime 保留实验自主权 | 大脑逐条命令 IPython | 大脑限定研究目标和资源，执行器选择具体方法；不建立第二套规划器 |
| 不重写 Prime | 复制其 kernel、工具循环或子代理管理 | 减少维护面，先用固定版本 RPC；仅适配缺口需要局部改动 |
| 本地编排、远程科学计算 | 直接把 IPython 当本地科研机器 | 保留用户既有 Bohrium-first 约束；IPython 作为控制环境，科学产物需远程来源 |
| 编辑态与运行快照分离 | 经验一修改就影响所有运行 | 可编辑性与实验可复现同时保留；下一 Trial 默认采用新版本 |
| 候选经验与已验证证据分离 | Trace 自动写入长期真理库 | 防止模型总结、偶然高分和平台异常变成错误规则；负历史不丢 |
| 首版关闭自动 harness 改写 | Prime /refine 自动改变全局运行方式 | 先量清监督/经验收益，不同时改内核变量；后续只有证据支持才启用 |
| 单 Run、单大脑、单顶层 Prime | 先做多题并发和代理群 | 第一条真实闭环更容易验证；上游子代理需受额度与统计约束 |
| 原生运行时优先，但两者逐个接入 | 一开始同时调试 Codex、Kimi、Prime 和平台 | 先用可用的一种完成垂直切片，第二种不更改核心架构 |
| 不确定提交先对账 | 网络失败立即重试写操作 | 防止重复创建 Job/Attempt、重复扣费和浪费尝试次数 |
| 单轮有界授权 | 每步人工批准或无限自动权限 | 用户一次授权范围内自主执行；预算、项目、资源或提交范围改变才重新确认 |
| 最佳产物冻结 | 新实验覆盖上一轮高分目录 | 保留可随时复现/提交的最佳版本，探索失败不破坏基线 |
| 前端与科学得分独立验收 | 漂亮演示或“agent completed”视作胜利 | UI、外部连接、远程产物、官方评分分别验收 |
| 监督可关闭 | 默认双层架构一定更强 | 以等总预算对照决定是否持续使用监督；不把组织复杂度当能力 |

## 尚未解决的外部事实

当前比赛的完整规则、正式截止时间、准确评分/提交载荷和用户实际可用模型，必须在施工环境连接后确认。本包已提供核查入口与阻塞语义，没有把历史协议假定为现行契约。

施工代理发现接口与设计冲突时，在此追加“事实 / 最小修改 / 实测证据”；不更改旧决定的历史描述，不未经实验扩展为通用框架。

## 施工期记录（2026-09-17，阶段 1）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 本机无 `codex` on PATH，但 `~/.codex/.sandbox-bin/codex.exe`（0.154.0-alpha.6.2）与 `~/AppData/Local/OpenAI/Codex/bin/*/codex.exe`（0.153.4）存在且 `~/.codex/auth.json` 在位 | 大脑选 Codex，可执行文件自动探测（环境变量 → PATH → 两个已知位置）；Kimi 保持未接入边界 | `docs/INTEGRATION_STATUS.md`：`codex --version` 与 app-server initialize 握手原始返回 |
| codex-cli 0.154 的 `initialize` 返回 `{userAgent, codexHome, platformFamily, platformOs}`，无 `serverInfo`/`capabilities` 字段 | 版本从 userAgent 正则提取；capabilities 记录为空对象，能力标记保守（resume/steer/usage 均 false） | 握手响应原文已存 INTEGRATION_STATUS.md |
| 握手成功不代表已登录 | `inspect()` 的 `authenticated` 置 `None`（未知），detail 明示“登录态未由握手验证” | 前端连接卡三分离显示 |
| Prime Agent、bohr CLI 均未安装；`prime-agent --mode rpc` 帧格式无本机核实途径 | 适配器只做 inspect（如实报未安装）+ Demo 执行器；未核实前拒绝启动真实会话 | 启动 connected Run 被 blocked，原因准确列出 |
| 无 WSL2 施工环境确认成本高于收益，且当前交付需在用户机器直接运行 | 阶段 1 后端原生 Windows 运行（Git Bash + uv），记录为偏差；文件锁用 msvcrt | `uv run cyberscientist serve` 实跑 + smoke 22/22 |
| Pydantic 模型定义在 `create_app` 内部时，`from __future__ import annotations` 导致 FastAPI 无法解析 body 模型（实测 422） | 全部请求模型移到模块级 | 修复后 smoke 通过 |
| FastAPI 异常 handler 需与 HTTPException 一致嵌套 `{"detail": {...}}`，且 `JSONResponse` 第一个位置参数是 content | 统一错误信封为 `{"detail":{code,message,recoverable,details_ref?,details?}}` | smoke 断言该形状 |
| 经验修订为内容寻址 hash，回滚必然命中已有 revision | 回滚幂等：指向已有修订而非报唯一键冲突；不制造伪历史 | `tests/test_experiences.py` + smoke 回滚用例 |
| 用户指导文本会进入事件库与操作日志 | 入库前截断（2000 字符）并遮蔽明显密钥形态（sk-/AKIA/Bearer 等） | `controller._redact` + 审查修复 |
| `model_turns` 等授权上限在阶段 1 无真实模型调用路径可强制 | Trial 数/运行时长/大脑判断数立即强制；`model_turns` 在 budget 响应中显式标 `enforced:false` + 原因 | `controller._budget_status` |
| 暂停期间 Demo 执行器仍会发完脚本事件 | 控制器在 pausing/paused 期间只记账不推进 Trial/大脑；恢复时若执行器空闲则重新下发任务（`prime.task_resumed`） | smoke 暂停/恢复/继续闭环 22/22 |
| 官方 install.sh 仅支持 macOS/Linux，Windows 无官方安装路径 | 手动复现脚本行为：R2 发布桶解析 stable 版本 → 下载 tarball + SHA256SUMS → 校验 → `npm install -g`（v0.9.5，190 包） | `prime-agent --version` = 0.9.5；INTEGRATION_STATUS.md |
| Prime RPC 实为 type-tagged JSONL（`{"type":...}`+可选 id 关联、响应 `{"type":"response"}`、`extension_ui_request` 需应答），非 JSON-RPC | 适配器按官方 docs/rpc.md v0.9.5 重写为 `PrimeJsonlClient`；JsonRpcStdio 保留给 Codex | get_state 探针成功，返回字段与文档一致 |
| OpenRouter 免费 GLM（`z-ai/glm-5.2:free`）不支持工具调用；智谱「GLM-5.3-Flash 夜间畅用」免费仅限 ZCode | Prime 执行器模型改用 `deepseek/deepseek-v4.1-flash`（用户授权付费，$0.15/$0.6 每 M token，工具支持）；密钥经 env 引用不入 models.json | 真实工具往返 PASS：ipython 写读文件，成本 $0.00185775，transcript 存 `checks/fixtures/real/` |
| npm 全局 bin 的 `.cmd` shim 不能经 CreateProcess 直接执行 | `PrimeRpc._resolve_argv` 解析全路径并用 `cmd /c` 包装 | spawn 矩阵测试 + 往返探针 |

## 施工期记录（2026-09-18，阶段 1.5/1.6：Kimi 大脑 + 执行系统三选一）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| Kimi Code 2.0（TypeScript 重写版）已移除 `--wire`；程序化接入面是 `kimi acp`（ACP，JSON-RPC 2.0 stdio） | 大脑适配器改为 ACP：`initialize` → `session/new`（**必须带 `mcpServers: []`**）→ `session/prompt` | `checks/probe_kimi_brain.py` PASS；agentInfo=Kimi Code CLI 2.0.0 |
| ACP 流式 chunk 是增量片段 | 空字符串无缝拼接（不可用换行），否则 Decision JSON 被切碎 | 探针 transcript；`brains/kimi.py` |
| ACP 反向 `session/request_permission` 应答形状未按标准形状生效（两种形状实测均判 rejected） | 执行器会话改用 `session/set_config_option {configId:"mode", value:"yolo"}`（引擎内自动批准），工具事件仍全程留痕；保留兜底自动同意分支 | `checks/probe_kimi_executor*.py`：yolo 后零权限请求、写文件 PASS |
| ACP `session/set_config_option` 支持 `model`/`thinking`（low\|high\|max）/`mode` | 思考强度 UI 通用档映射：low→low、medium→high、high→high、xhigh→max；大脑与执行器各自生效 | 探针 v2 实测 setter 返回更新后的 configOptions |
| Prime 的模型流式调用可无超时悬挂（实测 8 分钟死寂、CPU 全闲） | 执行器事件流加 240s 无事件看门狗（`with_stall_watchdog`），产 `trial.stalled`；控制器 abort+记 failed+大脑裁决 | run_7865220639 事件流；run_19c53aed8c 看门狗触发实测 |
| abort 后 Prime 会话拒绝新输入（"queued session input is suspended"）且事件泵已退出 | stall 处置改为：关旧会话、开全新会话、重启事件泵 | run_19c53aed8c `prime.task_accepted rejected` 事件 |
| Trial 正常完成后控制器事件泵退出，同会话下一 Trial 无事件来源（Kimi 执行器实测卡死） | `_apply_decision` start_trial 受理后重启泵（`_start_pump` 回调）；resume 路径同样 | run_82d3af8c4e 卡死 → 修复后 run_9785db28ab 两 Trial 连续完成 |
| Trial done 后 `_active_trial_id` 为 None 导致大脑 packet 丢 `latest_trial_status` | 无活跃 Trial 时回填最近一次 Trial | demo 闭环测试恢复通过 |
| 单用户本地工具，配对码/CSRF 是多余摩擦 | 删除配对码、会话 cookie、CSRF；后端仅绑 127.0.0.1，无任何认证（用户明确确认该边界） | 用户决定；前端配对门已删 |
| Prime 的 `~/.prime/agent/models.json` 手工维护会与 secrets.json 漂移 | 后端托管：secrets/settings 变更与启动时从 `llm_profiles`+secrets 重建 models.json；`_status.prime_models_synced` 真实回读校验 | PUT settings 后 `_status.prime_models_synced=true` 实测 |
| 执行系统选型落地为三选一 | `settings.executor.runtime` ∈ kimi（默认）/prime/codex；包目录仍名 `prime/`（改名 executors 留债阶段 2） | controller._make_prime 分发；run_9785db28ab 默认路径闭环 |
| Codex 执行器无额度无法实测 | `prime/codex_exec.py` 保守实现并显式标「未验证」；不作为默认可用路径宣传 | STATUS.md 未验证清单 |

## 施工期记录（2026-09-18，邮箱双轨：收割/实验）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户要求双轨邮箱：实验邮箱（批量注册、提交主体、每号限 10 次）+ 收割邮箱（唯一、用户提供、只提交实验邮箱已验证的最高分现成包） | 新表 mailboxes（harvest 唯一部分索引）+ submissions（score NULL=未知、operation_id 幂等、收割行引用来源提交）；服务层 `mailboxes.py`，平台适配器 `mailbox_platform.py`（demo / bohrium_playground 骨架报准确缺项） | `tests/test_mailboxes.py` 8 用例全过 |
| `authorizations.max_submissions` 一直只有记录没有消费点 | 本功能成为第一个真实强制点：提交前校验已用/上限，用尽 403 NEEDS_AUTHORIZATION | curl 实测 run_9785db28ab（0/0）被拒 |
| 收割资格必须可机械验证 | 硬条件：confirm=True（UI 手动确认）+ 来源是实验邮箱提交 + 已有官方得分 + 是当前最高分 + 包哈希未变；缺一拒绝并给出准确缺项 | 测试覆盖全部拒绝路径 |
| 外部平台调用（注册/提交/查分）不能在 DB 事务内 | 两段事务：配额原子预占 → 适配器调用（事务外）→ 结果落库；适配器失败释放邮箱配额 | 测试 + 代码审查 |
| GET /settings 响应的瞬态 `_status` 曾被前端整体回写 PUT，落盘进 settings.json（既有 bug） | PUT 时剥离 `_status`；清理已落盘字段；顺手把 contracts/config.schema.json 对齐现实（executor/shadow/mailbox/revision、空字符串默认、llm_profiles 实际字段） | DEFAULT_SETTINGS 与当前 settings.json 均通过 schema 校验 |
| 大脑的 request_submission 动作仍为 deferred | 本轮提交动作只由用户在 UI 发起；代理自动提交仍关闭（授权边界） | STATUS.md 未验证清单 |

## 施工期记录（2026-09-18，Playground 真实适配器接通）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户给的 asp_ token 是**人类账号**凭据（/auth/me → id 90229, userType=human），不是 agent token | 实验邮箱注册改走官方 Option A：人类 token 调 `POST /api/agent/register`，响应立即含 agent 的 asp_ token；收割邮箱直接用该 token 提交 | `checks/results/platform_probe2.json`（/auth/me、/agent/work、/agent/register 列表均 200） |
| 官方完整 API 文档在 `GET /api/docs/dev/AGENT_API.md`（13 篇 /api/docs 文章不含字段细节） | 抓取快照存 `checks/results/AGENT_API.md` 作为适配器依据；提交三步与查分形状按此实现 | 文档快照 + 公开 attempt 的 /score 实测形状 |
| 查分端点评分中是 `scoringState.scoreIsFinal=false`、`score` 可能是中间值 | `fetch_score` 只在 scoreIsFinal=true 采信（displayScore 优先，回退 score），否则如实 None | 真实 attempt 44507 的 /score 响应（evaluating 状态），原文存 `checks/results/score_shape_probe.json` |
| 平台 attempt id 是查分唯一入口，原 submissions 表无处存放 | 新增 `submissions.platform_ref` 列（幂等 ALTER），submit 回执落库，poll_scores 用它查分 | 迁移幂等；73/73 回归 |
| `submit_package` 原签名没有 challenge_id，真实平台提交必须定位 challenge | 接口加 `challenge_id` 与 `meta` 参数；服务层从 runs.challenge_id 取 | tests/test_mailbox_platform.py 9 用例 |
| 写操作（注册 agent / 提交 attempt）需要用户逐次触发授权 | 适配器只实现通路；平台切换后首次真实注册发生在用户点击前端「注册实验邮箱」时；不自动调用 | settings.mailbox.platform=bohrium_playground；前端按钮即授权点 |

## 施工期记录（2026-09-18，Aiyagari 闭环实测 + 提交动作分级）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| hackathon 题评分要求**真实复现图**（attempt 44534 只有 resultsJson 被拒："Please upload authentic result figures"） | 教训入档：此类题提交必须图+resultsJson+ARM bundle 三件套齐 | 44534 两次评分被拒原文 |
| 已提交 attempt **PATCH 405**（draft-only）、hackathon 题 **fork 403** | 图只能在创建 attempt 时挂载；适配器留债：submit_package 需支持 figures 参数 | 405/403 实测响应 |
| 平台评分器会长时间排队/抽风（44579 图比对 pending 超 15 分钟） | 评分等待改服务端后台轮询（45s，异常全吞下轮重试），任何调用方不再同步阻塞等分 | api.py lifespan 轮询；轮询日志 |
| 提交动作分级：实验邮箱=大脑指令自动执行；收割=用户手动确认 | 契约 Guidance.kind 增加 `submit`：控制器事务外自动 submit_experiment（幂等键绑 guidance），不投递执行器；收割三重硬校验不变 | tests 84/84（新增 3 用例）；CONTRACTS.md |
| 首次真实提交 401 根因：邮箱选择未按平台/真实性过滤，误拿 demo 邮箱 token | submit_experiment 选邮箱加 `platform=? AND is_demo=?` 条件 | sub_3bb8d1f26e 失败记录 → 44534 成功 |
| pypi.org 不可达，无 matplotlib | 纯 stdlib PNG 渲染器（checks/gen_figures_stdlib.py）画 4 张真实数据复现图；科学作图正式路径仍属 Bohrium Job（阶段 2） | fig_1..4.png + Fig3 八个 r 点 VFI 实测输出 |

## 施工期记录（2026-09-18，技能管理系统）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 平台题目详情（GET /challenges/{id}）无 skill 要求字段（实测 aiyagari-1994-qje 只有 datasets/figureData/hackathon 等） | 题目级技能绑定由用户在前端勾选，存自建表 `challenge_skills`；平台字段若将来出现可再接入 | 题目详情实测响应 |
| 「启用技能」需对 Kimi/Codex/Prime 三运行时都成立 | 启用 = start_trial 时把技能名称+描述注入执行器任务文本 + 事件 `trial.skills_enabled`；技能本体已物理装在各 CLI skills 目录，CLI 自行发现 | tests/test_collaboration.py 注入断言（FakeExecutor prompt 含技能段落） |
| 技能 frontmatter 有 `description: >` 折叠多行 | 复用项目已有 pyyaml 解析（未手写解析器），描述折叠为单行 | tests/test_skills.py 多行描述用例 |

## 施工期记录（2026-09-18，预算运行时可调）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 大脑判断上限读 Run 启动快照，其余预算（Trial/模型/时长/提交）都读实时 settings 或授权行——同一控制器两种口径 | `_run_one_review` 统一为实时 settings；运行中的 Run 用直接 UPDATE config_snapshot 热改（controller 每次审阅重新读 run 行，免重启生效） | 运行中 Run budget 显示 4/20 且持续推进；tests/test_controller.py 2 例 |
| 预算调整需覆盖两个存储面 | PUT /runs/{id}/budget 分流：大脑/Trial 上限→settings.run_defaults（全局实时）；模型/时长/提交→本 Run authorizations 行（本就实时读取，无需新列） | update_budget 测试 + 事件 run.budget_updated |

## 施工期记录（2026-09-18，大脑出错根因修复）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 提示词只给 `"watchlist":[]` 空数组示例，契约却要求五项必填的 Watch 对象 → 模型稳定输出字符串数组，审阅整单作废 | 双大脑提示词补 Watch 项结构 + "禁止字符串数组"；契约本身不变 | checks/brain_errors.log seq 43/48 报错原文；修复后回归 96/96 |
| Trial stalled 后语义校验拒绝 steer（"需要活跃 Trial"），而停滞现场正是最需要大脑裁决的时刻 → 拒绝死循环 | validate_semantics 加 stalled_trial_id 通道（仅限当前 stalled Trial）；steer 执行时 stalled→active 恢复 | seq 40/54 拒绝记录；test_steer_to_stalled_trial_recovers 端到端 |

| Decision 语义校验整单拒收：一个动作非法，合法动作与经验提议全部陪葬，大脑只能盲重试 | 逐动作校验执行；拒绝原因以 brain.action_rejected 进事件流，大脑下一帧可见并自我纠正；硬约束（授权/预算/方向唯一）保留 | test_decision_per_action_rejection / test_decision_second_direction_op_rejected_only |
| ReviewResult 一处格式错整单作废（笔记、观察范围全丢） | 两级 salvage：注释字段规整 → guidance 单点丢弃降级；全部修复进 brain.review_salvaged 事件，可审计 | test_review_salvage_string_watchlist / test_review_salvage_bad_guidance_downgrades |

| 后端重启后 phase=running 的 Run 无事件循环成僵尸，且控制接口提示"重启恢复"但重启什么都不做 | lifespan 启动对账 reconcile_on_startup：僵尸→recovering + 悬空审阅作废；resume 从 recovering 重建会话并让大脑以 recovery 审阅裁决，不盲目续跑 | test_reconcile_and_resume_after_restart |
| 终止只改 DB 不清理执行器会话（孤儿 CLI 进程） | terminate best-effort abort 执行器会话，成功/失败都记事件；stalled Trial 一并 interrupted | test_terminate_aborts_executor_and_cleans_trials |

## 施工期记录（2026-09-18，大脑自动唤起修复）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| submit_checkpoint 只在产生 review_id 时 notify——review="none" 的进度检查点落库后 shadow 无人唤醒，生产只靠 worker 空闲扫描（最长 60s） | 新检查点（非去重）一律 notify；去重/冲突路径不变 | test_t2/t3/t3b 等 checkpoint 驱动 shadow 用例在 max_interval=3600（关闭周期扫描）下仍即时触发，30/30 |
| shadow 只吃触发词表事件，执行器沉默干活（纯心跳/进度）时大脑永不唤起；max_interval_seconds 形同虚设 | 新增 periodic 兜底：到点且 covered_seq 之后有 executor/user 源新事件才排 shadow（trigger="periodic"）；大脑/控制器自身记账事件不算"新事件"——这是防自激的关键边界 | test_periodic_shadow_wakes_brain_when_executor_silent（唤起+答复后不自激） |
| MCP 桥单次 POST 曾 83s 超时（-32001），检查点上报丢失 | _post 超时 30s→10s，OSError 瞬断重试一次（HTTP 错误不重试）；超时根因未复现定性，标记未验证 | test_mcp_bridge_post_retries_transient_hang |

## 施工期记录（2026-09-18，MCP 桥孤代理崩溃）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 执行器读二进制/GBK 日志把孤代理字符（U+DCA2 类）带进报告文本；桥 _post 严格 UTF-8 编码抛 UnicodeEncodeError，崩溃发生在 HTTP 发送前，桥进程死亡 → 客户端 -32000，且每次重拉必再崩 | encode 改 errors="replace"（U+FFFD 替换，内容保留）；main() 兜底：_handle 任何异常返回 -32603 而不是进程死亡；stdin/stdout 显式 UTF-8（Windows GBK 是同族隐患） | ~/.kimi-code/logs/kimi-code.log 11 次同款崩溃 traceback；修复后真实子进程端到端 exit 0 双响应；test_mcp_bridge_survives_lone_surrogate_payload |
| 桥由 Kimi 客户端每次调用现拉起、模块从磁盘现读 | 修复即改即生效，运行中 Run 零干涉 | 日志显示客户端反复重拉（10:22/17:08/17:13/17:16/17:27 连续崩溃记录） |

## 施工期记录（2026-09-19，经验自进化闭环）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户原则：硬门只留「全局经验用户审批」，其余判断归大脑；冲突=更新而非拒绝框架 | proposal 直接落库：题内 active / 全局 candidate；target_id=追加新修订；无去重/动作集硬编码 | grilling 两轮记录；test_experience_challenge_proposal_lands_active / test_experience_target_id_updates_in_place |
| Run 终态是证据最完整的整理时机，但 review worker 在终态后退出 | finish 推迟为 curation 生命周期审阅，_finish_request 钩子在审阅完结后自动 _finalize_run；额度用尽/失败/作废都放行收尾（防死锁） | test_finish_defers_to_curation_then_finalizes |
| 全局整理没有 Run 可依附（用户手动触发） | 一次性大脑会话（brain.open/review/close），产出仍走 proposal 规则落 candidate；内存状态机 + CURATION_RUNNING 护栏 | test_curate_global_experience_runless_session |
| 效果回联粒度用户定为题目级、只在整理时给大脑看 | runs.experience_snapshot 起止各记一份版本清单；usage 聚合只在 curation packet 中出现，平时帧不带 | 同上测试断言 at_start/at_end 与 usage 字段 |
| 执行器拿不到经验正文（设计 A8：不注入，自读） | 任务文本给经验库目录 + executor.md 要求开工前读 active 条目；更新经大脑指导转发 | 测试断言任务文本含「经验库目录」 |

## 施工期记录（2026-09-19，走查修复批次）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 题页「提交与评分」按 run_id 查，跨 Run 提交不可见（用户此前报"二阶段接入"问题） | 新增 `GET /api/v1/challenges/{id}/submissions` 聚合端点；前端优先调之，旧后端 404 时回退 run 级 | WebBridge 实测 4 条全显（verify-2-aiyagari.png）；test_mailboxes 聚合用例 |
| curation 审阅完结依赖 phase=running 钩子，三条路径（obsolete/重启恢复/pause 在途）Run 永远到不了终态 | `_maybe_finalize_after_curation()` 统一收口，不再要求 phase=running，curation 任何终态都放行 finish | test_collaboration 4 个收尾用例 |
| curation 状态纯内存，后端重启后前端永卡「整理中」 | 状态变迁落盘 global_curation.json（原子写）；磁盘 running 残留重启后如实转 failed+interrupted | 重启对账用例；未伪造「成功」 |
| 手动轮询与后台轮询并发可重复记 scored 事件/覆盖分数 | scored 落库改条件 UPDATE（仅 unknown/pending→scored），rowcount≠1 跳过 | test_mailboxes 并发幂等用例 |
| poll 端点在事件循环内同步 HTTP，阻塞全服务 | `asyncio.to_thread` 卸载 | test_polling 慢评分接口下 health <0.5s 用例 |
| 前端 stalled 判定用 `prime.trial.stalled`，后端实际发 `trial.stalled` | 统一为后端实际事件名；labels.ts 批量补齐事件/状态中文映射 | labels.ts 映射表；走查事件流截图 |
| 指导状态 opId 匹配永不命中（后端不回带 operation_id） | 改时间序匹配：只认发送后到达的消费/投递事件，防 SSE 历史回放误判 | ResearchPage.tsx:209-223；构建零错误 |
| MCP 桥兜底分支对非 dict 消息二次 `msg.get` 崩溃 | isinstance 检查 → -32600，桥进程不死 | test_mcp_bridge subprocess 实测 null/数组/标量 |
| 题内 proposal 信任模型自报 challenge_id | scope=challenge 时强制绑定当前 Run 题目，不一致记 experience.proposal_rebound | proposal_rebound 用例 |

## 施工期记录（2026-09-19，URL 导入与弹窗误关）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 「URL 导入需要 Token」是硬编码 502 占位，与凭据无关；平台读端点公开无需 token | url 分支接真实 `GET /challenges/{id}`（to_thread 卸载）；slug 解析白名单；按 platform_challenge_id 幂等 | 真实 curl 三路径（幂等/404/422）；test_import_challenge_url_api |
| 平台题目详情 JSON 自带完整 Markdown 题面（content 字段），无需二次请求 /content | 单次 GET 落库；标题优先 title_zh；contract_status 如实 unknown | 真实响应 5394 字符题面 |
| 原生 dialog 的 click 在「输入框拖选后背板松手」时 target 也是 dialog → 误关 | Modal 改 mousedown+click 双确认背板才关闭 | components.tsx；npm build 零错误 |

## 施工期记录（2026-09-19，算力授权 max_jobs）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| max_jobs 只有 config 默认值，无存储/消费/API，大脑观测到 0 判"不能用 Bohrium" | authorizations 加列（幂等迁移）；authorize/update_budget/_budget_status/观测帧全链路；前端启动与预算弹窗加字段 | test_max_jobs_authorization_roundtrip；真实 Run PUT budget 回读 max_jobs=3 |
| 用户要求改默认 | DEFAULT_SETTINGS 与线上 settings.json 同步 0→3 | settings revision 13 回读 |
| 算力约束仍在提示层（观测帧+提示词），执行器 shell 无硬拦截 | 如实标注留债；硬拦截需钩子进执行器工具层，不在本切片 | STATUS 留债记录 |

## 施工期记录（2026-09-19，门禁兜底与待验收 steer）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| reported_complete Trial 等验收时大脑 steer 被「需要活跃 Trial」拒（事件 seq 363） | validate_semantics 加 reported_trial_id；steer 执行路径本就不改非 stalled 状态，保持验收语义归大脑 | test_semantics_steer_to_reported_trial + test_steer_to_reported_complete_trial_accepted |
| waiting_brain 唯一开门路径是 blocking+intervene 答复；承载审阅被重启作废后永久卡死（事件 seq 369） | 新增 _release_orphaned_gate：无在途 blocking 审阅时放行并留痕；挂 run_loop 启动对账后与回合边界。SILENT 不放行语义不动 | test_orphaned_waiting_brain_gate_released_at_turn_boundary + test_recovery_resume_heals_orphaned_gate_and_allows_start_trial |
| pausing（abort 收据 unknown 时可能长期停留）前端无任何控制按钮 | 终止按钮对 pausing 开放并标注「不等暂停确认」 | ResearchPage.tsx；npm build 零错误 |

## 施工期记录（2026-09-19，Decision salvage 与 kind 枚举）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 经验提议是注释性内容，但结构校验失败整单拒收，finish 主决定陪葬（seq 513-514） | _apply_decision 加 salvage：逐条剔除非法提议（全文留 brain.decision_salvaged 事件），剔除后重验 | test_decision_salvage_drops_only_invalid_proposals |
| 大脑提示词未列 kind 合法枚举，模型自创 'finding' | Kimi/Codex 提示词补「仅限 heuristic/procedure/failure/platform」 | 提示词 diff；真实表现待恢复后观察 |
| blocking 生命周期审阅收到被整单拒的 Decision 后请求标 done 但门禁不开 → 孤儿 waiting_brain | 已由 _release_orphaned_gate 兜底（恢复/回合边界放行并留痕） | 本论恢复后验证 |

## 施工期记录（2026-09-19，常驻目标与 time_limit 热循环）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 大脑以「完成侦察目标+省配额」判断 finish，与用户「满分前不停」意图冲突 | 提示词层写常驻目标（Decision 提示词 + shadow 指令段），不加硬代码闸门 | 恢复后大脑 steer 替代 finish（seq 533） |
| run.time_limit 分支无 await：置 paused 后 continue 空转，同步 DB 写堵死事件循环，垃圾事件 12.5 万条 | 守卫 phase=="running"：只触发一次，随后停泊等信号 | test_time_limit_pauses_once_without_hot_loop；health 恢复响应 |
| 授权时长按墙钟计（含暂停），90 分钟在暂停中耗尽 | 语义保留（有界授权初衷），用户可运行中经预算 API 调整；本次提至 1440 | PUT budget 回读 run_minutes_exceeded=false |

## 施工期记录（2026-09-19，blocking Decision 答复开门）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| blocking 生命周期审阅的答复形态是 Decision，但 start_trial 要求 gate=='open'，开门又只在 ReviewResult 路径 → 答复被自己的门禁拒绝（seq 868） | blocking 审阅收到 Decision 时先同事务开门（rowcount 守卫，只在等待中才记事件）再应用动作 | test_blocking_review_answered_by_decision_opens_gate（事故复现） |
| 资源核对：trisol/wenyon 是平台认证服务而非公开包，PyPI/bohr 查无不等于不可得；最佳尝试 100 分 | 结论记入 STATUS，供大脑下轮 steer 纠正「满分路径不可行」判断 | 平台资源页 + 公开 API + 题面 quickstart |

## 施工期记录（2026-09-19，开局大脑先行探查）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| lifecycle 帧无任何题目信息，大脑开局全盲、只能信执行器转述 | _lifecycle_packet 加 challenge 块（标题/链接/资源清单各帧带，完整题面仅 run_start/recovery） | test_lifecycle_packet_carries_challenge_at_run_start |
| 平台资源清单导入时未落库 | challenges.resources_json 幂等迁移 + 导入存储 + 存量回填 | test_import_challenge_url_api 扩展断言 |
| 大脑提示词一律「不要使用任何工具」，开局无法自查页面 | run_start 触发器解除禁令并要求先探查再规划；其他触发器不变 | 提示词 diff；真实表现待下个 Run |

## 施工期记录（2026-09-19，大脑证据帧盲区）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 执行器关键进展（认证通过/数据就绪）只写在思考流，不落 checkpoint；大脑帧对 progress 只计数 → 基于过期印象误 pause | 帧加 executor_digest（非思考 detail 摘录，尾部 12 条×160 字符，脱敏）；lifecycle 帧事件带 excerpt | test_t10b_executor_digest_reaches_frame |
| 行为层根因：执行器不知道「思考≠大脑可见」 | executor.md 加 checkpoint 纪律清单（认证/数据/任务/评分/阻塞/假设推翻立即落 checkpoint）；brain.md 说明 digest 证据效力 | 提示词 diff；真实表现待恢复后观察 |
| 思考流仍不进帧（信息边界与 token 上限） | 「思考:」前缀过滤，两侧帧一致 | 同上测试断言 |

## 施工期记录（2026-09-19，AskUserQuestion 路由大脑）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 响应帧缺 "jsonrpc":"2.0"，ACP elicitation 路径严格校验判为 RPC 失败 → 回退 request_permission；该回退对提问在当前 CLI 版本无效（选中仍 dismissed） | jsonrpc_stdio 请求/响应补 jsonrpc 字段；声明 elicitation.form 走正道 | 探针 v3：修复后无回退，工具结果含所选答案且代理确认 |
| 全自动系统没有人类在线，执行器提问需要回答者 | 问题路由大脑：executor_question 审阅（小上下文、选项校验、额度记账、140s 超时如实 decline） | test_t10e_executor_question_routed_to_brain |
| 「所有工具请求都应该批准」 | Kimi 执行器 mode=yolo（引擎内全批准）+ 兜底自动批准已在位，无需改动 | 既有探针/生产事件 |
## CS-EV-01 证据入口与准入（2026-09-26）

- PR-1 已获单次授权并完成：`GET https://play.bohrium.com/api/protocol` 返回 HTTP 200，原文 21194 字节，SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`。`contracts/arm_protocol.json` 保存该公开协议及抓取时间、来源哈希；本地完整度仍只叫 `local_estimate`，不冒充平台评分。协议规定七种 typed step 与六个准入信号，至少满足一个。
- PR-2 已获单次授权并完成：本机只读导出 USCT 接续 Run 的事件 3122、3138；脱敏摘录只保留准入与评分字段，不保留操作者身份、原始 manifest 或账号字段，也不进入本次提交。真实 bundle 回执的状态路径为 `bundleStatus=needs_review`，准入路径为 `validation.trace_admission.admitted=false`，规则路径为 `violations[].rule=trace_admission_blocked`。所以上传后必须先拦 `/submit`，保留远端 draft 与本地额度。
- PR-3 已获单次授权并尝试一次：本机配置的 Linux `bohr` 对固定命令 `wenyon dataset download paper2arm-task-reproduce-nonlocal-solitar-243cf090 --version 1 --output-dir ... --output json` 报 `unknown command "wenyon"`，没有文件落地。退出码为 0 但 `_native` 按错误文本判为失败。回执 JSON 形状、目录布局以及 `public_manifest_sha256` 的计算对象**仍未知**；Wenyon 物化即使由 fake CLI 成功也最多标为 `unverified`，`hash_semantics=unknown`。不得用这个失败探针推断账号权限或服务不可用。
- PR-4 未授权、未执行：镜像事实探针 Job 只提供模板与普通受控 Job 路径，真实镜像 API 和结果下载链路未验证。Wenyon 到 `dataset_path` 的映射同样未验证，大于 1 GiB 的输入明确拒绝。
- 数据物化的请求授权绑定发起 Run；即使同题另一条 Run 曾获授权或留下相同 operation_id 的回执，也不能借用其许可。逐文件哈希采用流式计算，避免为最多 1 GiB 的输入加载整份文件。
- 大脑上下文改造只测量，暂不改变审阅行为。后续若 `tokens_last_total` 中位数超过 120000，或 p90 延迟超过 60 秒且静默观察后 20 个事件内方向改变率低于 5%，再单独立项核查事件合并或按研究阶段传递证据。阈值是本地立项条件，不是模型质量结论。
- 回退边界：本次迁移只增加表和列，旧版代码看不到新字段。若新 Run 已处于 `awaiting_budget`，回退前须先提高预算/放弃待处理意图/结束 Run，不能让旧版控制器误以为研究门禁仍开放。

## CS-EV-01 工具链阻塞修复（2026-09-26）

- PR-3 的 `unknown command "wenyon"` 是本机 `bohr 1.1.0` 的命令缺失，不能推断服务、账号或数据集状态。项目忽略目录里已有来自 `@dptech-corp/bohr-cli-linux-amd64@2.7.8` 的二进制，缓存 npm 归档 integrity 与解包二进制一致；Wenyon 1.36.0 扩展二进制 SHA-256 与本地 manifest 一致。复制到 `.cyberscientist/tools/wenyon-local/` 后，隔离 HOME 下 `extension list` 返回 `status=ok`，`wenyon dataset download --help` 返回 0。只为数据入口配置该客户端，保留原 Job 客户端，避免新版 Job 标志/回执协议未经验证就切换。
- 旧版 bohr 的本机错误输出可能把 AccessKey 放进 URL 参数；诊断命令须经后端 `_native` 脱敏或在输出前脱敏，不能直接保存原始 stderr。Wenyon 的新版客户端仍不代表账号服务访问成功，真实下载与哈希语义要等待另一次有界授权验证。
- 第二次获授权的 PR-3 固定命令已到达 Wenyon，返回退出码 3 和 `401 Not authenticated`，无文件。专用 HOME 下新版 bohr 的本地 `auth status` 报 `ak_present=true`/`auth_method=access_key`，Wenyon 的本地 `auth whoami` 报 `not logged in (no state)`。这支持“Wenyon 缺少自身可用的 Vouch 登录态”的诊断，但不能据此推断 AccessKey 是否有效或数据集权限。后端既有 `AUTH_REQUIRED` 分类经真实脱敏回执回归测试覆盖；前端展示同一隔离 HOME 的登录检查提示。开发期间不自动登录、不追加下载尝试，真实数据和 `public_manifest_sha256` 语义仍为未知。

## CS-EV-01 PR-3 认证与清单核实（2026-09-26）

- 用户再次明确授权项目隔离 HOME 内的原生登录，以及登录态通过后的单次同数据集下载。新版 bohr 2.7.8 的 `auth login --ak` 退出码 0；Wenyon 1.36.0 的本地 `auth whoami` 随后通过。子进程的 HOME 与 XDG 配置、状态、缓存、运行目录均指向项目忽略目录，未改用户全局 CLI 配置。登录回执仅保存退出码和输出哈希，不记录账号标识或令牌。
- 唯一一次下载 `paper2arm-task-reproduce-nonlocal-solitar-243cf090@1` 返回退出码 0、`downloaded=2`、`failed=0`、`bytes=1148`；落地 `public-manifest.json`（467 字节）和 `resources/README.md`（681 字节）。本机第四季列表快照登记的 `public_manifest_sha256=0d3e9c45f69a43e78ec263e15f5e9f61b8bf5f479e744ee51541c3cc42d55a64`，恰等于 `public-manifest.json` **原文字节**的 SHA-256，而不等于对解析 JSON 重新序列化后的哈希或下载文件列表哈希。清单中的 README 哈希及大小、题目登记总字节数也完全匹配。完整回执、脱敏摘录、文件及其哈希清单保留本机；本次仅提交文字结论，不提交实验文件。
- 因此 Wenyon 物化仅在有 `public_manifest_sha256`、原始清单哈希匹配、清单为已识别的 `playground-wenyon-public-manifest/v1` 且全部声明文件和总字节数匹配时标 `verified`/`manifest_sha256`；未知清单格式仍 `unverified`，任何可核对的不匹配标 `HASH_MISMATCH`。Run 内物化的 `receipt_json` 保留 CLI 退出码、脱敏 stdout 哈希及非敏感下载计数，供后续审计。本次只是授权探针，不将数据冒充已进入真实 Run/Job；Run 内物化、Job 输入关联和其他数据集格式仍待真实验证。
- 原始 pytest 挂起的最小复现是 `asyncio.run(asyncio.to_thread(lambda: 1))` 在线程返回后不能退出。根因是当前沙箱拒绝 socketpair 的 `send(2)`（EPERM），但允许同一描述符的 `write(2)`；并非已证明的 Python 3.12 缺陷。`tests/conftest.py` 仅在探测到该限制时改用等价的 `os.write` 跨线程唤醒，不改产品运行时。回环监听被沙箱禁止时，真实 CLI SIGTERM 测试明确跳过；在允许回环监听的环境仍执行。

## CS-EV-01 真实 Run 与 PR-4 Job 验收（2026-09-26）

- 本次明确获授权继续真实运行验收和单个 PR-4 Job。Run 限 20 分钟、1 Job、同时 1 个、2 核/2 GB/10 GB、无 GPU，`max_submissions=0`。首次开局 Codex 大脑实际产出合法的 v2 Decision，但 `decision_extraction._extract_json` 只接受 v1，造成误暂停；修复为同时接受 v1/v2，使用同一 Run 的 recovery 控制恢复。实际原始最终消息经修复后提取并通过结构校验，回归测试覆盖 fenced v2 Decision；未改原生代理或授权边界。
- PR-4 模板原写 `c1_m1_cpu`，本次真实只读机器目录没有该规格，最小 CPU 为 `c2_m2_cpu`，故模板及断言按实际目录修正。唯一 Job 经普通网关提交，`purpose=probe`，其冻结输入和数据引用均指向本轮核验过的物化记录；逐文件哈希和远端创建回执均有本机审计记录。列表对账观察到 `Finished`，但描述和结果下载的旧 CLI 回执均为解析错误；新版 CLI 对该旧协议 Job 返回 404。故运行脚本是否成功、镜像事实和远端数据读取一律为 unknown。未创建第二 Job 或 Attempt。
- 审计根目录为本机忽略的 `.package-checks/real-acceptance-20260926T073421Z/`，其中保留数据库迁移前备份、授权/启动/物化/Job 回执、输入哈希清单及下载失败回执。执行器检查点和交付包保留在 `workspace/runs/`。可提交的实验结果概述见 `docs/CS_EV_01_REAL_RUN_ACCEPTANCE_2026-09-26.md`；本次不提交原始回执、下载数据、工作区包或经验产物。此处真实失败反馈只说明当前服务/客户端路径不可用于读取旧 Job 产物，不推广为所有 Bohrium Job 的结论。

## CS-EV-01a 修补（2026-09-26）

- F1：轨迹准入只适用于 ZIP bundle，代理证据门适用于所有提交格式。JSON/CSV 保持 `not_applicable` 轨迹结论，但在预留邮箱和调用平台前检查 `evidence_class=proxy`；显式覆盖标志随 `submission.created` 留痕。
- F2：用户放弃待处理 Trial 意图后，running Run 排入一次生命周期审阅，帧内带原意图与原因；paused Run 等恢复路径处理。额度用尽仍由现有审阅上限路径暂停，避免门禁打开却无人推进。
- F3：`awaiting_budget` 继续丢弃自动唤醒，但保留 `user_steer` 和显式用户审阅。帧提供当前门禁与待处理意图；Decision 的 `start_trial` 仍受门禁拒绝，合法的结束或放弃意图可执行。
- F4：`trace_anti_fraud.admission.thresholds` 提供日志锚点参与字段和修剪后整行的长度上下限。本地检查先判范围再匹配，不截断超长行，避免比平台宽松；缺失阈值时用当前默认值并记 notes。
- D1：`compute_jobs.retrieval_status` 仅追加列；受控 `job download`/`job log` 只有产生新文件且 CLI 回执成功才记 `retrieved` 并记录文件 SHA-256，否则记 `failed` 与脱敏失败事件。研究帧和前端显示取回状态，轨迹只追加终态结果文本，不改配对状态机。迁移前 SQLite 在线备份及真实探针回执均在本机忽略目录。
- 获授权的一次旧 USCT Finished Job 下载探针使用当前 bohr 1.1.0，进程退出码 0，但后端识别 `ok=false`、无文件；错误是当前沙箱 DNS 查询时 socket 权限拒绝，请求未到平台。该结果只能证明**本环境未能取回**，不能区分 PR-4 单例故障与客户端协议故障，也不能宣称所有 Job 均无法取回。本卡不重试、不切换客户端；下次真实 Run 前应在允许网络访问的环境核实取回链路。

## CS-EV-01b（2026-09-27）

- 不带凭据的网络前置检查一次通过：`getent hosts open.bohrium.com` 与 `getent hosts tiefblue.dp.tech` 均解析成功；`curl -sS -o /dev/null -w '%{http_code}' https://open.bohrium.com` 返回 HTTP 301。由此排除了上一轮探针遇到的本机 DNS/socket 权限阻断。
- 选取 USCT 接续 Run `run_16d9dfa230` 中已登记为 `Finished` 的 `668_joint_budget120_v1`（平台 Job `23424706`）；原 `trial_66895a856c/job1_results` 下已有 22 个结果文件。仅通过 `compute._native` 对当前 Job 客户端 bohr 1.1.0 执行一次只读 `job download`。进程退出码 0，但 `_native.ok=false`，脱敏 stdout 为 `Error: json: cannot unmarshal object into Go struct field RespErr.error of type string`，stderr 为空，新目录文件数 0，故无新旧文件哈希可逐一比对。完整脱敏回执和空输出目录仅保留于 `.package-checks/job-retrieval-probe-net-20260926T160849Z/`，未重试、未换客户端、未创建 Run/Job/Attempt。
- 该次错误已越过网络前置检查，不是上一轮的 DNS/socket 权限拒绝。最初按探针分支将其归类为旧客户端取回失败，并计划在下次真实 Run 前评估协议；随后同轮根因核查发现是后端传给旧客户端的 API host 错配，已按下文修复。失败探针本身不能证明所有远端 Job 都不可取回。
- 受控 `job download` 与 `job log` 的最近一次回执现在分别保存在 `receipt_json.retrieval.download` / `.log`；历史单字段回执按操作迁移。`download_ever_retrieved` 保留已成功下载的证据，使后续日志或下载失败不会把汇总状态降为 failed；未曾成功下载时汇总取最近一次操作结果。每次仍留原有成功/失败事件，研究帧与轨迹按事件截点计算相同汇总。前端继续读取账本汇总状态。
- 后续根因核查修正了本节的临时阻塞判断：旧 USCT 文件原由 `job log` 中嵌入的 ZIP 经 `recover.py` 恢复，不是 `job download` 的历史成功证据。旧客户端的下载请求先访问 `GET /openapi/v1/job/{id}`；后端此前强制给 bohr 1.1.0 设置 `OPENAPI_HOST=https://open.bohrium.com`，该主机对此旧路由返回 HTTP 404，错误信封的 `error` 为对象，恰触发旧 Go CLI 的 `RespErr.error` 字符串反序列化错误。同一 Job 在 `https://openapi.dp.tech/openapi/v1/job/{id}` 返回 HTTP 200、`code=0`。故障根因是**应用子进程 API host 错配**，不能解释为远端 Job 没有结果或必须升级客户端。
- 仅给旧 Job 客户端子进程及其连接检查改用 `https://openapi.dp.tech`，不改用户全局 CLI、不切换 bohr 版本；Wenyon 新客户端仍走 `https://open.bohrium.com`。同一 USCT Job 的 `job download` 随即成功：下载一个 1,900,228 字节的 `out.zip`，ZIP 校验通过，24 个归档条目中的 22 个与旧恢复目录逐文件 SHA-256 一致。PR-4 Job 也成功取回 582 字节 `out.zip`，其中 `results/facts.json` 与 `results/data-proof.json` 可读取。受控网关此前只查裸 `results/facts.json`，现从旧 CLI 的 `<job_id>/out.zip` 有界读取指定成员，不解压归档路径；实际受控下载已将 PR-4 `retrieval_status` 标为 `retrieved` 并登记 `image_facts`。PR-4 的远端 describe 回执给出 `Finished`、`exitCode=0`，数据证明与已登记的 `verified` 物化记录哈希一致；仍不据此宣称平台评分或科学结论。完整回执、归档和哈希清单保存在本机忽略目录，未提交原始实验文件。
