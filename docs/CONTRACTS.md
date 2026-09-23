# 本系统契约

这里的类名、路径和字段都是 **CyberScientist 的内部设计**；外部报文必须由 INTEGRATIONS 中的适配器转换，不能直接把下面的 JSON 发给 Bohrium/Prime/Codex/Kimi。

## 三种连接，不做一个万能 chat()

| 抽象 | 最少能力 | 配置归属 |
|---|---|---|
| `BrainRuntime` | 检查安装/认证、启动或恢复会话、执行一次 review、流式事件、取消、关闭 | 原生 CLI 与其模型/登录方式 |
| `PrimeRuntime` | 启动、prompt、steer、abort、读取状态、保存会话标识 | Prime 安装位置与独立 LLM Profile |
| `PlaygroundClient` / `BohriumCompute` | 平台读取、受控提交、Job 操作、结果核对 | 独立的平台凭据与项目 ID |

建议 Python Protocol 签名：

```python
# 设计签名；DTO 由实际实现定义，不是本包已提供的可执行 SDK。
class BrainRuntime(Protocol):
    async def inspect(self) -> RuntimeHealth: ...
    async def open(self, spec: BrainSessionSpec) -> SessionRef: ...
    def review(self, session: SessionRef, packet: ReviewPacket) -> AsyncIterator[BrainEvent]: ...
    async def cancel(self, session: SessionRef) -> ActionReceipt: ...
    async def close(self, session: SessionRef) -> None: ...

class PrimeRuntime(Protocol):
    async def inspect(self) -> RuntimeHealth: ...
    async def start(self, spec: TrialSpec) -> SessionRef: ...
    async def prompt(self, session: SessionRef, text: str) -> ActionReceipt: ...
    async def steer(self, session: SessionRef, text: str) -> ActionReceipt: ...
    async def abort(self, session: SessionRef) -> ActionReceipt: ...
    async def state(self, session: SessionRef) -> RuntimeState: ...
    def events(self, session: SessionRef) -> AsyncIterator[RuntimeEvent]: ...
```

`review()` 最终必须产生恰好一个 `decision` 或 `error` 事件；普通文字片段不是 Decision。标准化事件包含 `raw_ref` 保留协议溯源，但不把上游所有字段透传给浏览器。

`ActionReceipt.status` 为 `accepted / confirmed / rejected / unknown`。`accepted` 只确认接收；不具备确认能力时不能升级 confirmed。能力协商显式记录 `resume_conversation`、`resume_kernel`、`steer_delivery`、`usage_reporting`，禁止把所有适配器能力硬写成 true。

### 模型 Profile

`id / revision / label / protocol / base_url / model_id / secret_ref / reasoning / context_window / max_output_tokens / compat / pricing`。协议是 OpenAI Chat Completions、OpenAI Responses 或 Anthropic Messages 等可验证的具体协议。`compat` 只允许当前适配器已支持的键，不提供任意执行命令。

`pricing` 未知为 null；`usage.cost_amount` 同时带 `currency` 和 `source=provider|estimate|unknown`，缺失用量为 null。最终运行清单保存 Profile 的非秘密内容 hash，包含适配器/CLI 版本；只用 Profile ID 不足以复现。

大脑和 Prime 可以使用同一供应商，但配置与认证生命周期独立。Codex/Kimi 的原生登录不是本系统可以转换成任意第三方 API Key 的东西。

## 核心实体

| 实体 | 必需内容 |
|---|---|
| ChallengeSnapshot | 本地 ID、平台 challenge ID、origin、题面/content hash、规则/数据/评分引用、抓取时间、资格状态、contract_status |
| Run | ID、ChallengeSnapshot ID、模式、phase、state_version、授权 ID、配置/经验快照、当前 Trial、开始/结束时间 |
| Trial | ID、Run ID、parent_trial_id、假设、方案说明、成功判据、固定 manifest、checkpoint、结果分类 |
| JobRecord | 本地 operation ID、remote ID（可空）、所属 Trial、镜像/资源/命令/input hash、状态、最近核对时间、产物引用 |
| Submission | 本地 ID、remote Attempt ID（可空）、Trial、bundle hash、操作状态、评分状态、分数与资格原始证据引用 |
| ExperienceRevision | 经验 ID、revision hash、前驱 hash、正文/元数据、操作者、原因、证据引用、时间 |

