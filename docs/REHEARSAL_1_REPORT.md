# CS-RH-01 无人值守彩排一报告

## 摘要

- 2026-10-07 实际连接 S4 已结束的第 4、5 轮；6 个科研 Run 全部自行进入 `finished`，两赛道均 `complete`。
- 实验邮箱真实提交 6 次，6 次均稳定确认通用 ARM **0 分**；这不是比赛分，也不据此评价科研水平。
- **自动收割未打通**：窗口汇总正常，但无上限授权被收割入口错误跳过，收割回执为 0；本次不认证回退版本、不打 `lightchaser-rehearsal-1` 标签。
- R3 安全关机恢复、R4 崩溃恢复完成；后端启动分别耗时 196.038、132.029 秒，未观察到重复 Job、沙箱或提交。
- 用户在 22:54 改为“上一步完成后进行下一步”；R4–R6 按顺序提前推进，赛道时钟通过后端接口压缩。**未完成原计划 4.5/5 小时耐久验证**。
- 42 个 OpenAI/Codex 会话握手均确认 fast/priority；12 个 DeepSeek 提供方会话明确 `provider_not_supported`，不能称全部 Codex runtime 会话均启用 fast。
- 发现整段 JSON 脱敏破坏语法，导致两个自动复盘失败；一条沙箱创建结果仍 unknown。均只诊断，未做第 2、3 级修复。
- 已恢复赛末检查提前 2 小时、安全余量 15 分钟；未手动提交/收割、重发 unknown、修改既有授权或审批经验候选。

## 通过标准表

所有证据文件均位于本机忽略目录 `.package-checks/cs-rh-01-20261007/`，下文省略此前缀。事件写作 `Run#seq`。审计快照为 **2026-10-07 23:07:43（UTC+8）**；原始回执、数据库、轨迹不提交 Git。

| # | 标准 | 结论 | 证据和边界 |
| --- | --- | --- | --- |
| 1 | 无人干预跑到底 | 通过 | 六个 Run 全部 `finished`，终止事件见附带数据；`R6-A/B-track.json` 均 `complete`。只执行任务卡及用户后续时间调整，不介入科研决策。终止后的维护调用另见 R6 边界。 |
| 2 | 无超过 15 分钟未处理的真卡住 | 通过 | 压缩后的实际运行中未发现；最大相邻事件间隔 726.647 秒，发生在等分确认及 R4 停机期间。`event-silence-audit.json`、`watch-observations.jsonl`。事件活跃不能独立证明科研进展，不据此评价科学结果。 |
| 3 | 实验提交→确认出分→自动收割 | **不通过** | 六笔实验提交均 confirmed，但 `automatic_harvests=0`。A/B 汇总 `alert_d64d5a0fdfde` / `alert_6488576c835d`，主邮箱最好分均未建立；`R5-both-submission-confidence.json`、`R5-A-authorization-guard-evidence.json`。平台真实接受提交，不能使用“平台不再接受”豁免。 |
| 4 | R3 安全关机与恢复 | 通过 | `can_shutdown=true`、一致性备份、SIGTERM、同代码启动、`ops resume`、preflight、digest 均执行。`R3-result.json`、`R3-comparison.json`；Job/提交/沙箱条数不变，53 条原弹窗全部保留。 |
| 5 | R4 数据完整、自动恢复、unknown 均有结果 | **无法判定** | 已观察到六 Run 自动恢复、数据计数/高水位未回退、58 条弹窗保留；但 `trial9-clean-replay-create` 仍 unknown、无远端 ID，不能确认远端创建结果。已按不重发策略处置，未伪称已解决。`R4-comparison.json`、`R4-recovery-events.json`、`final-ledger-audit.json`。 |
| 6 | DeepSeek Run 端到端 | 通过 | CNVkit、TSA-seq 各两次真实提交及 confirmed 分数，最终自行终止。见附表和 `final-ledger-audit.json`；DeepSeek 的 fast 能力另判。 |
| 7 | 弹窗出现且重启保留 | 通过 | 后端弹窗队列实际出现 run.recovery、低分/窗口汇总等提醒；R3 53→57、R4 58→58，原 ID 无缺失。`R3/R4-alerts-before/after.json`。本轮按要求使用后端接口，未另测浏览器视觉渲染。 |
| 8 | 所有 Codex 会话 fast 生效 | **不通过（严格全会话口径）** | 快照共 54 条 session.configuration：OpenAI 42/42 为 enabled、observed_tier=priority；DeepSeek 12/12 为 provider_not_supported、enabled=false。均经 Codex runtime 接入，不能静默排除不支持的提供方后称“全部通过”。Astra xhigh、Sol high 均实际确认。`final-ledger-audit.json`、`R1-status.json`。 |
| 9 | 两赛道隔离、时钟/窗口/分组 | 通过（压缩版） | A v2、B v1，无串送；23:00 前 A active 时 B 仍 before_window，之后分别推进 B；A 已结束时 B 仍在运行。`A-prompt-v2-deliveries.json`、`R5-A-isolation-A/B.json`、`compressed-*.json`。原始 4.5/5h 时长未验证。 |
| 10 | 暂缓题启动、更新送达 PI | 通过 | 21:44:14 一键启动两题，实际 Run 于 21:44:20 创建；A v2 的“用户更新”送达 Deep BSDE#2562、CNVkit#1128、Packing#639，B 保持 v1。`deferred-start-A/B.json`、`A-prompt-v2-deliveries.json`。 |
| 11 | PI 只读文件痕迹 | 通过 | 六 Run 共 325 条 brain.file_read，含路径、SHA256、offset/bytes；例见附表。只验证痕迹，不将“读过文件”当科学复核结论。`final-ledger-audit.json`。 |
| 12 | 前后额度、10题24h估算 | 通过（粗估） | 同一 10080 分钟窗口，T0 前新鲜观测 1%，R1 12%，R3 37%，R4 49%，终止后 53%；压力情景估算见下文。共享账号增量无法归因到本轮科研。 |
| 13 | digest≤约60行、监控自身额度 | **无法判定** | 59 个轮询 digest 为 15–54 行，全量最终快照 54 行，行数部分通过。监控 goal 累计 token 计数已记录，但原生限额没有监控会话归因；仅能给出共享增量范围，不能制造单一百分比。 |

