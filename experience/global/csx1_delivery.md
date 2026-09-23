---
id: csx1_delivery
title: 交付物、提交回执与科研结论分别验收
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- reproducibility
- submission
- artifact
applicability: 准备提交科研结果，或根据平台反馈决定下一次尝试时。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailbox_platform.py
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_delivery
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 交付物、提交回执与科研结论分别验收

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
准备提交科研结果，或根据平台反馈决定下一次尝试时。

## 协作策略
执行器：提供可复现入口、环境、输入/输出、实际日志和产物哈希；说明已验证与未验证项。大脑：依次判断科学证据是否支持结论、交付物是否满足题目契约、平台是否已完成提交和评分。交接中绑定本次代码、结果包、Trial 和平台引用；未知回执先对账原提交，不凭异常自行重提。

## 检验与边界
不要把 HTTP 成功、上传完成或提交被受理写成评分完成。重提同一包不能算独立科学复现。程序没有保存真实回执时标 unknown，不编造证据链。

## 依据与反例
基于现有多阶段提交适配器及审计 B12/B16/B17。相关程序缺陷仍需按 BUG_FIXES.md 修复；本条不提供规避比赛额度的方法。
