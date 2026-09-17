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
- Codex `thread/start`、`turn/start` 字段形状与终态事件（需一次用户授权的模型往返）；Prime RPC 帧格式（prime-agent 未安装）；bohr 全部能力；Playground API 载荷。
- 真实模型 Decision + Prime 工具往返（未获授权，不自动消耗额度）。
- 后端崩溃恢复中对远程 Job/Attempt 的挂接（阶段 2 范围，本地状态已可重启读回）。
- 浏览器内 409 冲突对照视图的点击流（API 层已验；视图代码与后端契约核对一致）。

**阻塞项（准确缺项）**：
- Prime Agent 未安装 → connected 模式启动被准确阻止（phase=blocked + 原因），Demo 模式不受影响。
- `bohr` CLI 未安装、Playground Token 未配置 → 题目 URL 导入与 Bohrium 计算不可用（阶段 2）。
- 无 `kimi --wire` 可执行文件 → 第二大脑未接入（边界保留，阶段 3）。

**浏览器级验证（2026-09-17，kimi-webbridge，真实浏览器）**：
- 页面加载、演示模式徽章、配对对话框 → 输入配对码 → 会话建立（写请求可用）。
- 导入演示题目 → 题目栏显示 DEMO_CHALLENGE 与契约状态；历史 Run 状态正确显示“已完成”。
- 开始研究 → 预检与授权对话框（模型调用勾选、判断/时长/提交上限）→ 确认启动 → SSE 事件流实时渲染（大脑 Decision、Trial 创建、执行器事件、Trial 完成），Run 摘要费用显示“未知”而非 0。
- 经验库：Run 结束大脑提议的候选经验出现在列表（题目内/候选/假设徽章），编辑器 frontmatter 表单与 Markdown 正文完整。
- 连接与设置：大脑卡（Codex App Server/原生登录/检查安装/消耗额度确认勾选）、Prime 卡渲染正确。
- 截图证据：`checks/shots/01-workbench-paired.png`、`02-run-events.png`、`03-experience.png`、`04-settings.png`。
- 遗留：409 冲突左右对照视图未点击验证（API 契约已验）。
