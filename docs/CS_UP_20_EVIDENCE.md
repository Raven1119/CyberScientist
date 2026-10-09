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

## W2：系统补齐结果包

- 已实现：缺清单时从冻结题面/输出路径生成 ARM 1.1 最小清单；没有真实入口脚本则 entrypoint 为空，不编造执行；已有清单沿用原封存绑定逻辑，原科学字段不覆盖。outputs-only 不再误判 outputs/ 为外层包目录；仍支持单层包目录。
- 已实现：探索、干净复跑及旧非渐进首条提示都要求只交题面文件，不自写清单、轨迹、叙述。比赛执行者的 Codex 白名单和 MCP 桥列表均去掉叙述检查，开发旧接口保留。
- 已实际验证：官方 CLI 输入是暂存的题面输出与原生记录；试构建包中没有 `traces/cyberscientist_merged.jsonl`、`trace_narrative.jsonl`，科学文件与原生输入 SHA 逐项匹配。此测试真实执行固定官方 CLI 0.1.40，只使用明确 synthetic 原生 fixture 和只读账号 fixture，未访问真实账号、未建 Attempt，不宣称真实研究或上传。
- 已实际验证：`PATH=/home/wmywb/CyberScientist-comp/.runtime/bin:$PATH .venv/bin/pytest -q tests/test_output_only_package_cs20.py tests/test_trace_narrative.py tests/test_cli_submission_cs14.py tests/test_submission_outputs_cs15.py tests/test_mcp_bridge.py tests/test_role_prompts_cs19.py tests/test_clean_runs_cs16.py` → 73 passed/23.71 秒；补加真实提交预检入口覆盖后，单文件 7 passed/2.38 秒。源码编译与 diff 检查通过。
- 已实际验证：输出-only ZIP 完成预检、封存、schema 检查、科学输出暂存与真实 CLI 离线试构建；源 ZIP、产物和 native fixture 字节未变；已有清单科学字段保持原值；新探索/复跑提示要求一致。
- 尚未验证：新比赛运行时上的实际原生会话构建，留到 W9/W11；本卡无真实提交授权。
- 阻塞项：无。初次测试缺 Node PATH，随后 fixture 只有 session_meta 导致 CLI 无可归一化步骤；改用已安装 Linux Node 和明确标识的消息 fixture 后通过。两次失败日志分别保留于 `w2-tests-initial.log`、`w2-tests-second.log`；通过日志为 `.package-checks/cs-up20/w2-tests.log`、`w2-preflight-tests.log`。

## W3：平台明确拒收

- 已实现：CLI 非零退出只把明确的 429+提交上限与明确的包校验拒收分类；普通 429、创建记录校验、网络错误仍 unknown。记录独立 rejection 事件和前端告警；不自动重发。
- 已实现：账号身份与冻结平台/origin/题目键共同标记本题用尽；不禁用该账号的其他题。下一项新提交换账号；已排队的同账号请求发送前也重新检查。原同哈希账号绑定只在原账号明确用尽时允许换账号。
- 已实现：拒收无 Attempt ID 时释放本地预约；Worker 拒收而已知 Attempt ID 时保留 ID 和额度，记 failed，避免把远端已创建记录写成未存储。普通未知仍走原对账。
- 已实现：比赛面板显示本题各账号已确认 Attempt 次数、额度占用和用尽标记；次数合并完整分页的 CLI 基线与本地已知远端 ID，去重；不把未知预约算成已确认提交。
- 已实际验证：相关后端回归 64 passed/20.38 秒；追加计数/比赛面板覆盖 19 passed/5.37 秒；最后的发送前门禁专项 14 passed/3.61 秒。两种拒收、幂等不重发、下次换账号、不同题不串用、已知 Attempt 的预约保留、分页基线次数均为明确 synthetic 协议测试。
- 已实际验证：`PATH=/home/wmywb/.local/share/node-v22.17.0-linux-x64/bin:$PATH npm --prefix apps/web test -- --run src/CompetitionPanel.test.tsx` → 11 passed；次数/用尽状态渲染和现有操作覆盖。
- 尚未验证：平台真实拒收，本卡真实提交额度为 0，不能人为触发；RH-02 若出现则据真实回执核对。
- 阻塞项：无。日志在 `.package-checks/cs-up20/w3-{tests,extra-tests,final-tests,frontend-tests}.log`；最初 npm 不在当前 PATH，改用已有 Linux 安装，不安装或修改全局配置。