结论：**9 项通过、2 项不通过、2 项无法判定**。第 3 条不存在平台豁免条件，不满足认证标签要求。R6 的严格“结束后零新动作”也有下述明确边界。

## 时间线

以下均为 **2026-10-07，UTC+8**；原始日志使用 UTC。

| 时间 | 操作/观测 | 结果 |
| --- | --- | --- |
| 20:46:26 | 冻结代码、备份账本/设置、启动后端 | `068c3637238ae7647bb15e371642df38510beea0`，标签 lightchaser-fallback-3；20:48:36 health ready，首次启动约 129.8 秒。 |
| 20:48–20:59 | preflight、设置、导入、公开题目核验、提示词、分诊/选择/确认 | 两轮各 10 题 GET 均 open/approved；默认 ARM 1.1 transport 经协议探针及接口核对。每轮 2 立即、1 暂缓、7 跳过。 |
| 20:59:12.387 | T0 | 四题启动；原截止 A 10-08 01:29:11.822，B 01:59:11.822。 |
| 21:29:13–21:29:51 | R1 | CLI preflight exit 0，warn 仅镜像预热新鲜度未知；digest 54 行。 |
| 21:44:14 | 启动两条暂缓题 | Packing、XAS 实际约 21:44:20 开始。 |
| 21:44:57 / 21:46:17 | TSA-seq / CNVkit 首次实际提交成功 | 距 T0 45m45.5s / 47m05.4s；最初 draft 创建各早约 9–11 秒。 |
| 21:59:13–22:00:05 | A 提示词 v2；R2 reviewer off→on | off/on 各观察 25 秒，覆盖至少两个常规 controller 轮询；已有审查继续，没有新的审查启动落在关闭样本区间。 |
| 22:05 左右 | 前两笔成绩稳定确认 | TSA-seq#1224、CNVkit#1075；均通用 ARM 0 分，自动唤醒继续研究。 |
| 22:13 | Packing / XAS bundle 被平台拒收 | 保留同一 draft 和额度；监控未重发、未修包。 |
| 22:18:39 / 22:21:24 | 系统自行续提 Packing / XAS | draft_continuation_requested 为 Packing#878、XAS#1013；submitted 为 #890、#1030，未新增这些草稿的 Attempt。 |
| 22:21:00 | TSA-seq 第二次提交 | `sub_442b1b0348`。 |
| 22:29:14–22:32:52 | R3 | shutdown can_shutdown=true；原生会话收尾，备份后停止，启动对账后自动恢复；随后 ops resume 返回 ready/no-op，preflight warn、digest 54 行。 |
| 22:39:35 | CNVkit 第二次提交 | `sub_db174aa31c`；22:56:50 稳定确认。 |
| 22:54:37 | 用户变更时间要求 | 采用“上一步完成后进行下一步”，记录 `timing_override`，后续为压缩演练。 |
| 22:54:39–22:57:07 | R4 | 对精确匹配的本轮后端 PID 执行 SIGKILL，同版本启动，未手动恢复 Run；六题自动恢复。 |
| 22:57:28 / 22:58:43 | 分别推进 A / B 收割窗口 | 保留原 start；end 各调整到当时+1.5h−15s，等待 controller 后观察，各自产生窗口汇总。 |
| 22:57:58 / 22:59:14 | R5-A / R5-B | 窗口 active；自动收割为 0，定位无上限 guard。 |
| 22:59:44 / 23:01:01 | 分别推进 A / B 截止 | end 调整到当时+20s；授权未改变。 |
| 23:00:04 / 23:01:21 | A / B 真正截止 | 全部 Run 经 time_limit→finished，end_reason=authorization_expired；这里是赛道绝对截止，不是人为减少授权。 |
| 23:00:34 / 23:01:52 | R6-A / R6-B | 两赛道 complete；提交无 unknown/pending。 |
| 23:02:41 | 恢复设置 | revision 16：deadline_check_hours=2、safety_margin_minutes=15、score_threshold=100；GET 再确认。 |
| 23:03–23:07 | 终止后核验 | 六笔提交 confirmed、无自动收割；23 个 Job 最终均 Finished，21 个已取回、2 个未完整取回；23 个沙箱记录中 22 deleted、1 unknown。未主动删除远程资源。 |
| 23:06 后 | 报告交付前同步 main | `git pull --rebase` fast-forward 至 `9f5395c`，接收另一 worktree 的 S4 分析文件；彩排运行期间未 pull。 |

