---
title: 历史评分拟合前核对同策略配对证据
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: both
tags:
- scoring
- trace
- historical
applicability: 使用历史 Attempt 分数逆向科学或轨迹评分器时
evidence_refs:
- docs/SCORER_REVERSE_ENGINEERING.md
- sha256:f4186803bb61838af62e67adb8021c112451a24c0f37c5f2ee441392f6e531fe
- docs/AGENTMASTER_TRACE_SCORE_PAIRS_2026-09-28.md
- sha256:463474755db98db2abecbc8f61069295c92aabbeab6a9dac88dc867d7680670d
id: exp_cs_up03r_pair_before_fit_20260927
---
先按创建时间与评分字段区分实时双分项、轮次外旧分项和赛后通用评分。只在同一评分方式下，以精确 Attempt ID、提交命令和输入文件哈希配对内容与分项，再检查评分是否最终确认。CS-UP-03R 的 71 条实时双分项已与 AgentMaster 本地 CLI 上传轨迹输入配对，其中 58 条有最终轨迹分；平台 API 仍不能取回这些旧提交的归一化轨迹或 bundle。本地 grader 的轨迹分有 2 条与较晚取得的平台快照不同、4 条缺失，不能静默采用旧本地分。58 条完整展示分中有 10 条不符合主办方告知的 30–70 公式，但符合另一乘法计算；此冲突未获权威解释。在确认平台评分输入、估计重复噪声并完成按题目分层留出验证前，轨迹预测权重、误差和 ≥70/≥80 准确率都保持未知。经验仍是待用户审批的全局候选；详见两份证据报告。