## W4：平台评分元数据

- 已实现：模型投影去掉平台及原生 API wrapper 中的 scoring 元数据，加入 D-87 的 harbor 隐藏测试事实。覆盖当前/冻结题面、PI 生命周期帧、监督反馈、执行者探索/干净提示、渐进帧及可展开 facts。科学输出契约中名为 scoring 的字段仍保留，平台回执评分字段也不改。
- 已实际验证：数据库原始题面与 Run 配置快照字节在前后相同；模型帧、可读 facts 无原元数据；冻结科学正文和输出 schema 保留。完整/轨迹回执缺 harbor_score 时一次告警，科学分保持 unknown；普通排队不触发，后续真实字段可更新。
- 已实际验证：`.venv/bin/pytest -q tests/test_scoring_metadata_cs20.py tests/test_progressive_context_cs16.py tests/test_receipts_cs15.py tests/test_competition_panel_cs16.py tests/test_clean_runs_cs16.py` → 32 passed/9.53 秒，日志 `.package-checks/cs-up20/w4-tests.log`。
- 尚未验证：发布后新 PI/执行者真实原生帧，随 W9/W11；真实缺 harbor 回执不在本卡零提交授权内。
- 阻塞项：无。

## W5：人工复核

- 已实现：原始 pending_review/needs_review 单独登记；比赛面板、研究页及邮箱页显示“人工复核中”，发持久告警；不显示仍在评分的时长告警。PI 正常研究不被暂停，旧等待评分流程也可根据人工复核事实唤醒 PI，分数仍 unknown。
- 已实现：保持后台轮询；同一次观察中的人工复核状态优先于冲突的最终展示分标志，不能误记评分终态。真实明确终态到来后可恢复普通终态处理。
- 已实际验证：两个状态各连续轮询两次，未停轮询、未改变 running、未编造分数；冲突最终标志不关闭人工复核；旧等待标记可唤醒而没有分数。后端相关 18 passed/5.74 秒；前端比赛面板/邮箱页 21 passed，两个状态和告警显示已覆盖。
- 尚未验证：真实平台人工复核状态，本卡没有真实提交授权。
- 阻塞项：无。初次两项失败暴露“用最终标志推断 completed 覆盖人工复核”的问题，已修正并复测；原失败 `w5-tests-initial.log` 与通过 `w5-tests.log`、`w5-frontend-tests.log` 均在 `.package-checks/cs-up20/`。

## W6：环境标识与旧别名

- 已实现：配方目录 `cs-up-12` → `scientific-runtimes`，`cs-up-13` → `abacus-materials`；`environments/aliases.json` 保留旧名字查询，不用符号链接。环境目录的十个内部 ID 按下表迁移，能力/环境索引只显示新 ID；经旧 ID 新选择时冻结新 ID。
- 已实现：旧目录数据库行、descriptor 原文字节/SHA、冒烟回执和历史选择事件保留；新条目仅改 ID 并重新计算 descriptor SHA。旧选择仍恢复原镜像/命令/回执；重复启动幂等；新名字或别名冲突明确失败，不覆盖。远端镜像地址不改，未创建镜像或科研资源。
- 已实际验证：`.venv/bin/pytest -q tests/test_environment_aliases_cs20.py tests/test_environment_catalog_cs10.py tests/test_runtime_environments.py` → 19 passed/7.38 秒；`tests/test_progressive_context_cs16.py tests/test_content_import_cs20.py` → 8 passed/2.49 秒。覆盖旧数据库启动迁移、不可变历史、旧 Run 恢复、索引仅新名、冲突回滚、路径越界与注册别名。日志 `w6-tests.log`、`w6-context-tests.log`；有界审查核对事务、身份与路径约束，diff 检查通过。
- 尚未验证：比赛后端实际目录与启动迁移留 W11 发布核对，当前 4ef48d7 后端仍显示旧名。迁移前实际 13 条目录清单在 `.package-checks/cs-up20/environment-catalog-before.json`，不把临时数据库测试当实际迁移。
- 阻塞项：无，继续 W7。

