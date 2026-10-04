---
id: csup08_artifact_paths
title: 答案路径与 ARM result_package.zip 交付约定
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
audience: both
tags:
- 答案
- 路径
- ARM
- 封包
applicability: 题面路径和评分器路径不一致、ARM 封包
evidence_refs:
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/sandbox_compile_rootfixed.sh#sha256=5c84ec1ddb27c6ba55653bf858903b083ac8b261be604e4c4afe295ddfcf0abe
---
先读取题面输出契约、artifact_facts 和本地 scorer.json 的 verified_input_paths。制作题面要求的路径，评分器需要另一布局时由求解者明确提供兼容路径；不要假定根目录与 outputs/ 可以互换。

科学答案放在实际交付目录。ARM 包命名 result_package.zip，真实轨迹用合法 step_type，artifact_path 指向包内真实文件。先调用 research_package_check，再对封存包调用本地评分接口；每次修包后重新封存／核对哈希。

v1/v3 FigQA 与 Lean 的路径、manifest 和 Lean --root 问题已有明确审计。通用约定不覆盖某道新题的具体输出合同；合同不一致时记录两边，并继续已授权的独立研究。

证据引用：
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/sandbox_compile_rootfixed.sh#sha256=5c84ec1ddb27c6ba55653bf858903b083ac8b261be604e4c4afe295ddfcf0abe
