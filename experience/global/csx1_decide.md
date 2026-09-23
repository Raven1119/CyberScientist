---
id: csx1_decide
title: 用能够区分解释的实验推进研究
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- scientific-method
- experiment-selection
applicability: 已有明确科研目标，但存在多个解释、方法或下一步；特别是连续调参没有解释误差来源时。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/checks/build_arm_bundle.py
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_decide
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 用能够区分解释的实验推进研究

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
已有明确科研目标，但存在多个解释、方法或下一步；特别是连续调参没有解释误差来源时。

## 协作策略
大脑：维护当前目标、最重要的不确定性和资源约束，选出一个值得验证的问题，说明什么结果会改变路线。执行器：依据局部证据提出候选解释，自主实现能区分它们的最小实验；优先利用已有数据与失败轨迹。交接：报告实验前预测、实际结果、改变了哪些条件、哪些解释仍未排除。比较需要归因时尽量只改变一个主要因素；确需联合调整时明确混杂，不能归功于其中单项。

## 检验与边界
先检查实验能否改变决策，再看是否提高目标指标。一次干净的负结果也可能有价值。最小实验应保留关键物理/统计机制；小规模结果不能自动外推到正式规模。没有可区分的预测时允许先补资料或基础检查，不强行造假设。

## 依据与反例
本条是科研实验选择的设计先验，尚无本项目对照收益记录。Aiyagari 打包脚本记录了分参数误差与未完成的消融，只能支持“下一步应区分解释”，不能支持未完成方法已经有效。
