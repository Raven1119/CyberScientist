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

## CS-UP-01（2026-09-27）

- U1：`contracts/arm_protocol.json` 的 `tooling.recorder.trace_row_selection` 是本地选行的依据。公共顶层目录先确定包根；随后按 manifest 字符串指针、`traces/` 优先于 `trace/` 的目录扫描、旧式 JSON 数组依次选行。协议原文规定 `manifest_pointer.value_type` 不满足时忽略并尝试下一规则，所以旧的字典 `trace` 在选行时进入目录扫描，封存后改成规范字符串；其他非字符串/字典类型拒绝为 `INVALID_PACKAGE`。指针是以 `.jsonl` 结尾的字符串但目标不存在时记录 unresolved claim；未封存的准入判为 blocked，封存可用实际选中行修复指针。显式 ZIP 目录成员也参与公共顶层目录判断；缺失根 manifest、无法解析、重复成员和保留路径冲突均拒绝。封存只追加包根内的合并轨迹和数据出处，原执行器文件保持原字节；准入仅检查封存后的字节。未选中的行不能点亮准入信号。
- U2：平台额度以 `(mailbox_id, platform_challenge_id)` 上尚未释放的 `submissions` 预留为唯一来源，读取当前设置的 `mailbox.submission_limit`，不再更新旧 `submissions_used` 列；该列因只加列/表迁移约束保留但不再向 API 输出。旧 `exhausted` 是跨题全局计数的产物，不代表邮箱被停用，初始化时恢复为 `active`；`disabled` 不动。实验邮箱优先继续使用同题已有预留且未满的邮箱；选择、余量复查、冻结预留在同一 `BEGIN IMMEDIATE` 事务内。平台题目 ID 缺失的本地记录使用带 `local:` 前缀的本地 ID，防止多道未关联题被错误合并。
- U3：`displayScore` 是展示分权威值，旧适配器的 `score` 回退值仅保留为暂定且标记缺少 `displayScore`。首次有限最终分为 provisional；同分至少两次、相隔默认 600 秒且当前没有异常才 confirmed。真实旧回执可见 `scoreIsFinal=true`、`state=final`、`workerStatus=null`，因此空 workerStatus 在明确 final 时不单独视为错误；未知且无法判定的状态仍标异常。分项不一致是独立诊断，不覆写展示分，也不单独阻止确认。已确认分默认至少间隔 3600 秒自动复查，到 `roundEndAt+72h`，缺失时到提交后 7 天停止；手动轮询可越过间隔和停止点。经验仅在确认转移时追加结果关联，改分或异常降级时追加撤销事件，历史链接仍可审计，当前效果投影只把未撤销的确认分标为 active。
- U4：所有已出分实验提交都可供用户选择；非最高分、暂定、异常、分项不一致分别给出警示，服务端要求真正的布尔 `acknowledge_warnings=true`，且在预留事务内重算警示，避免评分变化后旧确认越过门禁。包哈希、来源身份、用户手动确认、幂等键和按题额度仍按原约束执行。收割预留事件保存警示及知悉标志。
- 本阶段仅用本机协议快照、已有脱敏证据和 fake 平台测试；未访问账号服务，未启动真实 Run、模型、Job、沙箱或 Attempt。真实平台对新封存包的准入和复评时间线仍需以后有界授权的运行验证。

## CS-UP-02（2026-09-27）

