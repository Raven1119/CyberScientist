# 第四季科学评分器：公开信息可复刻性核查

日期：2026-09-28。结论：存在可以从公开规则重建的科学评分器，但不能把它推广为第四季通用评分预测器。最值得新增验证的是 Matchgate/SWAP；DPA4C 适合检验公开工具链复用。USCT 等题缺少评分所必需的隐藏输入，公开指标不足以确定官方分数。

## 范围与证据

- 本轮匿名 GET 实时核对[第四季详情](https://play.bohrium.com/api/hackathon/seasons/4)与[轮次清单](https://play.bohrium.com/api/hackathon/seasons/by-slug/s4/rounds)：60 道，6 轮，每轮 10 道。逐题核对 16 道不同题目的公开正文、评分说明及资源声明，覆盖第 1、2、4、5、6 轮；这是有目的抽样，不推断全季可复刻比例。
- 原始响应、读取记录与 SHA-256 保存在忽略目录 `.package-checks/s4-scorer-public-review/`。只把结论写入仓库，不提交原始响应、题目数据或账号信息。
- 本轮未下载认证数据集，未运行新的科学评分、模型、Job、沙箱或 Attempt。资源表写“公开”的附件不等于本轮已取得和审读其源码；相关可实现判断仍以获得固定附件为前提。
- Paired-block 的历史实测来自[上一轮回放报告](PAIRED_BLOCK_SCORER_REPLAY_2026-09-28.md)，本轮仅刷新官网规范，没有重跑。仓库已有 `challenges/local_a619cdef/scorer/` 的 ABC 有界实现，也不因此宣称其全部官方输入范围已经验证。

## 先区分评分对象

[官方入门文档](https://play.bohrium.com/api/docs/getting-started)说明：`scoring` 字段声明平台自身策略，但整季交给外部评分 worker 的情况不会体现在该字段中。本轮 15 道题返回 `arm_v1_1_generic`，DPA4C 返回 `llm_judge_topic_markdown` 且带通用 ARM fallback；这些正文同时描述题目专属科学验证。因此不能据这个字段推断历史赛期没有专属评分器，也不能保证今天新交一次能调用当年的科学评分器。尤其 DPA4C 的题面确定性公式与当前元数据所指 LLM 路径必须分开。

本报告评估的是“按公开题面重建专属科学验证与计分”。它不同于通用 ARM 包评分、轨迹分、展示分及比赛资格。要声称官方数值一致，还需要相同输入、相同评分版本的实测对照。

## 16 道题的判断

“规则充分”表示可以开始实现并验证；不表示已经取得官方隐藏源码或通过本轮实测。

| 题目／轮次 | 公开信息能支持的实现 | 缺口与结论 |
|---|---|---|
| [Paired-block Lean／R4](https://play.bohrium.com/api/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a) | 固定定理类型和工程，40/30/20 分；全部证明通过后匹配题 4/3/3 分 | 核心规则充分。上一轮已有 4 份历史回放一致、8 种合成控制；匹配格式校验器不含答案，语义答案须独立判断。极端输入和完整隐藏防护不宣称等价。 |
| [Matchgate/SWAP 逆合成／R4](https://play.bohrium.com/api/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745) | 公开端点态、线路重放、酉性容差、保真度及四题各 25 分的连续函数 | 最好的新增候选。私有参考线路不参与候选评分；仍需取得固定实例、schema、运行依赖并做正负与边界控制。 |
| [ABC 记录／R5](https://play.bohrium.com/api/challenges/paper2arm-abc-conjecture-record-b335c57d) | 整数证书、因式分解、radical、质量及 0/5/10/20/100 档 | 无隐藏数据，常规输入规则充分。官方工作精度、巨大素数判定和临界阈值实现未完整公开；不能保证边界逐点一致。 |
| [DPA4C CPU kernel／R6](https://play.bohrium.com/api/challenges/optimize-the-isolated-csr-radial-angular-aggregati-dc3d6439) | 公开 ABI、正确性容差、三档工作负载加速比汇总、完整分段计分公式；声明提供检查与计时源码 | 给定合法计时值，可重建题面确定性分数。需审读附件；不同运行环境会改变 speedup。本题仍排除隐藏 cases 等材料；当前 API 声明 LLM 评分，不能保证与题面公式一致。 |
| [二元输出纠缠单配性证书／R1](https://play.bohrium.com/api/challenges/find-an-exact-binary-answer-monogamy-of-entangleme-55ab0d77) | 精确有理矩阵、PSD、归一化、枚举确定性响应上界、严格优势条件 | 科学接受判定可重建，无须隐藏答案；官方算法、预算内可处理规模及完整百分制映射未明。缺已知突破正例，造验证器不等于解题。 |
| [加权随机森林边相关反例／R1](https://play.bohrium.com/api/challenges/find-an-exactly-verifiable-counterexample-to-edge-7141d3ed) | 全森林精确配分函数与严格相关不等式 | 同样可重建证书接受判定；时间预算实现和百分制映射未完整给出，不宣称整套官方评分等价。 |
| [周期正四面体堆积／R4](https://play.bohrium.com/api/challenges/flowforge-periodic-regular-tetrahedra-packing-f45cec7b) | 几何、周期非重叠、密度、源码清单与文件哈希一致性 | 能复刻科学可行性和密度检查；公开 validator 明确不披露隐藏分数阈值，无法得到完整密度→分数映射。 |
| [2Fe–2S sparse CI／R2](https://play.bohrium.com/api/challenges/2fe-2s-sparse-ci-variational-energy-minimization-2bf4e3d5) | 从公开 FCIDUMP 重建 Hamiltonian，计算提交波函数的 Rayleigh 能量 | 可复算核心科学量。题面只给 RHF→0、incumbent→0.5 和单调性，未给完整归一化函数；不能据两个锚点自行补成官方分数。 |
| [CNVkit／R4](https://play.bohrium.com/api/challenges/biomaster-cnvkit-processed-segmentation-d6077a43) | 固定版本、命令和公共数据可重建参考处理结果，检验 600 项投影及交付一致性 | 已知 19 检查、五文件权重 56/17/17/8/2；具体检查拆分、数值容差、前提依赖及未完成上限不全。可做强自检，不能凭满分流程推断任意坏输入的官方分数。 |
| [Deep BSDE PDE／R4](https://play.bohrium.com/api/challenges/flowforge-deep-bsde-pde-c8d415de) | 公共 PDE、部分精确解、六文件契约及权重 30/20/17/16/14/3 | 可独立检查数值与实验一致性；16 检查中的目标、容差及依赖计分细节不全，不能还原完整科学分。 |
| [TBMA／R5](https://play.bohrium.com/api/challenges/paper2arm-tbma-mclafferty-0035bde0) | 电荷/自旋、结构、频率、IRC、能量差和 ABACUS 文件证据检查 | 24 检查与 13 文件权重公开，全部数值参照、容差、前提与封顶规则不全。能建立有科学意义的审计器，不能承诺精确总分。 |
| [非局域孤子／R5](https://play.bohrium.com/api/challenges/reproduce-nonlocal-solitary-wave-existence-branche-dddfc025) | 方程、公开网格、60 剖面、9 个模态、尺度关系与动态 solver 接口 | 适合独立物理验证和新参数测试。隐藏参数、完整阈值和权重未公开；局部重放可验证可执行性，不等于复现官方全部用例。 |
| [USCT／R4](https://play.bohrium.com/api/challenges/flowforge-usct-ring-sound-speed-attenuation-v2-5c9021cd) | 公共频率残差、复增益消除、单位/网格、双图与表格一致性 | 缺 1.30 MHz 隐藏观测、真实组织图与包涵体信息，以及明确未公布的清零阈值。仅公开资料不能确定官方总分。 |
| [地震 FWI／R6](https://play.bohrium.com/api/challenges/paper2arm-seismic-fwi-from-a-1d-trend-a0915222) | 公共炮记录拟合、速度范围、输出与源估计检查 | 评分依赖隐藏速度真值、真实源波形、四个隐藏炮记录及照明区实现。公式描述不能替代这些输入。 |
| [Pancreas 去噪／R4](https://play.bohrium.com/api/challenges/denoise-a-frozen-pancreas-indrop1-single-cell-rna-e673f74c) | 形状、非负性、公开指标与校准说明；可自设验证切分 | 官方 held-out 分子矩阵不在公开输入中。自设切分不是官方测试集，不能报告为官方精确分。 |
| [XAS 双向迁移／R5](https://play.bohrium.com/api/challenges/xas-sim2real-bidirectional-52f0be51) | 公共验证集上的 MAE、导数、峰位置及往返检查，方向权重 45/45/10 | 隐藏测试谱和子指标到分数的完整映射未公开，只能做公开验证指标或待校准代理。 |

## 为什么优先 Matchgate

这道题同时满足四个条件：候选是明确的数学对象；评判所需端点声明为公共固定输入；独立重放和误差定义明确；误差到分数的映射完整。

对每个合法案例，重放 Gaussian block 与普通相邻 SWAP 得到候选态，计算

\[
F_i=|\langle\psi_i^{\mathrm{target}}|\widehat\psi_i\rangle|^2,
\qquad S=25\sum_{i=1}^{4}\operatorname{clip}\left(\frac{F_i-0.80}{0.19},0,1\right).
\]

酉性使用题面规定的 Frobenius 容差；错维度、非法门数等按案例判无效。主办方持有的私有构造只是目标来源和资源最优性证明，题面明确不拿它比对提交。**出现“hidden verifier”一词，本身不意味着评分函数不可复刻。**

这是规范可实现性的判断。本轮没有读到完整实例附件和执行新评分，不能写成已验证复刻。后续应先核验公开资源 SHA，再用已知合法候选、非法候选和接近 0.80/0.99 的控制检查独立实现，最后才与合法取得的同题官方科学回执比较。

## 科学正确、分数与可执行性应分开

1. **可检验的科学量**：例如能量、PDE 残差、证明成立、几何密度。
2. **公开计分函数**：科学量如何变成分数，还包括依赖、封顶、容差和解析规则。缺这层时，应输出已验证指标和未确定项，不能自造一个 0–100 值冒充官方分。
3. **评测输入和运行条件**：隐藏真值、测试点、版本、时间预算和计时硬件。即便公式公开，缺输入也不能计算该次官方分数。

可执行性必须逐题解释：[非局域孤子](https://play.bohrium.com/api/challenges/reproduce-nonlocal-solitary-wave-existence-branche-dddfc025)确实执行 solver 的新参数调用和确定性检查；[四面体堆积](https://play.bohrium.com/api/challenges/flowforge-periodic-regular-tetrahedra-packing-f45cec7b)明确只审查搜索源码而不重跑搜索。不能统一加一条“所有代码必须被完整重跑”，再称其为官方复刻。平台[通用 ARM 文档](https://play.bohrium.com/api/docs/arm-bundles)中的结构可执行性信号，也不能代替题内实际计算验证。

因此扩展时优先顺序为：Matchgate 的完整公开数学评分、DPA4C 的公开计分工具链；CNVkit/非局域孤子适合做独立科学审计器。USCT、FWI、XAS 等保留公共验证能力，并明确官方总分未知。

## 本轮交付与限制

仅新增此公开资料核查报告并更新状态/决策记录，未修改运行时、评分器或经验。本轮不复跑应用测试和前端构建；文档检查与源快照核对结果另记于 `STATUS.md`，不沿用历史测试数字充当本轮测试。