| 旧 ID（保留别名） | 新 ID |
|---|---|
| cs10-private-python-v1 | python-minimal-private-v1 |
| cs10-public-python-v1 | python-3-10-public-v1 |
| cs12-lean-mathlib-v1 | lean-mathlib-v1 |
| cs12-pyscf-v1 | pyscf-v1 |
| cs12-sci-py-v1 | sci-python-v1 |
| cs12-torch-cpu-v1 | pytorch-cpu-v1 |
| cs12-torch-cuda-v1 | pytorch-cuda-v1 |
| cs13-abacus-v1 | abacus-plane-wave-v1 |
| cs13-abacus-v2 | abacus-plane-wave-v2 |
| cs13-materials-v1 | materials-python-v1 |

## W7：凭据路径与早期告警

- 已实际验证：只枚举文件名并做 exists/access/stat 检查，没有读取凭据内容；完整路径/存在清单在 `.package-checks/cs-up20/credential-paths-before.json`。比赛 HOME 的同类凭据文件存在数为 0，无多余明文副本可移；全局目录未改。下表只报告路径与存在状态。
- 已实现：当前比赛 Codex 执行器在原生工具开始事件上检查输入中的显式读取路径，包括 commandExecution、MCP 与 0.161 code-mode 的 dynamicToolCall；发现即发 `credentials_touched`，在控制器持久化、前端通用告警及 PI 观察摘要中可见。相同 session/item 去重，迟到的旧 Trial 通知仍按其归属记录，不自动暂停或新建 Trial。
- 已实现：告警仅含路径与 session/item/turn 身份，不保存命令或结果；不打开凭据，不修改供应商原生记录。观察的是原生报文中显式路径读取意图，不确认访问成功，无法判定未在输入中显式出现的间接访问。
- 已实际验证：先用 0.161 CLI 自带 `app-server generate-json-schema --experimental` 确认工具字段（私有 `codex-schema/`）；专项 26 passed/8.92 秒。补加全局 HOME/凭据目录与协作回归后，`.venv/bin/pytest -q tests/test_credential_watch_cs20.py tests/test_codex_runtime.py tests/test_collaboration.py tests/test_ops_cs10.py` → 109 passed/63.37 秒，日志 `w7-full-tests.log`。覆盖开始事件先于结果、代码模式、全局和比赛路径、一次告警、普通文件/输出/纯元数据不误报、Run 继续 running、原生字节哈希不变。
- 尚未验证：新比赛进程实际告警接入，随 W11 发布；本卡不令真实执行者读取凭据来制造验证。Kimi/Prime 的原生接入未增加此检测，本次比赛选用 Codex。
- 阻塞项：同一系统用户权限本身没有隔离；如记录真的读到密钥，需要干净 Trial，不能改写原始记录。有界审查核对检查只使用原生输入、告警不含秘密、事务去重与 Trial 归属；diff 检查通过。

| 路径 | 存在 |
|---|---|
| /home/wmywb/CyberScientist-comp/.cyberscientist/secrets.json | 是 |
| /home/wmywb/CyberScientist-comp/.env | 是 |
| /home/wmywb/CyberScientist-comp/.runtime/codex/auth.json | 是 |
| /home/wmywb/.codex/auth.json | 是 |
| /home/wmywb/.playground/config.json | 否 |
| /home/wmywb/.config/playground | 是 |
| /home/wmywb/.config/playground/agents/agentmaster-02.env | 是 |
| /home/wmywb/.config/playground/agents/agentmaster-03.env | 是 |
| /home/wmywb/.config/playground/agents/agentmaster-probe-01.env | 是 |
| /home/wmywb/.config/playground/credentials.env | 否 |
| /home/wmywb/.bohr/config、.bohr/config.json、.config/bohr/config.json、.config/bohrium/config.json、.bohrium/config.json | 均否 |
| /home/wmywb/.bohrium/bohr | 是 |
| /home/wmywb/CyberScientist-comp/.runtime/home/.codex/auth.json | 否 |
| /home/wmywb/CyberScientist-comp/.runtime/home/.playground/config.json | 否 |
| /home/wmywb/CyberScientist-comp/.runtime/home/.config/playground（含 agents/ 与 credentials.env） | 否 |
| /home/wmywb/CyberScientist-comp/.runtime/home 下 .bohr、.bohrium、.config/bohr、.config/bohrium | 均否 |

