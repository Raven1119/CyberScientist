---
title: 评分器研究先核对当前契约和独立分项
scope: global
status: candidate
evidence_status: observed
kind: platform
audience: both
tags:
- 评分契约
- 轨迹校准
- Bohrium
applicability: 在以平台科学分、轨迹分或展示分拟合本地评分器前；每个题目和当前轮次均须重新核对。
evidence_refs:
- https://play.bohrium.com/api/protocol
- https://play.bohrium.com/api/challenges/paper2arm-abc-conjecture-record-b335c57d
- https://play.bohrium.com/api/challenges/paper2arm-mcm-mechanism-reduction-7fe0238c
- event:run_b1ba85d4fb:2124
- .package-checks/cs-up-03-contract-refresh-20260927T121144Z/summary.json
expires_at: '2026-10-04T00:00:00+00:00'
id: exp_cs_up03_scoring_contract_20260927
---
## 观察与行动
2026-09-27 公开只读复核中，abc 与 MCM 的公布轮次均已结束，题目详情采用 `arm_v1_1_generic` 且没有专属 grader；本账号 abc 晚交回执已确认展示分，却没有独立的 `harbor_score`/`trace_score`。协议中的 `trace_quality` 是 0/0.5/1 分档，不能乘以 100 冒充历史 0–100 轨迹分。另查到的开放题目可采用人工或题目专用 LLM 评分；`open` 本身不保证旧双分项。

设计评分器实验前，先读当前题目 `scoring.strategy`、轮次截止、`/api/protocol`，再检查一次真实评分回执是否包含所需分项。缺少分项时保存 `unknown`，暂停该目标的拟合与付费对照；不要把本地题面评分、通用 ARM 展示分和历史旧评分混为同一口径。

## 边界
这只证明上述日期、题目与回执的契约状态，不证明其他题目或未来轮次永远缺少旧评分器。平台契约或轮次改变时重新核验。当前证据不足以计算旧轨迹分的 70/80 阈值、重复噪声或留出误差；本候选需要用户审批后才作为全局经验注入。
