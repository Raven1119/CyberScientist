# CS-UP-20 验证证据

本报告按 W0–W11 记录真实实现和验证；RH-02 的科学结果、平台回执与算力另记，不用本地测试证明远端成功。

## W0：开工与决定

- 已实现：D-85–D-88 及本卡/RH-02 授权分界已写入 DECISIONS。
- 已实际验证：`git status --short` 无跟踪文件改动，保留全部用户未跟踪材料；开发 HEAD `eaf1891f6c3792534f7c1b31ac7f0057c52ab4e4`；候选版 2 标签存在。
- 已实际验证：读比赛 `.runtime/version.json`，运行 `.venv/bin/cyberscientist ops digest --target comp --since 2026-10-09T09:00:00Z`，loaded/checkout 都是 `4ef48d74d2f3c3f174527423477a18baf79a9410`，matches=true；提交 unknown 数量为 0。
- 尚未验证：W1–W11 与 RH-02。
- 阻塞项：历史 `trial9-clean-replay-create` 沙箱仍 unknown，不重放创建；不属于本卡新建额度。

后续逐项追加命令、原始私有证据位置及边界。

## W1：内容导入

- 已实现：附录 A–G、I 的八个文件逐字覆盖；五个 Job 附件未改；本地评分实现保留，发布白名单停用 local-scorer/toolchain-reference 技能。Codex/Kimi 的通用交接提示都改为 D-88 的跨领域原文。
- 已实际验证：原文提取字节 SHA256 如下；经验经比赛后端 PUT/approve 接口完成，8 条 retired、2 条新修订 active，所有旧修订保留；其余 35 条 active 全局经验的 revision_hash 未变。比赛 skills/always_on 经接口更新为 22。
- 已实际验证：`.venv/bin/pytest -q tests/test_content_import_cs20.py tests/test_role_prompts_cs19.py tests/test_runtime_release_cs18.py tests/test_skills.py` → 47 passed，12.37 秒；测试日志在 `.package-checks/cs-up20/w1-tests.log`。
- 尚未验证：比赛物理/原生技能清单实际降到 22、v2 角色在新 PI/执行者原生前八帧出现，随 W9/W11 的实际发布与最小会话验收；当前运行的旧后端不能冒充新版本。
- 阻塞项：当前三个赛道均 complete，没有当前未结束赛道可发布提示；不改历史赛道。模板随 W11 发布，RH-02 前端新建赛道时由既有接口发布并冻结新模板，核对版本/hash。

### 原文指纹

| 文件 | SHA256 |
|---|---|
| prompts/roles/pi.md | bbc8aef68cfb17c6211bf691867951c47c8fe8b48da4de6f850106e7189238aa |
| prompts/roles/executor.md | 81191cb695cdede109e872020655d410de6cba6aca0d0d286ca0e565d30f7b67 |
| skills/cyberscientist-submission-gate/SKILL.md | ced568c20fdceeaafdd30e640934f69f93c19f8221d7a7d9af37ecdb2e724300 |
| skills/cyberscientist-trace-writing/SKILL.md | 2d6e59ead73f0344cbbd3b4869b914c7a7d7a87871b6702252c61853ad046ee6 |
| skills/cyberscientist-clean-rerun/SKILL.md | 286aad8844c669dbf3d969dc13a8acad4d4212d667f26bcaf421cd8bc2f967bc |
| skills/cyberscientist-job-spec/SKILL.md | c69faf8a23b5f27054886baeb6bfec65adde1b8500871020f99a7ad635770782 |
| skills/cyberscientist-sandbox/SKILL.md | 1d721ada77d6f15cc8045eccc7e57b70501c59d59e599e9878cf66967f623383 |
| templates/lightchaser-user-prompt.md | 43cf07c2deff67270e895949a6d4c7455b8833f11150ac1d6d4f966b20bc9b25 |

### 经验前后修订

