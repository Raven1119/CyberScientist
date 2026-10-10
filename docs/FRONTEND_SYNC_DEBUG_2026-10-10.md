# 前后端联调与通信检查（2026-10-10）

用户要求：用 WebBridge 调试真实前端；后端变化正确反映到界面；并行题目可切换查看而不控制研究；检查 Codex 信息截断及阻塞风险。

## 已实现

| 界面 | 后端来源 | 刷新与归属 |
|---|---|---|
| 题目、Run 总览、查看 Run | `/api/v1/challenges`、`/api/v1/runs`、`/api/v1/runs/overview` | 题目与 Run ID 分别选择，逐题记住 Run；跨主导航保留视图与未发送草稿 |
| 当前 Run 状态、活动、检查点 | `/api/v1/runs/{id}`、原有 Run SSE、`/checkpoints` | 详情 3 秒兜底；拒绝其他 Run 的事件及过期详情响应 |
| 本轮冻结模型 | Run `config_snapshot.settings` | 与题目配置的“下次研究模型”分开；未读到快照显示未确认 |
| Job、沙箱、整理 | `/api/v1/runs/{id}/jobs`、`/sandboxes`、`/curation` | 5 秒 GET；慢响应也可显示，旧响应不能把较新已完成状态覆盖成 unknown |
| 监督、方法审批 | Run `/supervision`、`/method` | 10 秒、5 秒 GET；按照 Run 和请求代次应用结果 |
| 比赛实时面板、账号 | `/api/v1/competition-panel`、`/api/v1/mailboxes`、`/api/v1/settings` | 5 秒 GET；查看研究传递准确题目 ID、Run ID，与控制操作分开 |
| 提交记录、本地科学分 | 题目 `/submissions`、`/local-scores`，Run `/submissions` 兼容回退 | 5 秒读取已存记录和 SSE 刷新；读取不触发平台提交或评分请求 |
| 自动提交、排队、门禁 | `/api/v1/features`、`/api/v1/submission_queue`、`/api/v1/ops/gates` | 5 秒 GET；自动提交未确认前不能操作开关 |
| 共享区、包审查、复盘 | 题目 `/shared`、Run `/package-reviews`、`/post-review` | 用户展开后 5 秒 GET；不额外调用模型；原操作 nonce 继续保留 |
| 持久化提醒 | `/api/v1/alerts` | 可“稍后查看”并重新打开；只有明确确认才 ACK，切题不被强制模态框阻挡 |

编辑中的配置表单仍是草稿，不以后台轮询覆盖用户未保存的输入。控制与提交仍走原有明确操作及授权。

通信修复：

1. PI 和执行者适配器保留完整工具回执，移除只保留末尾 12,000 字符的行为；原生记录不修改。
2. 用户给 PI 的指导、放弃待处理意图的原因、流程修复指导及已存公开回复保存完整脱敏正文，审计摘要不作为送达正文。
3. 科学 watchlist 不再裁掉尾部条件或多余项目来“通过”校验；保留语义后由原有合同显式拒绝越界输入。
4. PI 有界工具摘要标明 `…[截断]`、`body_truncated`，并提供 `event:{run_id}:{seq}` 原始记录引用及帧质量标记。原始回执保持完整，已有 `research_trace` 分段读取沿用原授权和总量限制。
5. RPC 请求超时覆盖 stdin 写入、背压等待及响应；通知、审批回复写入也有 60 秒上限。错误回执保留完整 JSON，防止截断后丢失可解析的拒绝码和错误尾部。
6. stderr 持续按字节消费；超长日志行只省略诊断摘要并明确标记，不会因 `readline()` 越界退出后堵住子进程。
7. `turn/start` 回执未知时保留 unknown，不假称空闲、不重发、不猜测 turn ID；明确协议拒绝或限流仍按原逻辑处理。

## 已实际验证

私有原始证据：`.package-checks/frontend-debug/`，不进入 Git。WebBridge 使用独立会话 `frontend-debug-1010`、标签组“前后端联调”。

