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
id: exp_cs_up03r_pair_before_fit_20260927
---
先按创建时间与评分字段区分实时双分项、轮次外旧分项和赛后通用评分。仅在同一评分方式下，把原始科学文件或被评判轨迹与对应分项配对后拟合；没有配对内容就把规则、误差和阈值准确率记为未知。CS-UP-03R 的 71 条实时双分项中，可取回原始包为 0；58 条完整展示分里有 10 条不符合预设公式，但符合另一乘法公式，且没有已验证的预先选择字段。这些分数可描述分布，不能训练内容评分器。详见证据报告；下次新轮次先保存同包重复和留出样本。
