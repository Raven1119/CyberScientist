---
id: lc_requested_method
title: 最终结果必须来自题目要求的方法（N14）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: both
tags:
- lightchaser
- trace
- N14
- method
applicability: 选择方法、遇到所要求的方法跑不通、准备交付时。
evidence_refs:
- cs-s4-analysis:data/deductions.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 不要用替代方法交最终结果

N14（题目要求的最终方法被替代或降级）出现在 32% 的 v8 提交中。评分器的说明是：出现"降级、代理"一类字眼只是提示，真正扣分的条件是看得出最终结果被替换了。

**做法**：
- 先读清题面要求的方法：算法、模型、精度、步骤。
- 替代方法只用来探索、做对照或保底；最终提交的数值必须由题目要求的方法算出。
- 要求的方法暂时跑不通时，先修它（换实现、调参数、换算力）。时间实在不够、只能交替代结果时，这一点 PI 必须明确知道，并在方法说明中如实写出，预期会被扣分。
- 不要用"近似、简化版"悄悄替换题目要求的步骤。
