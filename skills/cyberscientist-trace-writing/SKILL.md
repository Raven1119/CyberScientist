---
name: cyberscientist-trace-writing
description: Write evidence-linked ARM trace narratives for a Trial and check them before sealing or controlled variant submission.
metadata:
  audience: executor
---

# 轨迹叙述

在当前 Trial 的 `trace_narrative.jsonl` 写一行一个步骤。每行用 `cs_refs` 指向本 Run 的真实 `run_id#seq` 事件，按研究事实解释意图、动作、观察、失败修复和产物。工具 ID、输出原文、退出码、时间、费用和 artifact 哈希必须与引用记录或包内文件一致；不能编造工具调用、计算结果或成本。事后写的解释用 `annotation: true` 和写作时间，不充当工具步骤。

写完用 `research_trace_narrative_check` 检查所有行、合并轨迹和本地准入；修正列出的具体错误。未被叙述覆盖的事件投影仍会进入封存轨迹。比较表达方式时只改变叙述，并通过受控变体入口逐文件核对科学产物。提交前写明预计影响哪项分数；已确认的评分差异才可用于更新写作经验。

提交预检中的公开 v6 确定性诊断仅供核对真实工作，不能当作官方分数或绕过准入。CS-UP-04 对 63 份历史 v8 可见回执的条件比较中，N09（缺执行证据）和 N11（产物因果链不足）为可靠；N06（缺可核对的执行观察）、N08（调用/结果不配对）、N14（最终方法被替代）为提示性。遇到 N09/N06，核对真实命令、输入、回执与产物，未执行的计算应实际执行；遇到 N08，检查真实结果是否在投影或转换中丢失；遇到 N11，核对产物路径与哈希能否追溯到执行回执；遇到 N14，核对最终产物是否来自题目要求的方法，必要时重做实验。缺证据时保留未知或失败，不制造步骤。其他代码历史样本不足或不可观察，只在前端详情供人工核查。

将阶段覆盖、验证步骤、错误后修复和日志一致性用于组织真实证据，不把它们写成已验证的加分权重。CS-UP-03R 在 AgentMaster 本地以 Attempt ID 和提交命令找回 71 条旧分项的上传轨迹输入，其中 58 条有最终轨迹分；见 `docs/AGENTMASTER_TRACE_SCORE_PAIRS_2026-09-28.md`。API `/trace`、创建表单行内轨迹、CLI 上传输入、包内选中轨迹和原始消息应分别保存来源与哈希，不能凭 API 返回空数组否认本地原始轨迹。平台最终采纳的归一化轨迹、≥70/≥80 预测准确率与同包噪声仍未知；做题目分层留出验证前，把阈值预测标为未验证。