- 初始实际比赛端口 8765 无监听。恢复比赛目录后端后健康检查通过；历史非终态 Run 的 `resume_on_startup=0`，未开启科研或重放旧外部操作。
- 红色回归分别复现：RPC 写入挂起、超长 stderr 阻塞、长工具回执丢头、长用户指导丢尾、科学条件丢尾、启动回执未知后误报空闲、Job 旧响应覆盖新状态、旧 Run 缺少查看入口、提醒不能延期、摘要截短未标记。相应回归在修复后通过。
- 最终前端 `npm test -- --run`：26 文件、141 项通过；`npm run build` 通过。新增慢请求回归验证响应慢于轮询间隔也能显示、且不倒退。原始日志：`frontend-tests-final.log`、`frontend-build-final.log`。
- 原生协议、长消息及完整公开正文专项：36 项通过（`protocol-final.log`）；摘要引用专项 5 项通过（`digest-green.log`）；长错误 JSON 和意图放弃原因专项 2 项通过（`final-conditions-green.log`）。这些是本地应用协议测试，不冒充真实 Codex 模型调用。
- WebBridge 连接真实浏览器，并在独立数据库的 Demo 服务（18766）验证动态变化。服务、页面、题目均明确标记 Demo；无凭据、无科学 Job、无 Attempt、无模型调用。
- `demo-parallel.json`：两道 Demo 题目 A/B 的 Run 切换前后都为 `running`。旧 Run 保持 `created`。随后 Demo 自身结束时，界面显示对应题目的结束状态，切换未中断后台。
- `demo-sync.json`：后端自动提交 `false` → 前端“自动提交已暂停；科研继续”，1.446 秒；后端 `true` → 前端“自动提交已启用”，4.703 秒。无需页面刷新，最后恢复原值 true；比赛数据库未改动。
- `demo-draft-final.json`：题目 A、旧 Run `run_8603a9b26f`、未发送草稿，在跨主导航及 A→B→A 后仍匹配。`demo-switch-network.json`：99 个 API 请求均为 GET，无控制或提交请求。
- 实际浏览器截图 `demo/research.png` 经人工查看，题目、Run 下拉框、冻结/下次模型、Demo 标识正确；Demo 与比赛截图分目录保存。

- 全量后端 172 文件、1952 个唯一用例通过。三组分别覆盖 634、617、701 项，129 个后端源码文件在最终测试期间未改变；`final-validation.json` 核对收集结果、覆盖和源码哈希。
- 全量测试中两项中断原因已消除：官方 CLI 试构建需要将已有 Linux Node v22.17.0 所在的 `/home/wmywb/.local/bin` 加到测试 PATH；旧公开回执测试要求裁剪到 12,000 字符，现按用户要求改为校验完整尾部并保留脱敏/私有思考隔离断言。分别从失败文件完整续跑后段，没有跳过失败用例。
- 后端通过数按唯一用例去重：组 0 前段 472 + 后段 162，组 1 前段 390 + 后段 227，组 2 全部 701。重跑文件中此前通过的 6/4 项不重复计数。日志为 `backend-final-group-*.log`、`backend-final-group-{0,1}-remainder.log`；最初因继续修补而中断的运行不计为通过。
- 有界代码审查、`compileall`、`git diff --check` 通过。前端实体归属/响应顺序、提醒 ACK、后台查看不发控制操作，以及原生管道超时/unknown/脱敏路径已逐处检查。

- 源码修复提交 `562b2fe9ad82e48e5680731d0e50d511117e3265` 已推送，远端 main 读回一致。`ops release --commit 562b2fe9ad82e48e5680731d0e50d511117e3265 --target comp --timeout 420` 返回 completed；比赛后端 PID 33103，唯一 8765 监听，前端地址仍为 `http://localhost:8765/`。
- 发布后 loaded/checkout 均为上述 SHA、`matches=true`，运行指纹 `258f641e2cf2bcb9813bdc175a1bda3250100822848b8ca8f5640a5ea59f834b`。私有快照 `2c152c99d5e116948c6d5436122e26b6e011e12b` 已推送；250 个运行文件、257 个导出文件、22 个技能，密钥扫描 0 命中。
- `production-verification.json` / `production-bridge-records.json`：WebBridge 在实际比赛前端查看 `run_cc0251a839`，题目 ID、完整 Run ID、`cancelled` → “已终止”、冻结模型逐项匹配后端。冻结大脑/执行者均为历史 `gpt-6.1-sol/xhigh`；题目下次配置的大脑为 `gpt-6-astra`，界面分开显示，不把后续配置当历史会话模型。查看过程 350 个 API 请求均为 GET；比赛截图 `production/research.png` 经查看，无 Demo 标识。
- 发布前后 52 个 Run ID、15 条提交 ID 完全一致；设置文件及凭据存储文件的 SHA256 不变。自动提交仍 true、队列 0、暂停 false；历史 unknown 沙箱记录保留。独立 Demo 后端已停止，真实比赛后端保持运行。
- 本记录的最终文档提交在修复发布后追加；运行代码仍对应上述修复 SHA。未重试旧完整复盘、未新增科学 Run/Job/Attempt、未修改原生记录或全局 CLI 配置。

## 尚未验证

- 未追加真实原生模型调用、科学计算或比赛提交；当前修复的完整回执行为由协议回归验证，前端操作由真实 WebBridge 验证。
- 原生 stdout 仍有 64 MiB 明确帧上限，供应商模型也有上下文限制；不能承诺无限长度单帧或所有模型上下文都无上限。应用送达正文不静默裁剪，摘要明确标记并引用完整记录。
- 不声称排除所有可能的死锁；已验证 stdin 背压、超长 stderr、过期响应与启动回执未知这些具体阻塞/误重发路径。

## 阻塞项

没有当前实现阻塞。历史 `trial9-clean-replay-create` 沙箱 unknown、旧完整复盘缺块失败仍保留，本次不以重发或新增模型授权掩盖。
