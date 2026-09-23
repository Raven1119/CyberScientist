---
id: csx1_learn
title: 从实际采用与结果更新经验
scope: global
status: candidate
evidence_status: hypothesis
kind: heuristic
tags:
- cyberscientist
- collaboration
- seed-v1
- continual-learning
- provenance
applicability: 一项策略被明确采用、被可靠反证或完成修复，出现值得用于后续决策的新证据时。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_learn
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 从实际采用与结果更新经验

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
一项策略被明确采用、被可靠反证或完成修复，出现值得用于后续决策的新证据时。

## 协作策略
执行器：标明采用的经验 ID/版本或实际读取内容的哈希，交接对应行动、结果和未控制因素；拿不到版本时写 unknown，不补造。大脑：区分已展示、已采用、已执行和得到支持，优先更新已有条目的适用条件与反例；可以判断无需新经验。提炼“在什么条件下采用什么协作策略，预期什么，何时重试或停用”，不直接把整段轨迹或整轮最高分当作经验效果。

## 检验与边界
新经验只能解释产生后的采用；成功提交不证明科学结论正确，启用不提高证据等级。单次有效只保留在明确范围内。失败与被否决版本不删除；没有对照不能断言因果增益。取消/预算耗尽后仅保留待整理信息，不自行启动额外付费整理。

## 依据与反例
审计 B09/B10/B12 显示目前使用回联和反馈链存在缺口。修复前可在 checkpoint 中保留带引用的文本记录，但不能声称结构化采用追踪已经实现。