`contract_status=verified|partial|conflict|unknown`。`verified` 指所需提交契约已用指定版本与证据核实，不宣称科学真理已被验证。冲突必须显示原始来源，不由模型凭偏好选择。

### 事件

```json
{
  "event_id": "evt_local_001",
  "run_id": "run_local_001",
  "seq": 42,
  "occurred_at": "2026-09-17T12:00:00Z",
  "recorded_at": "2026-09-17T12:00:01Z",
  "source": "prime",
  "type": "checkpoint.created",
  "trial_id": "trial_local_001",
  "payload": {"checkpoint_id": "cp_local_001"},
  "raw_ref": "artifacts/protocol/prime-event-redacted-001.json"
}
```

示例是虚构测试数据。`seq` 在 Run 内单调递增，数据库唯一约束 `(run_id, seq)`。客户端以 `(run_id, seq)` 去重。事件需要按协议确认后归一化；不使用正则在自然语言里猜测 Job 成功或评分数字。

协议原始日志按来源拆分，脱敏存文件，事件保存引用。高频文本增量可短期缓冲；关键动作、最终消息、checkpoint 和外部反馈必须持久化。SSE 的游标使用规范化 seq，重连从 `after` 或 `Last-Event-ID` 补发，不丢关键状态。

## 大脑输入与输出

ReviewPacket 包含 `run_id / state_version / trigger / current_intention / trial_summary / evidence_index / latest_platform_state / budget_remaining / experience_manifest / new_events_since_last_review`（notable 事件与执行器实质进展带 `excerpt` 摘录）；shadow/requested 帧另有 `checkpoint_summaries / notable_events / executor_digest`（执行器非思考类进展摘录，已脱敏）。只附相关摘要与文件引用，允许按需读原始证据，不默认把全量 Trace 塞入每个判断；执行器思考流不进帧。

输出按 `contracts/decision.schema.json` 校验。动作的语义：

| 动作 | 含义 |
|---|---|
| `start_trial` | 开始下一轮，包含目标与成功判据；不得同时有其他活跃 Trial |
| `steer` | 给当前 Prime 排队指导，记录收据 |
| `wait` | 等待新的外部事件，不立即再次唤醒自己 |
| `pause` | 请求安全暂停并给出原因 |
| `refresh_platform` | 触发只读核对，仍尊重频率限制 |
| `request_submission` | 保留旧 Schema 兼容；当前明确拒绝并记录 `brain.action_rejected`，不执行提交。`bundle_manifest_ref` 尚无冻结包解析契约，不能视作 `package_path` |
| `promote_experience` | 请求晋升已有候选修订；检查证据与 scope，不改写历史 |
| `finish` | 结束当前研究 Run，说明停止原因；不代表获得高分 |

当前可用的提交建议入口是 requested/shadow 审阅的 `ReviewResult`（`guidance.kind=submit`）：控制器调用既有实验邮箱提交路径，仍检查 Run 授权、预算与去重。这不扩大正式参赛授权，也不把旧 `request_submission` 自动转换为提交；`policy.allow_formal_submission=false` 对旧动作的拒绝继续保留。

同一 Decision 最多三个动作，只能包含一个改变运行方向的主动作；合法组合由后端做语义校验。Schema 合法不意味着动作被授权。格式错误最多进行一次修复请求，仍失败就 blocked；不执行半解析出的片段。

经验候选可作为 Decision 的 `experience_proposals` 返回，每次最多三条；落盘后仍是候选。题目内经验可由大脑在审查证据后晋升；全局经验要求符合 EXPERIENCE 的推广条件。人可通过 UI 直接编辑并明确设置状态，但不能借编辑按钮伪造 validated 证据状态。

## 本地 HTTP API

生产应用使用 `/api/v1`。这些路由服务于前端和受控 skills，不是竞赛 API。

