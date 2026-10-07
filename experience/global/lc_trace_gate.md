---
id: lc_trace_gate
title: 轨迹门决定一半分数：提交前先过轨迹门
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: both
tags:
- lightchaser
- trace
- submission
- scoring
applicability: 任何准备提交（实验或收割）的时刻；PI 审阅提交前必读。
evidence_refs:
- cs-s4-analysis:scorer/display_formula_checks.csv
- cs-s4-analysis:scorer/code_table.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 轨迹门决定一半分数

展示分 = 科学分 × 轨迹因子：轨迹分 ≥70 为 accept，展示分等于科学分；低于 70 为 review，展示分按比例打折；被 block 则为 0。S4 中科学分 ≥90 的提交，只有 46% 过了这道门，29% 直接归零。一份科学分 95、轨迹分 29 的提交，最终是 0 分（例：49780）。

**做法**：提交前逐条核对，任何一条不满足，都先补证据再提交：
1. 每个提交文件，都能在轨迹中找到生成它的那条命令及其输出；
2. 最终结果来自题目要求的方法；
3. 题目特定的代码是在轨迹里可见地写出来的，不是拿现成文件直接跑；
4. 每个工具调用都有对应的结果；关键数字打印在输出里；
5. 有一次独立验证，并打印出结论；
6. 关键证据位于每个事件的开头部分；
7. 没有重复堆砌的步骤；时间戳是真实的。

科学部分再好，轨迹不过门就等于没做。
