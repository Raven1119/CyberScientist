---
name: cyberscientist-clean-rerun
description: How to do a clean rerun in a fresh executor session from the PI's four-part handoff — re-create code visibly, rerun stage by stage, validate, deliver outputs.
metadata:
  audience: executor
---

# 干净复跑

首条消息写着“方法来自本方此前的探索”时，你在一个新会话里按交接的方法从头真实重算。这条会话就是提交轨迹，它本身要完整：可见地写代码、运行、检查、交付。

1. 读交接的四段：流程、参数、验证、故障。参数可以直接使用。交接里没有探索得到的结果数值，你也不要去找。
2. 不读取此前探索的代码和产物；你的工作目录是一个新的空目录。
3. 按流程逐阶段做：写出该阶段的脚本（内容可以与探索时相同，但要在本会话中重新写出）→ 运行 → 打印关键数字 → 完成该阶段的检查。
4. 完成验证段要求的检查，打印结论。
5. 交付：按题面契约写出输出文件并打印关键内容，写结果包，报 trial_complete。
6. 计算放置与探索时相同（本题沙箱为主，长计算用 Job）。遇到故障段列出的现象，按其中的处理方式办。