### R3、R4 对照

| 指标（全账本计数，含历史数据） | R3 前→后 | R4 前→后 |
| --- | --- | --- |
| events | 43025→43087 | 45139→45198 |
| submissions | 11→11 | 12→12 |
| automatic_harvests | 0→0 | 0→0 |
| compute_jobs | 90→90 | 92→92 |
| compute_sandboxes | 58→58 | 63→63 |
| runs / authorizations | 47→47 / 47→47 | 47→47 / 47→47 |
| alerts | 53→57，原 ID 无缺失 | 58→58，原 ID 无缺失 |
| 启动 / 恢复观测 | 196.038s / 209.695s（含后续核验） | 132.029s / 147.390s |

R3 每个 Run 的剩余秒数见 `R3-comparison.json`：A 约 10797→10592、B 12597→12392，差额与墙钟经过约 206 秒相符；活动计时在 paused 时 `clock_active_since=null`，恢复后只增加约 0.004–0.121 秒（暂停请求前的正常活动另计）。绝对比赛截止不因停机延后。R4 自动恢复事件分别为 Deep BSDE#3903、TSA-seq#2007、NLS#1952、Packing#1224、XAS#1405；CNVkit 等分确认后 #1571 唤醒。随后均有 sessions_recovered，原生会话 ID 对照保存在快照；未承诺恢复 IPython 内存。

### R6 边界