| ID | 前状态 | 后状态 | 前修订 | 后修订 |
|---|---|---|---|---|
| lc_trace_gate | active | retired | rev_aa012b59dc2740afa3ab5d42dcd7a94d | rev_72b6ee2267df44b892f41465c428d924 |
| lc_submission_spacing | active | retired | rev_febcd19b0c4f4ea99043596067cdaa05 | rev_38e25256f6fa4f4687181756e707208c |
| lc_rhythm | active | retired | rev_bc495fd470204d25b7abdcd8da96589c | rev_51c17942c6734f528beb56d3351b2868 |
| lc_resubmit_policy | active | retired | rev_129b60445fc84fa2ae6aa90fe48ed2a3 | rev_e1032fdea5d0443ab2e8cbb16cedb2ed |
| csup08_verified_local_grade | active | retired | rev_fe6e25c2d698407d8e4a09608d348772 | rev_3abe2eb297974b939ec8ad33e82187a1 |
| csup08_artifact_paths | active | retired | rev_1c0b78586ba8497fb4a5a3e3ba25d9a7 | rev_188faed4037b4bd9b121e140da350448 |
| exp_cs_up03_scoring_contract_20260927 | candidate | retired | rev_74c5f259e2bf4d329c74a5feffe0c916 | rev_0809611040d44a0f901dc829fdeef3f2 |
| exp_cs_up03r_pair_before_fit_20260927 | active | retired | rev_709527b3a9d748eca8c1ccfe9b72a196 | rev_ed065c24e94f4f14a6f0583fcf743593 |
| lc_paired_evidence | active | active | rev_8150b019a72e44cfa37f8f7c368fff81 | rev_3d32f438315f4cadbd4f98471b629498 |
| lc_materials_env | active | active | rev_791f9b27fb3c4a82a1f756dd9d924767 | rev_16472a96299044d78d20c171d825b319 |

### 其余 active 全局经验（只列出，未修改）

