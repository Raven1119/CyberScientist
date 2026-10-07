---
id: lc_visible_creation
title: 题目特定的代码要在轨迹里可见地创建，不重放现成文件（N17/N18/蒸馏）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: both
tags:
- lightchaser
- trace
- N17
- N18
- distillation
- reuse
applicability: 干净复跑、复用其他 Run 或共享区的成果、使用经验中的代码片段时。
evidence_refs:
- cs-s4-analysis:data/deductions.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 在轨迹里写出代码，而不是运行现成的代码

v8 新增两条，触发后 accept 率都是 0：
- **N17**：实质产物在轨迹之前就已存在。评分器的说明是："重放或检查已经完成的源码和推导文件，不能证明当前轨迹产出了解答。"
- **N18**：过程证据低于底线，不能越过满分线。

此外，**N16 蒸馏**（复制、转述、重放他人已解出的题目特定工作）直接 −100 并 block。官方题目资产和通用库仍然允许使用。

**做法**：
- 求解脚本、推导和题目特定的实现，都在提交的那条轨迹里可见地写出来（写文件的命令或编辑工具，代码内容出现在轨迹中），然后运行。
- **干净复跑**：不能只是把已有的脚本拷进新环境运行。要在复跑的轨迹里重新写出这些脚本（可以与之前相同），再运行、验证。
- **复用本题其他 Run 或共享区的成果**：读取后要在本轨迹中重新实现并运行，或者至少在轨迹里写明"这段代码来自本队哪个 Run 的哪一步"，并把它的生成过程纳入本轨迹。不要直接拿另一个 Run 的成品文件提交。
- 经验和 skill 里的通用代码片段可以用，但题目特定的部分必须在本轨迹中推导和实现。
- 中间要有多次成功的科学计算，不能只跑一次就交。
