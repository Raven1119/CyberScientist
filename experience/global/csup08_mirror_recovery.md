---
id: csup08_mirror_recovery
title: 403 与 pip 安装超时后换已授权来源
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
audience: both
tags:
- pip
- '403'
- 依赖
- 环境
applicability: 镜像源 403、依赖下载超时、缺少 wheel
evidence_refs:
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
---
记录原 URL、HTTP 状态和安装输出，随后立即换一条有额度的通道。先在沙箱验证依赖，再把成功环境用于 Job，避免每次重启科研程序都安装。

授权的远程环境中可尝试官方 PyPI 源：
```bash
python3 -m pip download --index-url https://pypi.org/simple --timeout 30 --retries 2 numpy -d /tmp/public-wheels
python3 -m pip install --no-index --find-links /tmp/public-wheels numpy
python3 -c 'import numpy; print(numpy.__version__)'
```
实际工作中把 numpy 换成题目要求的固定版本列表；保存 wheel SHA256、版本与冒烟输出。官方源同样不可达时，从已核验的公开依赖文件／已登记环境转运，保持哈希与版本。

v3 Matchgate Job 的 NumPy 镜像 403 与后续安装超时是真实失败；以上官方源替代是待验证配方，不能写成当时已经验证成功。未知原 Job 不重复创建；新操作使用新 ID 并受原额度约束。

证据引用：
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
