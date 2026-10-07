# v6 确定性检查表与 63 份 v8 历史回执

## 预先固定的比较规则

以下规则在运行本轮逐项统计前记录，统计后不调整门槛。

- 主集是 63 份已按哈希找回原生轨迹的 v8 未遮蔽回执。V-CLI 与 V-CLI-fix 分别统计；原生直读只作解析诊断，不纳入一致率。
- 逐代码计算 TP、FP、FN、TN、精确率 TP/(TP+FP)、召回率 TP/(TP+FN) 及 v8 列出该代码的阳性数；分母为 0 时记 `unknown`，不当成 0 或 1。
- v6 某项为 `not_observable` 时不把它伪装为阴性；四格表只统计该项可观察的样本，并另列 `not_observable` 数。v8 独有或与 v6 同编号但不同全名的代码按**完整代码**区分，不能强行算作 v6 的阴性。
- **可靠**：v8 列出该代码的阳性数 ≥5，且精确率、召回率都 ≥0.9。**提示性**：阳性数 ≥3，且两项都 ≥0.7。其余为**不可用或未知**。只有可靠或提示性的检查项可以给执行器看；未知检查项最多进入前端详情。
- 解释 A：“回执未列出”当作未触发，列出项构成闭世界比较，按上述阈值给**条件分级**。解释 B：“回执未列出”视为不可观测；已列出阳性中的 TP/FN 可知，未列出的 FP/TN 不可确认。给出精确率与召回率在所有未列出项可任意隐藏触发时的最宽区间；这不把不确定状态硬算成真阴性。提示器只使用解释 A 达标的条件分级，明确标注其历史回执可见性限制；不能称为 v8 完整判定的可靠复刻。
- 上限比较只认本地 v6 函数给出的上限与 v8 实际轨迹分之间可观察的不等式；分数超过本地上限说明版本判法或输入不同，不能凭此证明其中一种具体原因。
- 转换、v6 与 v8 结果均需区分本地复算、历史平台回执和未知的服务端最终归一化输入。

## 逐项结果

<!-- BEGIN GENERATED AGREEMENT TABLES -->

本轮使用固定公开源码中的 `loadTrace`、`lintTrace`、`collectSubmissionEvidence` 和 `buildChecklistReport` 原函数。题面来自各次本地封存快照，产物目录先核对已有文件哈希；`runContext` 不可得时保留 `not_observable`，不伪造 worker 或裁判回执。

### V-CLI：原版转换

| 检查项完整代码 | v8 列出阳性 | 本地不可观察 | TP | FP | FN | TN | 精确率 | 召回率 | 条件分级 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| N00_TRACE_RECEIPT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N01_CROSS_TASK_TRACE_REUSE | 3 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N02_ARTIFACT_RECEIPT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N03_SYSTEM_CONTEXT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N04_TRACE_SCHEMA_INVALID | 2 | 0 | 2 | 0 | 0 | 61 | 1.000 | 1.000 | 不可用／未知 |
| N05_PROMPT_INJECTION_OR_SCORER_GAMING | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N06_FABRICATED_OR_UNSUPPORTED_EXECUTION | 4 | 0 | 4 | 0 | 0 | 59 | 1.000 | 1.000 | 提示性 |
| N07_REFERENCE_OR_ORACLE_LEAKAGE | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N08_UNPAIRED_TOOL_CALLS | 7 | 0 | 7 | 0 | 0 | 56 | 1.000 | 1.000 | 可靠 |
| N09_NO_EXECUTION_EVIDENCE | 12 | 0 | 12 | 0 | 0 | 51 | 1.000 | 1.000 | 可靠 |
| N10_TASK_TRACE_SEMANTIC_MISMATCH | 0 | 1 | 0 | 0 | 0 | 62 | 未知 | 未知 | 不可用／未知 |
| N11_OUTPUT_NOT_CAUSALLY_SUPPORTED | 19 | 0 | 19 | 2 | 0 | 42 | 0.905 | 1.000 | 可靠 |
| N12_TRACE_REPETITION_OR_INFLATION | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N13_EXTREME_BREVITY | 2 | 0 | 2 | 0 | 0 | 61 | 1.000 | 1.000 | 不可用／未知 |
| N14_METHOD_SUBSTITUTION_OR_FALLBACK | 8 | 0 | 8 | 1 | 0 | 54 | 0.889 | 1.000 | 提示性 |
| N15_PROVENANCE_METADATA_ANOMALY | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N16_DUPLICATE_OR_BURST_SUBMISSION | 2 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N16_EXTERNAL_SOLUTION_DISTILLATION | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |

可观察代码-样本对 818，闭世界不一致 3；v8 独有代码：N18_PROCESS_EVIDENCE_INSUFFICIENT。

### V-CLI-fix：修复版转换

