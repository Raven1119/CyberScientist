# 代码审计参考：对静默监督的实际影响

## 1. 基线和审计范围

仓库：`Raven1119/CyberScientist`。参考分支：`main`。固定提交：`27609e6afcc4f9987ec8459e87ff365b650d790c`。核查日期：2026-09-18。

本次通过 GitHub 连接器读取代码；核对了控制器相关段落、Kimi/Codex 大脑与执行适配器、JSON-RPC、SQLite、检查点/经验 API、根 AGENTS 与状态记录。**这是针对协作链的静态审计，没有运行仓库测试、安装用户 CLI 或验证本机账户。** 前端目录已确认存在，具体交互须施工代理在当前工作树复核。

实际代码已接入 Kimi/Codex 执行器，并非仅有旧 Prime 施工包。下一任务应增量修改，不从空目录重建。先记录本地 HEAD/dirty 状态，逐项判断下列发现是否仍存在；不得把远端参考版本覆盖到用户当前代码。

## 2. 关键发现与最小接入点

| ID | 源码事实与位置 | 对目标的影响 | 本任务最小处理 |
|---|---|---|---|
| A1 | `controller.py::_run_loop / _handle_signal` 直接 await `_brain_review`；评审中执行器 pump 仍可能写入队列，但主循环不能继续处理队列 | 审阅期间事件记账/控制处理延迟，无法可靠静默并行 | 独立且单飞的 review worker；结果回到控制器短事务处理 |
| A2 | `_brain_review` 的近期事件只有 seq/source/type；没有检查点正文/结果值；题目只传 challenge_id，经验 manifest 也只有标题和 hash | 大脑拿不到足够科学证据，经验正文未通过该路径注入 | 生成有界、带来源的科学观察帧；注入题面、选定经验正文和历史研究状态 |
| A3 | `api.py::save_checkpoint` 只插 checkpoints 和事件；新 UUID，不含去重/审阅请求；两步各自提交 | 执行器保存报告不能可靠唤起大脑，重试可重复 | 统一 checkpoint 服务，原子保存/排队，MCP 与 UI 复用该服务 |
| A4 | `prime/kimi_acp.py::_run_turn` 将 end_turn 及非标准结束映射到 trial.completed；`prime/codex_exec.py::_pump` 也把完成 turn 映射到 trial.completed | 一次汇报或 ACK 就可能结束科学 Trial；未知结果可能伪装成功 | 分开原生回合与实验交付；只有带证据的显式报告进入实验审阅 |
| A5 | 两个执行器的 `steer()` 都在 busy 时拒绝；`_apply_decision` 只记 receipt，没有可恢复指导 outbox | 大脑在正常执行期间提出的指导没有可靠等待/确认路径 | 持久化队列 + 检查点/空闲边界投递 + ACK；不依赖实时 steer |
| A6 | `_run_loop` 初始启动 pump，`start_trial` 的已接受分支又调用 start_pump；pump 遇 turn 映射的 trial.completed 后退出 | 存在同会话重复消费者和回合间事件缺口路径 | 每个原生会话常驻且唯一的 pump；session/turn/Trial/generation 绑定 |
| A7 | `db.execute / append_event / bump_state_version` 各自 commit；监督队列/投递状态未见现成结构。`_brain_review` 达上限直接把 Run 设 paused | 多步原子性不能靠注释成立；静默观察会不必要地阻断研究 | 真正事务入口；小型持久记录；shadow 子额度耗尽只降级监督 |
| A8 | `JsonRpcStdio.start` 创建 stderr PIPE，所读实现只消费 stdout；`CodexBrain.review` 在等待终态后才处理反向请求 | 长时间运行可能管道阻塞，权限/工具请求可能双方互等 | 持续 drain stderr（有界、脱敏）；反向 RPC 与事件流并发处理 |
| A9 | `with_stall_watchdog` 将无事件直接判 trial.stalled；控制器随后 abort、标失败、换会话 | 正常长计算可能被破坏，重启后有重复工作的风险 | 活性核对与科学结论分离；不因无输出自动判失败/重做 |
| A10 | 大脑以 cwd=None 打开；执行器使用题目目录；`AGENTS.md` 仍要求上游 Prime；`_snapshot_memory` 只写 manifest | 信息边界和代理实际指令不清，旧指令可能使施工偏航 | 明确大脑视图/提示词入口；验证经验正文加载；只更新现行指令，不删除历史 |

这十项是同一协作链的依赖，不是十个独立项目。按「事件接收/生命周期 → 观察/调度 → 投递/确认」集中修复；不要求重写其余平台代码。

### 运行时协议需要本机复核的具体差异

所审 Codex 代码使用 `agent_message / command_execution / file_change / mcp_tool_call`，当前官方 App Server 文档列出 camelCase item；启动代码未见初始化后的确认通知；中断代码未保存并传入 active turn ID。共享 JSON-RPC 代码也未自动补这些字段。它们是需要探针核对的明确差异，不能把“initialize 成功”当作整条 Codex 执行链已验证。[S1]

所审 Kimi 已使用 ACP，执行器忙时拒绝插话。官方能力表可在初始化时核查会话恢复等能力，但本机已安装版本仍需实测。保留此接入，不退回旧 Wire，不因此重造代理内核。[S2]

### 可以直接复用的资产

当前已有 Run/Trial、授权、事件序号和 SSE、经验修订/恢复、两种原生 CLI 的 stdio 封装、真实 React 页面。`prime/` 是现有实现包名，不需要为了术语整洁先搬迁整个目录。原有正式提交/计算模块的未接入部分，不是本轮静默监督必须重做的范围。

## 3. 可定位证据与施工复核

下列均固定到审计提交；路径+函数名是定位依据，行号可能随本地修改变化。

| 来源 | 链接 |
|---|---|
| 控制器 A1/A2/A5/A6/A7/A9/A10 | [controller.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/controller.py) |
| 检查点与经验 API A3 | [api.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/api.py) |
| Kimi 执行器 A4/A5 | [kimi_acp.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/prime/kimi_acp.py) |
| Codex 执行器 A4/A5 | [codex_exec.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/prime/codex_exec.py) |
| 看门狗和执行器协议 A9 | [prime/__init__.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/prime/__init__.py) |
| 存储 A7 | [db.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/db.py) |
| 协议读写 A8 | [jsonrpc_stdio.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/jsonrpc_stdio.py) |
| 大脑适配 A8/A10 | [brains/codex.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/brains/codex.py)、[brains/kimi.py](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/src/cyberscientist/brains/kimi.py) |
| 过期现行指令 A10 | [AGENTS.md](https://github.com/Raven1119/CyberScientist/blob/27609e6afcc4f9987ec8459e87ff365b650d790c/AGENTS.md) |
| 官方协议 S1 | [Codex App Server](https://developers.openai.com/codex/app-server/) |
| 官方协议 S2 | [Kimi ACP](https://moonshotai.github.io/kimi-code/en/reference/kimi-acp) |

施工代理将本机复核写入 `IMPLEMENTATION_RESULT.md`，每项只记录「仍存在并修复 / 已被现有代码解决 / 经实测不成立 / 当前受外部条件阻塞」及证据；不要机械套用旧审计结论。测试计数使用本次实际输出，不能复制 STATUS 历史数字。