| 路由 | 用途 |
|---|---|
| `GET /health`、`GET /settings`、`PUT /settings` | 后端健康与无秘密配置；更新需 base revision |
| `POST /secrets`、`DELETE /secrets/{id}` | 写入/删除秘密，只返回 SecretRef 和 configured 状态 |
| `POST /connections/{id}/test` | `kind=inspect|read_only|model_roundtrip`，后者需显式授权 |
| `POST /challenges/import`、`GET /challenges/{id}` | 以官方 URL/ID 导入并读取快照 |
| `POST /runs`、`GET /runs/{id}` | 创建 Run 与取得状态快照；创建不隐含启动付费操作 |
| `POST /runs/{id}/authorize`、`POST /runs/{id}/start` | 保存用户的有界授权，再开始 |
| `GET /runs/{id}/events` | SSE，可按 seq 续传 |
| `POST /runs/{id}/control` | `steer|pause|resume|terminate`；返回动作收据 |
| `POST /runs/{id}/jobs`、`GET /runs/{id}/jobs` | Prime 请求远程 Job、用户查看状态；参数只接受受控 JobSpec |
| `POST /runs/{id}/checkpoints` | 保存 Trial checkpoint 与证据引用 |
| `POST /runs/{id}/submissions`、`GET /runs/{id}/submissions` | 受控提交与结果列表 |
| `GET/POST /experiences`、`GET/PUT /experiences/{id}` | 搜索/创建/编辑经验，PUT 必须带 base hash |
| `GET /experiences/{id}/revisions`、`POST /experiences/{id}/restore` | 历史与回滚为新修订 |
| `GET /artifacts/{id}` | 经过授权和路径验证的产物读取，不接受任意绝对路径 |

错误响应统一 `{code, message, recoverable, details_ref}`。常见业务码包括 `MISSING_CREDENTIAL`、`NEEDS_AUTHORIZATION`、`CONTRACT_UNVERIFIED`、`STALE_DECISION`、`REVISION_CONFLICT`、`REMOTE_OUTCOME_UNKNOWN`；返回明确的下一恢复条件。

control、jobs、submissions 请求必须携带本地 `operation_id`，数据库拒绝重复动作；这只保证本系统去重，不宣称远端 exactly-once。运行只读快照可恢复 UI；不要要求用户重开页面重跑整个任务。

## 文件布局（施工目标）

```text
CyberScientist/
  apps/web/                         # React 应用
  src/cyberscientist/                # Python 后端、CLI、适配器
  tests/                            # 逻辑、协议、集成、浏览器测试
  config/                           # 非秘密配置样例
  contracts/                        # 已提供的 JSON Schema
  experience/global/                # 人可编辑的当前经验
  experience/challenges/<id>/
  .cyberscientist/                   # 不入 Git：数据库、凭据、内部修订操作
  workspace/challenges/<id>/         # 不入 Git：题目快照与资料
  workspace/runs/<run_id>/
    manifest.json
    brain/                          # 大脑自己的 scratch
    trials/<trial_id>/               # 每轮独立代码、输入清单、checkpoint
    artifacts/                      # 远程产物与脱敏原始反馈
    memory_snapshot/                # 实际使用的固定经验版本
  prototype/                        # 本包交互示范，不能混入真实数据
```

配置、模型或经验变更不直接覆盖运行目录。历史产物只追加；大体量原始结果可保存远程 URI+hash+访问元信息，禁止把有时效的签名 URL 当永久证据位置。

## 2026-09-23：受控算力与 Run 经验整理

- 能力令牌接口 `POST /api/v1/tools/job`：`action=submit|list|reconcile|stop`；提交/停止需稳定 `operation_id`。submit 附 `spec` 与当前工作目录内绝对 `input_directory`。Run 身份来自令牌，不信任模型传入的 run_id。
- `GET /api/v1/runs/{id}/jobs` 只读本地账本；`POST .../jobs/reconcile` 查询远端；`POST .../jobs/{operation_id}/stop` 只处理本 Run 已知任务。账本 status 的 accepted、unknown、stop_unknown 与 Finished/Failed/Stopped 分开。
- `POST /api/v1/runs/{id}/curation {operation_id}` / `GET .../curation`：仅 paused/recovering/终态允许整理，冻结证据、请求幂等、状态持久化。整理是独立模型调用，不恢复 Run。
- Brain `protocol=experience_curation` 输出 `{"schema_version":1,"message_type":"curation_result","summary":"...","experience_proposals":[]}`；提案形状沿用既有 experience_proposals。该协议不执行 Run actions。

细节与证据边界见 `TBMA_UPGRADE_2026-09-23.md`。