## W8：验证残留归档与冷启动

- 已实际验证：15 项移至 `/home/wmywb/CyberScientist-private-archive/cs-up20/w8-20261009T133207Z`（0700）：`validate-{audit-hidden.sh,audit.py,baseline.py,browser.py,identities.py,native.py,preview.py,sandbox-repair.py,sandbox.py,tools.py}`、`validation/`、`validation-native.log`、`reference-map.json`、`client-install{,-2}.log`。源 `.runtime` 对 validate-/validation 前缀搜索为 0；当前运行时代码及启动脚本无这些残留路径引用。
- 已实际验证：使用同一文件系统的 `os.rename`，不复制；validation 整目录按 inode/device/文件名/大小核对，不读取其中的秘密文件。其他验证脚本/日志按原 SHA 核对。私有完整清单在归档 `manifest.json` 和 `.package-checks/cs-up20/w8-cleanup.json`。运行依赖、版本、锁文件、启动器、运行日志及用户简历提交回执保留。
- 已实际验证：清理后经已核实 PID、safe-shutdown=true、端口释放，再冷启动原比赛版本 4ef48d7。新 PID 1748742，启动等待 135.60 秒；只读对账 ready；完整 preflight 为 warn、0 fail，总耗时 159.36 秒。身份、全部平台账号、Bohrium、Codex、原生宿主、fast、寿命记录、公共工具和代码自检通过；警告为旧赛道/镜像预热事实/已停用经验，不伪称全部 pass。
- 已实际验证：前后 Runs49、Trials130、Jobs163、Sandboxes67、Submissions14 完全相同，新科研/提交数量 0。日志 `.package-checks/cs-up20/w8-clean-cold-start.jsonl`。有界审查核对归档范围、运行时无引用和旧历史未重写；diff 检查通过。
- 尚未验证：候选版 3 的新代码冷启动留 W11 发布；本项验证清理后的当前比赛版本。
- 阻塞项：无。初次清理把 validation 误认为文件，检查即停止，未移动任何项；初次冷启动使用 60 秒窗口超时，但同 PID 存活，继续观察到健康，未重复拉起。随后完成目录归档并从清理后状态重跑上述完整冷启动；初始失败与同进程观察日志保留。

## W9：两端登录与最小原生回合

- 登录复核结论：开发端与比赛端属于同一 Codex 账户，但刷新令牌指纹不同；两端各自的原生登录均有效，比赛 PI/执行者及开发 PI 的真实最小回合全部完成。没有代登录、复制凭据或修改全局配置；不需要重登录。完整比较与原生回执保存在本地私有证据区，不随源码公开。
- 已实际验证：两端账户 ID 均为 `e1668cec-d8d7-4fcf-b1a8-2e679322df56`（相同）；刷新令牌指纹不同。只输出这一比较结论，没有输出指纹/令牌，没有复制凭据。比较证据 `.package-checks/cs-up20/w9-auth-comparison.json`。
- 已实际验证：开发、比赛均使用项目内 Codex CLI 0.161.0；各自原登录目录，比赛 CODEX_HOME 为 `.runtime/codex`。真实最小回合全部 completed、回复 READY，工具调用 0；原生目录、session/turn 身份及字节 SHA 在私有 `w9-{competition-pi,competition-executor,development-pi}.json`。没有创建 Run、Job、沙箱或 Attempt。
- 已实际验证：比赛 Astra xhigh PI 28.04 秒，比赛 Terra xhigh 执行者 32.36 秒，开发 Astra xhigh 16.62 秒；三会话 native model/list 支持 priority，thread/start 返回 priority、enabled=true；不把配置值冒充确认。
- 已实际验证：以当前源码角色文件作为 developerInstructions 的三个最小验证会话，原生前八帧均有对应 roles/pi 或 roles/executor v2。原生文件未改。运行命令 `.venv/bin/python .package-checks/cs-up20/w9-native-probe.py`；返回 0，标准错误为空。辅助脚本只做一次最小回合/目标、拒绝工具请求、关闭原进程，不写全局配置、不代登录。
- 尚未验证：新比赛后端实际创建 Run 时自动注入 v2 与物理 22 个技能，仍留 W11；本项是原生认证与角色传递验证，不把手动注入声明为已发布后端的真实 Run 验证。
- 阻塞项：无；比赛登录有效，不进入设备/安装身份排障或请求重登录分支。有界审查核对本机认证目录、会话参数与原生结果，diff 检查通过，继续 W10。

