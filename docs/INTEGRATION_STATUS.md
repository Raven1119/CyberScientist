# 外部集成探针记录
探针日期：2026-09-17 16:04 UTC。本文件只记录实际执行的命令与结果，不编造接口。
## Codex 大脑
- 可执行文件：`C:\Users\wmywb/.codex/.sandbox-bin/codex.exe`
- `✅ codex --version` → codex-cli 0.154.0-alpha.6.2（）
- `✅ codex app-server (initialize handshake)` → 0.154.0-alpha.6.2（app-server 握手成功（initialize），未发起模型调用； codexHome=C:\Users\wmywb\.codex；登录态未由握手验证（需登录状态探针））
- initialize 原始返回（脱敏原样记录）: `{"initialize_result": {"userAgent": "cyberscientist/0.154.0-alpha.6.2 (Windows 10.0.26200; x86_64) dumb (cyberscientist; 0.1.0)", "codexHome": "C:\\Users\\wmywb\\.codex", "platformFamily": "windows", "platformOs": "windows"}}`
- 已证实：app-server stdio 启动 + initialize/initialized 握手（零模型调用）。
- 未证实：thread/start、turn/start 的字段形状与终态事件（需一次授权的模型往返）；
  turn/interrupt、thread/resume、审批请求处理。能力标记保持保守。

## Prime Agent
- 可执行文件：`C:\Users\wmywb\AppData\Roaming\npm\prime-agent.CMD`
- `✅ prime-agent --version` → 0.9.5
- `✅ prime-agent --mode rpc (get_state)` → RPC get_state 探针成功（零模型调用）； sessionId=01a0b01c-fc9c-72e2-a40f-978033294394, isStreaming=False
- get_state 返回字段（原样记录）: `autoCompactionEnabled, followUpMode, goal, isCompacting, isStreaming, messageCount, model, sessionActions, sessionId, steeringMode, thinkingLevel`
- 已证实：版本探针 + RPC 模式启动 + `get_state` 零模型调用响应（sessionId/isStreaming/steeringMode 等字段与官方文档一致）。
- ✅ **真实模型工具往返（2026-09-18，用户授权 OpenRouter 付费额度）**：
  `checks/probe_prime_roundtrip.py` 驱动 Prime + `deepseek/deepseek-v4.1-flash`（经 OpenRouter），
  prompt → agent_start → ipython 工具执行（写 `probe_hello.txt` 并读回）→ tool_execution_end →
  agent_end → `get_last_assistant_text` 报告内容一致。用量：input 6749 / output 129 /
  cacheRead 5120 tokens，**成本 $0.00185775**（OpenRouter 计价，prime get_session_stats 上报）。
  脱敏 transcript：`checks/fixtures/real/prime-rpc-deepseek-v4.1-flash.jsonl`（53 事件）。
- 负面试试证（同轮记录）：`z-ai/glm-5.2:free` 工具调用被 OpenRouter 拒绝
  （"404 No endpoints found that support tool use"），免费 GLM 无法驱动 Prime 工具循环；
  智谱「夜间畅用」免费仅限 ZCode IDE，不覆盖第三方 Agent。
- 已证实（文档级，未实测）：steer 排队消费、abort 生效确认、`--session-dir` 恢复语义。
- 未证实：项目隔离 `--session-dir` 与自定义 models.json 的两 Profile 不串配置测试；
  长时间运行/自动 compaction 行为。

## bohr（Bohrium CLI）
- 安装：否（None）
- 版本：未在 PATH 或常见安装位置发现
- Bohrium 科学计算在阶段 2 接入；bohr 缺失时绝不回退本地科学计算。

