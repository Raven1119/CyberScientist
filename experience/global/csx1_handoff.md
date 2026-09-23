---
id: csx1_handoff
title: 大脑与执行器按决策需要交接证据
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- asymmetric-collaboration
- evidence-handoff
applicability: 大脑负责跨尝试路线，执行器掌握局部实施；出现路线分歧、关键状态变化或需要上层判断时。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/prompts/collaboration/executor.md
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/STATUS.md
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_handoff
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 大脑与执行器按决策需要交接证据

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
大脑负责跨尝试路线，执行器掌握局部实施；出现路线分歧、关键状态变化或需要上层判断时。

## 协作策略
大脑：给目标、成功判据、判断依据和改变路线的条件，不预排所有工具步骤。执行器：自主实施，交接当前结论、决定性证据引用、尚不确定之处与可恢复位置。认证、资源、任务或评分状态发生改变时及时写 checkpoint；常规进展用 none，可边做边讨论用 async，后续行动确实依赖裁决才用 blocking。收到指导后可接受或带证据质疑；收到指导不等于已经执行。

## 检验与边界
衡量旧状态误判、无效打断和缺证据往返是否减少。压缩不足以判断时明确请求缺失证据，不把未出现在摘要中的事实当作不存在。用户授权和暂停边界不可由经验扩大；阻塞通道失败也不能推定用户同意继续越界。

## 依据与反例
采用现有两角色和 checkpoint/guidance 接口。STATUS 记录过关键状态未到达大脑导致误判；具体传输或门禁故障仍须修程序。本条协作策略的收益尚未独立验证。
