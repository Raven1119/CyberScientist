---
id: csx1_atom
title: 原子模拟先通过构型与约定检查
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- atomistic-simulation
- defect
- lammps
applicability: 构建缺陷、界面或施加位移后，出现异常近邻、很大初始力、边界错误或结果对构造约定敏感。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_atom
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 原子模拟先通过构型与约定检查

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
构建缺陷、界面或施加位移后，出现异常近邻、很大初始力、边界错误或结果对构造约定敏感。

## 协作策略
执行器：对无缺陷、单项构造与组合构造分别检查原子数、边界、最近邻、初始力与序列化往返；报告单位、势函数和符号/坐标约定。大脑：判断异常源于几何/输入约定还是候选物理机制，再决定是否进入大规模弛豫或动力学。涉及分支切割或 Burgers 向量时按当前定义独立核对，不盲目沿用旧题符号。

## 检验与边界
阈值须依据当前晶体、势和任务设定，不复制旧题的最小间距或最大力。必要诊断仍在授权的计算环境中进行。构型检查通过不证明最终物理结论成立。

## 依据与反例
用户先前报告过坐标精度、branch-cut 对齐与 Burgers 符号的联合修复；该记录没有在本包重新运行。具体数值和“翻转符号”等处置未提升为通用规则。
