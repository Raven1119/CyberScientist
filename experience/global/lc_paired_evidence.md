---
id: lc_paired_evidence
title: 调用必有结果，数字要打印，推导和验证要留痕（N08/N09/N06）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: executor
tags:
- lightchaser
- trace
- N08
- N09
- N06
- verification
applicability: 整个求解过程。
evidence_refs:
- cs-s4-analysis:data/missing_evidence_classification.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 证据要成对、可见、可核对

触发 N09（没有执行证据）或 N06（叙述没有工具结果支撑）的提交，accept 率为 0；N08（调用与结果不配对）的 accept 率只有 26%。科学分 ≥90 却没过门的提交，最常被指出缺这几类证据：方法实现细节、代码与数据的来源、原始工具输出、中间推导、独立验证、优化日志。

**做法**：
- 每个工具调用都要有结果。被中断或失败的调用，也要留下失败输出，并在下一步说明处理方式。
- 运行时打印关键中间值和最终数值（例如收敛曲线的几个点、残差、能量、误差），不要只写"完成"。
- 推导或公式变换，在代码注释或打印输出里写出关键步骤。
- 至少做一次独立验证：换一种方法、换一组参数、做解析极限检查，或者用评分规则复算。单独运行，并打印"一致/不一致"和差值。
- 训练或优化类任务，保留并打印迭代日志的摘要（起点、若干中间点、终点）。
- 只写真实发生的事；没有运行过的计算，不能写成运行过。
