---
title: 本题实际评分路径为 arm_v1_1_generic 通用管线，非题面隐藏 controller
scope: challenge
challenge_id: local_14c116ff
status: active
evidence_status: observed
kind: platform
applicability: 在 play.bohrium.com 平台对 local_14c116ff 及同策略（arm_v1_1_generic）赛题规划提交与提分实验时适用。
evidence_refs:
- cp_998b52db60
- cp_c1b075083d
- workspace/challenges/local_14c116ff/results/attempt_44795_score_recheck.json
- workspace/challenges/local_14c116ff/platform_challenge.json
id: exp_aebf07c31d
tags: []
---
实测确认（2026-09-19）：local_14c116ff 未注册专用 grader，scoring.strategy=arm_v1_1_generic，分数来自 ARM bundle（arm_manifest v1.1 + characterization + trace + execution）经 submit_experiment → POST /attempts/{id}/bundle。题面 100 分制隐藏行为评分在本平台实例不存在。scorecard 分项含 packaging / trace_quality / executability；scoringDetails 赛后才公开（redacted）。roundEndAt 过后提交仍被打分但标记 late_scored，是否计入正式榜单 unknown。提分应面向 scorecard 分项而非题面评分表。
