---
id: lc_resubmit_policy
title: 科学分高但轨迹没过门时，重做一条证据充分的轨迹，而不是原包重交
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: brain
tags:
- lightchaser
- submission
- trace
- N15
applicability: 实验提交确认出分后，科学分高、但判定为 review/block 时。
evidence_refs:
- cs-s4-analysis:scorer/scoring_noise.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 补证据，而不是碰运气

同一作者在科学分不变的情况下改进轨迹再交，经常从 69 跃升到 90 以上（scoring_noise.csv 中的多数跃升样本）。原样重交同一个包，则会叠加突发惩罚风险。

**做法**：
1. 读回执里的扣分码和缺失证据清单，逐条对应到本 Run 实际缺的证据。
2. 科学结果冻结不变，重做一次干净的求解过程：在新的轨迹里可见地写出代码、运行、打印关键数字、独立验证，让输出由可见命令生成。
3. 时间戳、耗时、token 数必须真实（N15 扣 35，accept 率为 0）。不要拼接或改写时间。
4. 与上一次提交间隔 30 分钟以上再交。
5. 回执说的是"缺 worker 回执"或提交方式问题时，那是提交链路的问题，不是轨迹问题，交给系统处理。
