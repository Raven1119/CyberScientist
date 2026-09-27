# AgentMaster 本地轨迹与历史分数配对（2026-09-28）

**校正此前结论**：CyberScientist 工作区与平台只读 API 中确实没有 75 条旧轨迹分对应的可下载轨迹；但 `../AgentMaster/store/T0/` 保存了其中 71 条实时提交的原始轨迹。此前“0 条可配对”不能推广到本机其他项目目录。本轮没有修改 AgentMaster、调用模型、创建 Job 或向平台写入。

使用既有、逐文件哈希核验的历史评分表作为分数来源（本机 `.package-checks/scorer-re-20260927T132218Z/dataset.jsonl`，SHA-256 `f4186803bb61838af62e67adb8021c112451a24c0f37c5f2ee441392f6e531fe`）。新脚本 `checks/match_agentmaster_traces.py` 只读扫描 AgentMaster 的 `submission/submission.json`，以**精确 Attempt ID**连接评分表，再逐条核对 `status=submitted`、提交命令的 `--challenge-id` 和 `--trace` 指向同一迭代的 `raw.upload.jsonl`。它对原始 Codex 事件、实际传入 CLI 的上传副本、本地主机投影轨迹分别记录路径、字节数、SHA-256 和结构计数；真实内容及逐 Attempt 对照表仅保存在本机忽略目录 `.package-checks/agentmaster-pairs-20260928/`。其中 `pairs.jsonl` 的 SHA-256 为 `71fa7fad213fc4855b039d3dee5436d70b5f5f1a7268fa0fce73234a9fe5ba9a`，`summary.json` 为 `463474755db98db2abecbc8f61069295c92aabbeab6a9dac88dc867d7680670d`。

| 公开题目 ID | 精确配对 | 最终轨迹分 | 最终分 <70 | 最终分 70–<80 | 最终分 ≥80 |
|---|---:|---:|---:|---:|---:|
| `biomaster-cnvkit-processed-segmentation-d6077a43` | 2 | 2 | 0 | 0 | 2 |
| `closed-resource-mp-r-reconstruction-open-eft-multi-22502ae6` | 25 | 18 | 3 | 0 | 15 |
| `denoise-a-frozen-pancreas-indrop1-single-cell-rna-e673f74c` | 11 | 11 | 3 | 0 | 8 |
| `flowforge-deep-bsde-pde-c8d415de` | 5 | 3 | 2 | 0 | 1 |
| `flowforge-paired-block-boundary-projection-v10-fe06025a` | 8 | 5 | 1 | 3 | 1 |
| `flowforge-periodic-regular-tetrahedra-packing-f45cec7b` | 16 | 15 | 5 | 0 | 10 |
| `flowforge-usct-ring-sound-speed-attenuation-v2-5c9021cd` | 4 | 4 | 3 | 0 | 1 |
| **合计** | **71** | **58** | **17** | **3** | **38** |

AgentMaster 当前可见 148 个有 Attempt ID 的本地提交记录；与 75 条历史轨迹分的交集是上述 71 条，且 71 条都通过命令、题目和轨迹路径三重核对。其余 4 条评分记录中，1 条是轮次外旧分项，3 条是另一实验邮箱提交，不属于这批 AgentMaster 实时轨迹。每条配对都保留了 `raw.jsonl`、`raw.upload.jsonl` 和 `traces/trace.jsonl`。`raw.upload.jsonl` 是提交命令的输入：65 条与原始 `raw.jsonl` 字节相同，6 条经本机敏感/传输事件过滤。71 份上传输入没有相同 SHA-256，不能靠同轨迹重复提交测评分噪声。

后续用 `checks/audit_agentmaster_grader_diagnostics.py --older-pairs` 复核提交时 `stdout.log` 的 `bundle_response.native_trace_sha256`，并重新哈希本地 `raw.upload.jsonl`：**71/71 与回执原生轨迹哈希一致**。因此这 71 份不仅有命令路径关联，也有上传回执的字节哈希支撑；平台在此之后如何解析或投影轨迹仍不可见。该复核与另 62 份未遮蔽回执的结果见[历史评分规律审计](HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md)。

本地 `grader/grader.json` 的轨迹分在 65 条上与评分快照完全相同，2 条不同，4 条没有本地轨迹分；因此以较晚取得的平台评分快照为分数真值，保留分歧供复核。13/71 条的 `score_is_final=false`，不能当作最终评分训练或评估；其余 58 条才是下一步建模的候选样本。全部 71 条上传输入为 18–245 行原始 Codex 事件，**不是**直接等同于平台归一化后的评分轨迹：官方 CLI 可能转换这些事件，而目前平台 `/trace` 对旧提交返回空数组、bundle 不可下载。只证明“哪个本地输入经哪个提交命令关联到哪个 Attempt 及其当前分数”，尚不能证明平台评分器最终采纳了哪些行，也不能宣称预测准确率。

下一步若评估 ≥70/≥80，先以 58 条最终分为候选，按题目和时间封存训练/留出分割；分别从上传副本和本地主机投影提特征，不把投影当成已证实的评分输入。两条本地与平台分不一致的记录和 13 条非最终分须单列。现有记录足以撤销“缺少任何历史配对输入”的阻塞，但还不足以发布经过验证的预测器或解释评分器权重。
