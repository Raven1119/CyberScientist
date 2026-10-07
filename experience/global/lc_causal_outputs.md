---
id: lc_causal_outputs
title: 每个提交文件都要由轨迹里可见的命令生成（N11）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: executor
tags:
- lightchaser
- trace
- N11
- artifacts
applicability: 写出最终输出文件、整理提交包时。
evidence_refs:
- cs-s4-analysis:data/deductions.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 产物必须有可见的因果链

N11（提交产物没有被因果支撑）出现在 71% 的 v8 提交中，是最常见的扣分。评分器先看 worker 回执，再看文件名和内容能否与轨迹中的执行对应上。

**做法**：
- 最终的每个输出文件，都用一条在轨迹里可见的命令写出。路径与提交包中的路径完全一致，例如 `python solve.py --out outputs/answer.json`。
- 写完立刻用一条命令回显关键内容（`head`、`cat`、打印摘要数值），让文件内容出现在工具输出里。
- 不要在轨迹之外手工改输出文件，也不要从别处复制过来。需要改，就改生成它的代码并重新运行。
- 提交包里的数值，必须和轨迹最后一次生成时打印的一致。
