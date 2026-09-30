# CS-UP-05 W1：两层本地评测题目目录

目录见 [`evals/catalog.json`](../evals/catalog.json)，结构由 [`catalog.schema.json`](../evals/catalog.schema.json) 校验。`receipt_validated` 仅指所述历史规范输入与平台科学分对照；`spec_validated` 仅指公开规范与合成正反例对照。两者都不承诺复刻平台当前通用 ARM 评分、隐藏异常输入处理、轨迹裁判或展示分。

## 选题与实际分布

| 层级 | 题目 | 评分器状态 | 2026-09-22 公开榜单快照 | 选入理由 |
|---|---|---|---|---|
| 快速 | abc 纪录 | `spec_validated` | 45 个榜单条目，最低 0、中位 20、最高 20、满分条目 0 | 整数证书成本低，公开榜单不饱和；本机确认的 41.43 是较晚的通用 ARM 展示分，不能用来校准科学评分器。 |
| 快速 | FigQA-0177 | `receipt_validated` | 2026-09-30 匿名公开 Attempt GET 返回 404，分布未知 | 规范答案评分很快，11 份有效历史回放一致，可测运行与轨迹波动。 |
| 快速 | FigQA-0178 | `receipt_validated` | 同日匿名公开 Attempt GET 返回 404，分布未知 | 第二个独立固定答案题，四份历史科学分与公开标准答案一致。 |
| 困难 | Paired-block Lean | `receipt_validated` | 39 个榜单条目，中位 100，满分 21 | 用户指定的长证明流程；榜单已饱和，主要用来测依赖准备和长任务方差。 |
| 困难 | Matchgate/SWAP | `spec_validated` | 40 个榜单条目，中位 67.3，满分 6 | 公开连续计分完整、榜单较不饱和；大实例评估耗时尚未测量。 |

榜单数值是**每个公开榜单条目的最佳展示分**，并非所有 Attempt 的分布；快照来自本机忽略目录 `.package-checks/season4-selection/leaderboards/`，记录时间为 2026-09-22。FigQA 的历史自有提交不能代替公开分布。目录里的单次 Run 时间范围仅作预算规划，模型 token 与 Bohrium 金额均为 `null`，真实花费须在 W3 从回执统计；不把授权上限当作已消费成本。

## FigQA-0178 的独立答案与回执核对

锁定的 [Future-House/LAB-Bench 公开题库](https://github.com/Future-House/LAB-Bench/blob/998a8e0a40cf116c80e1b0e7a805ebb5fb9fa838/FigQA/figqa-v1-public.jsonl)文件 SHA-256 为 `28ae0293abe797917b37b6c6f3641e15cbde18ec7d3d870a7e2bd0a2e8271186`。实例 `1dcc341b-c11c-4d2b-b4e0-b331d98ca6b7` 的公开语义答案是 P7C3-A20；本机封存平台题面固定选项 **F = P7C3-A20**。本机 AgentMaster 四份不同历史迭代的封存 `outputs/answer.txt` 均为 `[ANSWER]F[/ANSWER]`，对应真实回执科学分均为 100；原始回执、包绑定记录和文件保持在 `/home/wmywb/AgentMaster/store/T0/lab-bench-figqa-figqa-0178-23afc746-ep001/`，仓库不复制它们。由此只验证了规范 F→100，其他规范选项的 0 分是公开答案相等规则的推导，未取得错误答案的本题平台回执；不规范解析返回 `unverified`。

## Matchgate 固定资源与合成控制

通过已有 `_native` 凭据注入仅下载一次公开 Wenyon 数据集 `paper2arm-public-s4r4-matchgate-4019e745@1`；此前沙箱内 DNS 失败的一次尝试没有取得数据。成功回执退出码 0、`ok=true`，下载包 24,137,739 字节，SHA-256 `3ed0a9a79f63504b8a6d7c84022dee9bc458aaf15bc23096d4e60b5c3f316e74`，与题目公开资源声明一致；包内 12 个实例文件的大小和 SHA 均与 `INSTANCE_MANIFEST.json` 相符，Q4 目标数组连接后的字节 SHA 也相符。原包、脱敏回执与解包文件留在 `.package-checks/cs-up-05/matchgate-public/`，不提交。

评分器按固定粒子数占据态重放每个 Gaussian block 与**普通相邻 qubit SWAP**，独立计算目标态保真度，再按每例 `25 × clip((F−0.80)/0.19, 0, 1)` 汇总。它校验矩阵维度、有限值、Frobenius 酉性容差 `1e-8`、恰好 `t` 个相邻 SWAP、恰好 `t+1` 个 Gaussian block；单例无效只令该例得 0。合成测试覆盖合法线路、错维度、错门数、非酉与非有限矩阵、0.80/0.99 两个边界，以及与独立小规模外积矩阵计算一致。未用平台提交校准。Q4 的全规模 CPU 耗时和 Bohrium 运行依赖尚未验收，W2 必须把已哈希核对的公开实例与 NumPy 2.2.6 供应给评分沙箱，W3 才能报告实测成本。

已有评分器边界保持明确：FigQA-0177 只观察过两种不同规范答案字节；Paired-block Lean 的 E000 未完成回放，中间分仅有合成反例；abc 在大素数与临界阈值附近未校准，且较晚通用 ARM 回执不是它的科学分标签。