| 检查项完整代码 | v8 列出阳性 | 本地不可观察 | TP | FP | FN | TN | 精确率 | 召回率 | 条件分级 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| N00_TRACE_RECEIPT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N01_CROSS_TASK_TRACE_REUSE | 3 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N02_ARTIFACT_RECEIPT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N03_SYSTEM_CONTEXT_MISMATCH | 0 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N04_TRACE_SCHEMA_INVALID | 2 | 0 | 0 | 0 | 2 | 61 | 未知 | 0.000 | 不可用／未知 |
| N05_PROMPT_INJECTION_OR_SCORER_GAMING | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N06_FABRICATED_OR_UNSUPPORTED_EXECUTION | 4 | 0 | 4 | 0 | 0 | 59 | 1.000 | 1.000 | 提示性 |
| N07_REFERENCE_OR_ORACLE_LEAKAGE | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N08_UNPAIRED_TOOL_CALLS | 7 | 0 | 7 | 1 | 0 | 55 | 0.875 | 1.000 | 提示性 |
| N09_NO_EXECUTION_EVIDENCE | 12 | 0 | 11 | 0 | 1 | 51 | 1.000 | 0.917 | 可靠 |
| N10_TASK_TRACE_SEMANTIC_MISMATCH | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N11_OUTPUT_NOT_CAUSALLY_SUPPORTED | 19 | 0 | 18 | 2 | 1 | 42 | 0.900 | 0.947 | 可靠 |
| N12_TRACE_REPETITION_OR_INFLATION | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N13_EXTREME_BREVITY | 2 | 0 | 0 | 0 | 2 | 61 | 未知 | 0.000 | 不可用／未知 |
| N14_METHOD_SUBSTITUTION_OR_FALLBACK | 8 | 0 | 8 | 1 | 0 | 54 | 0.889 | 1.000 | 提示性 |
| N15_PROVENANCE_METADATA_ANOMALY | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |
| N16_DUPLICATE_OR_BURST_SUBMISSION | 2 | 63 | 0 | 0 | 0 | 0 | 未知 | 未知 | 不可用／未知 |
| N16_EXTERNAL_SOLUTION_DISTILLATION | 0 | 0 | 0 | 0 | 0 | 63 | 未知 | 未知 | 不可用／未知 |

可观察代码-样本对 819，闭世界不一致 10；v8 独有代码：N18_PROCESS_EVIDENCE_INSUFFICIENT。

### 回执未列出的开放世界解释

下表将所有未列出的 v8 项视为可能被隐藏，仅列 v8 有阳性的代码。已列出阳性的命中／遗漏可知；未列出部分的 FP/TN 不可确认，因此给最宽的精确率、召回率区间。区间很宽时，闭世界条件分级不能当作已证明的完整 v8 触发规则。

| 转换 | 代码 | 精确率可行区间 | 召回率可行区间 |
|---|---|---|---|
| cli | N01_CROSS_TASK_TRACE_REUSE | 未知–未知 | 未知–未知 |
| cli | N04_TRACE_SCHEMA_INVALID | 1.000–1.000 | 0.032–1.000 |
| cli | N06_FABRICATED_OR_UNSUPPORTED_EXECUTION | 1.000–1.000 | 0.063–1.000 |
| cli | N08_UNPAIRED_TOOL_CALLS | 1.000–1.000 | 0.111–1.000 |
| cli | N09_NO_EXECUTION_EVIDENCE | 1.000–1.000 | 0.190–1.000 |
| cli | N11_OUTPUT_NOT_CAUSALLY_SUPPORTED | 0.905–1.000 | 0.311–1.000 |
| cli | N13_EXTREME_BREVITY | 1.000–1.000 | 0.032–1.000 |
| cli | N14_METHOD_SUBSTITUTION_OR_FALLBACK | 0.889–1.000 | 0.129–1.000 |
| cli | N16_DUPLICATE_OR_BURST_SUBMISSION | 未知–未知 | 未知–未知 |
| fix | N01_CROSS_TASK_TRACE_REUSE | 未知–未知 | 未知–未知 |
| fix | N04_TRACE_SCHEMA_INVALID | 未知–未知 | 0.000–0.000 |
| fix | N06_FABRICATED_OR_UNSUPPORTED_EXECUTION | 1.000–1.000 | 0.063–1.000 |
| fix | N08_UNPAIRED_TOOL_CALLS | 0.875–1.000 | 0.113–1.000 |
| fix | N09_NO_EXECUTION_EVIDENCE | 1.000–1.000 | 0.175–0.917 |
| fix | N11_OUTPUT_NOT_CAUSALLY_SUPPORTED | 0.900–1.000 | 0.295–0.952 |
| fix | N13_EXTREME_BREVITY | 未知–未知 | 0.000–0.000 |
| fix | N14_METHOD_SUBSTITUTION_OR_FALLBACK | 0.889–1.000 | 0.129–1.000 |
| fix | N16_DUPLICATE_OR_BURST_SUBMISSION | 未知–未知 | 未知–未知 |

