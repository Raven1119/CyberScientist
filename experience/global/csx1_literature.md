---
id: csx1_literature
title: 将文献方法转成可检验的题内候选
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- literature
- cold-start
- transfer
applicability: 新题缺少自身经验，需要从论文、官方示例或历史不同任务中获得初始方法。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_literature
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 将文献方法转成可检验的题内候选

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
新题缺少自身经验，需要从论文、官方示例或历史不同任务中获得初始方法。

## 协作策略
执行器：读取原始方法、关键假设、所需数据/资源和作者实际完成的验证，提取能在当前任务运行的最小案例。大脑：比较原场景与当前场景，选择迁移前必须核实的一个关键前提；新方法先登记为题内候选策略。交接包含来源定位、未核实假设、预测和失败/停止条件。

## 检验与边界
不要把论文自报效果当作本题效果；摘要相似或工作流相似均不能自动证明可迁移。优先低成本检查关键前提，保留与现有基线的可比性。

## 依据与反例
这是冷启动方法迁移的设计先验。本包不依赖未核实的前沿论文标题、性能数字或软件接口。
