---
id: lc_judge_visibility
title: 关键证据放在每个事件的开头，事件短而密，不要堆砌（截断/N12）
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: executor
tags:
- lightchaser
- trace
- truncation
- N12
applicability: 写命令、打印输出、写叙述时。
evidence_refs:
- cs-s4-analysis:data/truncation_check.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 让裁判看得见

裁判（按 v6 公开源码）对每个事件只看前 900 字符，题面只看前 5,000 字符，文件只看前 40 个，看不到图片内容；事件太多时也只摘取一部分。核对发现，约 17% 的"缺失证据"其实写在轨迹里，只是落在了裁判看不到的位置。

**做法**：
- 每次打印输出时，先打印结论和关键数字（例如 `RESULT energy=-1.2345 err=3e-6 PASS`），再打印细节。不要先倾倒几千行日志。
- 长输出写进文件，只把摘要打印出来，并注明文件路径。
- 一个事件只做一件事；不要把多个大脚本塞进同一条命令。
- 不要重复粘贴相同的内容或步骤（N12 扣 32，accept 率为 0）。
- 图片的结论要用文字和数字写出来。