### 上限不等式与转换影响

| 集合／转换 | 样本数 | v6 上限低于历史 v8 轨迹分 | 违反上限的分布 |
|---|---:|---:|---|
| 主集 cli | 63 | 0 | 无 |
| 辅助集 cli | 71 | 0 | 按本地上限 {}；按历史分段 {}；最终分样本 0 |
| 主集 fix | 63 | 0 | 无 |
| 辅助集 fix | 71 | 0 | 按本地上限 {}；按历史分段 {}；最终分样本 0 |

主集闭世界不一致从 V-CLI 的 **3** 增至 V-CLI-fix 的 **10**。两组均未发现上限不等式违例；这只说明这批实际分数没有超过本地上限，不证明 v8 用了同一上限。逐样本的违例清单当前为空。

### N18：v8 独有的过程证据项

| 脱敏样本 | v8 轨迹分 | v8 判定 | 修复版 v6 事件 | 工具调用／结果 | 修复版 v6 其他触发项 |
|---|---:|---|---:|---:|---|
| S10 | 2.25 | block | 65 | 52／25 | N08_UNPAIRED_TOOL_CALLS, N09_NO_EXECUTION_EVIDENCE, N11_OUTPUT_NOT_CAUSALLY_SUPPORTED |
| S30 | 5.8 | block | 27 | 20／10 | 无 |
| S48 | 29.0 | block | 12 | 8／4 | N09_NO_EXECUTION_EVIDENCE |
| S60 | 69.0 | review | 7 | 4／2 | 无 |

V-native 直接输入公开 v6 时，63/63 份均被判 N04；工具调用解析总数 0。这组不用于和 v8 做一致率统计。
<!-- END GENERATED AGREEMENT TABLES -->

## 解释、差异来源与适用边界

公开 v6 的确定性检查与 v8 回执在**可见代码**上高度一致，但这是一个有条件的观察：`runContext` 中的 worker 签名、跨题复用登记及完整性回执不可取得，N00–N03 和 v8 的 N01 无法可靠复算；v8 未列出的项也不一定真的未触发。表中“可靠”是按任务卡门槛对**回执可见标签**的条件分级，不是平台当前版本的保证，更不是轨迹最终分数预测器。尤其 N04/N13 在原版各有 2 个正例且 2/2 命中，仍因正例不足而不可用；不能挑几个高命中小样本上线。

转换修复带来的额外 7 处闭世界差异集中在 S10、S30：两条都有顶层 error 混入 Codex 原生流，原 CLI 因格式误判几乎只留下 error。修复后 v6 不再触发历史 v8 列出的 N04 与 N13；S30 还不再触发历史的 N09/N11，S10 新出现 N08。**修复后更偏离这批历史回执**，这与当时 v8 可能看到丢失后的轨迹相容，但没有取得服务端最终归一化输入，不能据此认定唯一原因或推断修复会降低未来评分。S30 即 E008 的原版 v6 是 0 分检查表、20 分上限、`block`；修复版是 100 分检查表、100 分上限，确定性判定 `insufficient_evidence`，并不预测它本来会得 100 分。

S15 的 N11 与 N14、S45 的 N11 是两种转换下都存在的本地触发而 v8 回执未列出的项。可能是 v6/v8 对文件内容关联或替代方法的判断不同，也可能是 v8 触发后没有列出；仅有可见回执无法区分。N08 修复版只有 S10 多一项，同样不能排除 v8 显示策略。N16 的 `DUPLICATE_OR_BURST_SUBMISSION` 与 `EXTERNAL_SOLUTION_DISTILLATION` 虽同编号但全名不同，已严格分开；前者所需提交时间/历史登记缺失，不能从编号相同臆造一致性。

4 条 N18 样本的历史轨迹分跨度为 2.25–69，判定为 3 条 block、1 条 review。修复版 v6 均解析到至少 2 个工具结果，但可见事件数、其他负项和转换经历不同：S10/S30 原版遭遇 error 误判，S48 有 N09，S60 没有其他负项。共同的只是 v8 在回执中列出了 N18，并非可推导的次数阈值；本地诊断器不会实现或宣称复刻 N18。

在固定输入与本地上限下，主集两种转换和辅助集两种转换都没有一条“历史轨迹分超过 v6 上限”。这些 0 次违反不等于 v8 完全采用 v6 上限：如果实际分数受其他更低因素制约，未被违反的上限不可识别。辅助集 71 条只有分项分数、没有逐项代码或判定，不进入上面的逐项混淆表；其中非最终分也不能当成已确定的完整评分回执。