终止后没有观察到新建科研 Job、实验提交或自动收割。已有 Job 的成本/状态轮询、迟到的沙箱创建回执及清理仍会写事件，不能误判为新创建。

但是结束后实际启动了独立经验整理、复盘及一次格式重写模型调用，例如 CNVkit#1653/#1659、Deep BSDE#4070、Packing#1340、TSA-seq#2100、NLS#2145、XAS#1523。这是 `controller.py` 结束路径和 `maintenance.py` 的现有设计，**不满足将“没有新动作”理解为所有后台调用归零的严格 R6 要求**。六个科研 Run 的终止没有等待维护完成；审计时四个复盘仍 running、两个 failed，未把维护完成伪称已验证。经验候选均未由监控审批。

## 发现的问题

### 开赛前必须修

1. **无上限 Run 不进入自动收割（建议第 2 级）。** `src/cyberscientist/auto_harvest.py:198` 的 `max_submissions<=0` guard 忽略 unlimited_resources。六题均 unlimited=1、max_submissions=0、automatic_harvest_version=1；四题已有合格 confirmed 实验分，A/B active 窗口、auto_harvest 开启、shutdown=false，汇总 main_best 为空，账本仍 0。复现：通过 UI 同款一键无上限模板确认，在真实确认分后进入窗口，检查 harvest.deadline_check/automatic_harvests。建议统一授权语义，补充“无上限确认→稳定出分→窗口自动收割”的集成验证；不要通过临时修改授权或手动收割掩盖。本轮未修。
2. **整段 JSON 脱敏破坏语法，自动复盘失败（建议第 2 级）。** Deep BSDE#4162、Packing#1350；`run_post_reviews.error` 为 Expecting ',' delimiter，列 875324 / 948763。`maintenance.py:106` 先序列化 steps、整段 strip_secrets、再 json.loads；只读复现两份输入均为有效 JSON，脱敏后均无效，错误位置与线上一致。`postreview-redaction-json-roundtrip.json` 只保留长度/位置，不输出原文。建议在字符串字段层递归脱敏后再序列化，覆盖转义引号和长轨迹；修复后再验证整理/复盘，不能将 failed 变为成功。本轮未修。
3. **赛前经验文件与系统修订登记不一致（建议第 2 级，需保留原文件审计）。** 后端持续报告 ENVIRONMENT_READ_ONLY。三个 env 文件在开局前已存在，mtime 为 10-07 02:33 左右；文件不匹配任何已登记 system_environment 修订，而初始/当前 DB head 相同。调用链 `sandboxes.py:770`→`environment_facts.py:54`→`experiences.py:208`。`diagnostic-preexisting-environment-mismatch.json` 保存比较结果及原文件副本。建议核对写入来源、保留差异，以受控系统修订恢复一致性；不要覆盖用户文件或批准候选来绕过。本轮未修。

### 可以接受，但须说明规避与边界

