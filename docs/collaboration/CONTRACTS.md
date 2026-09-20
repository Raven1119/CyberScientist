# 协议与实现约定

本文件中的工具、消息和字段为 CyberScientist 自定义契约，不是 Codex/Kimi 已有 API。字段命名可以与本地等价实现合并，行为约束不得丢失。

## 1. 执行器如何请求大脑

### 两个协作工具即可

首版给执行器接入 `research_checkpoint` 和 `ack_guidance`。大脑继续通过现有 `BrainRuntime.review()` 返回结构化结果，不必额外实现一条功能重复的 `commit_decision` 工具通道。

优先以运行时支持的项目/会话级 MCP 配置接入。MCP 桥只转发到现有后端的受限业务入口，不直接写数据库；工具超时不能覆盖整个大脑思考周期。不要解析普通 stdout 中的某个词来识别请求。

```json
{
  "schema_version": 1,
  "message_type": "checkpoint",
  "checkpoint_key": "trial-4/report-3",
  "review": "blocking",
  "stage": "progress",
  "report_md": "## 实测\n已有两个对照均未改善小尺度误差。\n## 解释\n噪声可能不是唯一因素。\n## 问题\n是否先检查表示方式？\n## 下一步\n用已有结果分组比较。\n## 恢复\n产物已保存，没有新增远程任务。",
  "evidence_refs": ["artifact:scale-results-v2"]
}
```

`run_id / trial_id / session_id / execution_generation` 由后端从受限身份绑定，不能由工具自行选择。`stage=progress|blocked|trial_complete` 表示执行器声明；它不代表控制器已经确认科学结论。

| `review` | 后端动作 | 工具快速返回后执行器的动作 |
|---|---|---|
| `none` | 保存检查点；不创建显式请求。启用了 shadow 时，科学变化仍可触发被动观察 | 继续当前工作 |
| `async` | 持久化显式审阅请求，唤醒调度器 | 不越过当前授权，继续工作 |
| `blocking` | 持久化请求，关闭新增受控研究动作入口，标记 `YIELDING` | 保存状态并结束当前 turn；等待大脑 |

同一事务写入「检查点 + 事件 + 待审阅请求/范围」，随后才通知内存调度器。对 `(run_id, trial_id, checkpoint_key)` 去重；同 key 同内容返回原 receipt，同 key 不同内容返回冲突。JSON 字段顺序不影响内容哈希。数据库是权威，丢失内存通知可由调度器扫描恢复。

工具返回 `checkpoint_id / review_id / next_action`，无需等待大脑返回。普通检查点还可携带已排队指导；`blocking` 返回只要求交棒，收到原生终态后才显示 `WAITING_BRAIN`。检查点/ACK/取消等管理操作不能被新增实验门禁一起锁死。

### 已结束 turn 与实验结束分别处理

适配器发出 `executor.turn_completed`，携带原始终态及绑定的 session、turn、Trial、generation；不能直接发 `trial.completed`。忙碌状态在终态通知对控制器可见之前更新。未知 stopReason 记 `unknown`，不能当成功。

执行器声明 `stage=trial_complete` 后，控制器核对当前 Trial、产物引用和退出边界，先记 `trial.reported_complete` / 待审阅；再由同一大脑调度器做原有生命周期决策。原生回合结束但没有交付声明时，当前 Trial 保持连续；必要时允许一次有界补报，不无限续跑。

`stage=trial_complete` 优先于普通 review 模式：工具要求结束当前 turn；显式请求与交付审阅合并，不能再产生两个重复审阅。

`progress` 的 blocking 审阅不会结束 Trial。大脑只要求补充观察时，沿同一 Trial、同一执行会话继续，不能无故清空上下文或新建一次实验。

### Agent 身份与 UI 身份分开

为工具桥签发仅绑定本 Run、角色和会话代次的短时能力令牌，仅允许登记检查点、读取本次投递、确认指导。令牌不进入提示词、URL、事件和 Git；后端校验与撤销。浏览器继续使用既有 cookie / CSRF；不能关闭整站鉴权来让工具调用通过。

若当前已有等价受控 RPC，就复用它，不另建服务。MCP 配置仅作用于本项目/本会话，不修改用户全局 Codex/Kimi 配置。平台密钥仍由平台适配器持有。

## 2. 大脑输入、输出与介入

### ObservationFrame：不可变输入快照

每次审阅固定一个 `frame_id`，记录：