## W10：原生用量统计与当前限额

- 已实现：`scripts/native_token_usage.py` 为 stdlib 只读脚本；从控制器 session.configuration 按 Run 发现原生日志（SQLite mode=ro/query_only），或显式指定 role=JSONL；统计每角色/小时的 input/output/reasoning/cached token、PI 轮数与首/末请求输入、整轮输入总量及 compaction 观察。只输出计数/身份，日志正文不进入报告，不调用模型、不读认证文件或写账本。
- 已实现：相邻累计快照求差，重复事件/同文件去重；--since 仍读前面的基线；累计回退、没有此前指标基线、缺失字段/文件/截断 JSON 均列 unknown，不把未观察当 0。reasoning 已包含在 output，不重复加总；跨小时请求按用量观察时刻归属，不声称精确拆分请求期间耗时。PI 单轮数据为与选定区间相交的完整可见轮次。
- 已实际验证：`.venv/bin/pytest -q tests/test_native_token_usage_cs20.py` → 6 passed/1.89 秒，覆盖跨小时、多轮输入、重复、since 基线、压缩/重置未知、后来才出现的指标、缺失/截断不泄露正文、数据库及原生字节只读。有界审查核对指标子集、基线与 readonly 连接，diff 检查通过。
- 已实际验证：真实运行脚本读取 W9 比赛两原生记录：21:00+08 小时 PI input 16643/output 5/reasoning 0、执行者 input 13597/output 5/reasoning 0，PI 1 轮首请求 input 16643，未知观察 0；前后 native SHA 不变。证据 `w10-real-native-usage.json`；这些是最小验证回合，不是科研吞吐量样本。
- 已实际验证：2026-10-09T13:46:23Z，通过比赛原生 `account/rateLimits/read` 只读查询，codex primary usedPercent=40、windowDurationMins=10080、resetsAt=1792049561（2026-10-15T07:32:41Z）；无 secondary 字段。原生接口未给绝对 token 容量，容量 unknown，不从百分比编造 token 上限。`w10-rates.json`，model_turns=0。
- 尚未验证：RH-02 的真实研究用量与 24 小时并发估算，随彩排收集；无绝对配额时是否够用仍可能 unknown。
- 阻塞项：无。初次命令引用不存在的 test_model_usage.py，没有执行测试；实际专项初次 1 failed/4 passed 是测试 fixture 目录已存在，改用独立 runtime fixture 后通过。原错误摘要与失败日志在 `w10-test-command-error.txt`、`w10-tests-initial.log`，通过在 `w10-tests.log`。

彩排只读统计命令：`python scripts/native_token_usage.py --root /home/wmywb/CyberScientist-comp --run-id <Run ID>`；可加 `--since <ISO>` 与 `--timezone Asia/Shanghai`。脚本供监控在开发目录运行，不给科研模型引入开发依赖。

## W11：完整验证与交付

