---
id: lc_submission_spacing
title: 同账号同题提交间隔 30 分钟以上，避免突发提交（N16）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: brain
tags:
- lightchaser
- submission
- N16
- rhythm
applicability: 决定是否提交、何时再提交时。
evidence_refs:
- cs-s4-analysis:data/deductions.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 不要连发

N16（重复或突发提交）按提交序列判定，扣 15。带这个码的提交中，43% 被 block。

触发概率与上一次提交（同账号同题）的间隔有关：

| 间隔 | ≤2 分钟 | 2–5 分钟 | 5–10 分钟 | 10–30 分钟 | 30 分钟以上 |
|---|---:|---:|---:|---:|---:|
| 触发概率 | 54% | 27% | 14% | 约 10% | 约 5% |

前 60 分钟内已有 3 次提交时，触发率为 27%；第 4 次以后的提交风险明显上升。账号在 30 分钟内跨题提交 5 次以上，也会被判突发。

**做法**：
- 同一账号同一题，两次提交之间至少间隔 30 分钟；每题每个账号尽量不超过 3–4 次。
- 只在有实质改进时才提交（科学分提高，或轨迹证据明显补强），不要拿同一个包反复试。
- 多道题同时在跑时，一个账号的提交错开，不要集中在几分钟内。