提交前提示只使用**修复版**中条件分级达标的 N06（提示性）、N08（提示性）、N09（可靠）、N11（可靠）、N14（提示性）。具体建议只能要求补做真实工作或补全命令、输入、返回值、产物之间的真实来源链；不能教人调整措辞来迎合检查器。其他项目只保留为前端详情中的未知/不可用诊断。v6 直接读取 63 份 Codex 原生轨迹全部错判 N04、识别工具调用数为 0，因此生产诊断必须先走固定转换。

离线复核顺序：先运行 `checks/build_trace_conversion_variants.py`，再运行 `checks/prepare_trace_checklist_inputs.py` 形成 331 个带真实题面与产物的输入；`checks/run_trace_checklist_v6.mjs` 只从锁定 SHA 的公开源码导出确定性函数，随后 `checks/analyze_trace_checklist_agreement.py` 生成本节两组逐项表和私有统计 JSON。主集 63 条的 v8 回执 SHA 与原因码、分数和判定在输入准备阶段重新核对；辅助集配对索引 SHA 也锁定。完整原始轨迹、回执、转换文件、私有统计和源码克隆只留 `.package-checks/cs-up-04/` 及原有本机目录；仓库报告只用 S/A 脱敏序号。

## CS-UP-11 expanded public snapshot

Generated 2026-10-07T15:52:22.140959+00:00. Current available v8 comparison: 521 of 7616 selected attempts / 9410 code pairs; 3114 unavailable pairs within that comparison. All selected IDs, including empty, uncollected, failed and non-v8 inputs, remain in private `scorer/v6_v8_coverage.csv`. This section is regenerated as trace collection advances. Original 63-sample evidence above remains unchanged.

| Full code | Observable positives | TP | FP | FN | TN | Precision | Recall | Conditional grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| N00_TRACE_RECEIPT_MISMATCH | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N01_CROSS_TASK_TRACE_REUSE | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N02_ARTIFACT_RECEIPT_MISMATCH | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N03_SYSTEM_CONTEXT_MISMATCH | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N04_TRACE_SCHEMA_INVALID | 6 | 0 | 16 | 6 | 499 | 0.000 | 0.000 | unknown_or_unusable |
| N05_PROMPT_INJECTION_OR_SCORER_GAMING | 3 | 0 | 0 | 3 | 518 | unknown | 0.000 | unknown_or_unusable |
| N06_FABRICATED_OR_UNSUPPORTED_EXECUTION | 34 | 32 | 234 | 2 | 253 | 0.120 | 0.941 | unknown_or_unusable |
| N07_REFERENCE_OR_ORACLE_LEAKAGE | 1 | 1 | 0 | 0 | 520 | 1.000 | 1.000 | unknown_or_unusable |
| N08_UNPAIRED_TOOL_CALLS | 33 | 3 | 3 | 30 | 485 | 0.500 | 0.091 | unknown_or_unusable |
| N09_NO_EXECUTION_EVIDENCE | 54 | 53 | 379 | 1 | 88 | 0.123 | 0.981 | unknown_or_unusable |
| N10_TASK_TRACE_SEMANTIC_MISMATCH | 0 | 0 | 0 | 0 | 500 | unknown | unknown | unknown_or_unusable |
| N11_OUTPUT_NOT_CAUSALLY_SUPPORTED | 42 | 35 | 9 | 7 | 14 | 0.795 | 0.833 | indicative |
| N12_TRACE_REPETITION_OR_INFLATION | 3 | 3 | 192 | 0 | 326 | 0.015 | 1.000 | unknown_or_unusable |
| N13_EXTREME_BREVITY | 11 | 6 | 39 | 5 | 471 | 0.133 | 0.545 | unknown_or_unusable |
| N14_METHOD_SUBSTITUTION_OR_FALLBACK | 106 | 26 | 7 | 80 | 408 | 0.788 | 0.245 | unknown_or_unusable |
| N15_PROVENANCE_METADATA_ANOMALY | 1 | 1 | 3 | 0 | 517 | 0.250 | 1.000 | unknown_or_unusable |
| N16_DUPLICATE_OR_BURST_SUBMISSION | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N16_EXTERNAL_SOLUTION_DISTILLATION | 10 | 1 | 0 | 9 | 511 | 1.000 | 0.100 | unknown_or_unusable |
| N17_PREEXISTING_SUBSTANTIVE_ARTIFACT | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |
| N18_PROCESS_EVIDENCE_INSUFFICIENT | 0 | 0 | 0 | 0 | 0 | unknown | unknown | unknown_or_unusable |

314 observed scores exceed the locally reconstructed v6 cap. This does not identify the cause: version, public-field omissions, redaction and worker input differences remain confounded. N17 and N18 have no pinned v6 rule and remain unknown for mechanical reproduction. Open-world precision/recall bounds and every attempt ID are retained in private scorer tables. Public missing tool fields cannot establish that original execution evidence was absent.