- **fast 能力边界。** OpenAI 原生会话均有实际 priority 回执；DeepSeek 会话明确不支持。不能伪造 enabled。建议第 2 级完善提供方能力展示并明确验收口径；需要原生 fast 的角色使用本轮已验证的 Astra/Sol。严格全 runtime fast 标准本轮失败。
- **终止后独立维护。** 当前源码明确让整理/复盘不阻塞科研结束。建议第 2 级明确产品的“科研终止”与“后台静默”边界、维护额度/截止和可观测状态；严格 R6 零新动作尚未满足。本轮只记录，不额外授予调用或重跑复盘。
- **创建 unknown 不可猜测。** Deep BSDE 沙箱 `trial9-clean-replay-create` 从 21:30 起无远端 ID；R3/R4 均保留，未重发。远端存在性/费用仍 unknown，需有界只读对账能力。7 条旧 Job unknown 和旧提交 `sub_5f0ec08d05` 属历史状态，未算进本次 6 笔实验，也未自动重放。建议第 2 级改进可核验关联证据；本轮无修复。
- **bundle 拒收后自主恢复。** Packing#742、XAS#797 初次均 bundle_blocked：handoff.status=complete 被拒，XAS 另缺 characterization modality；平台 draft 未 submit。执行器自行经明确 draft continuation 修正，两笔都最终 submitted/confirmed，持续阻塞已消失。保留反馈，不把这两次 unknown 当最终未解决提交；后续改善打包预检属于第 2 级，本轮没有手工修包。
- **取回未就绪与终止时未取回。** 早期 retrieval_failed 多发生在 Job Running，先前 15 个 Job 均后续取回，不能据首次失败宣称永久故障。最终 23 个 Job 均 Finished；`trial3-smoke-v1` 的 retrieval_status 仍 failed、XAS `6ff-registered-public-replay-v2` 为 not_attempted（任务在截止前创建）。原始资源和结果保留，不将未取回结果记为已验证，不手动取回/取消。
- **启动较慢。** 初次约 130s、R3 196s、R4 132s，期间对账可观察且最终恢复。部署需留至少实测量级余量；无需本轮改代码或清理历史账本来加速。
- **输入前提偏离。** MONITOR_PROMPT.md 经仓库/home 及 Windows 常用目录检索未找到；本轮依任务卡和 docs/OPS_CLI.md 执行明确步骤，未编造缺失规范。tracked 源码开局干净，但除任务卡外还有既有 untracked 经验文件，严格 clean 前提不成立；全部保留。B 分诊没有 easy（9 hard、1 medium），DeepSeek 槽选择 120 分钟档 TSA-seq，保留其 hard 标签，不称已覆盖“B 简单题”。应在下一次验收准备好监控文件、干净工作区及符合难度分布的题集。
- **压缩时间限制。** A 实际截止 T0+2h00m52s，B T0+2h02m09s；窗口分别观察约 156s / 159s，足以看到汇总及 guard 跳过，但不是原计划全天/5h耐久或评分等待覆盖。原时间表的长时验证需后续另做，不据本次压缩结果外推稳定性。

## 速率数据与规模估算

| 新鲜原生观测（UTC+8） | 周窗口已用 | 来源 |
| --- | --- | --- |
| 20:57:03.742 | 1% | poll-001-digest.json 内原生观测时间，T0 前约 129 秒 |
| 20:59:29.499 | 1% | poll-002-digest.json 内原生观测时间，T0 后约 17 秒再次一致 |
| 21:29:25.090 | 12% | R1-status.json |
| 22:33:00.324 | 37% | R3-status.json |
| 22:57:20.182 | 49% | R4-status.json |
| 23:01:30.658 | 53% | final-status.json，已在两赛道截止之后 |

以上为同一原生 `windowDurationMins=10080`、`resetsAt=1791949111`。最初直接 rateLimits/read 探针超时 20 秒，开局旧缓存的 38% 来自前一天且 reset 不同，**已排除**；随后原生会话提供了 T0 前 129 秒的新鲜 1%，T0 后 17 秒仍为 1%。没有用 38%→12% 伪造额度回落，也没有把 digest 读取时间冒充额度观测时间。

约 2.07 小时内共享账号增加 52 个百分点。6 Run 合计墙钟运行 10.643 Run·小时（含等分/停机，非纯模型活动时间）。若将全部共享增量都均摊给本轮，并机械外推相同组合的 **10题×24h=240 Run·小时**，则为 `52×240/10.643≈1173` 个百分点，约 **11.7 份当前周额度**。这是压力情景，远超一份额度，说明不能凭本次高强度配置承诺 24h 可持续；不是科学系统的可归因预测，也不是线性额度定价规则。正式估算需要分离监控/其他 worktree、模型和阶段，扩大观测，并实际验证限流与调度。

监控自身：23:02:54 的 goal 统计为累计 **508994 tokens**（工具累计口径，包含上下文处理；不是原生收费 token，也不是可直接换算的额度）。监控、科研会话和另一 worktree 共用原生账号，rateLimits 没有此会话的单独消耗字段。在上述同窗观测内，监控贡献只能保守列为 **0–52 个百分点的不可归因范围**；不能给可信点估计，故标准 13 保持无法判定。59 个自动 digest 轮询 15–54 行、最大 54 行通过；监控还进行了必要的 targeted SQL/status 诊断，其成本没有被隐藏为 0。

