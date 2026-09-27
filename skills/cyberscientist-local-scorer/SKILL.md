---
name: cyberscientist-local-scorer
description: Build and calibrate a challenge-specific local science scorer against an explicit rubric and confirmed platform feedback.
metadata:
  audience: both
---

# 本地科学评分器

从题面、公开评分协议和已确认的提交回执提取可复刻的计分条件。将可直接验证的条件写成确定性检查；隐藏参考值或不可观测门槛保持未知，给出低置信度或分数区间，不用一次反馈推断通用规则。不得通过构造提交索取隐藏答案或测试数据。

将评分器放在 `workspace/challenges/<challenge_id>/scorer/`，用 `scorer.json` 声明 Python 入口、题目镜像、人工版本和契约版本。入口接收从封存 ARM 包提取的科学输入 ZIP：轨迹成员已剔除，manifest 的 trace 指针已移除。只输出一个 JSON 对象：`score`（0–100）、`components`、`confidence`、`notes`、`scorer_version`；最后一项使用运行时提供的 `CS_SCORER_VERSION`。不要从主机执行科学计算；通过当前 Run 授权的 Bohrium 沙箱网关，在声明镜像中运行。评分器文件及镜像声明的任何变化都要产生新版本。

提交前对当前产物做本地评分，把评分器版本、封存包哈希和分项写入账本；每次实验提交写下可证伪的分数变化预测。平台分数只有在 `confirmed` 后才作为校准目标。对齐同一封存包哈希，分别看科学分、轨迹分和展示分；分数或回执修订时更新校准状态，不悄悄覆盖旧预测。将不一致归因于具体尚未复刻的规则，而非伪造更高本地分。
