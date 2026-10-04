---
id: csup08_verified_local_grade
title: 提交前先用固定本地评分器核验同一包
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
audience: both
tags:
- 评分器
- 验证
- Job
- 沙箱
applicability: 题目已登记本地评分器、提交前科学验收
evidence_refs:
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
---
已登记固定评分器时，先做 package_check，再通过 research_local_score evaluate，或 prepare→受控 sandbox.exec→register；Job 通道使用 prepare_job→research_job→register_job。评分器对求解者可读，用于快速迭代；本机不跑科学评分。

正式分必须来自后端核对的固定输入哈希、精确命令、成功退出码、单 JSON 与同次环境身份。求解者自报的数值、Job stdout 中随意打印的数字不是正式分。检查完整封存包和已登记科学最佳分的关系，再决定提交；修改任何科学文件后重新核验。

失败／unknown 要如实记录，换已授权通道继续，不将科学成绩填零。平台分、轨迹诊断与本地科学分分别报告。本配方不授权新提交，提交仍受用户次数、题目截止和账户授权约束。

证据引用：
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