| 部分 | 字段/内容 |
|---|---|
| 目标和依据 | Run、Trial、`state_version`、`evidence_revision`、`from_seq`、`through_seq`、模式、显式请求 |
| 科学上下文 | 题面与约束、当前方针、跨实验摘要、检查点摘要、反例/异常、来源引用 |
| 机械信息 | 工具活动计数、已登记结果/评分变化、远程任务状态、剩余额度；不存在的数据为未知 |
| 长期连续性 | 当前大脑研究笔记、最多三个观察项、选定经验修订正文 |
| 观察质量 | 截断标记、遗漏数量、未读引用、已知缺项和数据来源 |

控制器不从终端文本猜官方分数，不从文件名推断实验结论，不以任意 JSON 文本冒充平台证据。最小版本只支持已知结构化来源；其余内容保留为带来源的执行器报告。

`state_version` 复用当前控制版本；暂停、恢复、目标/Trial/运行配置/授权变更递增。静默监督开关单独递增 `shadow_epoch`，只使旧 shadow 审阅/未投递指导失效，不撤销用户或显式请求。`evidence_revision` 只随已登记科学证据变化递增。普通日志、SSE 心跳、大脑输出和 ACK 不提高科学证据版本。

`through_seq` 是审阅覆盖范围，不等于“必须一直与最新事件序号相同”。否则大脑自己的输出事件就会使自己的决定立即过期。

### ReviewResult：与旧生命周期 Decision 明确区分

```json
{
  "schema_version": 1,
  "message_type": "review_result",
  "frame_id": "frame-24",
  "disposition": "silent",
  "private_note_md": "当前证据还不足以区分表示能力与噪声的影响。",
  "watchlist": [
    {
      "id": "watch-scale",
      "hypothesis_md": "增益可能只来自大尺度结构。",
      "evidence_needed_md": "已有结果的尺度分组比较。",
      "intervene_when_md": "执行器准备扩大搜索且该不确定性仍未解决。",
      "evidence_refs": ["artifact:scale-results-v2"]
    }
  ],
  "guidance": null
}
```

`intervene` 必须提供 `guidance`：`kind=nudge|steer|stop|submit`、`intent=continue|observe|reframe`、科学指导正文、理由、证据、预期变化和重新讨论条件。后端生成 `guidance_id` 并绑定 frame 的目标和版本；不相信模型自报的运行身份或当前版本。

`kind=submit` 是系统级动作而非发给执行器的文本：大脑判断当前结果包已可提交时发出，控制器在审阅事务提交后自动用有配额的**实验邮箱**提交现成包（幂等键绑定 guidance_id），无需用户逐次确认；提交后进入评分等待，由服务端后台轮询拿回分数。只有**收割提交**（把实验邮箱已得最高分的现成包用收割邮箱再交一次）才必须用户手动确认。submit 指导不投递给执行器、不改变门禁；提交失败记 `submission.auto_failed` 事件并标 guidance `failed`，由大脑下一轮审阅决定是否重试——失败不自动重复配额动作。

SILENT 只原子保存大脑研究笔记、观察项和已审阅范围，以及供用户查看的审阅记录。**没有 outbox 写入，没有经验发布，没有执行器目录改动，没有调用执行器。** 结构不合法的结果按审阅失败处理，不能“修复”为一个会改变 Run 的旧动作。

对 `blocking` 请求，SILENT 无法解除等待，视为无有效回答。大脑可返回 `nudge + continue` 明确允许原方向继续；也可返回观察/转向方针。超时或错误保持 `WAITING_BRAIN` 并显示原因，不暗中放行。

### 主动改变观察角度

`intent=observe` 表示一次明确介入：例如“用已有结果按目标尺度分组比较，先不启动新训练”。大脑提交结果后结束 turn；控制器释放对应的研究门禁，执行器确认后在授权范围内补报，产生新的检查点再请求审阅。不存在“大脑占着回合等待执行器、执行器同时等待大脑”的流程。

### 可靠指导投递

本地记录至少区分：`queued → sending → sent → acknowledged`，异常终态为 `unknown / rejected / superseded`。执行态另记 `accepted / challenged / applied_reported`；只有后续检查点引用同一 guidance ID 及证据，才能记录 `applied_reported`。

发送前在短事务中再次核对 Run、Trial、会话代次、`state_version`、`evidence_revision`、shadow 来源的 `shadow_epoch` 和授权，保留一条状态版本一致的待投递记录。新证据使旧指导需要重新审阅；普通日志不使其失效。发送前暂停/换 Trial 的旧指导保留历史并失效。

实际 RPC 不放在数据库事务里。暂停若与已发出的 RPC 交错，记录真实 `sent/unknown`，由硬控制取消/关门；不能声称已撤回远端已经接收的消息。排队器和原生写通道保持确定顺序。