## 值班日志摘要

详见 [REHEARSAL_1_DUTY_LOG.md](REHEARSAL_1_DUTY_LOG.md)。请求、脱敏响应摘要、耗时及证据路径逐次保存在 `duty.jsonl`；原始材料只留忽略目录。

- 后端与代理均为 Linux 原生进程，Python 使用项目 .venv；实际 codex-cli 0.159.3、Node v22.17.0、Python 3.12.12。冻结运行源码 SHA256 为 `1bb04048b4bc4b8c0117769ade8bcd54786cc001ae25456ad6d23460f4e4fa6a`，R1/R3/R4 健康及 code 快照一致。
- 接通电源、AC sleep=0；DC sleep=180 秒，电池 82%、充电状态。只读检查，未改系统设置，拔掉电源存在睡眠风险。
- 每次提醒读取后保留待确认，不批准/驳回经验、不重发未知提交。最终 74 条 pending alerts，包含历史提醒；不能把这个总数当本次新故障数。
- 监控的 settings 初次误用 expected_revision 返回 422，改用 base_revision 后成功；A 分诊客户端 60s 超时后只读确认后台 10/10 完成，未重复发起。它们是操作/超时记录，不冒充产品科研故障。
- 一度怀疑低分 provisional 为缺评分字段，源码及后续确认事件证明是正常 600s 稳定确认；该猜测已在日志中撤回，不列缺陷。
- 两赛道结束后才执行 git pull --rebase；报告仅交付两个文档。没有执行应用回归测试，也不把诊断脚本/文档 diff-check 称为应用测试通过。

## 附带数据

### 各 Run

| 赛道/题目/求解者 | Run | 通用 ARM 最好确认分 | 成功提交数 | 首次成功提交距 T0 | 终止事件 | PI 文件读取示例/次数 |
| --- | --- | --- | --- | --- | --- | --- |
| A CNVkit / DeepSeek | run_c937c8e414 | 0 | 2 | 47m05.4s | #1649，23:00:04 | #380 qc_summary.json / 30 |
| A Deep BSDE / Sol | run_472994b1fd | unknown（未提交） | 0 | — | #4045，23:00:04 | #334 input/solver.py / 100 |
| A Packing / Sol（暂缓） | run_d4d0a11a67 | 0 | 1 | 79m26.7s | #1333，23:00:04 | #240 public_validate_v2.stdout / 46 |
| B TSA-seq / DeepSeek | run_19080bf816 | 0 | 2 | 45m45.5s | #2094，23:01:21 | #610 public_validation_clean.json / 49 |
| B NLS / Sol | run_45c53e60f1 | unknown（未提交） | 0 | — | #2140，23:01:21 | #170 solve_case.py / 49 |
| B XAS / Sol（暂缓） | run_defca520c0 | 0 | 1 | 82m11.7s | #1519，23:01:22 | #190 train_cv.py / 51 |

未提交不补零。首次提交采用 `submission.submitted` 实际成功事件，草稿创建/上传不算成功提交；Packing/XAS 同一 draft 的续提不算新增 Attempt。实验回执为 `sub_753c90b6e4`、`sub_2527934c74`、`sub_2e9104ed4e`、`sub_1d1cf9e790`、`sub_442b1b0348`、`sub_db174aa31c`；自动收割回执 **无**。

### 证据与交付边界

`before.sqlite`、R3 一致性关机备份、`settings-before.json`、`settings-restored-confirmed.json`、`schedule-state.json`、`duty.jsonl`、各 Rn 快照、`final-ledger-audit.json` 和诊断文件保留本机。六条授权记录与时间压缩前逐字段相同（authorization_records_unchanged=true）；没有通过改授权推动终止或修复收割。

本轮没有第 2/3 级代码修复，没有主邮箱手动提交/收割，没有审批候选、删除远程资源或更改全局 CLI 配置。既有用户任务卡及自动产生的经验文件未纳入交付。此次可交付的是**压缩彩排的失败/未知审计报告**，不是 lightchaser-fallback-3 的成功认证。