## Kimi Code（大脑 + 执行器，ACP）
- 可执行文件：`kimi.cmd`（npm 全局，`@moonshot-ai/kimi-code`）
- ✅ `kimi --version` → Kimi Code CLI 2.0.0
- ✅ ACP initialize 握手（protocolVersion 协商，零模型调用）
- 事实修正：2.0 无 `--wire`；接入面为 `kimi acp`（JSON-RPC 2.0 stdio）。
- ✅ `session/new`（必须带 `mcpServers: []`）、`session/set_model`、`session/set_config_option`
  （configId: model / thinking[low|high|max] / mode[default|plan|auto|yolo]）实测可用。
- ✅ 大脑 Decision 往返（kimi-code/k3）：`checks/probe_kimi_brain.py` PASS，
  输出 schema 合法 Decision；chunk 为增量片段需无缝拼接。
- ✅ 执行器工具往返（kimi-code/k3-256k，mode=yolo）：写文件 + 列目录 PASS；
  yolo 后无权限请求；tool_call/tool_call_update 事件全程留痕。
  注：`session/request_permission` 的两种应答形状实测均被判 rejected → 采用 yolo，记 DECISIONS。
- ✅ 默认路径全真实闭环（2026-09-18，run_9785db28ab）：K3 大脑 3 次 review +
  Kimi 执行器 2 个 Trial（基线产出、结果验证）→ K3 主动 finish → run.finished。
- 未证实：`session/load` 恢复；长上下文 compaction 行为；usage/token 统计字段。

## bohr（Bohrium CLI）
- 安装：否（None）
- 版本：未在 PATH 或常见安装位置发现
- Bohrium 科学计算在阶段 2 接入；bohr 缺失时绝不回退本地科学计算。

（注：「bohr（Bohrium CLI）」节因历史合并在上文出现两次，内容一致。）

## Bohrium Playground（提交平台，邮箱双轨的真实后端）
探针日期：2026-09-18。脱敏结果：`checks/results/platform_probe2.json`；
官方 API 文档快照：`checks/results/AGENT_API.md`（GET /api/docs/dev/AGENT_API.md）。
- ✅ `Authorization: Bearer <asp_ token>` 认证有效；`GET /api/challenges` 200。
- ✅ `GET /api/auth/me` → 该 token 是**人类账号**（id 90229，userType=human）。
  含义：收割邮箱直接用它提交；实验邮箱走文档 Option A（人类 token 调
  `POST /api/agent/register` 注册 agent 账号，响应立即含 agent 的 asp_ token，
  无需邮箱验证）。`GET /api/agent/register` 实测列出既有 agent（agentmaster-02/03）。
- ✅ `GET /api/agent/work?limit=1` 200；challenge id 为 slug 字符串。
- ✅ `GET /api/attempts/{id}/score` 返回形状实测：
  `{"score": float, "scoringState": {"scoreIsFinal": bool, "displayScore": ...}}`；
  适配器只在 scoreIsFinal=true 时采信，否则如实 unknown。
- 文档核实（未真实调用，写操作）：提交三步 = `POST /challenges/{id}/attempts`
  （multipart：method/type=agent/status=draft/outcome/trace[内联 JSON]）
  → zip 包 `POST /attempts/{id}/bundle`（字段名 bundle）→ `POST /attempts/{id}/submit`。
- ✅ 适配器 `BohriumPlaygroundPlatform` 已实现（`src/cyberscientist/mailbox_platform.py`），
  9 个 mock HTTP 单测通过（`tests/test_mailbox_platform.py`）；settings
  `mailbox.platform` 已切到 `bohrium_playground`。
- 未验证（需用户逐次授权的真实写操作）：真实注册 agent 账号、真实提交 attempt、
  真实评分回拉。首次点击前端「注册实验邮箱」即为真实注册。
- ❌ `openapi.bohrium.com` DNS 不解析；Bohrium 计算 API host 未确定
  （bohr CLI 未安装，官方推荐 `npm i -g @dptech-corp/bohr-cli`，默认 host
  `https://open.bohrium.com`，勿设裸 `OPENAPI_HOST`——见 AGENT_API.md CLI 节）。
