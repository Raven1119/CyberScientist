<div align="center">

# 🧬 CyberScientist

**让每一轮科学尝试都产生可提交的结果，或为下一轮留下可用的证据。**

大脑判断方向 · Prime 自主执行 · Bohrium 远程科学计算

[![阶段](https://img.shields.io/badge/%E9%98%B6%E6%AE%B5-1%20%E5%9E%82%E7%9B%B4%E5%88%87%E7%89%87-216d63)](#当前状态)
[![后端测试](https://img.shields.io/badge/pytest-31%20passed-2ea043)](#验证证据)
[![Smoke](https://img.shields.io/badge/smoke-22%2F22-2ea043)](#验证证据)
[![Codex 握手](https://img.shields.io/badge/Codex%20app--server-%E2%9C%85%200.154.0--alpha.6.2-496da0)](#外部协议探针)
[![License](https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF%E8%AF%81-%E6%9C%AA%E5%AE%9A-lightgrey)]()

</div>

---

## 这是什么

CyberScientist 是一个**单用户科学竞赛工作台**：导入一道题，授权一轮预算，大脑（LLM）审阅证据并判断方向，执行器（Prime Agent）自主完成实验，科学计算全部发生在 Bohrium 远程 Job 上——本地只做编排、证据和提交管理。

不是聊天框套壳，不是通用多代理平台。它是一个**可恢复、可审计、有界授权**的研究闭环：

```text
题目快照 → 大脑研究目标 → Prime 执行一轮 → 远程证据 → 大脑审查 → 继续/换路/提交 → 经验沉淀
```

## 当前状态

**阶段 1（可操作的研究垂直切片）已交付并实测通过**：Demo 模式下「配置连接 → 导入一道题 → 启动研究 → 观察与指导 → 保存经验 → 重启后可见」全链路可操作；真实 Codex 大脑完成握手探针；审查发现的 11 项问题全部修复复测。

| 组件 | 状态 | 说明 |
|---|---|---|
| 后端 + 前端 | ✅ 可运行 | FastAPI + SQLite + React/TS/Vite，`uv run cyberscientist serve` 一键启动 |
| Demo 闭环 | ✅ 22/22 smoke | 完整研究状态机 + SSE 事件流 + 经验编辑/历史 |
| Codex 大脑 | 🔵 握手探针通过 | `codex app-server` 0.154 实测；模型往返待你授权 |
| Prime 执行器 | ⬜ 适配器就位 | 上游未安装，如实报缺，不伪造联调 |
| Bohrium 计算 | ⬜ 阶段 2 | `bohr` CLI 未安装；绝不回退本地科学计算 |
| Kimi 大脑 | ⬜ 边界保留 | 无可执行文件，明确显示「未接入」 |

## 快速开始

```bash
git clone <your-repo> && cd CyberScientist
uv sync                                  # Python 3.11+ 后端依赖
uv run cyberscientist serve --port 8765  # 启动（控制台输出配对码）
```

浏览器打开 **http://127.0.0.1:8765/** → 输入配对码 → 导入演示题目 → 开始研究。

前端开发模式：`cd apps/web && npm install && npm run dev`（代理 `/api` 到 8765）。

```bash
uv run pytest tests/ -q                        # 31 个单元/协议测试
uv run python checks/smoke_vertical_slice.py   # 端到端 22 项断言（需后端运行中）
uv run python checks/probe_integrations.py     # 外部协议真实探针
```

## 界面

| 研究工作台 | 经验库 |
|---|---|
| ![研究工作台](checks/shots/02-run-events.png) | ![经验库](checks/shots/03-experience.png) |

实时事件流区分大脑/执行器/控制器角色；steer 显示「已排队」、以 `steer.consumed` 事件确认生效；暂停显示「正在暂停」，代理确认才显示已暂停；费用未知显示「未知」而不是 0。经验库中 Markdown 是编辑界面，修订历史内容寻址、永不覆盖，冲突时左右对照不丢任何一方。

## 架构

```text
浏览器：研究工作台 / 经验库 / 连接设置   ← SSE + 同源 HTTP →
Python 单进程后端（127.0.0.1）
  RunController ── SQLite（事件 seq 唯一、操作幂等、修订历史）
       ├─ BrainRuntime   Codex app-server │ Kimi Wire(未接入) │ Demo
       ├─ PrimeRuntime   prime-agent --mode rpc │ Demo
       └─ BohriumCompute bohr（阶段 2）
```

设计上的硬约束（全部在实施中保留）：

- **真实证据**：HTTP 成功 / RPC 接受 / 评分完成分别确认，不知道就显示 `unknown`；Demo 成功从不冒充真实联调
- **密钥隔离**：后端保存、前端写入后不回显、不进 Git/日志/经验/提交包；写请求全部要本地配对会话 + CSRF
- **有界授权**：模型调用、时长、Trial 数、提交数逐项授权逐项强制；`operation_id` 去重；并发 start 原子抢占
- **Bohrium-first**：科学计算只在远程 Job 执行；本地出科学结果标记来源不合格并远程重做
- **可恢复**：SQLite 是唯一权威源，重启后对账读回；工作区文件锁拒绝第二个控制器进程

## 验证证据

- `uv run pytest tests/ -q` → **31 passed**（决策 schema/语义校验、经验冲突/回滚/外部编辑、事件 seq 唯一、控制器全闭环、JSON-RPC 分帧 synthetic fixture）
- `checks/smoke_vertical_slice.py` → **22 PASS / 0 FAIL**：未授权启动拒绝、SSE 事件序列、暂停/恢复语义、steer 队列确认、operation_id 去重、经验 409 冲突双方内容、回滚幂等、连接探针、未确认消耗被拒
- 后端 kill 重启 → Run/Trial/经验候选**完整读回**
- kimi-webbridge 真实浏览器走查：配对 → 导入 → 授权启动 → 事件流 → 经验落盘 → 连接设置（截图见 `checks/shots/`）
- `docs/INTEGRATION_STATUS.md`：Codex `initialize` 握手原始响应（零模型调用）、Prime/bohr 缺失事实

## 路线图

- [x] **阶段 1**：研究垂直切片（本仓库当前状态）
- [ ] **阶段 2**：bohr Job 提交/查询/取回、Playground 两步提交、评分核对、崩溃恢复对账远程任务
- [ ] **阶段 3**：接入 Kimi 大脑、等预算对照实验（监督 vs 无监督、有经验 vs 无经验）

## 文档导航

| 文件 | 作用 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 进程边界、研究闭环、恢复、预算与密钥 |
| [docs/BUILD.md](docs/BUILD.md) | 三个交付阶段与验收标准 |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 数据、运行时与 HTTP 契约 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 设计调整与施工期实测记录 |
| [docs/INTEGRATION_STATUS.md](docs/INTEGRATION_STATUS.md) | 外部协议探针事实 |
| [STATUS.md](STATUS.md) | 交付事实：已实现/已验证/未验证/阻塞项 |
| [prototype/index.html](prototype/index.html) | 独立交互原型（演示数据，非生产） |

---

<div align="center">
<sub>一轮实验，一份证据。 · Built with FastAPI + React · 施工记录见 <a href="STATUS.md">STATUS.md</a></sub>
</div>
