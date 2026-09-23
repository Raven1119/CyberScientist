---
id: csx1_resource
title: 资源阻塞按可验证状态分类
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
tags:
- cyberscientist
- collaboration
- seed-v1
- platform
- resource-readiness
- authorization
applicability: 工具找不到、数据未就绪、认证失败、权限或硬件配额可能阻断科研路线时。
evidence_refs:
- docs/experience_kit_v1/PROVENANCE.md#design-prior
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/STATUS.md
source_type: design_prior
seed_pack: cyberscientist-experience-v1
seed_id: csx1_resource
derived_from: []
review_note: 冷启动设计先验，尚未在当前题目验证；全局版本需用户审批。
---
# 资源阻塞按可验证状态分类

证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。

## 适用情境
工具找不到、数据未就绪、认证失败、权限或硬件配额可能阻断科研路线时。

## 协作策略
执行器：分别检查官方资源入口、安装/调用方式、认证、权限与实际配额，交接具体响应、时间和下一项缺失信息，避免输出凭据。大脑：依据题面及当前证据判断真正阻塞；公开包管理器查无只能说明该入口未找到。已有进展必须更新，不能沿用先前失败印象。正式硬件或环境不可用时，区分诊断可继续与正式结果不合规。

## 检验与边界
某时刻某账号缺配额不意味着方法不可行或所有账号不可用。环境变化后允许重新探测；不自动建立账号、扩大配额、绕过规则或发起未授权作业。

## 依据与反例
STATUS 记录了工具来源误判、认证/数据就绪状态未传递及后来的配额阻塞。本条不把这些历史状态当作当前账户事实。
