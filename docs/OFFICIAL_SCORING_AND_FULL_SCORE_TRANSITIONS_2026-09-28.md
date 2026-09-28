# 官网评分契约与历史满分前的轨迹对照（2026-09-28）

本报告只读官网公开 API 与既有 AgentMaster 封存提交；没有创建 Run、模型调用、Job、Attempt 或新评分。官网原始响应和 SHA-256 留在本机忽略目录 `.package-checks/official-scoring-20260928/`，逐 Attempt 轨迹、包与回执索引留在 `.package-checks/agentmaster-grader-diagnostics-20260928/`、`.package-checks/agentmaster-pairs-20260928/`、`.package-checks/full-score-case-20260928/`。公开报告不列账号、Attempt ID、原生轨迹正文或原始包。

后续已发现公开 v6 评分源码，并复现 FigQA E008 的转换丢失与 E010 的 N09 上限；历史回执为 v8，仍有版本差异。公式和具体证据见[评分器源码逆向](TRACE_SCORER_SOURCE_REVERSE_ENGINEERING_2026-09-28.md)。本报告保留官网契约与历史成绩对照，不能以它代替新发现的源码证据。

## 先区分三条评分路径

[官网入门文档](https://play.bohrium.com/api/docs/getting-started)说，题目详情的 `scoring` 块给出 `strategy`、`formula_summary` 和适用指标；可见的策略有 `programmatic_grader`、`llm_judge_topic_markdown`、`arm_v1_1_generic`、`human_review_only`。同一文档特别说明：**整个赛季可以交给外部评分 worker，此时平台自己的评分停止**。因此当前题目元数据不能自动代表历史轮次当时运行的评分器。

同一入门文档还描述带目标图的题目会逐图比较：有论文数值误差时，数值部分占 85%、视觉相似度占 15%；图的匹配档位为 ≥85% `Match`、≥60% `Partial`、其余 `Mismatch`。这是该文档所述的**图像比较路径**，不是上述第四季历史双分项的通用合成公式，也不能套到无图的 Lean/JSON 题。

[官网 ARM 文档](https://play.bohrium.com/api/docs/arm-bundles)与[当前协议 v1.1](https://play.bohrium.com/api/protocol)对通用 ARM 路径给出以下可核实定义：

| 维度或关口 | 官网当前公开定义 | 可推出的边界 |
|---|---|---|
| `packaging` | 包结构完整度 | 文件存在不是科学结果正确。 |
| `executability` | 有 Dockerfile 为 1.0，仅有 requirements 为 0.5；协议标为计算维度 | 这是结构性信号，文档没有说 `Dockerfile=1` 等于镜像已成功构建、入口已真实执行。 |
| `output_coverage` | `characterization.deviations.target` 命中 `expected_outputs.name` 的比例 | 数目标被覆盖，不是逐目标精度。 |
| `result_fidelity` | `deviations.score` 简单平均；SSIM 项贡献上限 0.3 | 数值误差、物理一致性等应看题目契约；不能以图像相似度冒充数值复现。 |
| `trace_quality` | 提取后的轨迹 0 步→0、1–4 步→0.5、≥5 步→1；提取前可能仅按轨迹文件有无给值 | 与历史 0–100 `trace_score` 不同；不能据此推断过程真实或科学正确。 |
| `environment_reproducibility` | 在 scorecard 结构中，但当前协议明说服务端不计算 | 字段存在不代表已验证环境可复现。 |
| ARM 模态覆盖 | 7 种模态；官网文档称覆盖率占**通用 ARM 总分的 30%** | 只适用于该通用路径，不能套到专属赛题评分。 |
| 轨迹准入 | `log_anchor`、`artifact_path`、成对工具调用、费用、时间线、内容实质六信号中满足至少一项；不可完整读取为 `indeterminate` | 准入与 `trace_quality` 计分分离；通过关口不是诚实性证明。 |

官网文档进一步写明：有 `programmatic_grader` 的竞赛题可由专属评分器读提交指标，**即使没有 ARM 执行、表征或轨迹模态仍可能取得科学分**。本次[Lean 题当前详情](https://play.bohrium.com/api/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a)正暴露历史解释风险：题面仍列出 Lean 三定理 40＋30＋20、物理匹配 4＋3＋3 的精确规则，并说验算器只读 `Problem.lean` 与 `PHYSICS_MATCH.json`；但当前 `scoring.strategy` 却是 `arm_v1_1_generic`、`grader_name=null`，`formula_summary` 说无专属 grader。这两个当前可见字段不能同时证明旧轮次按哪条路径评分；历史回执的科学分和轨迹判定才是当时评分的证据。

[官网读轨迹指南](https://play.bohrium.com/api/docs/reading-a-trace)建议沿 setup、validation、computation、analysis、comparison 查决策、验证和失败修复；它是阅读与学习指南，**没有给这些阶段公布计分权重**。

历史 63 份未遮蔽回执来自 `trace-score-cli/0.3.0-beta.1+evidence-checklist-v8-process-evidence-sufficiency`，直接记录：`accept` 时 `trace_factor=1`，`review` 时为 `trace_score/100`，`block` 时为 0；各份展示分均为 `harbor_score × trace_factor`。26 份 accept 的轨迹分范围 74.175–98.25，20 份 review 为 32.125–69，17 份 block 为 0–29。另一组 58 份最终旧回执的展示分与这个暂定分段吻合，但没有判定类别；样本在 29–32.125 和 69–74.175 之间留空，**不能由数据证明精确阈值**。主办方告知、由用户转述的 30–70 线性因子规则与其中 10 条低分最终回执冲突，原因未知。详细核验见[历史评分规律审计](HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md)与[历史逆向核查](SCORER_REVERSE_ENGINEERING.md)。

## 同题初期非满分 → 最终满分

只在同一题内比较**最终已评分提交**，用科学分、轨迹分和展示分分开解释；不把某次提交的早期缓存当另一份研究轨迹。以下 `E` 为 AgentMaster `iterations/` 编号，公开不列 Attempt ID。每份对照都可由本机逐 Attempt 索引连接提交命令、平台接收包、输出快照、原生轨迹哈希与评分回执；错包及非最终快照另标记。

| 题目与阶段 | 科学分 | 轨迹分 / 判定 | 展示分 | 可核实的主要变化 |
|---|---:|---|---:|---|
| Paired-block Lean E000 | 0 | 59；旧组未返回判定 | 0 | `Problem.lean` 有 1 处 `sorry`；物理匹配文件通过格式验证，但云端 Lean 工具链没有可用编译成功回执。 |
| Lean E002 | 0 | 82.75；判定不可见 | 0 | 已无文本 `sorry/admit/axiom`，物理匹配仍在；云端编译链仍未取得通过回执。**轨迹分高于后来的满分提交，科学分仍是 0。** |
| Lean E005 | 0 | 78.025；判定不可见 | 0 | Bohrium 沙箱产生真实编译诊断，候选仍有 Lean 错误；封存输出中也没有可计分的物理匹配文件。 |
| Lean E009 | 100 | 75.925；由展示分推得处于不折减区，旧组无类别字段 | 100 | 轨迹记录固定工具链下三项定理编译成功、最终文件哈希和物理匹配 PASS；封存两份输出。该提交早期本地 grader 曾暂记 0／轨迹 59，较晚平台最终快照及本轮官方只读查分均为 100；缓存变化不能算另一份轨迹。 |
| FigQA-0177 E001 | 0 | 32.125 / review | 0 | 提交 `[ANSWER]C[/ANSWER]`；同题后续正确答案为 B。 |
| FigQA-0177 E002 | 100 | 59 / review | 59 | 答案已为 `[ANSWER]B[/ANSWER]`，但原生轨迹仅有 18 个上传事件；正确答案没有使总分满分。 |
| FigQA-0177 E010 | 100 | 49 / review | 49 | 同一答案 B；94 个上传事件、36 个完成命令，仍收到 `N09_NO_EXECUTION_EVIDENCE`。事件/成功命令数量不足以解释过程证据质量。 |
| FigQA-0177 E011 | 100 | 96.375 / accept | 100 | 同一答案 B；上传轨迹记录源代码审阅、像素分析失败后的修正、接受运行、独立重放、答案映射及字节一致性检查；输出还包含复现包。源文件和包内容也同时改变，不能给某一项动作单独归因。 |
| FigQA-0178 E000 | 100 | 1.75 / block | 0 | 输出已是最终相同的 F，但原生轨迹与另一题逐字复用；回执列 `N01`、`N06`、`N09`、`N16`，不能把这条当作独立研究质量对照。 |
| FigQA-0178 E001、E002 | 各 100 | 各 29 / block | 各 0 | 答案仍为 F。E001 声称看图并运行写答案脚本，回执列 `N11_OUTPUT_NOT_CAUSALLY_SUPPORTED`；E002 记录解码依赖失败和替代查看，回执没有列详细低分原因。 |
| FigQA-0178 E003 | 100 | 86 / accept | 100 | 答案仍为 F；原生轨迹包含图像查看声明、Java 解码裁剪、分组近似值比较、答案写入与读回，27 个事件。历史回执仍指出图像查看和柱图数值提取缺成对工具回执，所以满分不等于完整可审计。 |

另外两道最终满分题**没有现存的早期非满分提交**：CNVkit 三次提交的科学分和展示分均为 100；4×4 PPT channel 仅找到一次已评分提交，亦为 100。PPT 的这一次轨迹内部有 Job 创建被拒、云端断言失败、修复后成功取回的路径，可分析失败恢复，但不能构造“前次低分提交→后次满分提交”。CNVkit A/B 的数值结果基本一致，轨迹分 94.325/98.75，均在接受区；不是跨科学分的对照。八次历史满分的逐案边界见[满分提交审计](FULL_SCORE_ATTEMPT_CASE_AUDIT_2026-09-28.md)。

## 能归纳什么，不能归纳什么

1. 在这些**历史赛题回执**中，满分至少要有 `harbor_score=100` 且轨迹不折减；八次满分轨迹分实际为 75.925–98.75，没有一次轨迹分达到 100。反过来，高轨迹分不会弥补错误或未通过验算的科学产物，Lean E002 是同题直接反例。
2. “可执行性”应拆成三个可观察事实：**包结构足够让通用 ARM 扫描器标分**、**目标程序/证明在真实环境执行并取得可复核回执**、**上传轨迹把执行与产物因果连接起来**。官网通用 `executability` 主要是第一层；Lean 的科学 0→100 与第二层通过相伴；FigQA 的总分提升与第三层轨迹接受相伴。这是对现有样本的解释框架，不是平台公开的统一三段加权公式。
3. 同一正确答案可有 0、49、59、100 的展示分；FigQA-0177/0178 的历史回执将差别归于轨迹判定或提交完整性，说明只保存最终答案会丢失影响评分的过程证据。但 FigQA-0177 E000 的本地正确答案、科学分 0 是**平台接收包与目标题目错配**，应从正常答案对照中剔除。
4. 失败后的真实修复不必降低到不能满分；关键是最终输出可验证、所用输入/代码/日志能互相指认。PPT 满分但仍有 `N11`，FigQA-0178 满分仍缺成对视觉回执，说明总分 100 不能替代独立的过程可审计性判断。
5. 从轨迹到 `trace_score` 的完整算法、专属科学验算逐项结果、历史平台最终归一化轨迹和同包重评分噪声仍不可见。当前官网的通用 ARM 评分卡与历史外部/专属评分数据不能混合拟合；这些规律不应上线为确定性预测器或经验硬规则。

本次公开只读请求：`GET /api/docs`、`/api/docs/getting-started`、`/api/docs/arm-bundles`、`/api/docs/reading-a-trace`、`/api/protocol`、`/api/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a` 均 HTTP 200。协议响应 21194 字节，SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`；官网原文与其余响应哈希保存在本机忽略目录，不作为代码或实验文件提交。
