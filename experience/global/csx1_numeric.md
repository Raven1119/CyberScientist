---
id: csx1_numeric
title: 数值复现先定位误差结构再提高计算精度
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- numerical-reproduction
- aiyagari
- solver
applicability: 数值复现的结果与参考值不符，误差集中于部分参数或输出；单纯加密网格、收紧容差收益有限。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/checks/build_arm_bundle.py
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_numeric
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 数值复现先定位误差结构再提高计算精度

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
数值复现的结果与参考值不符，误差集中于部分参数或输出；单纯加密网格、收紧容差收益有限。

## 协作策略
执行器：按参数/输出整理绝对与相对误差，核对单位、定义和边界条件，并记录已做的精度检查。大脑：区分实现/定义错误、离散化、求解未收敛、参考解释差异，选择一个可辨别的对照。执行器自主构造守恒/残差/收敛或替代离散化诊断，交接预测与结果。不要在基础误差未定位时直接扩大所有计算。

## 检验与边界
新方法应同时检查目标偏差、残差或其他独立诊断。参考值接近零时不能仅依靠相对误差。方法适用性依赖方程、离散化及参数区域；某一格点改善不等于全区域有效。

## 依据与反例
Aiyagari 打包脚本记录了高风险厌恶部分格点偏差、精度调整及未完成的 Rouwenhorst 消融。本条没有将未完成的消融写为成功结论。
