---
id: lc_materials_env
title: 材料与电子结构题的环境起点和交付路径
scope: global
status: candidate
evidence_status: observed
kind: procedure
audience: executor
tags:
- lightchaser
- materials
- environment
- DFT
- ABACUS
applicability: 材料、DFT、分子动力学、谱学、量子化学类题目开局搭环境时。
evidence_refs:
- cs-s4-analysis:data/environments.csv
source_type: design_assistant_s4_analysis
review_note: 设计助手代审批（用户 10-08 授权）；原 evidence_status=observed_public_data，规范化为 observed；只表示公开数据观察。
---
# 材料题的环境

S4 材料、电子结构类题目的头部提交，以 numpy/scipy 为主，常配合 ase、spglib、pymatgen、ovito、pyscf、numba；DFT 题使用 ABACUS（可从 conda-forge 安装）；较重的计算交给 Bohrium Job（lbg）。

**做法**：
- 先从环境目录中选起点：通用科学栈用 sci-py；量子化学用 pyscf；有材料镜像时选材料镜像。在此基础上安装缺的包，并做冒烟测试（例如 import 后建一个小晶胞、算一次小体系）。
- **ABACUS**：优先找已验证可用的镜像或 conda-forge 包，记录版本；输入文件（STRU、INPUT、KPT、赝势和轨道文件）的生成要在轨迹中可见。
- **输出路径**：题面要求写到 `/app/outputs/...` 一类固定路径时，严格使用该路径和文件名，评分会在容器中重放。
- 秒级的小计算可以在本地运行；超过分钟级的，放到 Job 或沙箱。