- 已实现：发布快照提交信息使用本卡标记；preflight 检查五个已启用比赛技能，明确停用的经验不再误报缺失，未登记的缺失仍告警。最终审查补齐 native cwd、直接 workdir、code-mode workdir、限定名 read_file 及 shell cd 的凭据相对路径检测。
- 已实际验证：`npm test -- --run` → 25 文件/126 passed，21.83 秒；`npm run build` → TypeScript/Vite 通过，66 modules，2.37 秒。日志 `w11-frontend-full.log`、`w11-frontend-build.log`。最终审查专项 45 passed/13.55 秒；新版 Job 技能专项 16 passed/13.49 秒。`compileall -q src tests checks scripts` 与 `git diff --check` 均 exit 0；`w11-checks.json`。八个内容文件再次与本卡附录逐字比较一致，SHA 清单 `w11-source-exact-content.json`。
- 已实际验证：第一轮全量为修正审查问题中断，608 passed；第二轮按用户停止请求中断，1677 passed/1 failed，失败为旧技能测试仍要求已被授权原文删除的 v4/本地秒级/环境目录。将断言更新为实际的新预检与赛道时限要求，未修改技能原文；两轮分别保留 `w11-backend-initial-interrupted.log`、`w11-backend-stopped-with-old-assertion.log`，均不算全量通过。恢复后的全量从头执行，记录在 `w11-backend-full.log`。
- 已实际验证：发布前保存 135 个经验文件的 SHA，供发布后证明数据未覆盖；GitHub CLI 当前确认源码仓库 isPrivate=false、比赛快照仓库 isPrivate=true。只将本卡运行时投递到授权的私有快照仓库，源码逐项提交留在本地；候选标签的源码 SHA 与快照 SHA 将分别核对，不冒称相同。
- 已实际验证：有界代码审查覆盖停用经验判定、技能门禁、旧别名及凭据工作目录输入；原生报文与科研产出不改写，检测只记录读取意图，没有执行凭据读取。用于部署后验收的脚本放在开发目录私有证据区，比赛目录不新增验证残留。
- 已实际验证：最终完整后端命令 `PATH=<Node22>:<comp runtime bin>:$PATH .venv/bin/pytest -q`，exit 0，1884 passed/4 skipped/2 warnings，1359.90 秒。四项均为 `test_trace_diagnostics.py` 的固定旧 CLI 夹具；Node22 的 bin 中新版 playground 先于用户旧 CLI，被 SHA 门禁拒绝。旧 CLI SHA d231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03、companion 及 S30/S32/S33、H7 历史证据均实际存在。
- 已实际验证：私有证据区只为测试建立指向已核实旧 CLI 的 PATH 链接，不改全局 CLI/配置；`PATH=<historical-test-bin>:<Node22>:<comp runtime bin>:$PATH .venv/bin/pytest -q -ra tests/test_trace_diagnostics.py` → 7 passed/3.44 秒、0 skip，四项全部补验。总计 1888 个唯一用例均已实际通过，额外三项是重复验证，不额外计数。日志 `w11-historical-diagnostics-tests.log`；初次 PATH 仍由 Node22 中新版 CLI 抢先的 3 passed/4 skipped 保留在 `w11-historical-diagnostics-first-path.log`。没有排除、关闭或改写这些测试。
- 已实际验证：`ops release --target comp --commit 91ecfd39717c6b91bd37b88523b01d2c242ee744 --timeout 180` 完成冷启动与只读对账 ready；PID1771900、loaded commit匹配。完整自检 warn、0 fail：Codex inspect有一次workspace routing discovery超时警告，旧赛道与镜像预热事实仍warn，后续真实原生两角色完成；不把原自检改写成全pass。`w11-release.json`、`w11-release-audit.json` 核对245发布文件SHA、八个附录原文、13旧环境描述原字节、10旧ID别名、13新索引、135经验文件不变；运行内容违规0、验证残留0、比赛.git不存在。
- 已实际验证：第一次原生技能接口显示22比赛技能之外的无关插件，物理清单不能代替原生验收。只在比赛专用Codex配置现有features表加入plugins=false；全部其他配置字段相同、全局配置未改、没有读取/复制登录凭据。零模型调用复查22技能，包括17个bohrium-*和5个比赛技能；证据 `w11-plugin-isolation-config.json`、`w11-native-skill-isolation.json`。原生失败检查的Run run_b983fd5c69在模型调用前关闭，历史及失败日志保留于`w11-runtime-probe-index-rejection.*`。
- 已实际验证：新Run run_1b5cdf85b0经真实比赛API创建，使用已发布RunController的_brain_spec/_prime_spec及原生适配器，不手写角色内容。PI Astra xhigh完成21.34秒、执行者Terra xhigh完成29.09秒；双方native清单22、observed_tier=priority/enabled=true、原生前八帧有v2、开发路径及全局AGENTS内容0。使用其真实执行者原生记录和明确标注的应用就绪输出做系统补清单/暂存/官方CLI离线构建；输出与原生日志字节逐项核对，无合并轨迹/叙述进入CLI包，真实提交0。`w11-runtime-probe.json`含原始路径/ID/SHA及构建哈希，原生日志未改写；这不是科研计算或平台科学正确性证据。
- 已实际验证：两个旧非恢复验证Run被非终态容量计数占满上限2，首个创建请求明确409、数据库确认未建Run；临时经设置接口2→3创建验收Run，finally恢复2，不恢复或改写旧Run。两个新验收Run关闭前重新授权allow_model_calls=false，再经control terminate结案，全部历史保留，未增加维护模型调用。最终51Run/130Trial/163Job/67沙箱/14提交，较发布前只有两条验证Run增加。
- 已实际验证：首次发布快照b2cc2dd29c690a74ca71b3af1de687b32ff2ea8c后，刷新含隔离配置的私有快照301993e3c5350ece7237aa5978f34df37fb0fec2；245运行文件/252导出文件/22技能，扫描0，远端main核对成功。候选3本地源码标签指向91ecfd3，私有快照远端标签peeled SHA为301993e3；两种SHA分别记录，未推送公开源码仓库。比赛缓存release-aliases映射候选3到91ecfd3；`w11-final-snapshot.json`、`w11-tags.json`。暂存源码扫描的两处api_token形状命中是未变化的历史paper2arm-task数据集标识，严格按原HEAD同一行及前缀复核，已知秘密命中0，原文保留；`w11-staged-scan-review.json`。
- 尚未验证：RH-02 新赛道提示的新版本/冻结与完整科学闭环，按既有决定在下一步前端创建赛道后完成模板发布，不更改三个已结束赛道。
- 阻塞项：当前无；上述完整、补验与中断结果分别记录，不能混写为某一次全量 1888 passed。


