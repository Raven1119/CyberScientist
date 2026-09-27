---
name: cyberscientist-trace-writing
description: Write evidence-linked ARM trace narratives for a Trial and check them before sealing or controlled variant submission.
metadata:
  audience: executor
---

# 轨迹叙述

在当前 Trial 的 `trace_narrative.jsonl` 写一行一个步骤。每行用 `cs_refs` 指向本 Run 的真实 `run_id#seq` 事件，按研究事实解释意图、动作、观察、失败修复和产物。工具 ID、输出原文、退出码、时间、费用和 artifact 哈希必须与引用记录或包内文件一致；不能编造工具调用、计算结果或成本。事后写的解释用 `annotation: true` 和写作时间，不充当工具步骤。

写完用 `research_trace_narrative_check` 检查所有行、合并轨迹和本地准入；修正列出的具体错误。未被叙述覆盖的事件投影仍会进入封存轨迹。比较表达方式时只改变叙述，并通过受控变体入口逐文件核对科学产物。提交前写明预计影响哪项分数；已确认的评分差异才可用于更新写作经验。

将阶段覆盖、验证步骤、错误后修复和日志一致性用于组织真实证据，不把它们写成已验证的加分权重。CS-UP-03R 扩查 75 条带旧轨迹分的本人提交，仍无一条取回相应轨迹；8 条可读轨迹没有旧分项。API `/trace`、创建表单行内轨迹、包内按规则选中的轨迹和原始消息应分别保存来源与哈希：列表 `traceCount` 可为正而操作者读到空数组，API 轨迹也可能与包内选中行数不同。详见 `docs/OWNED_TRACE_ANALYSIS_2026-09-28.md`。≥70/≥80 预测准确率与同包噪声仍未知；在有配对轨迹、同包重复和留出验证前，把阈值预测标为未验证。