- W1：`max_active_runs` 统计全部非终态 Run（包括 created、blocked、recovering），在 SQLite `BEGIN IMMEDIATE` 中检查并插入，避免并发创建超过上限。原有设置文件若保存了 1，保留其用户可见值；新安装默认 3，可在前端改动。单后端进程锁仍保护 SQLite 和后台轮询所有权，Run 会话、执行器工作目录、令牌、事件和控制队列按 Run 隔离；不开放第二个后端进程共享同一数据库，以免重复恢复或轮询。某 Run 的重启对账失败时把它标为 recovering 并写可读原因；Job 占位保留为 unknown，其他 Run 继续恢复。
- W1：题目模型选择只保存 `runtime/model_id/reasoning_effort`，不保存密钥或可执行文件路径；Run 创建时把它合入非秘密配置快照。已有题目两列为空时，沿用当时全局配置作为旧数据兼容。若题目选了与全局不同的运行时，其可执行文件路径清空，由 Linux 原生发现逻辑查找；缺失会在启动前报错。Prime 模型必须与当前 Profile 一致，旧题目未显式选择时保留旧 Profile 行为。`model_selection` 连接检查只开关原生会话以确认所选模型被接受，不发起 turn；Kimi 设模型失败不再静默沿用默认。提交 `modelTag` 继续读取冻结的执行器配置。
- W1：总览只展示本机账本中的状态与已知得分；沙箱表尚未建立时数量为 0，待 W4 网关接入后自动从沙箱账本计数。未将多个 fake Run 的通过当作真实并行、真实账号限流或真实科研验证。
- W2：活性时钟只由实际研究进展推进：新 Trial/检查点、有效工具进展、指导交付、Job 接受或结果取回、提交和评分；心跳、usage、重复 `bohr job list`、轮询与审阅记账不续命。每 15 秒逐 Run 扫描，运行中且无合法远端 Job/沙箱执行/模型退避时，默认静默 300 秒排 `stall_detected` 生命周期审阅，帧内带组件诊断；修复没有产生进展且第二次到期时追加 `run.needs_attention` 并暂停。正在执行的审阅有单独 900 秒超时；会话失联先重建，执行器原始提示词只在本进程内保留并且仅在已确认空闲后重试，不重放远端 Job。暂停确认未知时保留 `pausing` 并每 30 秒重新核对，不伪造 `paused`。
- W2：模型 429、明确 rate-limit 和额度耗尽错误由同一个保守分类器识别；不确定的协议错误保持普通错误。参考 [OpenAI API 的限流信号](https://platform.openai.com/docs/api-reference/debugging-requests) 与 [官方 `rate_limit_exceeded` 错误码](https://platform.openai.com/docs/api-reference/run-steps/step-object)，但原生 Codex/Kimi CLI 的实际错误文案仍未经真实探针验证。限流只记录脱敏的角色、类型、次数和下次重试时间；有 `Retry-After` 则使用，否则 60 秒起指数退避到 900 秒，连续 3600 秒后暂停并提示。限流尝试不扣大脑判断数、不算审阅失败或执行器中止；重试状态落在每 Run、每角色的 SQLite 表，进程重启后的旧 Run 仍由原 recovery 门禁接管。
- W3：评分轮询分别读取 Attempt 与 `/score`；Attempt 的 `scorecard`、`scoringState`、`bundleStatus`、`updatedAt` 经脱敏和去重成为 `kind=attempt` 回执。分项优先取 Attempt，再兼容旧 `/score`；即使 `/score` 查询失败，已收到的 Attempt 回执仍保存，但不据此推断最终得分。公开 36189 的真实结构含 `harbor_score=100.0`、`trace_score=70.525`、`displayScore=80.0`；按当前一致性公式预期值为 100，因此一致性为 0。本项目历史 46231 的 Attempt 回执没有这两个分项，`/score` 也无 scorecard；这两项保持 unknown，不填零。可提交 fixture 仅保留字段名、类型和必要数值；真实脱敏回执留在忽略目录 `.package-checks/cs-up-02-w3-20260926T211157Z/`。
- W3：`bohrium.host_overrides` 现在可按 `legacy_job` 与 `wenyon` 分组；例如 `{"legacy_job":{"OPENAPI_HOST":"https://openapi.dp.tech"},"wenyon":{"OPENAPI_HOST":"https://open.bohrium.com"}}`。旧平铺 `OPENAPI_HOST` 对旧 Job 客户端仍兼容；平铺值若是新客户端的 `open.bohrium.com`，旧客户端改用已验证的 `openapi.dp.tech`，避免错误路由。新客户端忽略平铺的旧主机和含义不明的自定义旧主机；需要自定义时写入对应分组。应用仅修改隔离子进程环境，不改全局 CLI 配置。
- W3：一次受控 `bohr job list` 因非交互环境缺少 `/dev/tty` 失败；随后以 `bohr job list --json` 只读重查，bohr 1.1.0 在 `https://openapi.dp.tech` 下返回 `ok=true`、退出码 0 和 JSON 列表。前者验证了非交互模式的 CLI 限制，后者验证了旧主机的列表查询；`job submit` 仍未经本包真实验证。原始脱敏列表回执仅保存在上述本机忽略目录。
- W4：沙箱网关使用项目隔离的 bohr 2.7.8、登录态和 `open.bohrium.com`；旧 Job CLI 保持独立。创建在事务内预留数量与最坏存活时长，强制项目 ID、显式 timeout 和 `--request-id=operation_id`；MCP 变更操作使用稳定 ID，远端状态 unknown 时只按 request ID 对账。用户存储、Wenyon/JWT 挂载、继承认证、无期限及保留失败实例未开放。GPU 需单独授权。文件传输仅允许当前 Trial/题目路径，哈希与脱敏回执入账；沙箱 exec 的开始/完成事件投影为成对工具调用。删除请求和最终回收分开记录，远端仍 `destroying` 时保留 `deleting`，后续只读列表确认消失才标 `deleted`，不重复删除。
- W4 真实最小生命周期：第一次创建命令被 bohr 2.7.8 本地 `CONFIRMATION_REQUIRED` 拦下，回执明确未执行、未计费；原 request ID 描述返回不存在、列表为空。受控网关随后对已授权的单次实际创建增加 `--yes`，未更改全局 CLI。第二次创建得到 `data.sandboxID`；默认 `templateID=sdbxagent`，2 CPU、4096 MB。`sandbox exec` 的 JSON 在 `data.exit_code/stdout/stderr` 内；`python3 -c "print(1)"` 返回 0 与 `1`。内联写入小文件后读回字节一致，均有本地 SHA-256。删除命令成功后首个列表仍显示 `status_name=destroying`，稍后的只读对账确认目标不再存在；探针账本的暂态误判已据此修正。回执中的余额以 CNY 表示，但没有沙箱单价、计费时间单位或最终扣费记录，所以**实际计费单位与金额仍未知**。完整脱敏回执、临时探针 SQLite 和文件仅留在本机忽略目录 `.package-checks/cs-up-02-w4-20260926T213030Z/`；该 SQLite 中的夹具 Run 与产品 Run 数据库隔离，没有创建科研 Run、Job 或 Attempt。
- W5：`audience` 缺省为 `both`，老 Markdown 原字节不迁移。大脑帧和清单冻结 `brain/both`，Trial 冻结 `executor/both`；同一 Trial 与审阅帧使用不同边界，避免把执行器选中条目误当成大脑证据。环境事实只接受代码通过已登记的控制器回执事件写入；代理 schema 不允许 `environment`，普通文件编辑和 UI 均只读。沙箱机器/模板/配额、镜像事实和成功的 Job/沙箱客户端主机探测可自动形成全局 active 观察；事件引用、观察时间及 7 天复核期限一并保留。内容冲突追加修订，超期无回执改为带“待复核”的 candidate 并停止注入。旧环境观察不会被推断为当前平台保证；本包仅以 synthetic 回执测试逻辑，未增加外部探针。
- W6：只有新建 Run 的 `config_snapshot.submission_prediction_version=1` 强制 submit 指导带 `prediction_md`；旧 Run 仍可用原指导，手动提交 API 的既有授权和行为不变。缺预测时审阅保留为 silent 并记录可读 `guidance.rejected`，不会建立提交预留。指导预测写入账本，提交幂等哈希只在预测实际存在时包含预测字段，以免旧请求回放改变哈希。实验提交冻结预测，收割提交继承来源文本。审阅帧只从截止序号内已确认的评分事件构造预测与分数配对，分项缺失保留 null，变化相对本 Run 上一次已确认提交；判定只接受本 Run 已确认的预测并追加事件，评分修订或失去确认后使当前判定失效。运行整理素材包含这些配对。迁移前已在本机忽略目录备份 SQLite；本包用 fake 评分/代理验收，未进行真实提交或模型调用。
- W6 后续验收修正（2026-09-27）：上条所述“手动提交 API 的既有授权和行为不变”对新 Run 不再成立。设计 P3 要求每次实验提交都带预测；原实现只约束大脑 submit 指导，手动入口可绕过。现在 `mailboxes.submit_experiment` 根据冻结的 Run 版本标记在读取包和预留配额前拒绝空预测，API 透传预测，前端显示必填输入。旧 Run 仍允许不带预测，原授权、幂等与收割语义保持。此修正经临时数据库、fake 平台和前端测试验证；未进行真实提交。
- W7：大脑专用 MCP `platform_scores` 只经后端匿名 GET 读取本题公开 `/challenges/{slug}/attempts`，不携带账号令牌；执行器能力令牌在后端返回 403。分页遵循本机保存的官方 API 文档 `page`/`limit`/`sort` 参数和历史公开样本的 `attempts`/`total` 结构；逐页直到收齐 total，重复页、total 变化、缺字段和页数超限一律返回 unknown，不把部分样本冒充完整分布。只缓存匿名聚合 10 分钟，本机已确认最佳成绩每次重新读取；作者 ID 与尝试正文不出模块。分档只用 `scoringState.displayScore`，缺失/非有限数不填零；分位数基于实际存在的分项，未知保持 null。该工具仅供分诊参考，不形成优化目标。本包未新增真实公开 GET；外部接口分页在当前平台仍待实际运行复核。

## CS-UP-03

- W3–W5 评分契约复核（2026-09-27 10:15 UTC）：对主选 abc 和任务卡指定备选 MCM 分别只读查询当前题目详情、公开尝试首页，并查询 `/api/protocol`。两题的 `roundEndAt` 均为 2026-08-29 12:30 UTC，当前 `scoring.strategy=arm_v1_1_generic`、`grader_name=null`，题目说明明确没有专属 grader。两题可见的 `late_scored` 尝试均只有 `executability`、`output_coverage`、`packaging`、`result_fidelity`、`trace_quality` 五项 scorecard，缺少任务卡要求拟合的 `harbor_score` 和 `trace_score`。当前协议又明确 `trace_quality` 的轨迹提取后分档为 0/0.5/1，而非历史 0–100 的轨迹评分器；不能把它乘以 100 后冒充旧 `trace_score`。因此不新建备选 MCM Run 或付费 Job 去重复同一评分契约，也不将公开历史双分项提交混入本轮晚交基线拟合。原目标 W3 的双分项基线、W4 的 ≥70/≥80 对照及 W5 留出吻合仍未达成，等待能产生同一目标分项的当前评分轮次/契约，或用户另行明确变更研究目标。脱敏协议摘要和哈希留在本机忽略目录 `.package-checks/cs-up-03-score-contract-20260927T101535Z/`。
- W3 H5–H7（2026-09-27）：后续真实创建回执逐次揭示两个此前未写入公开 Agent API 文档的表单限制：行内 `timestamp` 至多 30 字符，`title` 至多 300 字符。只在发送表单时把带时区的长 ISO 时间戳等价转为 UTC `Z`，把过长标题截至 300 字符并将全文移入 `body`；封存 ARM 包和事实引用不改。H5、H6 的 HTTP 400 均明确声称 `nothing was stored`，因此适配器仅对创建接口带这一精确声明的回执判定无远端副作用并释放预留；旧 H5 记录以同一窄条件单次受控对账。原 H3 创建的错误正文缺失，继续 unknown 且占额度。H7 用新独立意图真实创建 Attempt `46889`，bundle `ready` 且 submit 成功，说明此处表单投影已越过创建与上传门禁；平台 `scoreIsFinal=true` 的展示分 41.43 经约 10 分钟后同值第二次观察被本地确认为 confirmed，仍无独立 harbor/trace 分项，也不据此推断比赛有效性。Run 的两次提交授权仍受原未知创建占用，不以服务端拒绝作为静默扩大授权的理由。
- W3 H4（2026-09-27）：用户要求不再等待后，现有 Run 经原生 `control/steer` 立即审阅并完成只读诊断 Trial，随后由大脑暂停。历史创建路径在内存中用原冻结包和当时的适配器重建为 7 个文本字段、0 个文件字段；20 条行内 trace 都只有 ARM `step_type` 而缺官方创建表单必需的 `type`。这证明一处可复现的契约违规，但原始 HTTP 400 正文和实际 wire 请求未留存，不能证明它是唯一根因。ARM 包内 trace-step 校验通过；另有 10 项 manifest/characterization 的官方 JSON Schema 错误只会影响后续 bundle 阶段。执行器仅在本机 Trial 目录修正两份元数据，科学输出与脚本逐成员不变，修正包离线 schema 通过；没有再次提交。认证的 `GET /attempts?author=<own-id>` 与匿名列表返回相同的两条非草稿，故私有 draft 仍无法排除，原 Submission 继续保留 `unknown/create_sent` 和预留。下一步需要平台提供该账号在原时间窗口的私有草稿及创建错误权威对账；在此之前不以新幂等键重发原意图，额外 CPU Job 对该阻塞无诊断价值。
- W4 预备：真实 abc 基线创建仍为 `unknown/create_sent`，因此先冻结对照设计而不启动变体提交。原轨迹变体以调用时最新事件序号重新投影，会把来源提交之后的 Run 事件混入对照；现从来源封存轨迹中的持久事件引用求截止序号，普通叙述与纯投影变体都用同一截止。纯投影变体先移除来源的表达层轨迹文件，再由已记录事件生成轨迹；无持久事件引用的历史包保守拒绝生成变体。此选择只控制比较条件，不把科学产物哈希一致等同于平台科学分一致；平台效应仍待真实分数验证。
- W0：执行器回合进行中时，原生 usage、reasoning 和消息片段只作为活性证据，不计为科研进展，也不进入大脑审阅帧。私有思考正文不落公开事件；高频片段仅以最多每 10 秒一条的无正文标记持久化，事件泵另记最近到达时间，避免“已到达但尚在队列”的消息触发误重启。原生流看门狗的 240 秒提示先保留忙态与 Trial 状态，由可配置 `stall_seconds` 判定是否重启执行器会话；重启不盲目重放原提示词或远端 Job。大脑 `wait` 可显式给 `duration_seconds`，超过 `max_brain_wait_seconds` 被拒；未给时采用 `stall_seconds`，期限到了恢复普通活性检查。没有活跃 Trial 的空闲 Run 仍按原规则检测。本包只用 fake 会话验证，没有触发真实模型。
- W1：轨迹叙述仅覆盖表达层。校验在封存前执行，事实字段只接受当前 Run 截止序号内的持久事件和包内文件；无效行逐条报告，投影中未覆盖的步骤仍保留。变体只从已确认实验提交的冻结包生成，在既有邮箱额度与本地准入门禁内提交；非轨迹、非 manifest 成员逐文件哈希相同才放行，原始回执和生成包留本机忽略目录。预检工具只读，且只读当前 Run/Trial 的包。科学产物等价限于包内字节，不推断平台评分不变。本包用 fake 平台验证，没有真实模型、Job 或 Attempt。
- W2：评分器是题目目录内的文件与声明镜像，不是后端硬编码题解；版本来自全部文件哈希。科学评分只经已有 Run 沙箱网关执行；控制器传给评分脚本的科学输入 ZIP 不含轨迹，manifest trace 指针也被移除，宿主机只读包、计算哈希和轨迹文本特征。初始轨迹模型固定输出低置信度占位预测，不将其视为达到 70 分的已验证保证；真实权重须等 W4 的受控数据。评分沙箱动作会增加事件，使提交时封存 SHA 改变，因此提交前只在非轨迹字节和评分相关 manifest 相同的条件下，将科学评分结果派生到最终封存包哈希，再按精确包哈希与 confirmed 平台分配对。实验预测引用原本地分数 ID 时可追踪这一派生关系。分项与展示分不一致分别入账，不倒推“正确”的平台分项；真实校准效果仍待 W3–W5 验证。
- W3 运行中发现 abc 题面明确声明 `Nothing is provided as input: the problem statement above is the whole input.`，但平台同时登记一个 `task-public-data` 资源。原先仅凭资源角色就把未下载的 Job 证据标为 `proxy`，使默认实验提交预检返回 `PROXY_EVIDENCE`；本 Run 无数据下载授权，因而大脑暂停。此处只对包含该完整无输入声明的题面，将登记资源视为非必需输入；其他题仍按原代理证据门禁。修复后同一原包默认预检得到 `admitted`、`evidence_class=not_applicable`、`error_code=null`，未使用代理放行参数或下载资源。经后端重启恢复同一 Run，大脑保留恢复审阅；执行器随后用当前 API 复验并在检查点纠正旧阻塞结论。平台是否接受提交及最终评分仍以真实回执为准。
- W3 主选题真实提交创建返回 HTTP 400；本地 Submission 保留 `unknown/create_sent`、无 Attempt ID、预留不释放。同账号认证只读查询可见的 171 条非草稿 Attempt 未发现匹配项，但接口未提供无 ID 的私有草稿对账，不能由此判定远端绝无副作用。适配器原本读取 HTTP 错误正文后丢弃，导致这次 400 原因不可恢复；现改为在后续错误中保留最多 300 字符的脱敏正文，且不把 HTTP 400 自动判为无副作用。任务卡的备选 MCM 题虽公开状态为 `open`，但也已过相同公布截止时间，且科学输入依赖登记的公开数据；本轮未获新增数据下载授权，不能仅凭题面“任务环境已包含数据”推断 Bohrium Job 镜像已有数据。因此不以新 Attempt/Job 试探平台，W4–W5 的真实评分对照等待可确认的实验基线。
- W3 后续只读协议核对：平台当前 Agent API 的创建表单要求行内轨迹步骤的 `type`，而本地曾把封存 ARM 轨迹中的 `step_type` 原样送入创建表单；历史成功提交只使用单条短的回退 observation，不能证明这次 20 步、约 19.9 KB 的行内轨迹符合当前契约。适配器现只把封存包的真实步骤投影为文档列出的行内字段，`tool_result.tool_output` 原文可进入 `body`，包内完整轨迹及事实引用不改。原请求 HTTP 400 的正文已丢失，字段差异或体积是否为根因仍未判定；在原 Attempt 状态 unknown 时不以新 POST 验证。
- W3 额外只读排查：失败实验邮箱与两个曾成功创建 Attempt 的实验邮箱均能通过 `/auth/me`，同为已确认的 agent 账号，不能把基本认证状态差异当成 400 根因。既往成功的另一题在提交时也已过公布轮次截止，故截止时间本身不足以解释本次拒绝。通用 `/attempts?status=draft` 实际仍返回 scored 列表，过滤参数不生效；账号 `/agent/work` 返回推荐题目而非私有草稿。因此这些 GET 不能证明本次创建无远端副作用，unknown 预留继续保留。
- W2 科学评分器真实验收（2026-09-27）：题面 abc 评分器作为项目源码置于 `challenges/local_a619cdef/scorer/`，结果与题面分档保持独立于平台晚交通用 ARM 展示分。首次 Run `run_06316b6fa6` 因 `cpu=2` 收到明确的 `INVALID_ARGUMENTS`，旧网关却记为 unknown；只读 request-ID 查询返回 `RESOURCE_NOT_FOUND` 后才将该历史预留释放。随后 `run_c118eaee44` 仅在本地路径门禁失败，未发远端创建；`run_312f38ada6` 发现 Codex 会话白名单漏列已有产品 MCP 工具，修复后创建真实沙箱，却又遇到桥对长调用 10 秒重试导致操作冲突，以及评分执行中删除沙箱的竞态，最终无分并确认回收。修复策略分别是本地 CPU 语法检查、只对权威拒绝/查无请求释放预留、显式列出执行器已有业务工具、长时变更操作单次等待、执行/传输期间拒绝删除。没有以新 operation ID 重发未知远端请求。
- 同一题 `run_ed3e28c12a` 在修复后通过产品预检，使用声明镜像和 `2c4g` CPU 沙箱得到本地科学分 20，版本 `83c33775ee2e8b33c8241e117492e6aa03d31e583268986e22fae25523f3a071`，并在删除请求后经只读对账确认远端回收。该分数只证明项目评分器对已验证纪录三元组的题面分档运行成功；H7 的平台展示分 41.43 属当前通用 ARM 评分且最终封存包不同，不拿来拟合或声称一致。W3 双分项重复基线和 W4/W5 仍受当前平台评分契约阻断。真实沙箱金额未见回执，保持 unknown。
- 本次 Run 收尾时，大脑数次提供了真实存在的 `event:run_ed3e28c12a:189` 与 `checkpoint:...`，控制器却只接受裸 event ID 或 `run_id#seq`，把 `finish(achieved)` 错拒为缺少证据。现在按产品自身产生的两类引用验证当前 Run 所有权，并保留旧式 event 引用；跨 Run 或不存在的引用仍拒。定向回归覆盖有效事件加检查点和跨 Run 伪引用。修复后通过原生 recovery/steer 恢复同一 Run，最终 `finished/achieved`；原生 curation 审阅为 done，题内经验保存了成功链路及此前失败边界。该收尾修复不产生新科研、Job、沙箱或 Attempt。

## CS-UP-03R

- AgentMaster 本地补证（2026-09-28）：先前 75 条旧轨迹分在平台 API 和 CyberScientist 工作区中没有可下载的对应内容，但这并非全机结论。只读检查独立的 `../AgentMaster/store/T0`，148 个有 Attempt ID 的本地提交记录与评分表相交 71 条；71 条均核对提交状态、题目 ID 和 CLI `--trace` 指向的上传副本，58 条有最终轨迹分。原始 Codex 事件、上传副本、本地投影分别保留哈希，不把投影视为已证明的平台评分输入。2 条本地 grader 轨迹分与后取得的平台评分快照不符、4 条缺本地分；以平台快照为当前分数事实，保留差异。原本“0 条可配对”只适用于平台/API 与 CyberScientist 来源，已在文档标注校正。逐条匹配表与原始文件只留本机忽略目录；系统原生接口修订既有全局经验候选，仍待用户审批；没有运行模型、Job、Attempt 或平台写操作。
- AgentMaster 评分规律复查（2026-09-28）：71 条提交的 CLI `--outputs` 与封存科学输出逐文件一致，但 58 条最终提交的输出树没有完全重复，不能测同包噪声。轨迹事件数、失败命令数的单特征阈值在按整题留出时，普通准确率低于训练折多数类；MP-R 单字段答案差异与科学分差相伴，但辅助推导也变化。决定只提交只读审计代码和脱敏报告，不晋升为生产轨迹预测器、逐题科学评分器或经验规则。平台最终归一化轨迹及逐项科学验算缺失时，保持机制 unknown。详见 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`。
- AgentMaster 未遮蔽回执补证（2026-09-28）：另外 63 份已评分历史回执直接记录 `trace_decision` 与 `trace_factor`，其中 1 份在独立 `harvest/` 目录。确认该引擎版本在这些提交上按 `accept→1`、`review→trace_score/100`、`block→0` 合成展示分；此前 58 条最终旧回执的分数也与相应暂定分段吻合。因旧组判定类别被遮蔽、两组边界附近无样本且当前评分版本未核对，只将该公式记录为历史实测行为，不替换运行时预测契约或声称已复刻轨迹打分内核。诊断代码的 `score_effect` 不是完整分数公式；同字节 FigQA 输出有 0/100 科学分差，故不从输出文件单独拟合确定性科学评分器。新回执与逐 Attempt 证据仅本机忽略保存，公开文档只放汇总。
- AgentMaster 轨迹输入哈希校正（2026-09-28）：在 63 份未遮蔽回执中，不能只因命令路径存在便声称当前文件就是评分输入。60 条路径仍存在，只有 57 条文件 SHA-256 与提交回执的 `native_trace_sha256` 相同；3 条不符，另 3 条原路径已消失。回执哈希在封存 `raw.jsonl`/`raw.upload.jsonl` 索引中找回这 6 条的原生字节：3 条同迭代、3 条其他迭代，来源类别保留。旧组 71/71 也与各自回执原生轨迹哈希相同。回执哈希确认 3 组跨题复用，与 3 条 `N01` 诊断相符。只从按回执哈希确认的本地文件抽取结构特征；仍不把原生输入等同于平台内部最终评分投影。`harvest/` 的科学输出缺封存快照，只计入轨迹和因子规则，不计入逐文件封存输出比较。
- 全账号轨迹扩查（2026-09-28）：用户将范围扩大到所有能取回的代理、实验与收割邮箱轨迹。用当前操作者 `/auth/me`、`GET /agent/register` 核验 15 个关联代理，再与数据库 1 个实验、0 个收割邮箱交叉去重；只读取归属已核实的 89 条可见 Attempt。`GET /attempts?author=...&limit=1000` 没有 total，page/offset 实测不分页，因此不声称含私有草稿。17 条列表称有轨迹，实际可读 8 条、165 个 API 步骤；9 条操作者 `/trace` 为空、`/export-arm` 为 403，其详情没有替代正文或日志。直接实验邮箱凭据可取回操作者视图为空的 3 条轨迹及 bundle；两种视图并存保存，不覆盖负证据。5 份 bundle 只有 4 个不同 SHA，包内选中轨迹可与 API 轨迹严重不一致，其中一份目录扫描得到 3303 条事件/里程碑记录而 0 条有轨迹类型加标题。75 条有旧 0–100 `trace_score` 的提交都没有可取回轨迹；8 条可读轨迹都没有该标签。只做来源分离和描述性结构分析，不以通用 `trace_quality` 训练旧阈值预测器，也不把重复包的非最终评分当噪声。原始材料和逐文件哈希仅在 `.package-checks/trace-all-20260928/`；可重建脚本、结果边界见 `docs/OWNED_TRACE_ANALYSIS_2026-09-28.md`。
- 用户校正与轨迹自查（2026-09-28）：30–70 轨迹因子公式是主办方告知、由用户转述的外部规则，不应称为从历史分数推断的候选门槛。10 条低分段历史展示分与该规则冲突；按 `harbor_score × trace_score/100` 计算虽在样本内吻合，也不是经平台确认的替代规则。当前官方 Agent API 的 `GET /attempts/{id}/trace` 可用于查看有记录的本人轨迹：项目实验邮箱的 3 条既有提交曾取回 10、6、131 步，本轮直接认证复查其中一条仍返回 10 步。操作者身份经 `/auth/me` 和登记关系核验后，对 3 个历史代理的全部 72 条提交逐条只读查详情，均 HTTP 200、`traceCount=0`，无 bundle、raw messages 或其他内容；每个代理各取一条作匿名与操作者 `/trace` 对照，均为空数组，操作者 `/bundle`、`/export-arm` 均 HTTP 403。不能把操作者身份等同于代理本人的 token，也不能由 API 不可见推断平台后台从未保存。当前已授权且可用的读取路径不能恢复这批旧轨迹；原始响应及哈希留本机忽略目录 `.package-checks/trace-self-20260928/`，无平台写请求。
- 后续本机只读复核（2026-09-27）：历史代理的 72 条公开详情均返回 `traceCount=0`，评分说明被标为 redacted；本机 `submissions.platform_ref` 与这些 Attempt ID 的交集为 0。在当前忽略目录可搜索的文本中只找到公开榜单和集成文档提及这些代理，未找到能按 Attempt 归属核验的旧原始包。71 条实时记录的 `harbor_reward` 与 `harbor_score` 则全部精确满足百分制换算（最大误差 0），可确认的只是输出换算层，不是产物到奖励值的题目评分逻辑。继续保留科学评分器与轨迹预测器的不可验证结论。
- W3–W5（2026-09-27）：58 条完整展示分里，任务卡公式只解释 48 条；另 10 条吻合 `harbor_score × trace_score / 100`。随后按原设计预先存在的轨迹 70 分界核对分段候选：低于 70 时取乘法公式，其余取任务卡公式，58 条均在 0.001 内，最大误差 0.000048。可区分的低分样本最高为 69，高分样本最低为 75.925；这段空白不能识别精确切换门槛。只将候选写入只读分析，不替换运行时预测公式或声称独立验证。所有 71 条实时双分项仍缺原始科学包和轨迹；不以总分猜隐藏的内容评分规则，不运行无输入的沙箱、不生成未经验证的新内容预测器。实时组同包重复数为 0，噪声及阈值准确率保持 unknown。
- `score_calibration` 仅接纳同封存 SHA 的本地评分与 confirmed 平台分；现有历史资料符合者为 0。先做 SQLite 忽略目录备份，再只加 `source` 列并重复初始化核对幂等，旧行默认 `realtime`，未来有精确配对才写 `historical`。本轮真实导入 0 行；前端显式展示来源。两个项目 skill 与原生全局经验候选只记录可执行的配对门槛及适用边界，候选等待用户审批。
- W2（2026-09-27）：分类同时看提交创建时刻和回执字段，不用题目**当前**通用 ARM 策略覆盖历史结论。75 条本人记录中，71 条是轮次内双分项、1 条带历史双分项但创建于轮次外，2 条是晚交通用 ARM，1 条待复核；轮次外异常单列，避免混入训练组。71 条分布于 7 题，但没有任何一条可取回原始 bundle；3 条有 bundle 的记录都不属于实时双分项组。缺原始内容时保持特征为空，不用公开他人的内容或自动生成的 starter manifest 代替。
- 同 10 道题的匿名公开背景分页共 43 页、3809 条，逐页只保留状态与三个分数字段，独立于本人表；其中 3406 条有轨迹分。这些背景数据仅用于描述分布，不用于拟合内容到分数的关系。原始分页和两张数据表均放在本机忽略目录，仓库只提交重建代码、fake 测试与汇总结论。
- W1（2026-09-27）：项目数据库只有 1 个实验邮箱、没有收割邮箱；该邮箱原有密钥通过 `/auth/me` 核验。操作者现有凭据的只读 `GET /agent/register` 确认另外 3 个任务指定代理均为其已确认关联账号，但项目密钥库与允许搜索的本机历史审计目录未找到这 3 个代理各自的完整 token。因此按任务卡收窄为只采集它们的公开评分和元数据，内容标为 unavailable；不借操作者身份推断可以读取代理私有内容，也不重新生成 token。
- 作者过滤的 `GET /attempts?author=...&limit=1000` 分别返回 3、15、20、37 条且逐条 `authorId` 匹配，但响应没有 `total` 或页码；不能宣称全历史绝对完整。对已发现的 10 道题另用官方 `/challenges/{id}/attempts?page=...&limit=100` 走完分页（每题公开 `total`），逐条精确作者 ID 交叉核对，0 请求错误、0 已知题目内计数差异。此法不能发现作者过滤列表完全遗漏的另一道题，数据集保留此覆盖限制。
- 官方文档确认本人 bundle 的 `GET /attempts/{id}/bundle`、轨迹的 `GET /attempts/{id}/trace` 以及自动导出 `GET /attempts/{id}/export-arm`。有直接凭据的 3 条 Attempt 均成功取回 bundle；三个历史账号的 72 条列表记录均标记无 bundle、原始消息或脚本。各抽取一条的公开轨迹 GET 返回空列表，bundle/export GET 返回 403；用已确认的操作者凭据重试一条仍为 403。不能把自动导出的 starter manifest 冒充原始科学文件，也不猜测 raw-message 路径。原始回执、身份、包及逐文件 SHA-256 仅在忽略目录 `.package-checks/scorer-re-20260927T132218Z/`；平台资源没有创建或修改。

## 2026-09-28：CS-UP-03R 公开评分源码与证据转换逆向

- 从已安装官方 CLI 的包元数据找到作者公开仓库，固定 `trace-score-cli@81c434907e7b0a2feccc79236f6601f7abbc1d84`。源码引擎为 v6，63 份历史回执为 v8；因此只把公开 reducer、上限、解析和摘要行为标为已验证，不把它接入生产作为已验证的 v8 预测器。完整发现见 `docs/TRACE_SCORER_SOURCE_REVERSE_ENGINEERING_2026-09-28.md`。
- 对本人三份按接收回执 SHA-256 配对的 FigQA 原生轨迹，只执行离线格式转换和检查。当前 Playground CLI `0.1.33` 中顶层 error 会先匹配 OpenCode，令 Codex E008 的 43 事件只剩 1 条 error；最小合成对照也复现。E010 的转换文件在公开 scorer 上触发 N09 / cap 49，E011 无负项。未取得服务端当时最终归一化文件，不把本次复现冒充历史 worker 的完整重放。
- 增加固定源码哈希的离线审计工具，使用原函数和合成裁判数值检验行为；禁用本进程网络、不调用真实评分模型。公共克隆和含原始证据的结果留 `.package-checks/`。本轮不改用户全局 CLI、不创建平台资源、不把未经验证的提示词技巧或评分预测写进生产。

## 2026-09-28：CS-UP-03R 本地科学评分器真实回放

- 完成 FigQA-0177 的规范答案评分器：标准语义答案来自公开 LAB-Bench，固定选项 B 来自封存题面；评分函数不读取历史标签或轨迹。B/C 两种字节内容的 11 条有效历史回放均一致，误差为 0。F000 因生成包与平台接收包 SHA 不一致而排除，保留原始证据；不把错包异常拟合成答案评分例外。
- 未见平台样本覆盖的非规范解析输入返回 unverified，不编造 0 分。公共 benchmark 相等比较不能证明 Bohrium 隐藏解析器全部细节；规范科学评分、封包对应、轨迹准入和展示分分别报告。
- 使用隔离的分析上下文复用生产沙箱网关，显式模型/Job/Attempt 额度为 0，支持收窄分钟上限。原始回执与科学文件全部留忽略目录；新的答案专用 ZIP 不冒充原始 ARM bundle，不伪写精确原包校准记录。
- Paired-block Lean 先行实现和应用测试保留为低置信度实验代码。实际准备遭遇网络故障，虽然已验证 Lean 版本、锁定源码并观察到缓存下载推进，但监督衔接未能在沙箱到期前取得候选评分。其误差和科学反例测试状态仍为 unknown，不与 FigQA 成功合并。失败详情、时长保守上界和后续条件见 `docs/LOCAL_SCORER_REPLAY_2026-09-28.md`。
- FigQA 改为全部输入备齐后一次执行“创建→上传→评分→取回→finally 删除”，再只读对账回收状态。它在后续独立的 15 分钟授权上下文内完成，和前次时长保守上界合计仍低于原 180 分钟预算，两个沙箱不同时存在。


## 2026-09-28：CS-UP-03R Lean 真实验算与验证范围

- 使用固定原始题面、Lean 4.32.2 与锁定依赖复验 4 份历史证明，全部匹配科学 0/100；另对有效证明构造 8 种可追溯反例，实际验证公理来源、确切定理类型、90 分匹配准入和部分分。反例没有平台回执，分别报告，不混入历史一致率。
- 环境准备先按真实 import 下载缓存，主批评分无需等待整个 Mathlib；E000 保留原始全量导入，不通过改写输入假装完成回放。其缓存超时及最后补验上传失败单列为未验证；主批完整证据已取回。详情见 `docs/PAIRED_BLOCK_SCORER_REPLAY_2026-09-28.md`。
- 评分函数数值逻辑保持冻结；确认 4/4 与 8/8 后只更新发布版本的 confidence/notes。报告分别记录实际回放的旧内容哈希与最终元数据更新后的哈希，不将后一版本称作新远端验收通过。
- 间歇 TLS 超时使删除状态曾为 unknown；仅在新的认证 describe 明确返回 running 后据实恢复隔离账本，后续经原生删除对账确认回收。没有放宽授权、重发未知创建或改全局网络配置。两个新增 CPU 沙箱不重叠；累计保守时间上界约 157.063 分钟，原授权为 180 分钟，费用未知。

## 2026-09-28：CS-UP-03R 第四季公开科学评分规则核查

- 按用户要求只读核对官网，确认第四季 60 道、6 轮，选读 16 道不同任务；没有新科研或评分运行。公开响应与哈希留本机忽略目录，交付结论见 `docs/SEASON4_PUBLIC_SCORER_FEASIBILITY_2026-09-28.md`。
- 可复刻性分别核对科学检验、数值计分和评测输入/运行条件。Matchgate 公开端点、重放与完整连续公式，因此列为首选新增候选；DPA4C 的确定性计分公式与机器相关计时分开。声明公开附件不冒充已审读源码。
- USCT 隐藏观测/真值/清零阈值缺失时不能给官方精确预测；CNVkit 能按固定流程重建科学参照也不等于知道所有容差与封顶。当前通用 ARM 字段不覆盖官网明示的整季外部 worker 情形，不用于否定历史专属评分。
- 原始字段复核确认 15 题当前为通用 ARM，DPA4C 为 LLM 且带 ARM fallback；保留 DPA4C 正文确定性公式与 API 策略不一致的观察，不保证当前新提交的实际路由和分数。
- 本轮只写文档，既有评分器及经验不改；不把 Paired-block 的既有历史回放写成这次新验收，不启动沙箱消耗旧额度。


## 2026-09-28：skills 保存与设置页故障修复

用户报告“勾选后无法保存或刷新丢失”。本轮先检查实际 HEAD（`16157b3`）与工作区，保留原有未跟踪任务卡和经验；使用 diagnosing-bugs 与 kimi-webbridge 在独立 Demo 数据目录复现。用户真实连接配置、研究数据及全局 CLI 配置未改动。

| 观察或回归 | 原因 | 本次修复 |
|---|---|---|
| 浏览器勾选 Bohrium Job 后点击“保存设置”，提示成功但后端 `skills.always_on=[]` | SkillsCard 保存自己的 checked；主页面提交的 Settings 没有同步这份选择 | 选择提升到整页 Settings 草稿，主按钮与卡片按钮共用同一次带 base_revision 的设置保存 |
| 先保存技能，再保存其他草稿字段不能落盘（新增前端回归在旧代码失败） | 独立技能接口增加 revision，主页面仍持有旧版本；两份状态相互脱节 | 卡片按钮明确改为“保存设置与技能”；使用保存响应推进整页 revision，不用无版本保护的独立技能写入 |
| 保存等待期间仍可编辑，随后响应覆盖新改动；加载失败一直显示加载中 | 无编辑互斥；加载错误只短暂 toast | 保存期间禁用字段；设置与目录的失败状态提供重试；保存冲突保留草稿，只在用户明确选择放弃时重载 |
| 人工构造非 UTF-8 SKILL.md 后整个 scan_catalog 抛 UnicodeDecodeError | 只处理 OSError，遗漏文本解码异常 | 单文件解码错误走既有元数据回退，保留目录名，其余技能继续可列出 |
| 文案称常驻对所有 Trial 立即生效、大脑也自动得到技能 | 实际常驻列表固定于 Run 创建快照；独立大脑刻意不注入执行技能 | 文案对齐现有架构，不改变大脑、执行器及授权语义 |

前端新增 7 条回归先在旧代码全部失败，修复后全部通过；完整前端 25 passed。首次构建发现新增测试使用了 Testing Library 不支持的 `exact` 选项，移除后 TypeScript/Vite 构建通过。后端完整回归 563 passed、1 skipped；被沙箱跳过的本机回环关闭测试在允许监听后另行通过。compileall 和 diff --check 通过。未添加真实模型或远程平台探针。

WebBridge 对新构建的真实页面验证了勾选/取消、主保存、卡片保存、连续保存与整页刷新。随后从前端导入合成题、额外绑定 Bohrium File，以零模型、零 Job、零提交、零沙箱、禁下载授权启动原生 Demo，运行到 finished；执行器技能事件同时包含默认技能、常驻 Bohrium Job 和题目绑定 Bohrium File，独立大脑记录不注入技能。本轮仅证明本地配置与投递闭环，不代表真实代理已读取并调用每个技能。

本机证据位于 `.package-checks/ui-bug-audit-20260928/`，不提交。一个后台标签页曾加载停滞并发生 WebBridge 命令超时；直连后端设置约 7 ms 返回 200，刷新后未再复现，保留为原因未判定，未把刷新恢复冒充代码修复。代码审查范围为设置草稿/版本、错误恢复、技能目录、投递语义和新增回归；没有修改科学评分、研究策略、原生运行时或付费操作边界。

## 2026-09-28：第二轮界面与运行生命周期故障修复

基线 `961c033`，保留原有未跟踪任务卡和经验。本轮按误操作、授权、证据错配和使用阻塞的影响排序；严重度描述潜在影响，不表示真实付费提交已经发生。通过 diagnosing-bugs 建立失败回归，再在隔离原生 Demo 中用 kimi-webbridge 验证实际页面。

| 优先级 | 已复现问题与原因 | 修复与证据 |
|---|---|---|
| 高 | 提交页取 `runs.items[0]`，研究页选择题目 B 后仍可能向最新题目 A 的 Run 提交；刷新还分段更新 Run/Trial | 优先采用当前题目，提供明确 Run 选择；数据全部到齐再启用提交，拒绝迟到响应；切换清空包路径、预测、候选确认和额外许可。旧代码的回归实际把请求发往 A；修复后测试和浏览器选中 B |
| 高 | 研究页题目详情、Run 详情和检查点请求没有选择身份/时序校验，旧响应覆盖新题目证据 | 校验选择 ID 和请求代次；派生详情必须匹配当前 ID；切换清除检查点，按题目/Run/Trial 重建相应表单；指导草稿按 Run 隔离。延迟响应回归在旧代码失败，修复后通过 |
| 高 | 创建成功、授权失败后再次启动会重新创建 Run；刷新后的 created Run 又被“已在进行中”挡住 | 保留创建 ID，重试先读取其阶段；created 可继续授权，running 只恢复展示，其他阶段不自动重授权。创建响应未知时停止盲目重试并要求先核对。回归覆盖重试、刷新、未知响应；浏览器启动已有 Demo 后 Run 数未增加 |
| 高 | 启动窗口加载默认预算期间可编辑/启动，迟到响应覆盖用户输入 | 默认预算加载完成前禁用授权编辑和启动；关闭/重新打开取消旧加载结果，失败时明确提示手动填写。新增回归先失败后通过 |
| 中 | 任意时间相近的 guidance queued/sent/ack 都可能把用户指导显示为已消费 | 将 operation_id 从控制请求带到生命周期审阅，在同一事务写 `user.steer.review_queued` 和真实 review_id。页面只匹配该操作，文案仅确认进入大脑审阅队列，不宣称执行器接收；同时处理 SSE 先于 HTTP 响应到达。数据库和界面回归通过 |
| 中 | 从其他页面返回研究页时本地选择重新初始化为 null，静默跳到最新题目 | 从应用当前题目初始化；浏览器发现并复现后增加失败回归，修复后页面往返保留 B |
| 中 | 终态 SSE 无限心跳，前端不能归档；隔离 Demo 服务缺少有界退出配置 | 先排空所有事件页，再对 finished/failed/cancelled 返回 EOF；paused 保持可续接。Demo 服务采用 5 秒优雅退出上限。测试覆盖 205 条跨页历史、暂停/恢复及两个服务入口带活跃 SSE 的 SIGTERM |

有界审查检查了异步身份、创建结果未知时的处理、已有 Run 授权、按操作关联回执、终态事件排空和原有授权边界。没有改写代理内核、研究策略、评分器或全局 CLI 设置；新指导事件只表示真实审阅请求已入队，不新增主动核查或强制大脑行为。

实际执行结果：

- `.venv/bin/pytest -q`：568 passed、2 skipped；沙箱跳过的是回环监听退出测试，允许本机监听后 `.venv/bin/pytest -q tests/test_cli_shutdown.py`：2 passed。
- `PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run`：38 passed；`npm --prefix apps/web run build` 的 TypeScript/Vite 构建通过。一次测试 fixture 重复 event_id 引起的 React key 警告已改为独立事件 ID，最终回归无该警告。
- `.venv/bin/python -m compileall -q src tests checks/serve_ui_demo.py` 和 `git diff --check`：通过。
- `checks/serve_ui_demo.py --port 18766 --data-root .package-checks/bug-audit-20260928-round2/workspace` 启动独立无凭据 Demo。合成题目通过原生 API 导入；WebBridge 验证选题/选 Run/清空旧提交许可/页面往返，并从页面对已有 Demo Run 给予零模型、零 Job、零提交、零沙箱、禁下载授权后启动。Run 到 finished、总数保持 2；32 条 SSE 事件与数据库数量一致，读取到 EOF，页面显示归档。三个远程操作账本均为 0。

浏览器验收最初用固定 1 秒等待归档，早于异步状态更新而失败；后续只读核实已归档，脚本改为有界条件等待。账本辅助检查曾误写不存在的 `sandboxes` 表，核对 schema 后使用 `compute_sandboxes` 完成检查。这两项是验收脚本问题，不计入产品缺陷。验收后 Ctrl+C 停止 Demo，进程退出码 0；仍有一个连接在 5 秒宽限到期时被取消，Uvicorn 打印 CancelledError，未使用 SIGKILL，不能称为所有连接都自然结束。原始记录保留于 `.package-checks/bug-audit-20260928-round2/`；不上传 Demo 数据、数据库或原始回执。上一轮偶发标签页停滞根因仍未判定，本轮没有真实科研或平台调用验收。
