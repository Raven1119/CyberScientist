---
id: csx1_inverse
title: 反问题同时检查数据拟合与重建可信度
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- inverse-problem
- fwi
- muon
applicability: 存在潜在结构/参数和可观测数据，需要从观测反推模型；适用于波形、层析或边界重建任务的候选方法选择。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_inverse
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 反问题同时检查数据拟合与重建可信度

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
存在潜在结构/参数和可观测数据，需要从观测反推模型；适用于波形、层析或边界重建任务的候选方法选择。

## 协作策略
执行器：先验证正演接口、坐标/单位和一个已知可控案例；交接数据拟合、重建误差的可用代理、约束及计算成本。大脑：明确哪些结果仅说明拟合改善，哪些能支持结构恢复；在同一可比设置下选择要检验的正则化、参数化或初始化变化。观测不足以区分多个解时，交接不可辨识部分，不虚构唯一答案。

## 检验与边界
合成诊断只能验证受控场景，不能代替未知真实样本。保护留出数据；没有真值时报告可识别性与不确定性，不用训练残差替代结构正确性。实际评价项以该题题面为准。

## 依据与反例
这是面向反问题的实验设计先验。本包未重新读取 FWI/muon 的完整题面，不预置其评分公式、最优算法或获胜参数。
