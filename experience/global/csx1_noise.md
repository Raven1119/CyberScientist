---
id: csx1_noise
title: 指标改善先排除随机性与口径变化
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- statistics
- noisy-evaluation
- comparison
applicability: 两次结果差距较小、随机初始化/采样显著，或评价口径可能随尝试变化。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_noise
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 指标改善先排除随机性与口径变化

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
两次结果差距较小、随机初始化/采样显著，或评价口径可能随尝试变化。

## 协作策略
执行器：交接可比样本、随机种子、重复次数、原始指标及失败运行，不只报最好一次。大脑：根据实际波动与验证成本决定是否需要小规模重复或配对比较；声明什么差异足以改变下一步。资源紧张时允许暂记为趋势，不强行宣布新方案优越。

## 检验与边界
重复应按实验独立性解释，不能把同一输出重复评分当独立样本。不能用固定显著性阈值替代题目目标；不同数据集/评分版本的分数不直接相减归因。

## 依据与反例
这是统计比较的设计先验，未给任何赛题预设噪声分布、效应大小或胜率。