默认投递点是下一个自然检查点的工具返回，或已确认空闲的原生 turn 边界。选择一个传输途径并记 operation ID，不能同时 MCP 返回和 follow-up prompt 各发一次。发送成功不算模型读到。

```json
{
  "schema_version": 1,
  "message_type": "guidance_ack",
  "guidance_id": "guidance-19",
  "disposition": "accepted",
  "reason_md": "先整理已有结果，不增加计算。"
}
```

ACK 只能确认本会话实际已投递的指导；重复 ACK 幂等。传输超时未知时先核对原生会话/ACK，再决定是否需要提示核对；不盲目重发一个会创建科研任务的 prompt。执行器在自己的笔记中保留最近处理的 guidance ID，重复送达只重新 ACK，不重做已完成动作。

`stop` 先关闭新增受控动作入口并请求取消；收到原生取消/终态确认才记已停。普通 nudge/steer 不调用 cancel。远程 Job 是否仍在运行单独展示，不能从会话状态推断。

## 3. 并发、持久化和运行时接入

### 最小存储扩展

复用当前 `events / checkpoints / operations / experience_revisions`。需要额外持久化的逻辑记录只有「每 Run 的监督状态」「审阅请求」「指导投递」。可采用三个小表或与现有表等价合并；不另建一份可独立修改的事件日志。

| 记录 | 最少保存的内容 |
|---|---|
| 监督状态 | 开关、已覆盖/已尝试的事件位置、待处理范围、证据版本、private note、watchlist、额度、会话/generation 引用 |
| 审阅请求 | request ID、来源/阻塞性、frame 快照、pending/running/done/error/obsolete、结果和调用记账 |
| 指导投递 | guidance ID、来源 frame/目标/版本、正文、传输状态、operation ID、ACK 与行动证据 |

新增迁移应对现有数据库幂等执行，不删除历史表。提供真正的 `db.transaction()` 或等价事务入口；事务内部不得调用会自行 `commit` 的旧 helper。暂停/版本变化、检查点/入队、审阅结果/outbox 各自需要原子提交；不能跨模型请求持有事务或锁。

### 一个事件泵，一个审阅 worker

每个原生会话只允许一个通知消费者；不要每次 Trial 开始都重启第二个 pump，也不要在一次 turn 结束时销毁整个会话事件泵。stdout、stderr、反向 RPC 必须持续处理；反向请求不能等到模型 turn 结束才响应。

主控制循环只处理短事务和调度。审阅 worker 拿固定 frame 调模型，完成后把结果送回控制器；最终接受、过期判断和投递由控制器单点执行。审阅期间执行器事件继续落库、前端继续更新，暂停仍可立即关门。

调度优先级默认作用于待处理队列，不强行抢占正在进行的大脑审阅；显式请求到达后由当前审阅的有界超时保证可交接。用户暂停不受此限制。

用 `asyncio.Event` 或队列作内存唤醒提示；数据库中的 pending 请求是权威。大脑繁忙时合并未覆盖范围，不丢显式请求 ID。失败审阅不推进成功覆盖游标，不自动自循环重试；标记 degraded 后等待新的有效事件按有限退避再试或用户恢复，失败次数受原额度约束。

### 重启和故障

恢复先重建监督队列、核对原生会话与已有外部操作；不把所有 running 审阅和 sending 指导直接重跑。无法确认的在途投递记 unknown；旧代次事件只记历史，不重新绑定到当前 Trial。

原生 resume 支持且已验证时恢复会话；否则新建会话并注入保存的宏观/实验交接资料，明确记录 session replacement。恢复对话不等于恢复计算进程或变量。没有新授权，不重做已经提交的远程 Job/Attempt。

执行器静默一段时间只代表需要检查活性，不能直接判定科学失败或取消正常长实验。先结合进程存活、已知长工具/远程任务和原授权核对；证据不足显示 stalled/unknown，停止新扩展并保留现场，不把“没输出”作为重做任务的许可。

### 运行时最小核查

保留已有 Kimi ACP 和 Codex App Server 适配器。核实本机版本、握手、会话配置、取消和终态、事件命名及反向 RPC。适配层保存 native session/turn ID，公共层使用中性的 executor 语义；历史 `prime.*` 可兼容展示，不全仓改名。

Codex 当前公开文档与所审代码在初始化后通知、item 命名和中断参数上有差异，见审计表；按本机 Schema/探针修正，不从旧模板复制。Kimi 模型/推理档位设置失败不能悄悄当成设置成功；返回有效配置或明确未知。首版不依赖运行中 steer，缺此能力不阻断边界投递。

观察帧、提示词和运行配置需留可追溯 hash。只记录决策依据、摘要和工具/实验事实；不把供应商内部思维链作为必需输入、经验或交付证据。
