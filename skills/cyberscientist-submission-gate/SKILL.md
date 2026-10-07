---
name: cyberscientist-submission-gate
description: Pre-submission checklist for the trace gate, packaging and submission spacing; read before any experiment or harvest submission decision.
metadata:
  audience: both
---

# 提交前检查

## 一、轨迹门（任一不满足，先补证据）

1. 每个提交文件，都能在轨迹中找到生成它的命令和输出（N11）。
2. 最终结果来自题目要求的方法（N14）。
3. 题目特定代码在轨迹中可见地创建（N17/N18/N16 蒸馏）。
4. 工具调用都有结果；关键数字已打印（N08/N09/N06）。
5. 有一次独立验证的输出。
6. 关键证据在每个事件的开头；没有重复堆砌（N12）；时间真实（N15）。
7. 本地 v8 确定性检查没有报出可靠的扣分码；本地复刻裁判的结果只作提示。

## 二、提交包

- 文件名、路径、格式与题面要求逐一对照，题面说写到 `/app/outputs/...` 就严格使用。
- 先用平台公开 schema 做结构预检（manifest、characterization、handoff 等）。彩排中出现过两类拒收：
  - `handoff.status=complete` 不被接受；
  - characterization 缺少 modality。

  这类拒收会让草稿进入 bundle_blocked 状态，要在提交前就排除。
- 方法说明（README）要写全：问题、方法（点明题目要求的方法）、关键公式、验证、结果、局限。

## 三、节奏与间隔

- 同一账号同一题，两次提交间隔至少 30 分钟（≤2 分钟触发突发惩罚的概率是 54%，30 分钟以上约 5%）；每题每账号尽量不超过 3–4 次。系统也会强制执行。
- 一个账号在多道题上的提交要错开，不要在 30 分钟内集中提交 5 次以上。
- 只在有实质改进时提交：科学分提高，或轨迹证据明显补强。
- 科学分高但判为 review/block 时：读扣分码和缺失证据，冻结科学结果，按干净复跑的做法重做一条证据充分的轨迹，再间隔提交。不要原包重交。
- 回执中的 `missing_worker_submission` 或 `nonstandard-submission-guard` 是提交链路问题，立即报告，不要在轨迹上找原因。
