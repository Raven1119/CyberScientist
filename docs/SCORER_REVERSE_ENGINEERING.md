# CS-UP-03R：本人历史评分逆向核查

本报告只用本人已有提交的评分回执与可取得的原始包；匿名公开提交仅用于分布对照。可重建脚本为 `checks/build_scorer_dataset.py`，逐条公式核查为 `checks/analyze_historical_scores.py`。原始回执、Attempt 标识、身份与包只保留在本机忽略目录。

## 科学评分：W3

71 条轮次内历史记录带 `harbor_score`、`trace_score`，分布在 7 道题。58 条同时有展示分，13 条展示分缺失且回执的 `scoreIsFinal=false`。任务卡提出的展示分公式

`harbor_score × clamp((trace_score − 30) / 40, 0, 1)`

在 58 条完整记录中，有 30 条仅与该公式吻合，18 条同时与该公式及 `harbor_score × clamp(trace_score / 100, 0, 1)` 吻合，另 10 条仅与后者吻合（绝对误差阈值 0.001）。只用任务卡公式的最大绝对误差为 20.758，平均绝对误差为 2.520；10 条不吻合记录均有最终分且 `overrideInEffect=false`。它们不能直接归因于覆盖或赛后复评。两种公式对全部 58 条都能事后解释，但回执没有已验证的公式选择字段，因而不能把按已知结果选公式当成预测器。轮次外那条历史双分项单独保留，不参与上述统计。

| 题目（公开标识） | 实时样本 | 展示分完整 | 可取回实时科学包 | 结论 | 本地验证误差 |
|---|---:|---:|---:|---|---|
| `biomaster-cnvkit-processed-segmentation-d6077a43` | 2 | 2 | 0 | 不可复刻 | 不可计算 |
| `closed-resource-mp-r-reconstruction-open-eft-multi-22502ae6` | 25 | 18 | 0 | 不可复刻 | 不可计算 |
| `denoise-a-frozen-pancreas-indrop1-single-cell-rna-e673f74c` | 11 | 11 | 0 | 不可复刻 | 不可计算 |
| `flowforge-deep-bsde-pde-c8d415de` | 5 | 3 | 0 | 不可复刻 | 不可计算 |
| `flowforge-paired-block-boundary-projection-v10-fe06025a` | 8 | 5 | 0 | 不可复刻 | 不可计算 |
| `flowforge-periodic-regular-tetrahedra-packing-f45cec7b` | 16 | 15 | 0 | 不可复刻 | 不可计算 |
| `flowforge-usct-ring-sound-speed-attenuation-v2-5c9021cd` | 4 | 4 | 0 | 不可复刻 | 不可计算 |

这 71 条旧提交没有一条可下载原始 bundle、轨迹或科学文件；另 3 条有包的记录使用赛后通用评分或仍待复核。仅凭总分无法推断输入字段、门槛顺序、容差或隐藏测试。因此没有为这 7 道题编造评分器，也没有可执行的留一验证；已有其他题目的本地评分器不算作本组历史验证。没有科学输入可交给沙箱，本轮未创建分析 Run 或付费沙箱。

## 轨迹评分：W4 预登记

以下假设在分析轨迹分与特征关系前登记；缺少实时组的轨迹内容时，预期结果可能是“无法判定”，不会用公开背景分数替代内容。

- H-T1 评判对象：分别比较 bundle 选中轨迹、创建表单行内 trace 和原始消息的特征与评分；任一对象不可取得则标为不可检验。
- H-T2 叙述质量：检查 setup、validation、computation、analysis、comparison 阶段覆盖，以及明确验证、错误后修复和失败恢复。
- H-T3 一致性：核对叙述中的输出与运行日志、结果和 characterization 的对应关系。
- H-T4 结构：比较步骤数分档和步骤类型多样性，先检查同包重复噪声再拟合。
- H-T5 元数据：模型与 harness 只作可观察关联，不把共同题目或时间造成的差异解释为因果效果。

预定评估是按题目分层的留一或留出测试，报告轨迹分绝对误差、≥70 与 ≥80 判定及所有误判；若无内容或同包重复，分别报告不可拟合与噪声未知。
