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
