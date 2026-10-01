---
name: cyberscientist-local-scorer
description: Build and calibrate a challenge-specific local science scorer against an explicit rubric and confirmed platform feedback.
metadata:
  audience: both
---

# 本地科学评分器

从题面、公开评分协议和已确认的提交回执提取可复刻的计分条件。将可直接验证的条件写成确定性检查；隐藏参考值或不可观测门槛保持未知，给出低置信度或分数区间，不用一次反馈推断通用规则。不得通过构造提交索取隐藏答案或测试数据。

先核对每条样本在提交时的轮次、评分策略、原始科学文件和分项回执。只有同一评分方式下可配对的输入与科学分，才用于推断字段、门槛或容差；仅有总分时记录“不可复刻”。主办方告知的 30–70 轨迹因子规则是外部规则，不是从历史分数推断的。CS-UP-03R 的 71 条历史实时分项记录没有可取回科学包或轨迹；10 条完整展示分与告知规则冲突，另一个分段计算虽能在样本内解释它们，平台未确认其适用性，见 `docs/SCORER_REVERSE_ENGINEERING.md`。不要把这些分数当作产物评分器的验收样本。

将评分器放在 `workspace/challenges/<challenge_id>/scorer/`，用 `scorer.json` 声明 Python 入口、题目镜像、人工版本和契约版本。入口接收从封存 ARM 包提取的科学输入 ZIP：轨迹成员已剔除，manifest 的 trace 指针已移除。只输出一个 JSON 对象：`score`（0–100）、`components`、`confidence`、`notes`、`scorer_version`；最后一项使用运行时提供的 `CS_SCORER_VERSION`。不要从主机执行科学计算；通过当前 Run 授权的 Bohrium 沙箱网关，在声明镜像中运行。评分器文件及镜像声明的任何变化都要产生新版本。

提交前对当前产物做本地评分，把评分器版本、封存包哈希和分项写入账本；每次实验提交写下可证伪的分数变化预测。平台分数只有在 `confirmed` 后才作为校准目标。对齐同一封存包哈希，分别看科学分、轨迹分和展示分；分数或回执修订时更新校准状态，不悄悄覆盖旧预测。将不一致归因于具体尚未复刻的规则，而非伪造更高本地分。

子项候选只有经 `research_local_score` 评分并登记后，才进入本 Run 的正式候选记录；独立实验日志中的自报数值不会自动登记。评分器的 `components` 中，嵌套子项用 `score`、`points` 或 `*_score` 表示分数，其余字段为诊断。系统按 Run、评分器哈希和完整科学输入哈希复用评分；finish 会比较实际最终包与已登记的子项最佳成绩。退步时由大脑修正，或用反馈中的 `confirmation_token` 在 finish 动作的 `finish_confirmation` 中提供 token 和 reason_md，明确保留当前包；系统不替换产物。
