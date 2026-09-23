---
id: csx1_reopen
title: 负经验保留失败条件与重新尝试条件
scope: global
status: candidate
evidence_status: hypothesis
kind: heuristic
tags:
- cyberscientist
- collaboration
- seed-v1
- negative-experience
- failure-diagnosis
applicability: 某路线失败、被大脑否决，或后来新证据可能改变旧判断。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_reopen
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 负经验保留失败条件与重新尝试条件

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
某路线失败、被大脑否决，或后来新证据可能改变旧判断。

## 协作策略
执行器：记录失败发生的准确阶段、输入/环境和可观测结果，分开科学反例、实现错误、资源缺失与提交异常。大脑：保留最窄的可支持结论及尚未排除的解释，写清哪些新条件值得重试。后续成功追加新条件和证据，不抹掉旧失败，也不把暂时失败升级为永久禁用。

## 检验与边界
同一失败表象可能有不同根因；条件不匹配时只作提醒。缺少决定性证据时状态保持 hypothesis/unknown，不把大脑置信表达当作验证。

## 依据与反例
依据既有保留失败版本的项目要求与本包审计的证据分层；策略本身尚无收益对照。