| ID | 标题 | 一行摘要 |
|---|---|---|
| csup08_large_transfers | 大输入传输：优先已有对象或数据集，逐次核验完整哈希 | 先看 operating_facts 的按输入大小分档结果。大输入优先复用已有数据集挂载或题目资源物化，减少重复上传；当前卡只授权公开软件新建环境，不能把题目答案或密钥装进环境。 没有可复用数据集时，可把公开依赖文件随受控 Job 输入冻结上传，再由系统下载；沙箱 files.w |
| csup08_lean_environment | Bohrium Lean 4.32.2 与 Mathlib 固定环境 | 先复用已登记且身份符合的环境；没有环境时在授权 Bohrium 沙箱中准备，冒烟通过后才交给 Job。固定 Lean 4.32.2，Mathlib revision 905b95818eb32af7874a58b427f50c1711a5e96c；Lean 官方 tar.zst  |
| csup08_mirror_recovery | 403 与 pip 安装超时后换已授权来源 | 记录原 URL、HTTP 状态和安装输出，随后立即换一条有额度的通道。先在沙箱验证依赖，再把成功环境用于 Job，避免每次重启科研程序都安装。 授权的远程环境中可尝试官方 PyPI 源： ```bash python3 -m pip download --index-url ht |
| csx1_atom | 原子模拟先通过构型与约定检查 | # 原子模拟先通过构型与约定检查 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 构建缺陷、界面或施加位移后，出现异常近邻、很大初始力、边界错误或结果对构造约定敏感。 ## 协作策略 执行器：对无 |
| csx1_decide | 用能够区分解释的实验推进研究 | # 用能够区分解释的实验推进研究 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 已有明确科研目标，但存在多个解释、方法或下一步；特别是连续调参没有解释误差来源时。 ## 协作策略 大脑：维护当前 |
| csx1_delivery | 交付物、提交回执与科研结论分别验收 | # 交付物、提交回执与科研结论分别验收 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 准备提交科研结果，或根据平台反馈决定下一次尝试时。 ## 协作策略 执行器：提供可复现入口、环境、输入/输出 |
| csx1_handoff | 大脑与执行器按决策需要交接证据 | # 大脑与执行器按决策需要交接证据 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 大脑负责跨尝试路线，执行器掌握局部实施；出现路线分歧、关键状态变化或需要上层判断时。 ## 协作策略 大脑：给目 |
| csx1_inverse | 反问题同时检查数据拟合与重建可信度 | # 反问题同时检查数据拟合与重建可信度 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 存在潜在结构/参数和可观测数据，需要从观测反推模型；适用于波形、层析或边界重建任务的候选方法选择。 ## 协 |
| csx1_literature | 将文献方法转成可检验的题内候选 | # 将文献方法转成可检验的题内候选 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 新题缺少自身经验，需要从论文、官方示例或历史不同任务中获得初始方法。 ## 协作策略 执行器：读取原始方法、关键 |
| csx1_ml | 模型优化保持可比评估与数据边界 | # 模型优化保持可比评估与数据边界 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 微调、训练或模型配置优化需要比较多次尝试；预算有限且任务有特定数据、硬件或提交要求。 ## 协作策略 执行器：在 |
| csx1_noise | 指标改善先排除随机性与口径变化 | # 指标改善先排除随机性与口径变化 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 两次结果差距较小、随机初始化/采样显著，或评价口径可能随尝试变化。 ## 协作策略 执行器：交接可比样本、随机种 |
| csx1_numeric | 数值复现先定位误差结构再提高计算精度 | # 数值复现先定位误差结构再提高计算精度 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 数值复现的结果与参考值不符，误差集中于部分参数或输出；单纯加密网格、收紧容差收益有限。 ## 协作策略 执 |
| csx1_reopen | 负经验保留失败条件与重新尝试条件 | # 负经验保留失败条件与重新尝试条件 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 某路线失败、被大脑否决，或后来新证据可能改变旧判断。 ## 协作策略 执行器：记录失败发生的准确阶段、输入/环 |
| csx1_resource | 资源阻塞按可验证状态分类 | # 资源阻塞按可验证状态分类 证据等级：**hypothesis，待验证的设计先验**。启用只表示允许有条件试用，不表示该策略已被实验证明有效。 ## 适用情境 工具找不到、数据未就绪、认证失败、权限或硬件配额可能阻断科研路线时。 ## 协作策略 执行器：分别检查官方资源入口、安 |
| env_05c5d9e0e816a77587d8ba96 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "8eeb092e7567563decbef0f19558ac62d2fed560527c30356f118b096b809666", "image_address": "regis |
| env_27f12b667d8354cbe0a599d3 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "0edc48ae2ee0010b2ff77edc25da87c0031e326c9adddafc970d94f223a3db97", "image_address": "regis |
| env_4ba6c98d6c4a8f371c4d32eb | Bohrium 沙箱 template.list | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"items": [{"active_revision_id": 9538, "cluster_names": "S5000", "command": ["sh"], "cpu": "4", "create_time" |
| env_54ebc8461c6b9e818bcfb036 | Bohrium 沙箱 quota | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"is_admin": false, "max_extra_ephemeral_storage_gb": {"limit": 50, "source": "system_default"}, "running_sand |
| env_5f90993ab43387dac00828d0 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "3121e77acb86e3697939d2fe1c4941bdfc32761516767e13dae5245e4d5c4df8", "image_address": "regis |
| env_6603056db4bc204561d53b7b | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "262cb2c4984fb1f66fb47a185cd7fe4ef76bc49dd700a3be8c2a24a0402dfd32", "image_address": "regis |
| env_675705e5e89f6d481d62f019 | Bohrium 沙箱 machine.list | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"items": [{"class": "cpu", "cpu": "1", "memory": "2Gi", "price": "0.00 RMB/h", "sku_id": 18903, "sku_name": " |
| env_72713113cbe9f65a8a9bdc4f | Bohrium Job 客户端主机 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"client": "bohr_v4", "host": "https://open.bohrium.com"} ``` |
| env_7c556087b62b76e7ebeed6eb | Bohrium 沙箱客户端主机 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"cli_version": "2.7.8", "host": "https://open.bohrium.com"} ``` |
| env_805bed2952e1fba5f5c2618b | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "4542544a0c523076c22cb008e278b509d3708b38bdd86c0ea002c40bc7d3f8d9", "image_address": "regis |
| env_881caab7c7ea204219fdd5d2 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "003da3c744786d3639eadf8d2446218f8dd71b0a0baa6d11f0f65f803a0866a5", "image_address": "regis |
| env_9cf7026357c72efb8d64a97a | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "106ba4474bf46a9d81d49b27233ce926f1387534bbafe5c34a1f2c27e5b175c1", "image_address": "regis |
| env_a06e53028328001387129c59 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "6f67e98d0bec6737782aa3f57416b08e32f69dc265bd4388f05cb1959e2a120e", "image_address": "regis |
| env_b0c2134fb033ab0ed8763d53 | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "d3748a992bce2f59d3b1108a7c816a725e7671ddde5f395dea24eec5a1339261", "image_address": "regis |
| env_b6ae19119697105d26e82a7f | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "e1bc3ea3f9ef0f7b6ff1014354c0c8ce180852c5efec9df3f8bd1ee953ca0e85", "image_address": "regis |
| env_d9c46d4be59bb60bd34b7baa | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "f7467a23d2d94fdb969b5a05b4e406b52a8c527d3feb55ea135681dab3a78b47", "image_address": "regis |
| env_ea3a46cc65bdd02a9c1ad13b | 冒烟命令回执与配方候选 | 来自真实回执的环境观察；仅代表观察时状态。 ```json {"command_sha256": "82e6ba77b6d7c3639a39b6bb6b79981f4f84eb40f4026b6b0a9cd8aa69d306ed", "image_address": "regis |
| lc_causal_outputs | 每个提交文件都要由轨迹里可见的命令生成（N11） | # 产物必须有可见的因果链 N11（提交产物没有被因果支撑）出现在 71% 的 v8 提交中，是最常见的扣分。评分器先看 worker 回执，再看文件名和内容能否与轨迹中的执行对应上。 **做法**： - 最终的每个输出文件，都用一条在轨迹里可见的命令写出。路径与提交包中的路径完 |
| lc_judge_visibility | 关键证据放在每个事件的开头，事件短而密，不要堆砌（截断/N12） | # 让裁判看得见 裁判（按 v6 公开源码）对每个事件只看前 900 字符，题面只看前 5,000 字符，文件只看前 40 个，看不到图片内容；事件太多时也只摘取一部分。核对发现，约 17% 的"缺失证据"其实写在轨迹里，只是落在了裁判看不到的位置。 **做法**： - 每次打印 |
| lc_requested_method | 最终结果必须来自题目要求的方法（N14） | # 不要用替代方法交最终结果 N14（题目要求的最终方法被替代或降级）出现在 32% 的 v8 提交中。评分器的说明是：出现"降级、代理"一类字眼只是提示，真正扣分的条件是看得出最终结果被替换了。 **做法**： - 先读清题面要求的方法：算法、模型、精度、步骤。 - 替代方法只 |
| lc_visible_creation | 题目特定的代码要在轨迹里可见地创建，不重放现成文件（N17/N18/蒸馏） | # 在轨迹里写出代码，而不是运行现成的代码 v8 新增两条，触发后 accept 率都是 0： - **N17**：实质产物在轨迹之前就已存在。评分器的说明是："重放或检查已经完成的源码和推导文件，不能证明当前轨迹产出了解答。" - **N18**：过程证据低于底线，不能越过满分 |

前后接口回执、旧历史列表和不变指纹在 `.package-checks/cs-up20/experience-targets-{before,after}.json`、`untouched-active-global.json`、`skills-enabled.json`，不含凭据，不进入 Git。