## RH-02 前置复核（用户授权推送与恢复自动提交）

- 开发仓库 main 已从 eaf1891 快进推送到 9789931f8c3ec4ff0ce4082307d628e88e9b9c8e；GitHub refs 读回一致，远端 CS_UP_20_EVIDENCE.md 第 190 行已含 W9 登录结论。公开源码标签 lightchaser-candidate-3 的 peeled SHA 为 91ecfd39717c6b91bd37b88523b01d2c242ee744；私有比赛快照的同名标签仍为 301993e3，二者分别记录。只有三份跟踪文档进入本次补充提交，用户简历、任务文件、原生记录、凭据和私有回执未入 Git。
- 自动提交关闭确实由链路保护触发。数据库留有 auto_submission_paused=1；六次 submission.nonstandard 事件全部发生在 2026-10-08 10:36–11:11（+08），旧提交没有 Worker job_id，其中 Attempt 49916 明确返回 missing_worker_submission / playground-worker/nonstandard-submission-guard。没有新增同类事件。
- 私有快照 b2cc2dd 的设置版本24为 true，301993e 的版本29为 false。后端生命周期维护及评分轮询调用 submission_gate.synchronize_pause，将数据库暂停标记同步为配置 false；W11 两次临时 Run 容量调整共四次设置保存解释其余版本增长。没有逐版本25–28的留存快照，以上是从两端快照、现有控制流和实际操作清单复核的结论，不伪称每个中间版本都有独立审计记录。
- 链路修复已有真实标准 Worker 证据：应用提交 Attempt50211 / Worker27828，实际发送包 SHA ab837a062a1adcc8ec52f14ecf4fc5db8b5c42f8ab41e10d6a3e1c991a98d8ec 与 Worker 核验一致；scored_by=playground-worker/harbor-lbg+trace-score-cli、harbor reward=1、轨迹82.425、accept、final=true。此次只读核对已有回执，没有新建验证提交。仍保留其 N11/N14 扣分和不计季事实。
- 前端在“提交排队与保护”点击“恢复自动提交”，读回设置版本30的 auto_submission=true、system_state 暂停记录0、待发队列0；重新加载后界面显示“自动提交已启用”。后续仅为 RH 创建容量临时改 max_active_runs=3，版本31仍 true，其余功能及 Run 默认设置字段相同。
- 已有去重位于 mailboxes._record_feedback：完全相同的旧回执不会撤销显式恢复，真正变化的非标准反馈仍暂停。专项命令 .venv/bin/pytest -q tests/test_submission_gate_cs13.py -k nonstandard_feedback → 4 passed/6 deselected，5.84秒。该验证为应用测试；原生记录与旧提交均未改写，未重新提交。私有清单位于 .package-checks/rh02/pre-rh-*.json。
