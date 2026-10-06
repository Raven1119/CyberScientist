# 设计调整记录

以下是相对最初“大脑监督 Prime + 双层经验”想法作出的选择。它们以更快获得可信成绩为目标，未证明会提高分数的部分保留可关闭开关。

## CS-UP-06：基线缺陷修复与模型变更评测（2026-10-01）

### W0：只读审计

- 实际基线 `55b8c8c1741866e6e50fd0ca970674d3f214f96a`；开工保留已有未跟踪任务卡和经验。用户提供的完整任务卡为本轮依据，仓库没有同名任务文件。
- 审读两层 v1 全部 10 Run 的 7,220 条持久化原生运行时/系统事件和 65 份审阅帧及回答，产物与评分回执只读核对。交付 `docs/EVAL_V1_RUN_AUDIT.md`，原始导出和哈希只留本机忽略目录。本工作包没有模型调用、沙箱、Job、重评分或平台请求。
- 依任务卡区分科学选择和机制缺陷。Matchgate 第一轮提前结束的已知原因是未知 Job 创建与重复风险；第二轮 40 步规则由大脑提出、执行器实施，不通过题目提示纠正。两个早期高指标只是 Job 重放，不追认为正式本地评分。
- W1 除 F1–F4，还需修复评测目标与授权 note 混用、静默/执行器审阅分支漏传沙箱权限与评测交接、CLI 结果序列化之后脱敏破坏 JSON 转义。Job 列表确实请求平台但分页反复超时，不能把返回本机账本误写成从未查询。旧后端已经修复的拒绝反馈、恢复、混流、DNS 和 manifest 错误单列并保留回归验证。
- 现有完整原生 rollout 文件未找到，不声称持有供应商内部记录；以实际持久化命令通知、大脑输出、审阅帧和回执作为可审计证据。科学计算不在本机执行。
- W0 有界审查检查逐 Run 覆盖、分类证据、当前源码与旧运行版本的区别、分数 unknown 边界。后续不将修复与换模型分别归因，不增加题目科学内容或例外规则。
- W0 交付检查：`.venv/bin/pytest -q` 640 passed、2 skipped（回环监听被沙箱禁止），前端 40 passed，TypeScript/Vite 构建、compileall 和 diff --check 通过。原始审计材料不暂存；没有改动 v1 数据库、封存包或经验。
- 模型前置检查仅调用当前配置的 Linux 原生 Codex 0.155.1 的 initialize 与完整 model/list（includeHidden，100/页，一页结束）；返回 9 个模型，没有 `gpt-6.1-sol`。没有线程、模型 turn 或全局设置修改。沙箱内原生握手因进程关闭失败，允许原生认证/缓存访问后完成只读检查。继续 W1，准确目标不可用时不跑 W2、不用其他模型替代。

### W1：通用修复与未完成验收

- F1：所有受控本地评分经 `_record_score` 保存完整科学结果、科学输入哈希、评分器哈希和产物哈希，并写 `local_score.registered`。按 Run 和当前评分器版本跨 Trial 求各显式 score/points/\*_score 子项的最佳成绩；诊断数值不当成绩。finish 在封存前给实际完整包评分，退步以 `brain.action_rejected.final_package_check` 回给大脑，包含子项、两边数值和候选哈希。稀疏生命周期帧和审阅帧都有完整反馈，不要求主动读轨迹。大脑修正或提供绑定科学输入、评分器和最佳成绩快照的确认 token 与原因；明确确认写 `run.final_package_confirmed`，控制器不组合或替换产物。暂停竞态和最终快照篡改均拒绝。候选包按接受的评分记录哈希核验后用于评测封存。
- F1 缓存：同 Run、确定性科学输入 ZIP（剔除轨迹且规范化 manifest）、评分器哈希相同，直接派生新的轨迹诊断记录，沙箱创建之前复用。修改产物、manifest 或评分器均失效；旧无输入哈希的记录不擅自认定命中。仅加 `local_scores.science_input_sha256`，已备份 SQLite 并实际验证幂等迁移。skill 仅说明正式候选登记接口及控制器确认协议，没有题目方法、参数或答案。
- F2：评分器可声明经过验证的输入路径；启动 Trial 的共用文本和封存预检同时展示题面输出相关路径及评分器接受路径。路径提取明确标为可能不完整；布局不同时提示执行器自行决定，不搬运或补写科学文件。评分前通用校验取代 FigQA ID 特例。五份 scorer.json 只补既有输入/环境协议；科学评分 Python 源码未修改。
- F3：固定公开 Lean 4.32.2（工具链 SHA 固定）与 Mathlib 905b95818eb32af7874a58b427f50c1711a5e96c 的镜像配方，仅含公开工具链/缓存，不含题目证明或答案。配方存在不等于环境可用：后台注册表只接受版本相符的镜像观察回执，公共事实标明 verified/unverified。评分环境声明及固定公开项目的路径/哈希由 scorer.json 配置，不按题目 ID 分支。新准备路径只传小的固定项目归档，连接镜像里的缓存，运行时不下载工具链/Mathlib，不分块传大归档。Job 输入超过 256 MiB 时，预约和创建之前返回实际字节数、预置环境状态及明确确认方式。注册表只加表，科学依赖验证未在本机进行。
- F3 **真实验收阻塞**：Dockerfile 校验 HTTP 200/code 0/result=true。首次创建因 projectId 字符串不能解析为 uint64 被明确拒绝；确认列表无同名项后改整数发送。本次唯一资源创建返回 HTTP 200/code 148888/rpc error，无 ID，结果 unknown。新主机完整私有列表 total=0、同名 0；旧主机只读列表 HTTP 401/code 2000，不能用于否定创建。官方公开 schema 对 projectId/buildType 写成 string，与实际 Go 解码不符，不能照 schema 冒充正确协议。未知预约占用这次唯一私有资源额度，不再次创建，也不改建数据集。两次沙箱、两次 CPU Job 的离线构建及历史证明重评分均 **未执行**，F3 未验收。真实请求用的 Dockerfile SHA 与后续只补描述字段的当前配方 SHA 分别记录在本机账本；两者都没有验证成可用镜像。[官方自定义软件说明](https://bohrium-doc.dp.tech/docs/software/OtherSoftwares/)、[官方 OpenAPI](https://raw.githubusercontent.com/dptech-corp/bohrium-skills/main/docs/api/openapi.json)供核对，真实回执优先。
- F4：旧 Job API 的 pageSize=100 实际有效，perPage 和 jobName 过滤在探针中无效。后台采用最多三页的只读适配器；后页失败不丢前页证据，只匹配控制器唯一名称和已有 ID，不记录其他账号 Job 的信息。数字状态 2 经十个既有 Finished Job 核对；其他未确认数字状态仍保持未知。匹配不到或多重匹配不释放预约。v1 两个 unknown 各做了一次有界观察，仍未找到同名项，保持 unknown；本机事件 Lean #1588、Matchgate 第一轮 #1358 保存这次结论。
- F4 费用 **部分完成**：十个有 ID 的 v1 Job 取得平台 cost 字段，原始金额合计 0.34，币种未注明；0.00 是平台显示精度下的数值，不能推断免费。沙箱、无回执任务和实际总账单仍 unknown。GET 官方 node/resources/price 返回 HTTP 400/code 148888，未得到可匹配单价；公开 Job 定价页只有 JS 容器，不能据此编造费率。`eval report` 从本机 Job 回执投影重新生成原始金额、覆盖项数和缺项；前端保留总额 unknown，同时标明 Job 原始金额“币种未确认，非总费用”。[官方计价说明](https://bohrium-doc.dp.tech/docs/bohrctl/pricing/)说明 Job 机时价格随机型，未证实旧 API cost 的币种和沙箱费率，因此不外推或硬填估算。完整账单/估算验收仍未满足。
- F5：评测 authorize 的 objective 明确传完整题面，授权备注不再当研究目标；生命周期与 shadow/requested 共用包含 Job、沙箱、GPU、下载和评测隔离边界的授权事实。共用执行任务文本明确反映已授权 Job/沙箱，而非误写只能 Job。结构化 bohr 输出逐字符串脱敏后再序列化，修复引号破坏 JSON。评测冻结题目级模型选择，兼容旧冻结记录，不改全局 CLI、认证或默认设置。这些修复基于接口事实，不调整科学策略、停止规则或题目经验。
- 验证额度：W1 新科学沙箱 0 分钟、新 CPU Job 0、新真实研究 Run 0；唯一私有镜像请求保留 unknown，其费用 unknown。应用单测全部是假协议/临时 SQLite；新环境不因 fake 通过而标成真实可用。SQLite 在 `.package-checks/cs-up-06/migrations/` 做一致备份后才加列/表，两次初始化通过；原有 recovering Run 未启动、重启或修改其授权。

- W1 有界代码审查核对：不加入评测题方法/参数/答案；通用 scorer 输入/环境声明替代运行时题目 ID 分支；真实环境没有凭 fake 晋升；最终快照须与接受的评分记录绑定；评分期间暂停不得被 finish 覆盖；只读成本查询不覆盖原创建回执。最终完整 pytest 664 passed、2 skipped，前端 40 passed、构建/compileall/diff --check 通过。F3 实环境和 F4 完整金额仍未验收，代码通过不等于整个 W1 已满足。

### W1 接续：固定项目构建与有来源的沙箱估算

- 有界复查发现预置环境准备只连接依赖缓存，没有构建评分器声明的固定公开项目。现在先执行固定版本 Lake 的 `--no-cache build`，禁用 Mathlib 自动下载缓存的更新钩子，并限制 Git 为本地协议；构建日志进入 stderr。失败或 unknown 的构建回执阻止评分。fake 先复现遗漏及两种失败，再验证修复；没有增加证明内容、科学方法或题目路径规则。这仍是应用流程验证，未替代 F3 的真实环境验收。[固定版本 Lake 参数](https://github.com/leanprover/lean4/blob/v4.32.2/src/lake/Lake/CLI/Help.lean)和项目锁定 Mathlib 的 lakefile 用于核对参数。
- F4 价格接口的初次 HTTP400 查询没有 SKU，不能泛化成“所有价格接口不可用”。只读资源列表后携带 Node SKU 查询实际返回 `price=0.8`，但 Node 单价不能视为沙箱单价，因此不混用。
- 经现有后台 `_native` 执行一次只读 `sandbox machine list --output json`，获得沙箱自身的公开报价及单位：`c2_m4_cpu` 为 `0.16 RMB/h`、`c4_m8_cpu` 为 `0.80 RMB/h`。脱敏原始输出 SHA-256 为 `518bef14508b14b57ede737acc60ee3eaebb491ee0c03dec621c24032f446844`，完整回执仅在忽略目录。应用严格检查 CPU SKU、规格和币种/小时单位，逐 Run 留存报价事件；未知单位或冲突 SKU 不推定价格。
- 模板创建时实际硬件只在原生创建回执中，删除回执会覆盖当前 receipt。网关现在单独保留绑定 operation_id/sandbox_id 的实际 CPU、内存及已观察 GPU 数量；费用投影优先使用该事实。历史 Lean 第二轮以本 Run #60 的成功原生创建回执核对实际 `2c4g`、GPU0，追加有事件引用和哈希的资源事实；没有改写原请求，也不猜模板配置。不同 sandbox ID、非整数规格和不完整规格有失败回归。
- `eval report` 与前端分别呈现 Job 原始金额、沙箱估算和总额 unknown。沙箱估算采用**当前公开沙箱报价 × 控制器观察生命周期**，不是历史单价或实际账单；未定价项不计零，不与未知币种 Job cost 混加。九个有沙箱的 v1 Run 的估算合计 `0.4065 CNY`；没有沙箱的 Run 保留空估算。两个无平台 ID 的 Job、Job cost 币种及完整总账单继续 unknown。原科学分、封存包、经验和研究配置未改变。
- 沙箱回执脱敏也统一为逐字符串处理后再编码，补测带引号的已知密钥不会因 JSON 转义而漏遮蔽。全部是通用数据/环境契约修复，不新增题目科学内容。W1 新增科学沙箱0分钟、Job0、真实Run0，唯一私有镜像请求仍 unknown，不重复创建。
- 新价格读取只在正常评测调度的工作线程执行，超时/失败只留费用缺项；不阻塞后端事件循环。本地 `_finish_result`、`eval report` 与原回执恢复保持离线，回归检查线程边界及零额外调用。接续只读镜像列表在 15:05 UTC 返回 HTTP200/code0/total0、同名0，仍不足以否定创建；唯一资源预约继续 unknown。已取得的官方 OpenAPI 161 个路径中未发现只读 bill/expense/cost/consumption/balance 路径，这不是“平台没有任何内部账单”的证明。
- 接续最终 `.venv/bin/pytest -q` 为677 passed、2 skipped；前端40 passed，TypeScript/Vite构建、compileall、diff --check通过。全套通过后新增线程/离线边界检查又重跑全套；没有凭旧测试数字认定新代码通过。14个本次待提交文件的已知密钥/1MiB大文件扫描均无命中，原有任务卡与经验不暂存。

### W2：准确模型缺失时遵守停跑边界

当前配置的 Linux Codex 0.155.1 完整原生 model/list 有 9 个模型，无准确 `gpt-6.1-sol`；PATH 中也没有另一份 codex。未作模型 turn，不把 gpt-6-sol 当成目标模型。按本卡仅完成可推进的 W0/W1，W2 两个 eval run 命令不执行，不建假结果或填零分。停跑报告 `docs/EVAL_V2_2026-10.md` 已如实列明 0/10、模型门槛和 F3/F4 未完成验收；不声称“基础设施未知科学分已归零”，也不拆分修复/模型因果。

接续复核（15:12 UTC）：同一原生客户端完整 model/list 已变化，仍为九项；id/model/displayName 均未提供准确目标，新出现的隐藏 Daybreak 条目没有与 gpt-6.1-sol 的可验证映射，不进行别名替代。最新原始字段保存本机，v2报告分清首次与本次观察；用户 PATH 的较旧客户端不构成目标可用性证据。SQLite 中准确标签评测0组、verified环境0项，真实 W2 与 F3验收均未启动。

环境替代核对没有找到可直接接受的回执：Bohrium按 keyword 搜 Lean 却返回其他软件，不能据此声称不存在；锁定 Mathlib 上游 Dockerfile 明示不预装 Mathlib，Kimina 上游默认 v4.26.0，没有取得符合本卡版本的现成镜像回执。版本不符或未验证的公共镜像不能标记成 fixed环境，不租新资源做无据试错；不重复未知私有镜像创建或另建数据集突破一次资源上限。原始请求、上一接续和本次均受同一未知创建/准确模型缺失门槛约束，剩余验收需外部状态变化，不能标成完成。


### 接续：补齐独立原生轨迹（2026-10-02）

本机原生会话索引按十个Run精确根目录及子目录定位到27个现存rollout（15大脑/12执行器），逐文件核对归属和哈希，11,604条JSONL记录、44,391,466字节。原始材料与哈希仅留本机，公开审计新增线程/行号引用并纠正“未显示跨Run读取”：已有自有历史资料确实被读取，重复独立性不成立为已验证事实。没有证据显示读取他人提交或评测经验写入。

本卡未要求无历史盲测，且v1本身使用工作台已有资料/经验；因此不临时增加提示、隐藏资料或改变v2权限来纠正代理的历史复用选择。它作为科学决策及评测条件记录，不能把满分等同无历史独立求解，也不能把重复差异全归因模型。系统缺陷的既有分类仍有原事件/原生证据支持；40步停止规则有大脑原生判据引用，不通过经验改写。

### 接续：原生客户端更新与直接启动原计划（2026-10-02）

用户指出新模型刚更新，并授权更新CyberScientist后开跑；随后取消额外快速题验证。应用模型ID本来就是自由输入，不加白名单或科学内容。官方npm稳定版0.159.3在项目忽略目录独立安装，两包SHA-512校验通过；旧0.155.1保留。只更新应用两个原生执行路径与五个题目模型选择，全局CLI配置、认证、默认模型不变。

新版完整清单11项包含准确gpt-6.1-sol，两角色零turn会话确认xhigh；正式首轮原生线程同样确认模型/xhigh，并有实际输出和用量。旧客户端的停跑观察保留为历史，不能外推为账户永远不可用。[官方文档](https://developers.openai.com/api/docs/models/gpt-6.1-sol)确认准确标识及xhigh支持。

直接执行原计划fast/repeats2/label=v2-gpt-6.1-sol命令，建立eval_95a39bcde778，六项结果队列持久化，首轮run_224c5edd1b运行中。没有额外W1验证Run，临时单题入口没有保留。用户要求直接开跑后先推进不依赖Lean的快速层；F3固定环境验收仍未完成，困难层须保留缺项，不能把环境故障作为科学失败。额度、提交权和经验隔离规则不变，不手工指导科学方法。

两原生适配器既有fake协议回归新增模型参数，确认请求原样传递；真实成功由Run证据另行验证。pytest679通过/2跳过、前端40通过、构建/compileall/diff检查通过。原生轨迹、安装归档、回执、配置和SQLite备份仅留本机。


### W2发现并修复：失败Job的终态映射

v2首轮run_224c5edd1b的Job23455392在原生describe中明确为Failed/exitCode1，但账本仍为accepted；原先旧API适配器仅确认数字2为Finished。两次后端受控只读检查将同一ID的列表status=-1与原生statusStr=Failed、webStatus=-1精确对应。CLI另一个status字段为0，不能与列表枚举混用，也没有将数字0加入终态映射。

通用修复只补旧API的已验证-1→Failed，保留精确名称/ID匹配、终态不降级及未知状态不释放。失败的已创建Job仍占累计Job额度，只释放活跃槽位；不改科研脚本、方法或资源断言。fake复现accepted未更新、外来ID同名不能结算、未知0/999仍unknown、重复观察幂等与累计额度不释放。真实首次账本用已取得的只读证据结算为Failed；核对没有提交/停止中的操作后有界重载后端，以同一Run和原生会话恢复应用修复，预算和started_at保持原值。该轮确实受到原缺陷与部署重载影响，最终v2须标注，不能称始终冻结同一后端版本。

定向网关/对账49通过，全套pytest682通过/2跳过（回环限制）；前端40通过及build沿用本轮模型更新后的检查，前端源码未变。原始回执和部署记录只留本机，公开记录不含账号字段或科学候选。

### W2发现并修复：完整包传输与授权到期队列

run_224c5edd1b #617的完整科学ZIP为33,513,990字节，CLI写入返回COMMAND_FAILED/http400及context deadline exceeded；#618拒绝finish。执行器随后按原身份观察远端ZIP截断并保留回执，评分未启动；原沙箱已删除。#782大脑因此暂停，原队列没有对暂停Run执行授权到期收尾。首轮正式科学分保持unknown，不把Job内的代理评分结果写进正式local_scores。

通用修复：原生CLI已结束但结构化错误中是HTTP deadline时保留unknown，不以HTTP400判断变更明确失败；不自动重发旧操作。后端创建的评分沙箱使用Run绑定的session，并通过bohr2.7.8原生/bohr-workspace对象存储通道传输原ZIP。普通沙箱与/tmp路径保留原行为；调用者不能选择别的Run会话，不继承认证、不挂个人盘、不新建数据集。评分存活时长只收缩到原Run与累计沙箱剩余额度，创建时仍原子复核，不延长授权。来源是当前CLI内置references/sandbox/files.md和真实失败回执，不写题目科学内容。

评测原授权到期后通过既有terminate入口停本机原生会话并回收自有沙箱，记录evaluation.budget_exhausted及前一故障事件号；不租 late scorer，不以0填缺失，不改普通用户暂停语义。首轮#786已实际触发，ended_at为19:05 UTC，墙钟3794.221秒包含暂停与Run外部署延迟，不能声称恰好60分钟收尾；没有在原授权到期后为该Run新增模型turn/Job/沙箱。原第二轮run_a96d4666d4随后启动，原六项队列没有增加重复。第二次有界后端重载只部署应用修复，当前v2包含动态部署及首轮基础设施缺分，不能称为完整干净基线。

fake覆盖原HTTP400/deadline、成功输出含deadline不误判、旧操作不重发、工作区Run归属、原生大文件通道、科学包字节不变、剩余授权收缩和unknown不释放、暂停Run到期不续租及原队列继续。最新完整pytest693 passed/2 skipped、compileall/diff通过，前端源码未改，沿用本轮40 passed/build。后续真实完整包传输尚未完成，不用fake宣布外部故障消失。

额外只读核对F3/F4：配置项目在新平台精简项目列表可见，私有镜像type=1及带projectId查询均total0；这不能否定先前未知创建。新CLI image build的dry-run只显示POST /openapi/v4/sandbox_work/image/build，没有执行创建；与旧v2请求是不同入口，没有据此清空未知预约或再造镜像。F3仍未验收。billing ledger真实只读返回1条resource=consume记录，无资源ID；沙箱历史列表则精确对应13个自有评测沙箱，包括首轮cost0.08/paymentType0。当前CLI契约将paymentType0解释为CNY、1为光子；这些查询时金额可能延迟结算，既不是估算，也不是最终账单。完整回执只存本机；应用实际金额接入待完成，不能将通用consume记录或其他资源费用归到Run。


### W2接续：查询费用、轨迹诊断与固定环境前置

- F4实际金额已接入：原生sandbox list按自有sandbox_id与operation_id双绑定，仅投影这些资源的cost/paymentType。按当前CLI契约分别保留CNY与光子，不混算、缺项不填零；显式0仅是平台查询值，不推定免费或最终结算。完整脱敏回执仅保存在忽略的audit/billing目录，普通consume记录因无资源ID不归因。后端worker在原正常评分收尾做有界只读查询；eval report与前端读取事件，不主动再访问平台。
- 历史查询投影以CLI meta.timestamp记录查询时间，另记recorded_at；延迟落账不能冒称重新查询。2026-10-01 19:06:41 UTC原输出SHA-256为41912eafd920ae2c1cbdcefabf6c52dfaa7449f9163ee9dd2504f737c747492b，v1可见自有资源金额合计0.17 CNY、v2首轮0.08 CNY；均非最终总账单。原Job币种、未知预约及未匹配沙箱仍保留缺项。费用来源和估算在UI与报告分别展示。
- 第二轮abc run_a96d4666d4在原额度内已正常finished，正式科学分20，原生对象存储完整包传输及正式评分成功。首轮unknown不被覆盖。第二轮受应用热部署影响，不能当作冻结单一后端版本的干净样本。
- 第二轮#610轨迹诊断RuntimeError来自应用的20 MB产物证据限制，声明产物39,437,810字节；与科学答案无关。通用上限改为有界128 MiB，保留完整字节/哈希，500文件及路径边界不变；不裁剪产物、不改固定公开评分源码。fake覆盖超过旧上限的原始字节与哈希以及新上限拒绝。仅对原封存包重做离线确定性诊断，得到公开v6检查表100、91对工具调用，保留旧unavailable事件并追加重新诊断事件；没有模型调用或科学重评分。
- 保守运行决策：评分器明确依赖的固定环境必须在付费评测Run创建前可解析，否则该原计划项记录EnvironmentUnavailable且不创建Run、模型会话或计算资源。此规则按环境声明生效，不按Lean或任何题目ID特例，fake验证其他队列项照常推进。F3未知镜像仍占唯一资源预约，不借新版build入口另创资源。原困难层仍只建立一轮两题各两次；固定环境未验收时两次Lean会作为未执行的基础设施阻塞项如实报告，不能声称完成十个Run或基础设施缺分归零。保留其题面、额度和模型，不用替代题目或额外重复掩盖缺项。
- 本阶段有界审查确认费用只归属自有资源、支付单位分别求和、报告不联网、真实回执不进Git、诊断不裁剪产物、环境门禁不新增科学策略。完整pytest708 passed/2 skipped，前端40 passed及build，compileall和diff --check通过。


困难层原命令已实际执行并建立eval_c941ff072c61；两次Lean已在创建Run前记failed/EnvironmentUnavailable，两个Matchgate仍在原队列。首次CLI调用因命令沙箱拒绝回环健康检查而没有建组，未将此视为远端创建unknown；SQLite确认无组后，同一预算预约在允许回环环境执行，只有一个困难层组。最新修复已以同一FigQA-0177第二轮会话恢复部署，原started_at及授权未重置。两层创建命令总预算仍各一轮。

报告生成器发现无Run的预检失败只有eval_results.error、没有result_json，原Markdown遗漏原因。通用报告现在回退到该行error，并有fake回归，科学分仍unknown；不伪造Run资源或数值。定向评测测试24 passed；本次修改后全量pytest708 passed/2 skipped，compileall与diff --check通过；前端源码未改，沿用本轮40 passed/build。FigQA-0177两轮正式科学分均100；第二轮abc20，原首轮缺分仍保留。删除尚未完成的沙箱分钟是过程下界，最终文档和API按deleted_at重新投影，不用早期值冒充最终值。


快速层eval_95a39bcde778现已complete_with_failures：原6次中5次正式评分，abc第二轮20，两道FigQA各两次100；首轮abc的基础设施缺分不重跑或按0计入。可评分子集均值84并非完整六次均值；FigQA两次重复差/样本方差均0。原困难层Matchgate第一轮run_ee8143cd3e已启动，首个CPU Job失败且产物取回，执行器在原额度内自主做CPU沙箱恢复；没有人工科学指导。两次Lean仍因固定环境阻塞未创建Run。比赛提交与产品经验写入保持0。

有界验收复查记录两项统计/语义边界：token依当前累计usage差分算法重建，失败请求未返回usage时不计量，不能冒称供应商最终账单；F1只比较显式score/points，不猜诊断指标方向，同分区间的科学数值提升不触发退步拒绝。保留这一从严边界，不在本轮引入某题fidelity阈值或方法特例。实际最终候选退步拒绝的困难层验收仍待终态。


### F1接续：同分平台期的候选丢失

复查发现原F1仅比较正式score/points，原Matchgate科学指标提升落在计分平台期时，同分占位结果仍能通过。这不满足任务卡要求的原场景候选保留；之前记录的限制不作为完成验收。增加通用、由已审查评分器声明的comparison_contract：只比较明确声明为单调计分输入的字段，支持组件通配路径，不猜其他诊断数值的方向。声明随评分器哈希冻结并原子登记；不改原正式分数、公式、阈值或科学方法，不加入答案、参数或题目ID分支。具体字段只是既有评分输出接口，和输入路径声明一样属于适配契约。

fake现在复现正式总分/两子项分数均0、两项质量已登记更好而最终占位质量退步的场景；finish拒绝、事实值与候选哈希正确，大脑明确确认仍能完成。缓存派生保持声明，不新建或执行沙箱；后续文件编辑不能解释旧登记；无效声明拒绝；评分与声明事件写入失败一起回滚。声明不从科研Run提供，代理不能借输出字段自行启用比较规则；既有科学评分器Python保持字节不变。定向49项通过，完整pytest715 passed/2 skipped；compileall和diff通过，前端源码未变，沿用40 passed/build。真实困难层终态仍待验收。

部署自动审批明确拒绝“活动Matchgate Run中重启后端并修改其评分器声明”，认为可能改变当前评测语义。该脚本没有执行，真实评分器声明未修改。安全替代是等待两次受影响Run均终结后才绑定既有公开单调输入并重载；不改当前Run、评分器Python或研究策略。代码与fake已完成，当前真实v2不能声称平台期退步门禁已经启用；保留为部署/验收缺项，不以本轮成绩替代该证据。

### F3接续：有界公共目录读取

21:23–21:25 UTC按已公布的只读路径完整读取20个公共分类，再读取Basic Image 21/21、Third-party software 42/42及Tools for Agents首100/88,011条版本描述。未观察到固定Lean/Mathlib环境证据。代理工具目录未穷尽，而且缺少描述不能证明镜像内部没有软件；不编造全局不存在结论，也不把目录GET成功算作环境验收。响应文件哈希见EVAL_V2，原响应脱敏后留本机。未知私有创建占用唯一预约，不能用另一份镜像/数据集/节点来绕过；本次仅只读，无新算力或验证Run。

固定revision的上游blueprint配方及Docker CI进一步证实：相关官方镜像名称不代表预置Mathlib缓存；blueprint说明其在启动后才下载。Kimina公共标签查询仅得到连接超时，不能用网络失败证明不存在固定版本。只记录这些证据，不拿明知未满足缓存前提的环境占用W1算力做无效验收；全部原响应与错误记录留本机忽略目录。

后续按公开工具页面确认详情索引采用owner_repository键，而非短仓库名。Lean4及Mathlib4详情均HTTP200/code0并包含镜像URI；元数据分别标v4.12.0-rc1/v4.27.0-rc1。Lean配方安装stable工具链且没有Mathlib；Mathlib配方只clone未固定分支，没有缓存获取或构建步骤。这些是目录/配方事实，不能冒充镜像内固定4.32.2/905b958环境的实测。子域目录返回ClickHouse连接超时，短名详情的no rows也不能推断平台没有工具。不执行混合/向量检索，不调用模型或租VM验证已知缺少固定缓存的声明。

22:22:55 UTC经受控_native使用既有镜像客户端bohr2.7.8的默认私有列表，正确参数为`image list --size 512 --no-interactive --output json`，退出0/ok=true/items=[]/total=0/has_more=false。此前`--json`只在本机报不支持，不算平台目录结果；技能示例的type字符串与已取得OpenAPI整数schema不一致，另用原生默认查询避免依赖该筛选。空目录仍不能确认旧v2异步创建已经明确失败，未知资源预约保留；没有另发build、修改认证或切换Job客户端。原始回执和公开配方仅留本机，哈希见EVAL_V2。

### W2只读核查暴露：临时下载凭证脱敏缺口

旧Job客户端1.1.0的只读详细describe输出带临时签名URL；原脱敏只处理已知账户密钥及accessKey，未处理未知OSSAccessKeyId/Signature等下载凭证。通用修复只遮蔽URL查询中的凭证值，涵盖OSS/AWS/GCS及SAS形式和JSON/HTML/整URL编码，不按Job、题目或供应商账号分支。科学结构中的普通signature字段与分数保持不变，下载仍在原生CLI内部完成，不改变结果文件。新探针回执在本机补脱敏并保留旧/新SHA映射，没有重写冻结科研轨迹；原始回执与链接不入Git。

38个fake在旧规则失败，新增编码值内部的分隔符边界后定向110 passed、全量754 passed/2 skipped；compileall/diff通过。前端未修改，沿用本轮40 passed/build。此代码尚待安全重载，原后台进程仍旧版本；不能把源码检查冒充已全面部署的真实防护。

F4同时取得Job场景完整55机型目录，当前c2_m2_cpu/c2_m4_cpu为0.16、c4_m8_cpu为0.32，引用[官方费用计价页](https://bohrium-doc.dp.tech/docs/bohrctl/pricing/)的Job元/小时单位。与沙箱机型报价分别保存，不能用Node或Sandbox报价替代Job单价；也不能据此改写旧API cost字段币种。目录查询不新建/停止资源，不修改Job客户端或全局CLI设置。完整目录回执SHA为03691d5f180d0b184f51bb81cd3f256df9e13b8d27de03e9b9bd692787108957；应用Job估算尚待接入。

### W2新缺陷：评分沙箱寿命与命令超时脱节

run_ee8143cd3e #2195–2200完整科学包/评分器/公共输入均已上传并解压成功；#2201拒绝finish，原因是固定1200秒命令上限超过按原授权收缩后的沙箱剩余寿命。这是控制器时间计算错误，非科学决策或传输失败。执行器#2329核对三个远端ZIP哈希，随后在原沙箱内自行运行原评分器并取回恢复记录（#2362），在授权内得到64.7854435501222；没有正式local_score登记。#2463大脑暂停等待接口修复，Run原时长到期cancelled，不扩大额度，也不将恢复文件数值直接冒充正式最终包成绩。

通用修复在mkdir、解压及最终评分前重新计算命令上限，取声明上限、当前沙箱剩余时间、原Run剩余时间中的最小值，保留5秒余量。资源已过期、非active或非本Run直接拒绝；普通执行器的显式超时校验保持不变，不重试旧操作、不延长授权。fake先复现原INVALID_COMMAND，再验证传输耗时后的重算及预算/所有权拒绝；已有happy-path fake沙箱过期时间修正为未来，未降低检查。定向78 passed、全量760 passed/2 skipped，compileall/diff通过；前端未改，沿用40 passed/build。

用户任务卡明确授权运行中新程序缺陷修复后继续。自动审批批准了这次仅应用代码的部署：与先前被拒的比较声明变更分开，所有科学评分器/声明逐文件哈希保持不变，比较声明仍延期。后端PID50677→30348，实际健康200；第二轮run_a654e422fd #432/#434按原生恢复同一会话，原started_at、authorization_id及模型配置快照逐值一致，无新Run、额外模型探针或预算追加。真实缩时评分仍待第二轮验收，不由fake推断成功。两层eval report已从数据库重新生成，原首轮缺分及预算到期保留。


| 决策 | 替换的设计 | 原因与影响 |
|---|---|---|
| 三类连接分别建模 | 把 Codex/Kimi、Prime LLM、Bohrium 都放进万能模型接口 | 原生代理有会话/认证/审批，模型有供应商协议，平台有 Job/提交；保留各自语义，避免错误抽象 |
| 控制器处理轮询，大脑事件驱动 | 大脑持续读全量 Trace、询问评分器 | 将模型调用集中在需要判断的变化，普通状态轮询不花推理预算 |
| Prime 保留实验自主权 | 大脑逐条命令 IPython | 大脑限定研究目标和资源，执行器选择具体方法；不建立第二套规划器 |
| 不重写 Prime | 复制其 kernel、工具循环或子代理管理 | 减少维护面，先用固定版本 RPC；仅适配缺口需要局部改动 |
| 本地编排、远程科学计算 | 直接把 IPython 当本地科研机器 | 保留用户既有 Bohrium-first 约束；IPython 作为控制环境，科学产物需远程来源 |
| 编辑态与运行快照分离 | 经验一修改就影响所有运行 | 可编辑性与实验可复现同时保留；下一 Trial 默认采用新版本 |
| 候选经验与已验证证据分离 | Trace 自动写入长期真理库 | 防止模型总结、偶然高分和平台异常变成错误规则；负历史不丢 |
| 首版关闭自动 harness 改写 | Prime /refine 自动改变全局运行方式 | 先量清监督/经验收益，不同时改内核变量；后续只有证据支持才启用 |
| 单 Run、单大脑、单顶层 Prime | 先做多题并发和代理群 | 第一条真实闭环更容易验证；上游子代理需受额度与统计约束 |
| 原生运行时优先，但两者逐个接入 | 一开始同时调试 Codex、Kimi、Prime 和平台 | 先用可用的一种完成垂直切片，第二种不更改核心架构 |
| 不确定提交先对账 | 网络失败立即重试写操作 | 防止重复创建 Job/Attempt、重复扣费和浪费尝试次数 |
| 单轮有界授权 | 每步人工批准或无限自动权限 | 用户一次授权范围内自主执行；预算、项目、资源或提交范围改变才重新确认 |
| 最佳产物冻结 | 新实验覆盖上一轮高分目录 | 保留可随时复现/提交的最佳版本，探索失败不破坏基线 |
| 前端与科学得分独立验收 | 漂亮演示或“agent completed”视作胜利 | UI、外部连接、远程产物、官方评分分别验收 |
| 监督可关闭 | 默认双层架构一定更强 | 以等总预算对照决定是否持续使用监督；不把组织复杂度当能力 |

## 尚未解决的外部事实

当前比赛的完整规则、正式截止时间、准确评分/提交载荷和用户实际可用模型，必须在施工环境连接后确认。本包已提供核查入口与阻塞语义，没有把历史协议假定为现行契约。

施工代理发现接口与设计冲突时，在此追加“事实 / 最小修改 / 实测证据”；不更改旧决定的历史描述，不未经实验扩展为通用框架。

## 施工期记录（2026-09-17，阶段 1）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 本机无 `codex` on PATH，但 `~/.codex/.sandbox-bin/codex.exe`（0.154.0-alpha.6.2）与 `~/AppData/Local/OpenAI/Codex/bin/*/codex.exe`（0.153.4）存在且 `~/.codex/auth.json` 在位 | 大脑选 Codex，可执行文件自动探测（环境变量 → PATH → 两个已知位置）；Kimi 保持未接入边界 | `docs/INTEGRATION_STATUS.md`：`codex --version` 与 app-server initialize 握手原始返回 |
| codex-cli 0.154 的 `initialize` 返回 `{userAgent, codexHome, platformFamily, platformOs}`，无 `serverInfo`/`capabilities` 字段 | 版本从 userAgent 正则提取；capabilities 记录为空对象，能力标记保守（resume/steer/usage 均 false） | 握手响应原文已存 INTEGRATION_STATUS.md |
| 握手成功不代表已登录 | `inspect()` 的 `authenticated` 置 `None`（未知），detail 明示“登录态未由握手验证” | 前端连接卡三分离显示 |
| Prime Agent、bohr CLI 均未安装；`prime-agent --mode rpc` 帧格式无本机核实途径 | 适配器只做 inspect（如实报未安装）+ Demo 执行器；未核实前拒绝启动真实会话 | 启动 connected Run 被 blocked，原因准确列出 |
| 无 WSL2 施工环境确认成本高于收益，且当前交付需在用户机器直接运行 | 阶段 1 后端原生 Windows 运行（Git Bash + uv），记录为偏差；文件锁用 msvcrt | `uv run cyberscientist serve` 实跑 + smoke 22/22 |
| Pydantic 模型定义在 `create_app` 内部时，`from __future__ import annotations` 导致 FastAPI 无法解析 body 模型（实测 422） | 全部请求模型移到模块级 | 修复后 smoke 通过 |
| FastAPI 异常 handler 需与 HTTPException 一致嵌套 `{"detail": {...}}`，且 `JSONResponse` 第一个位置参数是 content | 统一错误信封为 `{"detail":{code,message,recoverable,details_ref?,details?}}` | smoke 断言该形状 |
| 经验修订为内容寻址 hash，回滚必然命中已有 revision | 回滚幂等：指向已有修订而非报唯一键冲突；不制造伪历史 | `tests/test_experiences.py` + smoke 回滚用例 |
| 用户指导文本会进入事件库与操作日志 | 入库前截断（2000 字符）并遮蔽明显密钥形态（sk-/AKIA/Bearer 等） | `controller._redact` + 审查修复 |
| `model_turns` 等授权上限在阶段 1 无真实模型调用路径可强制 | Trial 数/运行时长/大脑判断数立即强制；`model_turns` 在 budget 响应中显式标 `enforced:false` + 原因 | `controller._budget_status` |
| 暂停期间 Demo 执行器仍会发完脚本事件 | 控制器在 pausing/paused 期间只记账不推进 Trial/大脑；恢复时若执行器空闲则重新下发任务（`prime.task_resumed`） | smoke 暂停/恢复/继续闭环 22/22 |
| 官方 install.sh 仅支持 macOS/Linux，Windows 无官方安装路径 | 手动复现脚本行为：R2 发布桶解析 stable 版本 → 下载 tarball + SHA256SUMS → 校验 → `npm install -g`（v0.9.5，190 包） | `prime-agent --version` = 0.9.5；INTEGRATION_STATUS.md |
| Prime RPC 实为 type-tagged JSONL（`{"type":...}`+可选 id 关联、响应 `{"type":"response"}`、`extension_ui_request` 需应答），非 JSON-RPC | 适配器按官方 docs/rpc.md v0.9.5 重写为 `PrimeJsonlClient`；JsonRpcStdio 保留给 Codex | get_state 探针成功，返回字段与文档一致 |
| OpenRouter 免费 GLM（`z-ai/glm-5.2:free`）不支持工具调用；智谱「GLM-5.3-Flash 夜间畅用」免费仅限 ZCode | Prime 执行器模型改用 `deepseek/deepseek-v4.1-flash`（用户授权付费，$0.15/$0.6 每 M token，工具支持）；密钥经 env 引用不入 models.json | 真实工具往返 PASS：ipython 写读文件，成本 $0.00185775，transcript 存 `checks/fixtures/real/` |
| npm 全局 bin 的 `.cmd` shim 不能经 CreateProcess 直接执行 | `PrimeRpc._resolve_argv` 解析全路径并用 `cmd /c` 包装 | spawn 矩阵测试 + 往返探针 |

## 施工期记录（2026-09-18，阶段 1.5/1.6：Kimi 大脑 + 执行系统三选一）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| Kimi Code 2.0（TypeScript 重写版）已移除 `--wire`；程序化接入面是 `kimi acp`（ACP，JSON-RPC 2.0 stdio） | 大脑适配器改为 ACP：`initialize` → `session/new`（**必须带 `mcpServers: []`**）→ `session/prompt` | `checks/probe_kimi_brain.py` PASS；agentInfo=Kimi Code CLI 2.0.0 |
| ACP 流式 chunk 是增量片段 | 空字符串无缝拼接（不可用换行），否则 Decision JSON 被切碎 | 探针 transcript；`brains/kimi.py` |
| ACP 反向 `session/request_permission` 应答形状未按标准形状生效（两种形状实测均判 rejected） | 执行器会话改用 `session/set_config_option {configId:"mode", value:"yolo"}`（引擎内自动批准），工具事件仍全程留痕；保留兜底自动同意分支 | `checks/probe_kimi_executor*.py`：yolo 后零权限请求、写文件 PASS |
| ACP `session/set_config_option` 支持 `model`/`thinking`（low\|high\|max）/`mode` | 思考强度 UI 通用档映射：low→low、medium→high、high→high、xhigh→max；大脑与执行器各自生效 | 探针 v2 实测 setter 返回更新后的 configOptions |
| Prime 的模型流式调用可无超时悬挂（实测 8 分钟死寂、CPU 全闲） | 执行器事件流加 240s 无事件看门狗（`with_stall_watchdog`），产 `trial.stalled`；控制器 abort+记 failed+大脑裁决 | run_7865220639 事件流；run_19c53aed8c 看门狗触发实测 |
| abort 后 Prime 会话拒绝新输入（"queued session input is suspended"）且事件泵已退出 | stall 处置改为：关旧会话、开全新会话、重启事件泵 | run_19c53aed8c `prime.task_accepted rejected` 事件 |
| Trial 正常完成后控制器事件泵退出，同会话下一 Trial 无事件来源（Kimi 执行器实测卡死） | `_apply_decision` start_trial 受理后重启泵（`_start_pump` 回调）；resume 路径同样 | run_82d3af8c4e 卡死 → 修复后 run_9785db28ab 两 Trial 连续完成 |
| Trial done 后 `_active_trial_id` 为 None 导致大脑 packet 丢 `latest_trial_status` | 无活跃 Trial 时回填最近一次 Trial | demo 闭环测试恢复通过 |
| 单用户本地工具，配对码/CSRF 是多余摩擦 | 删除配对码、会话 cookie、CSRF；后端仅绑 127.0.0.1，无任何认证（用户明确确认该边界） | 用户决定；前端配对门已删 |
| Prime 的 `~/.prime/agent/models.json` 手工维护会与 secrets.json 漂移 | 后端托管：secrets/settings 变更与启动时从 `llm_profiles`+secrets 重建 models.json；`_status.prime_models_synced` 真实回读校验 | PUT settings 后 `_status.prime_models_synced=true` 实测 |
| 执行系统选型落地为三选一 | `settings.executor.runtime` ∈ kimi（默认）/prime/codex；包目录仍名 `prime/`（改名 executors 留债阶段 2） | controller._make_prime 分发；run_9785db28ab 默认路径闭环 |
| Codex 执行器无额度无法实测 | `prime/codex_exec.py` 保守实现并显式标「未验证」；不作为默认可用路径宣传 | STATUS.md 未验证清单 |

## 施工期记录（2026-09-18，邮箱双轨：收割/实验）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户要求双轨邮箱：实验邮箱（批量注册、提交主体、每号限 10 次）+ 收割邮箱（唯一、用户提供、只提交实验邮箱已验证的最高分现成包） | 新表 mailboxes（harvest 唯一部分索引）+ submissions（score NULL=未知、operation_id 幂等、收割行引用来源提交）；服务层 `mailboxes.py`，平台适配器 `mailbox_platform.py`（demo / bohrium_playground 骨架报准确缺项） | `tests/test_mailboxes.py` 8 用例全过 |
| `authorizations.max_submissions` 一直只有记录没有消费点 | 本功能成为第一个真实强制点：提交前校验已用/上限，用尽 403 NEEDS_AUTHORIZATION | curl 实测 run_9785db28ab（0/0）被拒 |
| 收割资格必须可机械验证 | 硬条件：confirm=True（UI 手动确认）+ 来源是实验邮箱提交 + 已有官方得分 + 是当前最高分 + 包哈希未变；缺一拒绝并给出准确缺项 | 测试覆盖全部拒绝路径 |
| 外部平台调用（注册/提交/查分）不能在 DB 事务内 | 两段事务：配额原子预占 → 适配器调用（事务外）→ 结果落库；适配器失败释放邮箱配额 | 测试 + 代码审查 |
| GET /settings 响应的瞬态 `_status` 曾被前端整体回写 PUT，落盘进 settings.json（既有 bug） | PUT 时剥离 `_status`；清理已落盘字段；顺手把 contracts/config.schema.json 对齐现实（executor/shadow/mailbox/revision、空字符串默认、llm_profiles 实际字段） | DEFAULT_SETTINGS 与当前 settings.json 均通过 schema 校验 |
| 大脑的 request_submission 动作仍为 deferred | 本轮提交动作只由用户在 UI 发起；代理自动提交仍关闭（授权边界） | STATUS.md 未验证清单 |

## 施工期记录（2026-09-18，Playground 真实适配器接通）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户给的 asp_ token 是**人类账号**凭据（/auth/me → id 90229, userType=human），不是 agent token | 实验邮箱注册改走官方 Option A：人类 token 调 `POST /api/agent/register`，响应立即含 agent 的 asp_ token；收割邮箱直接用该 token 提交 | `checks/results/platform_probe2.json`（/auth/me、/agent/work、/agent/register 列表均 200） |
| 官方完整 API 文档在 `GET /api/docs/dev/AGENT_API.md`（13 篇 /api/docs 文章不含字段细节） | 抓取快照存 `checks/results/AGENT_API.md` 作为适配器依据；提交三步与查分形状按此实现 | 文档快照 + 公开 attempt 的 /score 实测形状 |
| 查分端点评分中是 `scoringState.scoreIsFinal=false`、`score` 可能是中间值 | `fetch_score` 只在 scoreIsFinal=true 采信（displayScore 优先，回退 score），否则如实 None | 真实 attempt 44507 的 /score 响应（evaluating 状态），原文存 `checks/results/score_shape_probe.json` |
| 平台 attempt id 是查分唯一入口，原 submissions 表无处存放 | 新增 `submissions.platform_ref` 列（幂等 ALTER），submit 回执落库，poll_scores 用它查分 | 迁移幂等；73/73 回归 |
| `submit_package` 原签名没有 challenge_id，真实平台提交必须定位 challenge | 接口加 `challenge_id` 与 `meta` 参数；服务层从 runs.challenge_id 取 | tests/test_mailbox_platform.py 9 用例 |
| 写操作（注册 agent / 提交 attempt）需要用户逐次触发授权 | 适配器只实现通路；平台切换后首次真实注册发生在用户点击前端「注册实验邮箱」时；不自动调用 | settings.mailbox.platform=bohrium_playground；前端按钮即授权点 |

## 施工期记录（2026-09-18，Aiyagari 闭环实测 + 提交动作分级）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| hackathon 题评分要求**真实复现图**（attempt 44534 只有 resultsJson 被拒："Please upload authentic result figures"） | 教训入档：此类题提交必须图+resultsJson+ARM bundle 三件套齐 | 44534 两次评分被拒原文 |
| 已提交 attempt **PATCH 405**（draft-only）、hackathon 题 **fork 403** | 图只能在创建 attempt 时挂载；适配器留债：submit_package 需支持 figures 参数 | 405/403 实测响应 |
| 平台评分器会长时间排队/抽风（44579 图比对 pending 超 15 分钟） | 评分等待改服务端后台轮询（45s，异常全吞下轮重试），任何调用方不再同步阻塞等分 | api.py lifespan 轮询；轮询日志 |
| 提交动作分级：实验邮箱=大脑指令自动执行；收割=用户手动确认 | 契约 Guidance.kind 增加 `submit`：控制器事务外自动 submit_experiment（幂等键绑 guidance），不投递执行器；收割三重硬校验不变 | tests 84/84（新增 3 用例）；CONTRACTS.md |
| 首次真实提交 401 根因：邮箱选择未按平台/真实性过滤，误拿 demo 邮箱 token | submit_experiment 选邮箱加 `platform=? AND is_demo=?` 条件 | sub_3bb8d1f26e 失败记录 → 44534 成功 |
| pypi.org 不可达，无 matplotlib | 纯 stdlib PNG 渲染器（checks/gen_figures_stdlib.py）画 4 张真实数据复现图；科学作图正式路径仍属 Bohrium Job（阶段 2） | fig_1..4.png + Fig3 八个 r 点 VFI 实测输出 |

## 施工期记录（2026-09-18，技能管理系统）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 平台题目详情（GET /challenges/{id}）无 skill 要求字段（实测 aiyagari-1994-qje 只有 datasets/figureData/hackathon 等） | 题目级技能绑定由用户在前端勾选，存自建表 `challenge_skills`；平台字段若将来出现可再接入 | 题目详情实测响应 |
| 「启用技能」需对 Kimi/Codex/Prime 三运行时都成立 | 启用 = start_trial 时把技能名称+描述注入执行器任务文本 + 事件 `trial.skills_enabled`；技能本体已物理装在各 CLI skills 目录，CLI 自行发现 | tests/test_collaboration.py 注入断言（FakeExecutor prompt 含技能段落） |
| 技能 frontmatter 有 `description: >` 折叠多行 | 复用项目已有 pyyaml 解析（未手写解析器），描述折叠为单行 | tests/test_skills.py 多行描述用例 |

## 施工期记录（2026-09-18，预算运行时可调）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 大脑判断上限读 Run 启动快照，其余预算（Trial/模型/时长/提交）都读实时 settings 或授权行——同一控制器两种口径 | `_run_one_review` 统一为实时 settings；运行中的 Run 用直接 UPDATE config_snapshot 热改（controller 每次审阅重新读 run 行，免重启生效） | 运行中 Run budget 显示 4/20 且持续推进；tests/test_controller.py 2 例 |
| 预算调整需覆盖两个存储面 | PUT /runs/{id}/budget 分流：大脑/Trial 上限→settings.run_defaults（全局实时）；模型/时长/提交→本 Run authorizations 行（本就实时读取，无需新列） | update_budget 测试 + 事件 run.budget_updated |

## 施工期记录（2026-09-18，大脑出错根因修复）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 提示词只给 `"watchlist":[]` 空数组示例，契约却要求五项必填的 Watch 对象 → 模型稳定输出字符串数组，审阅整单作废 | 双大脑提示词补 Watch 项结构 + "禁止字符串数组"；契约本身不变 | checks/brain_errors.log seq 43/48 报错原文；修复后回归 96/96 |
| Trial stalled 后语义校验拒绝 steer（"需要活跃 Trial"），而停滞现场正是最需要大脑裁决的时刻 → 拒绝死循环 | validate_semantics 加 stalled_trial_id 通道（仅限当前 stalled Trial）；steer 执行时 stalled→active 恢复 | seq 40/54 拒绝记录；test_steer_to_stalled_trial_recovers 端到端 |

| Decision 语义校验整单拒收：一个动作非法，合法动作与经验提议全部陪葬，大脑只能盲重试 | 逐动作校验执行；拒绝原因以 brain.action_rejected 进事件流，大脑下一帧可见并自我纠正；硬约束（授权/预算/方向唯一）保留 | test_decision_per_action_rejection / test_decision_second_direction_op_rejected_only |
| ReviewResult 一处格式错整单作废（笔记、观察范围全丢） | 两级 salvage：注释字段规整 → guidance 单点丢弃降级；全部修复进 brain.review_salvaged 事件，可审计 | test_review_salvage_string_watchlist / test_review_salvage_bad_guidance_downgrades |

| 后端重启后 phase=running 的 Run 无事件循环成僵尸，且控制接口提示"重启恢复"但重启什么都不做 | lifespan 启动对账 reconcile_on_startup：僵尸→recovering + 悬空审阅作废；resume 从 recovering 重建会话并让大脑以 recovery 审阅裁决，不盲目续跑 | test_reconcile_and_resume_after_restart |
| 终止只改 DB 不清理执行器会话（孤儿 CLI 进程） | terminate best-effort abort 执行器会话，成功/失败都记事件；stalled Trial 一并 interrupted | test_terminate_aborts_executor_and_cleans_trials |

## 施工期记录（2026-09-18，大脑自动唤起修复）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| submit_checkpoint 只在产生 review_id 时 notify——review="none" 的进度检查点落库后 shadow 无人唤醒，生产只靠 worker 空闲扫描（最长 60s） | 新检查点（非去重）一律 notify；去重/冲突路径不变 | test_t2/t3/t3b 等 checkpoint 驱动 shadow 用例在 max_interval=3600（关闭周期扫描）下仍即时触发，30/30 |
| shadow 只吃触发词表事件，执行器沉默干活（纯心跳/进度）时大脑永不唤起；max_interval_seconds 形同虚设 | 新增 periodic 兜底：到点且 covered_seq 之后有 executor/user 源新事件才排 shadow（trigger="periodic"）；大脑/控制器自身记账事件不算"新事件"——这是防自激的关键边界 | test_periodic_shadow_wakes_brain_when_executor_silent（唤起+答复后不自激） |
| MCP 桥单次 POST 曾 83s 超时（-32001），检查点上报丢失 | _post 超时 30s→10s，OSError 瞬断重试一次（HTTP 错误不重试）；超时根因未复现定性，标记未验证 | test_mcp_bridge_post_retries_transient_hang |

## 施工期记录（2026-09-18，MCP 桥孤代理崩溃）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 执行器读二进制/GBK 日志把孤代理字符（U+DCA2 类）带进报告文本；桥 _post 严格 UTF-8 编码抛 UnicodeEncodeError，崩溃发生在 HTTP 发送前，桥进程死亡 → 客户端 -32000，且每次重拉必再崩 | encode 改 errors="replace"（U+FFFD 替换，内容保留）；main() 兜底：_handle 任何异常返回 -32603 而不是进程死亡；stdin/stdout 显式 UTF-8（Windows GBK 是同族隐患） | ~/.kimi-code/logs/kimi-code.log 11 次同款崩溃 traceback；修复后真实子进程端到端 exit 0 双响应；test_mcp_bridge_survives_lone_surrogate_payload |
| 桥由 Kimi 客户端每次调用现拉起、模块从磁盘现读 | 修复即改即生效，运行中 Run 零干涉 | 日志显示客户端反复重拉（10:22/17:08/17:13/17:16/17:27 连续崩溃记录） |

## 施工期记录（2026-09-19，经验自进化闭环）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 用户原则：硬门只留「全局经验用户审批」，其余判断归大脑；冲突=更新而非拒绝框架 | proposal 直接落库：题内 active / 全局 candidate；target_id=追加新修订；无去重/动作集硬编码 | grilling 两轮记录；test_experience_challenge_proposal_lands_active / test_experience_target_id_updates_in_place |
| Run 终态是证据最完整的整理时机，但 review worker 在终态后退出 | finish 推迟为 curation 生命周期审阅，_finish_request 钩子在审阅完结后自动 _finalize_run；额度用尽/失败/作废都放行收尾（防死锁） | test_finish_defers_to_curation_then_finalizes |
| 全局整理没有 Run 可依附（用户手动触发） | 一次性大脑会话（brain.open/review/close），产出仍走 proposal 规则落 candidate；内存状态机 + CURATION_RUNNING 护栏 | test_curate_global_experience_runless_session |
| 效果回联粒度用户定为题目级、只在整理时给大脑看 | runs.experience_snapshot 起止各记一份版本清单；usage 聚合只在 curation packet 中出现，平时帧不带 | 同上测试断言 at_start/at_end 与 usage 字段 |
| 执行器拿不到经验正文（设计 A8：不注入，自读） | 任务文本给经验库目录 + executor.md 要求开工前读 active 条目；更新经大脑指导转发 | 测试断言任务文本含「经验库目录」 |

## 施工期记录（2026-09-19，走查修复批次）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 题页「提交与评分」按 run_id 查，跨 Run 提交不可见（用户此前报"二阶段接入"问题） | 新增 `GET /api/v1/challenges/{id}/submissions` 聚合端点；前端优先调之，旧后端 404 时回退 run 级 | WebBridge 实测 4 条全显（verify-2-aiyagari.png）；test_mailboxes 聚合用例 |
| curation 审阅完结依赖 phase=running 钩子，三条路径（obsolete/重启恢复/pause 在途）Run 永远到不了终态 | `_maybe_finalize_after_curation()` 统一收口，不再要求 phase=running，curation 任何终态都放行 finish | test_collaboration 4 个收尾用例 |
| curation 状态纯内存，后端重启后前端永卡「整理中」 | 状态变迁落盘 global_curation.json（原子写）；磁盘 running 残留重启后如实转 failed+interrupted | 重启对账用例；未伪造「成功」 |
| 手动轮询与后台轮询并发可重复记 scored 事件/覆盖分数 | scored 落库改条件 UPDATE（仅 unknown/pending→scored），rowcount≠1 跳过 | test_mailboxes 并发幂等用例 |
| poll 端点在事件循环内同步 HTTP，阻塞全服务 | `asyncio.to_thread` 卸载 | test_polling 慢评分接口下 health <0.5s 用例 |
| 前端 stalled 判定用 `prime.trial.stalled`，后端实际发 `trial.stalled` | 统一为后端实际事件名；labels.ts 批量补齐事件/状态中文映射 | labels.ts 映射表；走查事件流截图 |
| 指导状态 opId 匹配永不命中（后端不回带 operation_id） | 改时间序匹配：只认发送后到达的消费/投递事件，防 SSE 历史回放误判 | ResearchPage.tsx:209-223；构建零错误 |
| MCP 桥兜底分支对非 dict 消息二次 `msg.get` 崩溃 | isinstance 检查 → -32600，桥进程不死 | test_mcp_bridge subprocess 实测 null/数组/标量 |
| 题内 proposal 信任模型自报 challenge_id | scope=challenge 时强制绑定当前 Run 题目，不一致记 experience.proposal_rebound | proposal_rebound 用例 |

## 施工期记录（2026-09-19，URL 导入与弹窗误关）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 「URL 导入需要 Token」是硬编码 502 占位，与凭据无关；平台读端点公开无需 token | url 分支接真实 `GET /challenges/{id}`（to_thread 卸载）；slug 解析白名单；按 platform_challenge_id 幂等 | 真实 curl 三路径（幂等/404/422）；test_import_challenge_url_api |
| 平台题目详情 JSON 自带完整 Markdown 题面（content 字段），无需二次请求 /content | 单次 GET 落库；标题优先 title_zh；contract_status 如实 unknown | 真实响应 5394 字符题面 |
| 原生 dialog 的 click 在「输入框拖选后背板松手」时 target 也是 dialog → 误关 | Modal 改 mousedown+click 双确认背板才关闭 | components.tsx；npm build 零错误 |

## 施工期记录（2026-09-19，算力授权 max_jobs）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| max_jobs 只有 config 默认值，无存储/消费/API，大脑观测到 0 判"不能用 Bohrium" | authorizations 加列（幂等迁移）；authorize/update_budget/_budget_status/观测帧全链路；前端启动与预算弹窗加字段 | test_max_jobs_authorization_roundtrip；真实 Run PUT budget 回读 max_jobs=3 |
| 用户要求改默认 | DEFAULT_SETTINGS 与线上 settings.json 同步 0→3 | settings revision 13 回读 |
| 算力约束仍在提示层（观测帧+提示词），执行器 shell 无硬拦截 | 如实标注留债；硬拦截需钩子进执行器工具层，不在本切片 | STATUS 留债记录 |

## 施工期记录（2026-09-19，门禁兜底与待验收 steer）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| reported_complete Trial 等验收时大脑 steer 被「需要活跃 Trial」拒（事件 seq 363） | validate_semantics 加 reported_trial_id；steer 执行路径本就不改非 stalled 状态，保持验收语义归大脑 | test_semantics_steer_to_reported_trial + test_steer_to_reported_complete_trial_accepted |
| waiting_brain 唯一开门路径是 blocking+intervene 答复；承载审阅被重启作废后永久卡死（事件 seq 369） | 新增 _release_orphaned_gate：无在途 blocking 审阅时放行并留痕；挂 run_loop 启动对账后与回合边界。SILENT 不放行语义不动 | test_orphaned_waiting_brain_gate_released_at_turn_boundary + test_recovery_resume_heals_orphaned_gate_and_allows_start_trial |
| pausing（abort 收据 unknown 时可能长期停留）前端无任何控制按钮 | 终止按钮对 pausing 开放并标注「不等暂停确认」 | ResearchPage.tsx；npm build 零错误 |

## 施工期记录（2026-09-19，Decision salvage 与 kind 枚举）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 经验提议是注释性内容，但结构校验失败整单拒收，finish 主决定陪葬（seq 513-514） | _apply_decision 加 salvage：逐条剔除非法提议（全文留 brain.decision_salvaged 事件），剔除后重验 | test_decision_salvage_drops_only_invalid_proposals |
| 大脑提示词未列 kind 合法枚举，模型自创 'finding' | Kimi/Codex 提示词补「仅限 heuristic/procedure/failure/platform」 | 提示词 diff；真实表现待恢复后观察 |
| blocking 生命周期审阅收到被整单拒的 Decision 后请求标 done 但门禁不开 → 孤儿 waiting_brain | 已由 _release_orphaned_gate 兜底（恢复/回合边界放行并留痕） | 本论恢复后验证 |

## 施工期记录（2026-09-19，常驻目标与 time_limit 热循环）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 大脑以「完成侦察目标+省配额」判断 finish，与用户「满分前不停」意图冲突 | 提示词层写常驻目标（Decision 提示词 + shadow 指令段），不加硬代码闸门 | 恢复后大脑 steer 替代 finish（seq 533） |
| run.time_limit 分支无 await：置 paused 后 continue 空转，同步 DB 写堵死事件循环，垃圾事件 12.5 万条 | 守卫 phase=="running"：只触发一次，随后停泊等信号 | test_time_limit_pauses_once_without_hot_loop；health 恢复响应 |
| 授权时长按墙钟计（含暂停），90 分钟在暂停中耗尽 | 语义保留（有界授权初衷），用户可运行中经预算 API 调整；本次提至 1440 | PUT budget 回读 run_minutes_exceeded=false |

## 施工期记录（2026-09-19，blocking Decision 答复开门）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| blocking 生命周期审阅的答复形态是 Decision，但 start_trial 要求 gate=='open'，开门又只在 ReviewResult 路径 → 答复被自己的门禁拒绝（seq 868） | blocking 审阅收到 Decision 时先同事务开门（rowcount 守卫，只在等待中才记事件）再应用动作 | test_blocking_review_answered_by_decision_opens_gate（事故复现） |
| 资源核对：trisol/wenyon 是平台认证服务而非公开包，PyPI/bohr 查无不等于不可得；最佳尝试 100 分 | 结论记入 STATUS，供大脑下轮 steer 纠正「满分路径不可行」判断 | 平台资源页 + 公开 API + 题面 quickstart |

## 施工期记录（2026-09-19，开局大脑先行探查）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| lifecycle 帧无任何题目信息，大脑开局全盲、只能信执行器转述 | _lifecycle_packet 加 challenge 块（标题/链接/资源清单各帧带，完整题面仅 run_start/recovery） | test_lifecycle_packet_carries_challenge_at_run_start |
| 平台资源清单导入时未落库 | challenges.resources_json 幂等迁移 + 导入存储 + 存量回填 | test_import_challenge_url_api 扩展断言 |
| 大脑提示词一律「不要使用任何工具」，开局无法自查页面 | run_start 触发器解除禁令并要求先探查再规划；其他触发器不变 | 提示词 diff；真实表现待下个 Run |

## 施工期记录（2026-09-19，大脑证据帧盲区）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 执行器关键进展（认证通过/数据就绪）只写在思考流，不落 checkpoint；大脑帧对 progress 只计数 → 基于过期印象误 pause | 帧加 executor_digest（非思考 detail 摘录，尾部 12 条×160 字符，脱敏）；lifecycle 帧事件带 excerpt | test_t10b_executor_digest_reaches_frame |
| 行为层根因：执行器不知道「思考≠大脑可见」 | executor.md 加 checkpoint 纪律清单（认证/数据/任务/评分/阻塞/假设推翻立即落 checkpoint）；brain.md 说明 digest 证据效力 | 提示词 diff；真实表现待恢复后观察 |
| 思考流仍不进帧（信息边界与 token 上限） | 「思考:」前缀过滤，两侧帧一致 | 同上测试断言 |

## 施工期记录（2026-09-19，AskUserQuestion 路由大脑）

| 事实 | 最小修改 | 实测证据 |
|---|---|---|
| 响应帧缺 "jsonrpc":"2.0"，ACP elicitation 路径严格校验判为 RPC 失败 → 回退 request_permission；该回退对提问在当前 CLI 版本无效（选中仍 dismissed） | jsonrpc_stdio 请求/响应补 jsonrpc 字段；声明 elicitation.form 走正道 | 探针 v3：修复后无回退，工具结果含所选答案且代理确认 |
| 全自动系统没有人类在线，执行器提问需要回答者 | 问题路由大脑：executor_question 审阅（小上下文、选项校验、额度记账、140s 超时如实 decline） | test_t10e_executor_question_routed_to_brain |
| 「所有工具请求都应该批准」 | Kimi 执行器 mode=yolo（引擎内全批准）+ 兜底自动批准已在位，无需改动 | 既有探针/生产事件 |
## CS-EV-01 证据入口与准入（2026-09-26）

- PR-1 已获单次授权并完成：`GET https://play.bohrium.com/api/protocol` 返回 HTTP 200，原文 21194 字节，SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`。`contracts/arm_protocol.json` 保存该公开协议及抓取时间、来源哈希；本地完整度仍只叫 `local_estimate`，不冒充平台评分。协议规定七种 typed step 与六个准入信号，至少满足一个。
- PR-2 已获单次授权并完成：本机只读导出 USCT 接续 Run 的事件 3122、3138；脱敏摘录只保留准入与评分字段，不保留操作者身份、原始 manifest 或账号字段，也不进入本次提交。真实 bundle 回执的状态路径为 `bundleStatus=needs_review`，准入路径为 `validation.trace_admission.admitted=false`，规则路径为 `violations[].rule=trace_admission_blocked`。所以上传后必须先拦 `/submit`，保留远端 draft 与本地额度。
- PR-3 已获单次授权并尝试一次：本机配置的 Linux `bohr` 对固定命令 `wenyon dataset download paper2arm-task-reproduce-nonlocal-solitar-243cf090 --version 1 --output-dir ... --output json` 报 `unknown command "wenyon"`，没有文件落地。退出码为 0 但 `_native` 按错误文本判为失败。回执 JSON 形状、目录布局以及 `public_manifest_sha256` 的计算对象**仍未知**；Wenyon 物化即使由 fake CLI 成功也最多标为 `unverified`，`hash_semantics=unknown`。不得用这个失败探针推断账号权限或服务不可用。
- PR-4 未授权、未执行：镜像事实探针 Job 只提供模板与普通受控 Job 路径，真实镜像 API 和结果下载链路未验证。Wenyon 到 `dataset_path` 的映射同样未验证，大于 1 GiB 的输入明确拒绝。
- 数据物化的请求授权绑定发起 Run；即使同题另一条 Run 曾获授权或留下相同 operation_id 的回执，也不能借用其许可。逐文件哈希采用流式计算，避免为最多 1 GiB 的输入加载整份文件。
- 大脑上下文改造只测量，暂不改变审阅行为。后续若 `tokens_last_total` 中位数超过 120000，或 p90 延迟超过 60 秒且静默观察后 20 个事件内方向改变率低于 5%，再单独立项核查事件合并或按研究阶段传递证据。阈值是本地立项条件，不是模型质量结论。
- 回退边界：本次迁移只增加表和列，旧版代码看不到新字段。若新 Run 已处于 `awaiting_budget`，回退前须先提高预算/放弃待处理意图/结束 Run，不能让旧版控制器误以为研究门禁仍开放。

## CS-EV-01 工具链阻塞修复（2026-09-26）

- PR-3 的 `unknown command "wenyon"` 是本机 `bohr 1.1.0` 的命令缺失，不能推断服务、账号或数据集状态。项目忽略目录里已有来自 `@dptech-corp/bohr-cli-linux-amd64@2.7.8` 的二进制，缓存 npm 归档 integrity 与解包二进制一致；Wenyon 1.36.0 扩展二进制 SHA-256 与本地 manifest 一致。复制到 `.cyberscientist/tools/wenyon-local/` 后，隔离 HOME 下 `extension list` 返回 `status=ok`，`wenyon dataset download --help` 返回 0。只为数据入口配置该客户端，保留原 Job 客户端，避免新版 Job 标志/回执协议未经验证就切换。
- 旧版 bohr 的本机错误输出可能把 AccessKey 放进 URL 参数；诊断命令须经后端 `_native` 脱敏或在输出前脱敏，不能直接保存原始 stderr。Wenyon 的新版客户端仍不代表账号服务访问成功，真实下载与哈希语义要等待另一次有界授权验证。
- 第二次获授权的 PR-3 固定命令已到达 Wenyon，返回退出码 3 和 `401 Not authenticated`，无文件。专用 HOME 下新版 bohr 的本地 `auth status` 报 `ak_present=true`/`auth_method=access_key`，Wenyon 的本地 `auth whoami` 报 `not logged in (no state)`。这支持“Wenyon 缺少自身可用的 Vouch 登录态”的诊断，但不能据此推断 AccessKey 是否有效或数据集权限。后端既有 `AUTH_REQUIRED` 分类经真实脱敏回执回归测试覆盖；前端展示同一隔离 HOME 的登录检查提示。开发期间不自动登录、不追加下载尝试，真实数据和 `public_manifest_sha256` 语义仍为未知。

## CS-EV-01 PR-3 认证与清单核实（2026-09-26）

- 用户再次明确授权项目隔离 HOME 内的原生登录，以及登录态通过后的单次同数据集下载。新版 bohr 2.7.8 的 `auth login --ak` 退出码 0；Wenyon 1.36.0 的本地 `auth whoami` 随后通过。子进程的 HOME 与 XDG 配置、状态、缓存、运行目录均指向项目忽略目录，未改用户全局 CLI 配置。登录回执仅保存退出码和输出哈希，不记录账号标识或令牌。
- 唯一一次下载 `paper2arm-task-reproduce-nonlocal-solitar-243cf090@1` 返回退出码 0、`downloaded=2`、`failed=0`、`bytes=1148`；落地 `public-manifest.json`（467 字节）和 `resources/README.md`（681 字节）。本机第四季列表快照登记的 `public_manifest_sha256=0d3e9c45f69a43e78ec263e15f5e9f61b8bf5f479e744ee51541c3cc42d55a64`，恰等于 `public-manifest.json` **原文字节**的 SHA-256，而不等于对解析 JSON 重新序列化后的哈希或下载文件列表哈希。清单中的 README 哈希及大小、题目登记总字节数也完全匹配。完整回执、脱敏摘录、文件及其哈希清单保留本机；本次仅提交文字结论，不提交实验文件。
- 因此 Wenyon 物化仅在有 `public_manifest_sha256`、原始清单哈希匹配、清单为已识别的 `playground-wenyon-public-manifest/v1` 且全部声明文件和总字节数匹配时标 `verified`/`manifest_sha256`；未知清单格式仍 `unverified`，任何可核对的不匹配标 `HASH_MISMATCH`。Run 内物化的 `receipt_json` 保留 CLI 退出码、脱敏 stdout 哈希及非敏感下载计数，供后续审计。本次只是授权探针，不将数据冒充已进入真实 Run/Job；Run 内物化、Job 输入关联和其他数据集格式仍待真实验证。
- 原始 pytest 挂起的最小复现是 `asyncio.run(asyncio.to_thread(lambda: 1))` 在线程返回后不能退出。根因是当前沙箱拒绝 socketpair 的 `send(2)`（EPERM），但允许同一描述符的 `write(2)`；并非已证明的 Python 3.12 缺陷。`tests/conftest.py` 仅在探测到该限制时改用等价的 `os.write` 跨线程唤醒，不改产品运行时。回环监听被沙箱禁止时，真实 CLI SIGTERM 测试明确跳过；在允许回环监听的环境仍执行。

## CS-EV-01 真实 Run 与 PR-4 Job 验收（2026-09-26）

- 本次明确获授权继续真实运行验收和单个 PR-4 Job。Run 限 20 分钟、1 Job、同时 1 个、2 核/2 GB/10 GB、无 GPU，`max_submissions=0`。首次开局 Codex 大脑实际产出合法的 v2 Decision，但 `decision_extraction._extract_json` 只接受 v1，造成误暂停；修复为同时接受 v1/v2，使用同一 Run 的 recovery 控制恢复。实际原始最终消息经修复后提取并通过结构校验，回归测试覆盖 fenced v2 Decision；未改原生代理或授权边界。
- PR-4 模板原写 `c1_m1_cpu`，本次真实只读机器目录没有该规格，最小 CPU 为 `c2_m2_cpu`，故模板及断言按实际目录修正。唯一 Job 经普通网关提交，`purpose=probe`，其冻结输入和数据引用均指向本轮核验过的物化记录；逐文件哈希和远端创建回执均有本机审计记录。列表对账观察到 `Finished`，但描述和结果下载的旧 CLI 回执均为解析错误；新版 CLI 对该旧协议 Job 返回 404。故运行脚本是否成功、镜像事实和远端数据读取一律为 unknown。未创建第二 Job 或 Attempt。
- 审计根目录为本机忽略的 `.package-checks/real-acceptance-20260926T073421Z/`，其中保留数据库迁移前备份、授权/启动/物化/Job 回执、输入哈希清单及下载失败回执。执行器检查点和交付包保留在 `workspace/runs/`。可提交的实验结果概述见 `docs/CS_EV_01_REAL_RUN_ACCEPTANCE_2026-09-26.md`；本次不提交原始回执、下载数据、工作区包或经验产物。此处真实失败反馈只说明当前服务/客户端路径不可用于读取旧 Job 产物，不推广为所有 Bohrium Job 的结论。

## CS-EV-01a 修补（2026-09-26）

- F1：轨迹准入只适用于 ZIP bundle，代理证据门适用于所有提交格式。JSON/CSV 保持 `not_applicable` 轨迹结论，但在预留邮箱和调用平台前检查 `evidence_class=proxy`；显式覆盖标志随 `submission.created` 留痕。
- F2：用户放弃待处理 Trial 意图后，running Run 排入一次生命周期审阅，帧内带原意图与原因；paused Run 等恢复路径处理。额度用尽仍由现有审阅上限路径暂停，避免门禁打开却无人推进。
- F3：`awaiting_budget` 继续丢弃自动唤醒，但保留 `user_steer` 和显式用户审阅。帧提供当前门禁与待处理意图；Decision 的 `start_trial` 仍受门禁拒绝，合法的结束或放弃意图可执行。
- F4：`trace_anti_fraud.admission.thresholds` 提供日志锚点参与字段和修剪后整行的长度上下限。本地检查先判范围再匹配，不截断超长行，避免比平台宽松；缺失阈值时用当前默认值并记 notes。
- D1：`compute_jobs.retrieval_status` 仅追加列；受控 `job download`/`job log` 只有产生新文件且 CLI 回执成功才记 `retrieved` 并记录文件 SHA-256，否则记 `failed` 与脱敏失败事件。研究帧和前端显示取回状态，轨迹只追加终态结果文本，不改配对状态机。迁移前 SQLite 在线备份及真实探针回执均在本机忽略目录。
- 获授权的一次旧 USCT Finished Job 下载探针使用当前 bohr 1.1.0，进程退出码 0，但后端识别 `ok=false`、无文件；错误是当前沙箱 DNS 查询时 socket 权限拒绝，请求未到平台。该结果只能证明**本环境未能取回**，不能区分 PR-4 单例故障与客户端协议故障，也不能宣称所有 Job 均无法取回。本卡不重试、不切换客户端；下次真实 Run 前应在允许网络访问的环境核实取回链路。

## CS-EV-01b（2026-09-27）

- 不带凭据的网络前置检查一次通过：`getent hosts open.bohrium.com` 与 `getent hosts tiefblue.dp.tech` 均解析成功；`curl -sS -o /dev/null -w '%{http_code}' https://open.bohrium.com` 返回 HTTP 301。由此排除了上一轮探针遇到的本机 DNS/socket 权限阻断。
- 选取 USCT 接续 Run `run_16d9dfa230` 中已登记为 `Finished` 的 `668_joint_budget120_v1`（平台 Job `23424706`）；原 `trial_66895a856c/job1_results` 下已有 22 个结果文件。仅通过 `compute._native` 对当前 Job 客户端 bohr 1.1.0 执行一次只读 `job download`。进程退出码 0，但 `_native.ok=false`，脱敏 stdout 为 `Error: json: cannot unmarshal object into Go struct field RespErr.error of type string`，stderr 为空，新目录文件数 0，故无新旧文件哈希可逐一比对。完整脱敏回执和空输出目录仅保留于 `.package-checks/job-retrieval-probe-net-20260926T160849Z/`，未重试、未换客户端、未创建 Run/Job/Attempt。
- 该次错误已越过网络前置检查，不是上一轮的 DNS/socket 权限拒绝。最初按探针分支将其归类为旧客户端取回失败，并计划在下次真实 Run 前评估协议；随后同轮根因核查发现是后端传给旧客户端的 API host 错配，已按下文修复。失败探针本身不能证明所有远端 Job 都不可取回。
- 受控 `job download` 与 `job log` 的最近一次回执现在分别保存在 `receipt_json.retrieval.download` / `.log`；历史单字段回执按操作迁移。`download_ever_retrieved` 保留已成功下载的证据，使后续日志或下载失败不会把汇总状态降为 failed；未曾成功下载时汇总取最近一次操作结果。每次仍留原有成功/失败事件，研究帧与轨迹按事件截点计算相同汇总。前端继续读取账本汇总状态。
- 后续根因核查修正了本节的临时阻塞判断：旧 USCT 文件原由 `job log` 中嵌入的 ZIP 经 `recover.py` 恢复，不是 `job download` 的历史成功证据。旧客户端的下载请求先访问 `GET /openapi/v1/job/{id}`；后端此前强制给 bohr 1.1.0 设置 `OPENAPI_HOST=https://open.bohrium.com`，该主机对此旧路由返回 HTTP 404，错误信封的 `error` 为对象，恰触发旧 Go CLI 的 `RespErr.error` 字符串反序列化错误。同一 Job 在 `https://openapi.dp.tech/openapi/v1/job/{id}` 返回 HTTP 200、`code=0`。故障根因是**应用子进程 API host 错配**，不能解释为远端 Job 没有结果或必须升级客户端。
- 仅给旧 Job 客户端子进程及其连接检查改用 `https://openapi.dp.tech`，不改用户全局 CLI、不切换 bohr 版本；Wenyon 新客户端仍走 `https://open.bohrium.com`。同一 USCT Job 的 `job download` 随即成功：下载一个 1,900,228 字节的 `out.zip`，ZIP 校验通过，24 个归档条目中的 22 个与旧恢复目录逐文件 SHA-256 一致。PR-4 Job 也成功取回 582 字节 `out.zip`，其中 `results/facts.json` 与 `results/data-proof.json` 可读取。受控网关此前只查裸 `results/facts.json`，现从旧 CLI 的 `<job_id>/out.zip` 有界读取指定成员，不解压归档路径；实际受控下载已将 PR-4 `retrieval_status` 标为 `retrieved` 并登记 `image_facts`。PR-4 的远端 describe 回执给出 `Finished`、`exitCode=0`，数据证明与已登记的 `verified` 物化记录哈希一致；仍不据此宣称平台评分或科学结论。完整回执、归档和哈希清单保存在本机忽略目录，未提交原始实验文件。

## CS-UP-01（2026-09-27）

- U1：`contracts/arm_protocol.json` 的 `tooling.recorder.trace_row_selection` 是本地选行的依据。公共顶层目录先确定包根；随后按 manifest 字符串指针、`traces/` 优先于 `trace/` 的目录扫描、旧式 JSON 数组依次选行。协议原文规定 `manifest_pointer.value_type` 不满足时忽略并尝试下一规则，所以旧的字典 `trace` 在选行时进入目录扫描，封存后改成规范字符串；其他非字符串/字典类型拒绝为 `INVALID_PACKAGE`。指针是以 `.jsonl` 结尾的字符串但目标不存在时记录 unresolved claim；未封存的准入判为 blocked，封存可用实际选中行修复指针。显式 ZIP 目录成员也参与公共顶层目录判断；缺失根 manifest、无法解析、重复成员和保留路径冲突均拒绝。封存只追加包根内的合并轨迹和数据出处，原执行器文件保持原字节；准入仅检查封存后的字节。未选中的行不能点亮准入信号。
- U2：平台额度以 `(mailbox_id, platform_challenge_id)` 上尚未释放的 `submissions` 预留为唯一来源，读取当前设置的 `mailbox.submission_limit`，不再更新旧 `submissions_used` 列；该列因只加列/表迁移约束保留但不再向 API 输出。旧 `exhausted` 是跨题全局计数的产物，不代表邮箱被停用，初始化时恢复为 `active`；`disabled` 不动。实验邮箱优先继续使用同题已有预留且未满的邮箱；选择、余量复查、冻结预留在同一 `BEGIN IMMEDIATE` 事务内。平台题目 ID 缺失的本地记录使用带 `local:` 前缀的本地 ID，防止多道未关联题被错误合并。
- U3：`displayScore` 是展示分权威值，旧适配器的 `score` 回退值仅保留为暂定且标记缺少 `displayScore`。首次有限最终分为 provisional；同分至少两次、相隔默认 600 秒且当前没有异常才 confirmed。真实旧回执可见 `scoreIsFinal=true`、`state=final`、`workerStatus=null`，因此空 workerStatus 在明确 final 时不单独视为错误；未知且无法判定的状态仍标异常。分项不一致是独立诊断，不覆写展示分，也不单独阻止确认。已确认分默认至少间隔 3600 秒自动复查，到 `roundEndAt+72h`，缺失时到提交后 7 天停止；手动轮询可越过间隔和停止点。经验仅在确认转移时追加结果关联，改分或异常降级时追加撤销事件，历史链接仍可审计，当前效果投影只把未撤销的确认分标为 active。
- U4：所有已出分实验提交都可供用户选择；非最高分、暂定、异常、分项不一致分别给出警示，服务端要求真正的布尔 `acknowledge_warnings=true`，且在预留事务内重算警示，避免评分变化后旧确认越过门禁。包哈希、来源身份、用户手动确认、幂等键和按题额度仍按原约束执行。收割预留事件保存警示及知悉标志。
- 本阶段仅用本机协议快照、已有脱敏证据和 fake 平台测试；未访问账号服务，未启动真实 Run、模型、Job、沙箱或 Attempt。真实平台对新封存包的准入和复评时间线仍需以后有界授权的运行验证。

## CS-UP-02（2026-09-27）

- W1：`max_active_runs` 统计全部非终态 Run（包括 created、blocked、recovering），在 SQLite `BEGIN IMMEDIATE` 中检查并插入，避免并发创建超过上限。原有设置文件若保存了 1，保留其用户可见值；新安装默认 3，可在前端改动。单后端进程锁仍保护 SQLite 和后台轮询所有权，Run 会话、执行器工作目录、令牌、事件和控制队列按 Run 隔离；不开放第二个后端进程共享同一数据库，以免重复恢复或轮询。某 Run 的重启对账失败时把它标为 recovering 并写可读原因；Job 占位保留为 unknown，其他 Run 继续恢复。
- W1：题目模型选择只保存 `runtime/model_id/reasoning_effort`，不保存密钥或可执行文件路径；Run 创建时把它合入非秘密配置快照。已有题目两列为空时，沿用当时全局配置作为旧数据兼容。若题目选了与全局不同的运行时，其可执行文件路径清空，由 Linux 原生发现逻辑查找；缺失会在启动前报错。Prime 模型必须与当前 Profile 一致，旧题目未显式选择时保留旧 Profile 行为。`model_selection` 连接检查只开关原生会话以确认所选模型被接受，不发起 turn；Kimi 设模型失败不再静默沿用默认。提交 `modelTag` 继续读取冻结的执行器配置。
- W1：总览只展示本机账本中的状态与已知得分；沙箱表尚未建立时数量为 0，待 W4 网关接入后自动从沙箱账本计数。未将多个 fake Run 的通过当作真实并行、真实账号限流或真实科研验证。
- W2：活性时钟只由实际研究进展推进：新 Trial/检查点、有效工具进展、指导交付、Job 接受或结果取回、提交和评分；心跳、usage、重复 `bohr job list`、轮询与审阅记账不续命。每 15 秒逐 Run 扫描，运行中且无合法远端 Job/沙箱执行/模型退避时，默认静默 300 秒排 `stall_detected` 生命周期审阅，帧内带组件诊断；修复没有产生进展且第二次到期时追加 `run.needs_attention` 并暂停。正在执行的审阅有单独 900 秒超时；会话失联先重建，执行器原始提示词只在本进程内保留并且仅在已确认空闲后重试，不重放远端 Job。暂停确认未知时保留 `pausing` 并每 30 秒重新核对，不伪造 `paused`。
- W2：模型 429、明确 rate-limit 和额度耗尽错误由同一个保守分类器识别；不确定的协议错误保持普通错误。参考 [OpenAI API 的限流信号](https://platform.openai.com/docs/api-reference/debugging-requests) 与 [官方 `rate_limit_exceeded` 错误码](https://platform.openai.com/docs/api-reference/run-steps/step-object)，但原生 Codex/Kimi CLI 的实际错误文案仍未经真实探针验证。限流只记录脱敏的角色、类型、次数和下次重试时间；有 `Retry-After` 则使用，否则 60 秒起指数退避到 900 秒，连续 3600 秒后暂停并提示。限流尝试不扣大脑判断数、不算审阅失败或执行器中止；重试状态落在每 Run、每角色的 SQLite 表，进程重启后的旧 Run 仍由原 recovery 门禁接管。
- W3：评分轮询分别读取 Attempt 与 `/score`；Attempt 的 `scorecard`、`scoringState`、`bundleStatus`、`updatedAt` 经脱敏和去重成为 `kind=attempt` 回执。分项优先取 Attempt，再兼容旧 `/score`；即使 `/score` 查询失败，已收到的 Attempt 回执仍保存，但不据此推断最终得分。公开 36189 的真实结构含 `harbor_score=100.0`、`trace_score=70.525`、`displayScore=80.0`；按当前一致性公式预期值为 100，因此一致性为 0。本项目历史 46231 的 Attempt 回执没有这两个分项，`/score` 也无 scorecard；这两项保持 unknown，不填零。可提交 fixture 仅保留字段名、类型和必要数值；真实脱敏回执留在忽略目录 `.package-checks/cs-up-02-w3-20260926T211157Z/`。
- W3：`bohrium.host_overrides` 现在可按 `legacy_job` 与 `wenyon` 分组；例如 `{"legacy_job":{"OPENAPI_HOST":"https://openapi.dp.tech"},"wenyon":{"OPENAPI_HOST":"https://open.bohrium.com"}}`。旧平铺 `OPENAPI_HOST` 对旧 Job 客户端仍兼容；平铺值若是新客户端的 `open.bohrium.com`，旧客户端改用已验证的 `openapi.dp.tech`，避免错误路由。新客户端忽略平铺的旧主机和含义不明的自定义旧主机；需要自定义时写入对应分组。应用仅修改隔离子进程环境，不改全局 CLI 配置。
- W3：一次受控 `bohr job list` 因非交互环境缺少 `/dev/tty` 失败；随后以 `bohr job list --json` 只读重查，bohr 1.1.0 在 `https://openapi.dp.tech` 下返回 `ok=true`、退出码 0 和 JSON 列表。前者验证了非交互模式的 CLI 限制，后者验证了旧主机的列表查询；`job submit` 仍未经本包真实验证。原始脱敏列表回执仅保存在上述本机忽略目录。
- W4：沙箱网关使用项目隔离的 bohr 2.7.8、登录态和 `open.bohrium.com`；旧 Job CLI 保持独立。创建在事务内预留数量与最坏存活时长，强制项目 ID、显式 timeout 和 `--request-id=operation_id`；MCP 变更操作使用稳定 ID，远端状态 unknown 时只按 request ID 对账。用户存储、Wenyon/JWT 挂载、继承认证、无期限及保留失败实例未开放。GPU 需单独授权。文件传输仅允许当前 Trial/题目路径，哈希与脱敏回执入账；沙箱 exec 的开始/完成事件投影为成对工具调用。删除请求和最终回收分开记录，远端仍 `destroying` 时保留 `deleting`，后续只读列表确认消失才标 `deleted`，不重复删除。
- W4 真实最小生命周期：第一次创建命令被 bohr 2.7.8 本地 `CONFIRMATION_REQUIRED` 拦下，回执明确未执行、未计费；原 request ID 描述返回不存在、列表为空。受控网关随后对已授权的单次实际创建增加 `--yes`，未更改全局 CLI。第二次创建得到 `data.sandboxID`；默认 `templateID=sdbxagent`，2 CPU、4096 MB。`sandbox exec` 的 JSON 在 `data.exit_code/stdout/stderr` 内；`python3 -c "print(1)"` 返回 0 与 `1`。内联写入小文件后读回字节一致，均有本地 SHA-256。删除命令成功后首个列表仍显示 `status_name=destroying`，稍后的只读对账确认目标不再存在；探针账本的暂态误判已据此修正。回执中的余额以 CNY 表示，但没有沙箱单价、计费时间单位或最终扣费记录，所以**实际计费单位与金额仍未知**。完整脱敏回执、临时探针 SQLite 和文件仅留在本机忽略目录 `.package-checks/cs-up-02-w4-20260926T213030Z/`；该 SQLite 中的夹具 Run 与产品 Run 数据库隔离，没有创建科研 Run、Job 或 Attempt。
- W5：`audience` 缺省为 `both`，老 Markdown 原字节不迁移。大脑帧和清单冻结 `brain/both`，Trial 冻结 `executor/both`；同一 Trial 与审阅帧使用不同边界，避免把执行器选中条目误当成大脑证据。环境事实只接受代码通过已登记的控制器回执事件写入；代理 schema 不允许 `environment`，普通文件编辑和 UI 均只读。沙箱机器/模板/配额、镜像事实和成功的 Job/沙箱客户端主机探测可自动形成全局 active 观察；事件引用、观察时间及 7 天复核期限一并保留。内容冲突追加修订，超期无回执改为带“待复核”的 candidate 并停止注入。旧环境观察不会被推断为当前平台保证；本包仅以 synthetic 回执测试逻辑，未增加外部探针。
- W6：只有新建 Run 的 `config_snapshot.submission_prediction_version=1` 强制 submit 指导带 `prediction_md`；旧 Run 仍可用原指导，手动提交 API 的既有授权和行为不变。缺预测时审阅保留为 silent 并记录可读 `guidance.rejected`，不会建立提交预留。指导预测写入账本，提交幂等哈希只在预测实际存在时包含预测字段，以免旧请求回放改变哈希。实验提交冻结预测，收割提交继承来源文本。审阅帧只从截止序号内已确认的评分事件构造预测与分数配对，分项缺失保留 null，变化相对本 Run 上一次已确认提交；判定只接受本 Run 已确认的预测并追加事件，评分修订或失去确认后使当前判定失效。运行整理素材包含这些配对。迁移前已在本机忽略目录备份 SQLite；本包用 fake 评分/代理验收，未进行真实提交或模型调用。
- W6 后续验收修正（2026-09-27）：上条所述“手动提交 API 的既有授权和行为不变”对新 Run 不再成立。设计 P3 要求每次实验提交都带预测；原实现只约束大脑 submit 指导，手动入口可绕过。现在 `mailboxes.submit_experiment` 根据冻结的 Run 版本标记在读取包和预留配额前拒绝空预测，API 透传预测，前端显示必填输入。旧 Run 仍允许不带预测，原授权、幂等与收割语义保持。此修正经临时数据库、fake 平台和前端测试验证；未进行真实提交。
- W7：大脑专用 MCP `platform_scores` 只经后端匿名 GET 读取本题公开 `/challenges/{slug}/attempts`，不携带账号令牌；执行器能力令牌在后端返回 403。分页遵循本机保存的官方 API 文档 `page`/`limit`/`sort` 参数和历史公开样本的 `attempts`/`total` 结构；逐页直到收齐 total，重复页、total 变化、缺字段和页数超限一律返回 unknown，不把部分样本冒充完整分布。只缓存匿名聚合 10 分钟，本机已确认最佳成绩每次重新读取；作者 ID 与尝试正文不出模块。分档只用 `scoringState.displayScore`，缺失/非有限数不填零；分位数基于实际存在的分项，未知保持 null。该工具仅供分诊参考，不形成优化目标。本包未新增真实公开 GET；外部接口分页在当前平台仍待实际运行复核。

## CS-UP-03

- W3–W5 评分契约复核（2026-09-27 10:15 UTC）：对主选 abc 和任务卡指定备选 MCM 分别只读查询当前题目详情、公开尝试首页，并查询 `/api/protocol`。两题的 `roundEndAt` 均为 2026-08-29 12:30 UTC，当前 `scoring.strategy=arm_v1_1_generic`、`grader_name=null`，题目说明明确没有专属 grader。两题可见的 `late_scored` 尝试均只有 `executability`、`output_coverage`、`packaging`、`result_fidelity`、`trace_quality` 五项 scorecard，缺少任务卡要求拟合的 `harbor_score` 和 `trace_score`。当前协议又明确 `trace_quality` 的轨迹提取后分档为 0/0.5/1，而非历史 0–100 的轨迹评分器；不能把它乘以 100 后冒充旧 `trace_score`。因此不新建备选 MCM Run 或付费 Job 去重复同一评分契约，也不将公开历史双分项提交混入本轮晚交基线拟合。原目标 W3 的双分项基线、W4 的 ≥70/≥80 对照及 W5 留出吻合仍未达成，等待能产生同一目标分项的当前评分轮次/契约，或用户另行明确变更研究目标。脱敏协议摘要和哈希留在本机忽略目录 `.package-checks/cs-up-03-score-contract-20260927T101535Z/`。
- W3 H5–H7（2026-09-27）：后续真实创建回执逐次揭示两个此前未写入公开 Agent API 文档的表单限制：行内 `timestamp` 至多 30 字符，`title` 至多 300 字符。只在发送表单时把带时区的长 ISO 时间戳等价转为 UTC `Z`，把过长标题截至 300 字符并将全文移入 `body`；封存 ARM 包和事实引用不改。H5、H6 的 HTTP 400 均明确声称 `nothing was stored`，因此适配器仅对创建接口带这一精确声明的回执判定无远端副作用并释放预留；旧 H5 记录以同一窄条件单次受控对账。原 H3 创建的错误正文缺失，继续 unknown 且占额度。H7 用新独立意图真实创建 Attempt `46889`，bundle `ready` 且 submit 成功，说明此处表单投影已越过创建与上传门禁；平台 `scoreIsFinal=true` 的展示分 41.43 经约 10 分钟后同值第二次观察被本地确认为 confirmed，仍无独立 harbor/trace 分项，也不据此推断比赛有效性。Run 的两次提交授权仍受原未知创建占用，不以服务端拒绝作为静默扩大授权的理由。
- W3 H4（2026-09-27）：用户要求不再等待后，现有 Run 经原生 `control/steer` 立即审阅并完成只读诊断 Trial，随后由大脑暂停。历史创建路径在内存中用原冻结包和当时的适配器重建为 7 个文本字段、0 个文件字段；20 条行内 trace 都只有 ARM `step_type` 而缺官方创建表单必需的 `type`。这证明一处可复现的契约违规，但原始 HTTP 400 正文和实际 wire 请求未留存，不能证明它是唯一根因。ARM 包内 trace-step 校验通过；另有 10 项 manifest/characterization 的官方 JSON Schema 错误只会影响后续 bundle 阶段。执行器仅在本机 Trial 目录修正两份元数据，科学输出与脚本逐成员不变，修正包离线 schema 通过；没有再次提交。认证的 `GET /attempts?author=<own-id>` 与匿名列表返回相同的两条非草稿，故私有 draft 仍无法排除，原 Submission 继续保留 `unknown/create_sent` 和预留。下一步需要平台提供该账号在原时间窗口的私有草稿及创建错误权威对账；在此之前不以新幂等键重发原意图，额外 CPU Job 对该阻塞无诊断价值。
- W4 预备：真实 abc 基线创建仍为 `unknown/create_sent`，因此先冻结对照设计而不启动变体提交。原轨迹变体以调用时最新事件序号重新投影，会把来源提交之后的 Run 事件混入对照；现从来源封存轨迹中的持久事件引用求截止序号，普通叙述与纯投影变体都用同一截止。纯投影变体先移除来源的表达层轨迹文件，再由已记录事件生成轨迹；无持久事件引用的历史包保守拒绝生成变体。此选择只控制比较条件，不把科学产物哈希一致等同于平台科学分一致；平台效应仍待真实分数验证。
- W0：执行器回合进行中时，原生 usage、reasoning 和消息片段只作为活性证据，不计为科研进展，也不进入大脑审阅帧。私有思考正文不落公开事件；高频片段仅以最多每 10 秒一条的无正文标记持久化，事件泵另记最近到达时间，避免“已到达但尚在队列”的消息触发误重启。原生流看门狗的 240 秒提示先保留忙态与 Trial 状态，由可配置 `stall_seconds` 判定是否重启执行器会话；重启不盲目重放原提示词或远端 Job。大脑 `wait` 可显式给 `duration_seconds`，超过 `max_brain_wait_seconds` 被拒；未给时采用 `stall_seconds`，期限到了恢复普通活性检查。没有活跃 Trial 的空闲 Run 仍按原规则检测。本包只用 fake 会话验证，没有触发真实模型。
- W1：轨迹叙述仅覆盖表达层。校验在封存前执行，事实字段只接受当前 Run 截止序号内的持久事件和包内文件；无效行逐条报告，投影中未覆盖的步骤仍保留。变体只从已确认实验提交的冻结包生成，在既有邮箱额度与本地准入门禁内提交；非轨迹、非 manifest 成员逐文件哈希相同才放行，原始回执和生成包留本机忽略目录。预检工具只读，且只读当前 Run/Trial 的包。科学产物等价限于包内字节，不推断平台评分不变。本包用 fake 平台验证，没有真实模型、Job 或 Attempt。
- W2：评分器是题目目录内的文件与声明镜像，不是后端硬编码题解；版本来自全部文件哈希。科学评分只经已有 Run 沙箱网关执行；控制器传给评分脚本的科学输入 ZIP 不含轨迹，manifest trace 指针也被移除，宿主机只读包、计算哈希和轨迹文本特征。初始轨迹模型固定输出低置信度占位预测，不将其视为达到 70 分的已验证保证；真实权重须等 W4 的受控数据。评分沙箱动作会增加事件，使提交时封存 SHA 改变，因此提交前只在非轨迹字节和评分相关 manifest 相同的条件下，将科学评分结果派生到最终封存包哈希，再按精确包哈希与 confirmed 平台分配对。实验预测引用原本地分数 ID 时可追踪这一派生关系。分项与展示分不一致分别入账，不倒推“正确”的平台分项；真实校准效果仍待 W3–W5 验证。
- W3 运行中发现 abc 题面明确声明 `Nothing is provided as input: the problem statement above is the whole input.`，但平台同时登记一个 `task-public-data` 资源。原先仅凭资源角色就把未下载的 Job 证据标为 `proxy`，使默认实验提交预检返回 `PROXY_EVIDENCE`；本 Run 无数据下载授权，因而大脑暂停。此处只对包含该完整无输入声明的题面，将登记资源视为非必需输入；其他题仍按原代理证据门禁。修复后同一原包默认预检得到 `admitted`、`evidence_class=not_applicable`、`error_code=null`，未使用代理放行参数或下载资源。经后端重启恢复同一 Run，大脑保留恢复审阅；执行器随后用当前 API 复验并在检查点纠正旧阻塞结论。平台是否接受提交及最终评分仍以真实回执为准。
- W3 主选题真实提交创建返回 HTTP 400；本地 Submission 保留 `unknown/create_sent`、无 Attempt ID、预留不释放。同账号认证只读查询可见的 171 条非草稿 Attempt 未发现匹配项，但接口未提供无 ID 的私有草稿对账，不能由此判定远端绝无副作用。适配器原本读取 HTTP 错误正文后丢弃，导致这次 400 原因不可恢复；现改为在后续错误中保留最多 300 字符的脱敏正文，且不把 HTTP 400 自动判为无副作用。任务卡的备选 MCM 题虽公开状态为 `open`，但也已过相同公布截止时间，且科学输入依赖登记的公开数据；本轮未获新增数据下载授权，不能仅凭题面“任务环境已包含数据”推断 Bohrium Job 镜像已有数据。因此不以新 Attempt/Job 试探平台，W4–W5 的真实评分对照等待可确认的实验基线。
- W3 后续只读协议核对：平台当前 Agent API 的创建表单要求行内轨迹步骤的 `type`，而本地曾把封存 ARM 轨迹中的 `step_type` 原样送入创建表单；历史成功提交只使用单条短的回退 observation，不能证明这次 20 步、约 19.9 KB 的行内轨迹符合当前契约。适配器现只把封存包的真实步骤投影为文档列出的行内字段，`tool_result.tool_output` 原文可进入 `body`，包内完整轨迹及事实引用不改。原请求 HTTP 400 的正文已丢失，字段差异或体积是否为根因仍未判定；在原 Attempt 状态 unknown 时不以新 POST 验证。
- W3 额外只读排查：失败实验邮箱与两个曾成功创建 Attempt 的实验邮箱均能通过 `/auth/me`，同为已确认的 agent 账号，不能把基本认证状态差异当成 400 根因。既往成功的另一题在提交时也已过公布轮次截止，故截止时间本身不足以解释本次拒绝。通用 `/attempts?status=draft` 实际仍返回 scored 列表，过滤参数不生效；账号 `/agent/work` 返回推荐题目而非私有草稿。因此这些 GET 不能证明本次创建无远端副作用，unknown 预留继续保留。
- W2 科学评分器真实验收（2026-09-27）：题面 abc 评分器作为项目源码置于 `challenges/local_a619cdef/scorer/`，结果与题面分档保持独立于平台晚交通用 ARM 展示分。首次 Run `run_06316b6fa6` 因 `cpu=2` 收到明确的 `INVALID_ARGUMENTS`，旧网关却记为 unknown；只读 request-ID 查询返回 `RESOURCE_NOT_FOUND` 后才将该历史预留释放。随后 `run_c118eaee44` 仅在本地路径门禁失败，未发远端创建；`run_312f38ada6` 发现 Codex 会话白名单漏列已有产品 MCP 工具，修复后创建真实沙箱，却又遇到桥对长调用 10 秒重试导致操作冲突，以及评分执行中删除沙箱的竞态，最终无分并确认回收。修复策略分别是本地 CPU 语法检查、只对权威拒绝/查无请求释放预留、显式列出执行器已有业务工具、长时变更操作单次等待、执行/传输期间拒绝删除。没有以新 operation ID 重发未知远端请求。
- 同一题 `run_ed3e28c12a` 在修复后通过产品预检，使用声明镜像和 `2c4g` CPU 沙箱得到本地科学分 20，版本 `83c33775ee2e8b33c8241e117492e6aa03d31e583268986e22fae25523f3a071`，并在删除请求后经只读对账确认远端回收。该分数只证明项目评分器对已验证纪录三元组的题面分档运行成功；H7 的平台展示分 41.43 属当前通用 ARM 评分且最终封存包不同，不拿来拟合或声称一致。W3 双分项重复基线和 W4/W5 仍受当前平台评分契约阻断。真实沙箱金额未见回执，保持 unknown。
- 本次 Run 收尾时，大脑数次提供了真实存在的 `event:run_ed3e28c12a:189` 与 `checkpoint:...`，控制器却只接受裸 event ID 或 `run_id#seq`，把 `finish(achieved)` 错拒为缺少证据。现在按产品自身产生的两类引用验证当前 Run 所有权，并保留旧式 event 引用；跨 Run 或不存在的引用仍拒。定向回归覆盖有效事件加检查点和跨 Run 伪引用。修复后通过原生 recovery/steer 恢复同一 Run，最终 `finished/achieved`；原生 curation 审阅为 done，题内经验保存了成功链路及此前失败边界。该收尾修复不产生新科研、Job、沙箱或 Attempt。

## CS-UP-03R

- AgentMaster 本地补证（2026-09-28）：先前 75 条旧轨迹分在平台 API 和 CyberScientist 工作区中没有可下载的对应内容，但这并非全机结论。只读检查独立的 `../AgentMaster/store/T0`，148 个有 Attempt ID 的本地提交记录与评分表相交 71 条；71 条均核对提交状态、题目 ID 和 CLI `--trace` 指向的上传副本，58 条有最终轨迹分。原始 Codex 事件、上传副本、本地投影分别保留哈希，不把投影视为已证明的平台评分输入。2 条本地 grader 轨迹分与后取得的平台评分快照不符、4 条缺本地分；以平台快照为当前分数事实，保留差异。原本“0 条可配对”只适用于平台/API 与 CyberScientist 来源，已在文档标注校正。逐条匹配表与原始文件只留本机忽略目录；系统原生接口修订既有全局经验候选，仍待用户审批；没有运行模型、Job、Attempt 或平台写操作。
- AgentMaster 评分规律复查（2026-09-28）：71 条提交的 CLI `--outputs` 与封存科学输出逐文件一致，但 58 条最终提交的输出树没有完全重复，不能测同包噪声。轨迹事件数、失败命令数的单特征阈值在按整题留出时，普通准确率低于训练折多数类；MP-R 单字段答案差异与科学分差相伴，但辅助推导也变化。决定只提交只读审计代码和脱敏报告，不晋升为生产轨迹预测器、逐题科学评分器或经验规则。平台最终归一化轨迹及逐项科学验算缺失时，保持机制 unknown。详见 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`。
- AgentMaster 未遮蔽回执补证（2026-09-28）：另外 63 份已评分历史回执直接记录 `trace_decision` 与 `trace_factor`，其中 1 份在独立 `harvest/` 目录。确认该引擎版本在这些提交上按 `accept→1`、`review→trace_score/100`、`block→0` 合成展示分；此前 58 条最终旧回执的分数也与相应暂定分段吻合。因旧组判定类别被遮蔽、两组边界附近无样本且当前评分版本未核对，只将该公式记录为历史实测行为，不替换运行时预测契约或声称已复刻轨迹打分内核。诊断代码的 `score_effect` 不是完整分数公式；同字节 FigQA 输出有 0/100 科学分差，故不从输出文件单独拟合确定性科学评分器。新回执与逐 Attempt 证据仅本机忽略保存，公开文档只放汇总。
- AgentMaster 轨迹输入哈希校正（2026-09-28）：在 63 份未遮蔽回执中，不能只因命令路径存在便声称当前文件就是评分输入。60 条路径仍存在，只有 57 条文件 SHA-256 与提交回执的 `native_trace_sha256` 相同；3 条不符，另 3 条原路径已消失。回执哈希在封存 `raw.jsonl`/`raw.upload.jsonl` 索引中找回这 6 条的原生字节：3 条同迭代、3 条其他迭代，来源类别保留。旧组 71/71 也与各自回执原生轨迹哈希相同。回执哈希确认 3 组跨题复用，与 3 条 `N01` 诊断相符。只从按回执哈希确认的本地文件抽取结构特征；仍不把原生输入等同于平台内部最终评分投影。`harvest/` 的科学输出缺封存快照，只计入轨迹和因子规则，不计入逐文件封存输出比较。
- 全账号轨迹扩查（2026-09-28）：用户将范围扩大到所有能取回的代理、实验与收割邮箱轨迹。用当前操作者 `/auth/me`、`GET /agent/register` 核验 15 个关联代理，再与数据库 1 个实验、0 个收割邮箱交叉去重；只读取归属已核实的 89 条可见 Attempt。`GET /attempts?author=...&limit=1000` 没有 total，page/offset 实测不分页，因此不声称含私有草稿。17 条列表称有轨迹，实际可读 8 条、165 个 API 步骤；9 条操作者 `/trace` 为空、`/export-arm` 为 403，其详情没有替代正文或日志。直接实验邮箱凭据可取回操作者视图为空的 3 条轨迹及 bundle；两种视图并存保存，不覆盖负证据。5 份 bundle 只有 4 个不同 SHA，包内选中轨迹可与 API 轨迹严重不一致，其中一份目录扫描得到 3303 条事件/里程碑记录而 0 条有轨迹类型加标题。75 条有旧 0–100 `trace_score` 的提交都没有可取回轨迹；8 条可读轨迹都没有该标签。只做来源分离和描述性结构分析，不以通用 `trace_quality` 训练旧阈值预测器，也不把重复包的非最终评分当噪声。原始材料和逐文件哈希仅在 `.package-checks/trace-all-20260928/`；可重建脚本、结果边界见 `docs/OWNED_TRACE_ANALYSIS_2026-09-28.md`。
- 用户校正与轨迹自查（2026-09-28）：30–70 轨迹因子公式是主办方告知、由用户转述的外部规则，不应称为从历史分数推断的候选门槛。10 条低分段历史展示分与该规则冲突；按 `harbor_score × trace_score/100` 计算虽在样本内吻合，也不是经平台确认的替代规则。当前官方 Agent API 的 `GET /attempts/{id}/trace` 可用于查看有记录的本人轨迹：项目实验邮箱的 3 条既有提交曾取回 10、6、131 步，本轮直接认证复查其中一条仍返回 10 步。操作者身份经 `/auth/me` 和登记关系核验后，对 3 个历史代理的全部 72 条提交逐条只读查详情，均 HTTP 200、`traceCount=0`，无 bundle、raw messages 或其他内容；每个代理各取一条作匿名与操作者 `/trace` 对照，均为空数组，操作者 `/bundle`、`/export-arm` 均 HTTP 403。不能把操作者身份等同于代理本人的 token，也不能由 API 不可见推断平台后台从未保存。当前已授权且可用的读取路径不能恢复这批旧轨迹；原始响应及哈希留本机忽略目录 `.package-checks/trace-self-20260928/`，无平台写请求。
- 后续本机只读复核（2026-09-27）：历史代理的 72 条公开详情均返回 `traceCount=0`，评分说明被标为 redacted；本机 `submissions.platform_ref` 与这些 Attempt ID 的交集为 0。在当前忽略目录可搜索的文本中只找到公开榜单和集成文档提及这些代理，未找到能按 Attempt 归属核验的旧原始包。71 条实时记录的 `harbor_reward` 与 `harbor_score` 则全部精确满足百分制换算（最大误差 0），可确认的只是输出换算层，不是产物到奖励值的题目评分逻辑。继续保留科学评分器与轨迹预测器的不可验证结论。
- W3–W5（2026-09-27）：58 条完整展示分里，任务卡公式只解释 48 条；另 10 条吻合 `harbor_score × trace_score / 100`。随后按原设计预先存在的轨迹 70 分界核对分段候选：低于 70 时取乘法公式，其余取任务卡公式，58 条均在 0.001 内，最大误差 0.000048。可区分的低分样本最高为 69，高分样本最低为 75.925；这段空白不能识别精确切换门槛。只将候选写入只读分析，不替换运行时预测公式或声称独立验证。所有 71 条实时双分项仍缺原始科学包和轨迹；不以总分猜隐藏的内容评分规则，不运行无输入的沙箱、不生成未经验证的新内容预测器。实时组同包重复数为 0，噪声及阈值准确率保持 unknown。
- `score_calibration` 仅接纳同封存 SHA 的本地评分与 confirmed 平台分；现有历史资料符合者为 0。先做 SQLite 忽略目录备份，再只加 `source` 列并重复初始化核对幂等，旧行默认 `realtime`，未来有精确配对才写 `historical`。本轮真实导入 0 行；前端显式展示来源。两个项目 skill 与原生全局经验候选只记录可执行的配对门槛及适用边界，候选等待用户审批。
- W2（2026-09-27）：分类同时看提交创建时刻和回执字段，不用题目**当前**通用 ARM 策略覆盖历史结论。75 条本人记录中，71 条是轮次内双分项、1 条带历史双分项但创建于轮次外，2 条是晚交通用 ARM，1 条待复核；轮次外异常单列，避免混入训练组。71 条分布于 7 题，但没有任何一条可取回原始 bundle；3 条有 bundle 的记录都不属于实时双分项组。缺原始内容时保持特征为空，不用公开他人的内容或自动生成的 starter manifest 代替。
- 同 10 道题的匿名公开背景分页共 43 页、3809 条，逐页只保留状态与三个分数字段，独立于本人表；其中 3406 条有轨迹分。这些背景数据仅用于描述分布，不用于拟合内容到分数的关系。原始分页和两张数据表均放在本机忽略目录，仓库只提交重建代码、fake 测试与汇总结论。
- W1（2026-09-27）：项目数据库只有 1 个实验邮箱、没有收割邮箱；该邮箱原有密钥通过 `/auth/me` 核验。操作者现有凭据的只读 `GET /agent/register` 确认另外 3 个任务指定代理均为其已确认关联账号，但项目密钥库与允许搜索的本机历史审计目录未找到这 3 个代理各自的完整 token。因此按任务卡收窄为只采集它们的公开评分和元数据，内容标为 unavailable；不借操作者身份推断可以读取代理私有内容，也不重新生成 token。
- 作者过滤的 `GET /attempts?author=...&limit=1000` 分别返回 3、15、20、37 条且逐条 `authorId` 匹配，但响应没有 `total` 或页码；不能宣称全历史绝对完整。对已发现的 10 道题另用官方 `/challenges/{id}/attempts?page=...&limit=100` 走完分页（每题公开 `total`），逐条精确作者 ID 交叉核对，0 请求错误、0 已知题目内计数差异。此法不能发现作者过滤列表完全遗漏的另一道题，数据集保留此覆盖限制。
- 官方文档确认本人 bundle 的 `GET /attempts/{id}/bundle`、轨迹的 `GET /attempts/{id}/trace` 以及自动导出 `GET /attempts/{id}/export-arm`。有直接凭据的 3 条 Attempt 均成功取回 bundle；三个历史账号的 72 条列表记录均标记无 bundle、原始消息或脚本。各抽取一条的公开轨迹 GET 返回空列表，bundle/export GET 返回 403；用已确认的操作者凭据重试一条仍为 403。不能把自动导出的 starter manifest 冒充原始科学文件，也不猜测 raw-message 路径。原始回执、身份、包及逐文件 SHA-256 仅在忽略目录 `.package-checks/scorer-re-20260927T132218Z/`；平台资源没有创建或修改。

## 2026-09-28：CS-UP-03R 公开评分源码与证据转换逆向

- 从已安装官方 CLI 的包元数据找到作者公开仓库，固定 `trace-score-cli@81c434907e7b0a2feccc79236f6601f7abbc1d84`。源码引擎为 v6，63 份历史回执为 v8；因此只把公开 reducer、上限、解析和摘要行为标为已验证，不把它接入生产作为已验证的 v8 预测器。完整发现见 `docs/TRACE_SCORER_SOURCE_REVERSE_ENGINEERING_2026-09-28.md`。
- 对本人三份按接收回执 SHA-256 配对的 FigQA 原生轨迹，只执行离线格式转换和检查。当前 Playground CLI `0.1.33` 中顶层 error 会先匹配 OpenCode，令 Codex E008 的 43 事件只剩 1 条 error；最小合成对照也复现。E010 的转换文件在公开 scorer 上触发 N09 / cap 49，E011 无负项。未取得服务端当时最终归一化文件，不把本次复现冒充历史 worker 的完整重放。
- 增加固定源码哈希的离线审计工具，使用原函数和合成裁判数值检验行为；禁用本进程网络、不调用真实评分模型。公共克隆和含原始证据的结果留 `.package-checks/`。本轮不改用户全局 CLI、不创建平台资源、不把未经验证的提示词技巧或评分预测写进生产。

## 2026-09-28：CS-UP-03R 本地科学评分器真实回放

- 完成 FigQA-0177 的规范答案评分器：标准语义答案来自公开 LAB-Bench，固定选项 B 来自封存题面；评分函数不读取历史标签或轨迹。B/C 两种字节内容的 11 条有效历史回放均一致，误差为 0。F000 因生成包与平台接收包 SHA 不一致而排除，保留原始证据；不把错包异常拟合成答案评分例外。
- 未见平台样本覆盖的非规范解析输入返回 unverified，不编造 0 分。公共 benchmark 相等比较不能证明 Bohrium 隐藏解析器全部细节；规范科学评分、封包对应、轨迹准入和展示分分别报告。
- 使用隔离的分析上下文复用生产沙箱网关，显式模型/Job/Attempt 额度为 0，支持收窄分钟上限。原始回执与科学文件全部留忽略目录；新的答案专用 ZIP 不冒充原始 ARM bundle，不伪写精确原包校准记录。
- Paired-block Lean 先行实现和应用测试保留为低置信度实验代码。实际准备遭遇网络故障，虽然已验证 Lean 版本、锁定源码并观察到缓存下载推进，但监督衔接未能在沙箱到期前取得候选评分。其误差和科学反例测试状态仍为 unknown，不与 FigQA 成功合并。失败详情、时长保守上界和后续条件见 `docs/LOCAL_SCORER_REPLAY_2026-09-28.md`。
- FigQA 改为全部输入备齐后一次执行“创建→上传→评分→取回→finally 删除”，再只读对账回收状态。它在后续独立的 15 分钟授权上下文内完成，和前次时长保守上界合计仍低于原 180 分钟预算，两个沙箱不同时存在。


## 2026-09-28：CS-UP-03R Lean 真实验算与验证范围

- 使用固定原始题面、Lean 4.32.2 与锁定依赖复验 4 份历史证明，全部匹配科学 0/100；另对有效证明构造 8 种可追溯反例，实际验证公理来源、确切定理类型、90 分匹配准入和部分分。反例没有平台回执，分别报告，不混入历史一致率。
- 环境准备先按真实 import 下载缓存，主批评分无需等待整个 Mathlib；E000 保留原始全量导入，不通过改写输入假装完成回放。其缓存超时及最后补验上传失败单列为未验证；主批完整证据已取回。详情见 `docs/PAIRED_BLOCK_SCORER_REPLAY_2026-09-28.md`。
- 评分函数数值逻辑保持冻结；确认 4/4 与 8/8 后只更新发布版本的 confidence/notes。报告分别记录实际回放的旧内容哈希与最终元数据更新后的哈希，不将后一版本称作新远端验收通过。
- 间歇 TLS 超时使删除状态曾为 unknown；仅在新的认证 describe 明确返回 running 后据实恢复隔离账本，后续经原生删除对账确认回收。没有放宽授权、重发未知创建或改全局网络配置。两个新增 CPU 沙箱不重叠；累计保守时间上界约 157.063 分钟，原授权为 180 分钟，费用未知。

## 2026-09-28：CS-UP-03R 第四季公开科学评分规则核查

- 按用户要求只读核对官网，确认第四季 60 道、6 轮，选读 16 道不同任务；没有新科研或评分运行。公开响应与哈希留本机忽略目录，交付结论见 `docs/SEASON4_PUBLIC_SCORER_FEASIBILITY_2026-09-28.md`。
- 可复刻性分别核对科学检验、数值计分和评测输入/运行条件。Matchgate 公开端点、重放与完整连续公式，因此列为首选新增候选；DPA4C 的确定性计分公式与机器相关计时分开。声明公开附件不冒充已审读源码。
- USCT 隐藏观测/真值/清零阈值缺失时不能给官方精确预测；CNVkit 能按固定流程重建科学参照也不等于知道所有容差与封顶。当前通用 ARM 字段不覆盖官网明示的整季外部 worker 情形，不用于否定历史专属评分。
- 原始字段复核确认 15 题当前为通用 ARM，DPA4C 为 LLM 且带 ARM fallback；保留 DPA4C 正文确定性公式与 API 策略不一致的观察，不保证当前新提交的实际路由和分数。
- 本轮只写文档，既有评分器及经验不改；不把 Paired-block 的既有历史回放写成这次新验收，不启动沙箱消耗旧额度。


## 2026-09-28：skills 保存与设置页故障修复

用户报告“勾选后无法保存或刷新丢失”。本轮先检查实际 HEAD（`16157b3`）与工作区，保留原有未跟踪任务卡和经验；使用 diagnosing-bugs 与 kimi-webbridge 在独立 Demo 数据目录复现。用户真实连接配置、研究数据及全局 CLI 配置未改动。

| 观察或回归 | 原因 | 本次修复 |
|---|---|---|
| 浏览器勾选 Bohrium Job 后点击“保存设置”，提示成功但后端 `skills.always_on=[]` | SkillsCard 保存自己的 checked；主页面提交的 Settings 没有同步这份选择 | 选择提升到整页 Settings 草稿，主按钮与卡片按钮共用同一次带 base_revision 的设置保存 |
| 先保存技能，再保存其他草稿字段不能落盘（新增前端回归在旧代码失败） | 独立技能接口增加 revision，主页面仍持有旧版本；两份状态相互脱节 | 卡片按钮明确改为“保存设置与技能”；使用保存响应推进整页 revision，不用无版本保护的独立技能写入 |
| 保存等待期间仍可编辑，随后响应覆盖新改动；加载失败一直显示加载中 | 无编辑互斥；加载错误只短暂 toast | 保存期间禁用字段；设置与目录的失败状态提供重试；保存冲突保留草稿，只在用户明确选择放弃时重载 |
| 人工构造非 UTF-8 SKILL.md 后整个 scan_catalog 抛 UnicodeDecodeError | 只处理 OSError，遗漏文本解码异常 | 单文件解码错误走既有元数据回退，保留目录名，其余技能继续可列出 |
| 文案称常驻对所有 Trial 立即生效、大脑也自动得到技能 | 实际常驻列表固定于 Run 创建快照；独立大脑刻意不注入执行技能 | 文案对齐现有架构，不改变大脑、执行器及授权语义 |

前端新增 7 条回归先在旧代码全部失败，修复后全部通过；完整前端 25 passed。首次构建发现新增测试使用了 Testing Library 不支持的 `exact` 选项，移除后 TypeScript/Vite 构建通过。后端完整回归 563 passed、1 skipped；被沙箱跳过的本机回环关闭测试在允许监听后另行通过。compileall 和 diff --check 通过。未添加真实模型或远程平台探针。

WebBridge 对新构建的真实页面验证了勾选/取消、主保存、卡片保存、连续保存与整页刷新。随后从前端导入合成题、额外绑定 Bohrium File，以零模型、零 Job、零提交、零沙箱、禁下载授权启动原生 Demo，运行到 finished；执行器技能事件同时包含默认技能、常驻 Bohrium Job 和题目绑定 Bohrium File，独立大脑记录不注入技能。本轮仅证明本地配置与投递闭环，不代表真实代理已读取并调用每个技能。

本机证据位于 `.package-checks/ui-bug-audit-20260928/`，不提交。一个后台标签页曾加载停滞并发生 WebBridge 命令超时；直连后端设置约 7 ms 返回 200，刷新后未再复现，保留为原因未判定，未把刷新恢复冒充代码修复。代码审查范围为设置草稿/版本、错误恢复、技能目录、投递语义和新增回归；没有修改科学评分、研究策略、原生运行时或付费操作边界。

## 2026-09-28：第二轮界面与运行生命周期故障修复

基线 `961c033`，保留原有未跟踪任务卡和经验。本轮按误操作、授权、证据错配和使用阻塞的影响排序；严重度描述潜在影响，不表示真实付费提交已经发生。通过 diagnosing-bugs 建立失败回归，再在隔离原生 Demo 中用 kimi-webbridge 验证实际页面。

| 优先级 | 已复现问题与原因 | 修复与证据 |
|---|---|---|
| 高 | 提交页取 `runs.items[0]`，研究页选择题目 B 后仍可能向最新题目 A 的 Run 提交；刷新还分段更新 Run/Trial | 优先采用当前题目，提供明确 Run 选择；数据全部到齐再启用提交，拒绝迟到响应；切换清空包路径、预测、候选确认和额外许可。旧代码的回归实际把请求发往 A；修复后测试和浏览器选中 B |
| 高 | 研究页题目详情、Run 详情和检查点请求没有选择身份/时序校验，旧响应覆盖新题目证据 | 校验选择 ID 和请求代次；派生详情必须匹配当前 ID；切换清除检查点，按题目/Run/Trial 重建相应表单；指导草稿按 Run 隔离。延迟响应回归在旧代码失败，修复后通过 |
| 高 | 创建成功、授权失败后再次启动会重新创建 Run；刷新后的 created Run 又被“已在进行中”挡住 | 保留创建 ID，重试先读取其阶段；created 可继续授权，running 只恢复展示，其他阶段不自动重授权。创建响应未知时停止盲目重试并要求先核对。回归覆盖重试、刷新、未知响应；浏览器启动已有 Demo 后 Run 数未增加 |
| 高 | 启动窗口加载默认预算期间可编辑/启动，迟到响应覆盖用户输入 | 默认预算加载完成前禁用授权编辑和启动；关闭/重新打开取消旧加载结果，失败时明确提示手动填写。新增回归先失败后通过 |
| 中 | 任意时间相近的 guidance queued/sent/ack 都可能把用户指导显示为已消费 | 将 operation_id 从控制请求带到生命周期审阅，在同一事务写 `user.steer.review_queued` 和真实 review_id。页面只匹配该操作，文案仅确认进入大脑审阅队列，不宣称执行器接收；同时处理 SSE 先于 HTTP 响应到达。数据库和界面回归通过 |
| 中 | 从其他页面返回研究页时本地选择重新初始化为 null，静默跳到最新题目 | 从应用当前题目初始化；浏览器发现并复现后增加失败回归，修复后页面往返保留 B |
| 中 | 终态 SSE 无限心跳，前端不能归档；隔离 Demo 服务缺少有界退出配置 | 先排空所有事件页，再对 finished/failed/cancelled 返回 EOF；paused 保持可续接。Demo 服务采用 5 秒优雅退出上限。测试覆盖 205 条跨页历史、暂停/恢复及两个服务入口带活跃 SSE 的 SIGTERM |

有界审查检查了异步身份、创建结果未知时的处理、已有 Run 授权、按操作关联回执、终态事件排空和原有授权边界。没有改写代理内核、研究策略、评分器或全局 CLI 设置；新指导事件只表示真实审阅请求已入队，不新增主动核查或强制大脑行为。

实际执行结果：

- `.venv/bin/pytest -q`：568 passed、2 skipped；沙箱跳过的是回环监听退出测试，允许本机监听后 `.venv/bin/pytest -q tests/test_cli_shutdown.py`：2 passed。
- `PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run`：38 passed；`npm --prefix apps/web run build` 的 TypeScript/Vite 构建通过。一次测试 fixture 重复 event_id 引起的 React key 警告已改为独立事件 ID，最终回归无该警告。
- `.venv/bin/python -m compileall -q src tests checks/serve_ui_demo.py` 和 `git diff --check`：通过。
- `checks/serve_ui_demo.py --port 18766 --data-root .package-checks/bug-audit-20260928-round2/workspace` 启动独立无凭据 Demo。合成题目通过原生 API 导入；WebBridge 验证选题/选 Run/清空旧提交许可/页面往返，并从页面对已有 Demo Run 给予零模型、零 Job、零提交、零沙箱、禁下载授权后启动。Run 到 finished、总数保持 2；32 条 SSE 事件与数据库数量一致，读取到 EOF，页面显示归档。三个远程操作账本均为 0。

浏览器验收最初用固定 1 秒等待归档，早于异步状态更新而失败；后续只读核实已归档，脚本改为有界条件等待。账本辅助检查曾误写不存在的 `sandboxes` 表，核对 schema 后使用 `compute_sandboxes` 完成检查。这两项是验收脚本问题，不计入产品缺陷。验收后 Ctrl+C 停止 Demo，进程退出码 0；仍有一个连接在 5 秒宽限到期时被取消，Uvicorn 打印 CancelledError，未使用 SIGKILL，不能称为所有连接都自然结束。原始记录保留于 `.package-checks/bug-audit-20260928-round2/`；不上传 Demo 数据、数据库或原始回执。上一轮偶发标签页停滞根因仍未判定，本轮没有真实科研或平台调用验收。

## CS-UP-04：提交前确定性轨迹诊断与相邻缺陷修复（2026-09-30）

公开 `trace-score-cli` 固定 commit `81c434907e7b0a2feccc79236f6601f7abbc1d84` 的许可证是 MIT，故只将 SHA-256 为 `afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46` 的 `src/index.ts` 和原许可证 vendor 入仓。运行器仅抽取原源码中的确定性 `loadTrace`、`lintTrace`、`collectSubmissionEvidence`、`buildChecklistReport`；不调用模型裁判。Playground CLI 0.1.33 的安装文件 SHA-256 固定为 `d231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03`；仅在临时副本上把 OpenCode/Codex 判断先后的一处条件改为 W1 已核验的 2 行 diff，补丁副本 SHA-256 为 `52b85b55e038e383d0350b153b648c45269e5ff9a98edb5b5454d181f7d5c065`。全局 CLI 和平台协议均不改。

分级阈值在统计前固定：历史 v8 可见阳性至少 5 且闭世界精确率、召回率均至少 0.9 为条件可靠；阳性至少 3 且两项均至少 0.7 为条件提示性；其余不可用／未知。v8 回执未列出的代码可能被隐藏，因此这不是完整 v8 规则的证明。V-CLI-fix 只有 N06、N08、N09、N11、N14 达标；其余代码仅在前端详情供人工核查。完整逐项表、开放世界区间和上限对照见 `docs/TRACE_CHECKLIST_V6_V8_AGREEMENT.md`。

诊断在包封存与平台选行后离线运行，结果与既有准入代码分离；CLI 缺失、哈希不符、转换丢行/丢配对、超时或评分器失败都返回 `unavailable`，不改提交流程。建议只指向真实计算、真实回执、产物因果链和传递缺口。审阅帧只读取实际提交时持久化的同 Trial 摘要；未达标代码造成的更严上限不写进执行器或大脑摘要。前端展示公开 v6 的全量诊断并明确与官方判定的边界。

本轮按影响排序修复的相邻缺陷：**高**，旧 CyberScientist H7 封存轨迹有 43 组已配对工具事件，但 v6 将缺少 `tool_name` 的调用视为 malformed，误读成 0 调用/43 结果；新投影加入真实适配器来源字段与已有命令/详情正文，旧包仅在临时本地诊断输入中补来源标签，封存字节不改，并在评分器配对数不符时返回 unavailable。**高**，执行器包预检工具原本会直接回传完整诊断，与“低一致性代码只在前端详情展示”的边界冲突；工具响应现在只包含达标建议与可归因上限。**中**，预检页变更包路径后仍可显示旧哈希/诊断，现清除旧结果并拒收迟到响应。**中**，审阅摘要可能把无充分历史一致性的检查项上限或其他 Trial 的结论传给大脑，现只持久化达标项可归因的上限并按 Trial 过滤。上述严重度按潜在错误决策影响排序，不表示已发生真实平台提交损失。

## CS-UP-05：本地评测框架（2026-10-01）

评测通过现有题目导入、Run 授权和原生大脑/执行器运行；`eval_results.run_id` 与 Run 在同一事务绑定，重启后从 SQLite 恢复。每次启动冻结经验内容、技能选择、模型和 shadow 开关；题目级模型用 Run 快照中的 gpt-6-sol 覆盖，不改用户全局 CLI 或项目默认设置。`eval_scoring` 是研究完成后的独立阶段，使封存与 Bohrium 沙箱评分可以在重启后继续，同时阻断新的研究判断。相同层级与标签的运行中评测复用原 ID，防止命令超时重试生成重复付费 Run。

评测 Run 的提交入口和经验写入入口在后端拒绝并记事件；`max_submissions=0` 只是额外预算保护。科学评分运行在题目声明的 Bohrium 镜像，封存输入与操作 ID 在本机留存，不能确认完成的执行保留 unavailable。评测允许代理数据证据以及轨迹准入的软拒绝继续做**独立科学评分**，但保留 `data_evidence_class` 和 `admission_error_code`；这不宣称具备正式提交资格，结构性封存失败仍阻断评分。展示分仅按任务卡给出的区间公式计算；轨迹 C 是公开 v6 确定性检查表，本地与历史 v8 的一致性只对回执可见代码成立，不能表述为官方分数预测。Matchgate 的公开数据按固定 SHA 使用；Lean 可信项目和大规模评分环境仍须由真实基线检验。原始包、回执与评测 JSON/Markdown 先留在忽略目录，Git 只收源码、测试和脱敏结论。

W3 启动时，当前公开接口对 FigQA-0177 返回 HTTP 404；第一次快速层命令在评测建档前停止，未创建 Run、Job 或模型调用。历史题面曾由当前操作者本机公开挑战快照保存，且 Matchgate 有既有公开 GET 快照。对这四个非 abc 目录题，只取公开题面字段形成仓库内固定快照，记录来源文件哈希、快照哈希和题面哈希。导入时仍优先尝试当前公开 GET；取回失败才使用匹配题目 ID、且哈希全部核对通过的固定快照。Run 和结果记录来源及题面哈希，报告须标出这些题不是当前公开接口的实时题面；不得由历史 `status=open` 推断当前轮次仍开放。该回退解决赛后题面不可取回导致评测无法启动的问题，不增加平台提交权，也不把历史科学答案或提交包带入评测。

真实 abc 首轮暴露成本账本的时序问题：`eval_results.result_json` 在评分沙箱异步删除前生成，原报告永久显示 `lower_bound_pending_cleanup` 和偏低的沙箱分钟数。现在 `get_evaluation`／`eval report` 按当前 `compute_sandboxes` 生命周期重新计算分钟数；删除前仍标下界，删除确认后才标 `confirmed`。这只校正沙箱占用时间，Bohrium 实际金额仍为 unknown。abc 首轮执行器自评与评测封存后的再评分具有相同科学产物和评分器哈希，但包哈希不同；本轮保留两次独立评分以维持已启动基线的一致性，将可验证的科学分复用列为后续成本优化候选。

FigQA-0177 首轮暴露稀疏审阅反馈缺口：大脑两次以真实事件引用混合 `ReviewPacket.*` 标签声明目标 `achieved`；控制器正确拒绝不可解析引用，却把 `brain.action_rejected` 从稀疏审阅帧两处摘要过滤掉，也没有立即排队复审。旧进程两次 300 秒无进展检测后暂停同一 Run。修复只传递控制器拒绝原因及脱敏的无效引用，不代替大脑判断科学答案；拒绝后立即请求复审，最多两次，仍无可解析引用则明确暂停以免模型循环。定向回归验证事件在稀疏帧可见及两次上限。后端按原生恢复对账续跑同一 Run，恢复审阅做出可接受的完成判定，本地科学评分为 100；该轮墙钟耗时包括旧缺陷暂停，不作为正常速度样本。

FigQA-0177 第二轮封存包只有根目录 `answer.txt`，内容为规范 `[ANSWER]B[/ANSWER]`；此前以 11 份历史回执验证的本地评分器要求唯一 `outputs/answer.txt`，真实评分沙箱返回 `unverified`、退出码 2。公开题面只写 `answer.txt`，隐藏封装层是否接收根目录路径未得到回执；因此该轮科学分保留 unknown，不能因答案内容正确就假定平台会给 100。评分器的可验证范围不扩大，封存包不改写。评测评分前新增只读 ZIP 路径检查，对这两道 FigQA 的不支持布局给出明确 unavailable，避免租用注定失败的沙箱；测试验证根目录、唯一支持路径及重复路径，并断言不创建评分沙箱。该改动只影响后续装载新版后端的 Run，已发生的失败和资源成本保留在基线。

FigQA-0178 首轮暴露另一个事实传递缺口：SQLite 授权已含 `max_sandboxes=2`、`max_sandbox_minutes=60`、无 GPU，生命周期审阅帧却只列 Job/提交/时长。大脑因误认没有沙箱授权而暂停请求追加权限。修复在审阅帧完整列出沙箱及数据下载授权，并注明评测 Run 的独立评分会在大脑结束研究后由系统接管，不要求大脑先租评分沙箱；这些是现有权限与生命周期事实，不改变科研答案或授权额度。重启后同一 Run 原生恢复，实际恢复帧核对了上述字段；大脑随后结束，封存包同时含根目录和 `outputs/answer.txt`，Bohrium 沙箱科学分 100。该轮耗时包含旧缺陷暂停。

Paired-block Lean 的真实评分需要与历史回放一致的 Lean 4.32.2、固定项目和 Mathlib 缓存。评测评分前先按既有哈希核对公开工具链/依赖，在 Bohrium 沙箱准备环境；仅转移候选无关的公开项目与依赖，不转移历史候选证明、分数或标签。首轮封存包的原始评分遭遇项目小归档 TLS 传输失败；按原 Run 剩余额度对同一封存包只执行一次受控补评分，项目及前两个 Lean 分块成功、第三个分块超时。两次均无科学分，保持 unavailable/unknown，不把传输失败判作证明错误，也不再次租评分沙箱。

大输入 Job 的冻结阶段原来整文件读入内存，且固定 180 秒提交超时；约 897 MiB 的 Lean 请求在上传时超时后，无法证明远端未创建，保留 `unknown`、不重发。冻结改为流式复制及跨块密钥扫描，超过 256 MiB 的提交调用允许最多 1200 秒；MCP 单次等待同步增至 1350 秒，不自动重试。初次改动误将请求哈希变量遮蔽为 SHA-256 对象，导致两个新 Job 在本机 manifest 序列化失败，尚未调用平台。修复变量后，结合无 `manifest.json`、无平台 ID 与本机异常回执，仅这两个精确操作标记 `not_started`，保留原预约和事件，允许执行器自行选择新操作 ID；其他上传超时仍为 unknown。以后报告的 Job 数只计已取得平台 ID 的任务，另列无 ID 且仍可能已发送到远端的 unknown 预约，本机明确未开始的预约不充当付费 Job。

W3 后端重启后出现两种恢复空转：已授权 Trial 的执行器会话丢失却未重新提示，评测恢复操作 ID 又在后续重启重复使用，控制器幂等返回但没有恢复原生会话。恢复时对已授权活跃 Trial 安排原生续跑，并让操作 ID 包含持久化恢复事件序号；相同恢复事件仍幂等，新的恢复事件可重新建立会话。Run 终结时还将未完成的提交预约保守标为 unknown 并记事件，不再永久显示 `submitting`。这些修复都不扩大授权或重复提交不明状态的远端任务。

Matchgate 第一轮评分沙箱原执行退出码 0，stdout 末行是符合版本及结构契约的科学分 JSON；同一 stdout 前面的 pip 安装日志使网关严格的单 JSON 解析报 unavailable。后续评分命令将依赖安装 stdout 重定向到 stderr，保留评分器 stdout 单 JSON 契约。原 Run 的分数不通过重跑研究获得：本机只读恢复同时验证原封存包 SHA、评分器 ZIP 字节、科学包 ZIP 字节、公开资源固定哈希、原沙箱镜像与已删除生命周期、单个完成执行事件的 ID/时间/命令/退出码，且只解析末行科学分契约；证据不全就拒绝恢复。由此得到本地科学分 0，未伪称平台成绩。一次既有授权内的补评分调用从当前命令沙箱出发，在 DNS 查询处因本机 socket 权限拒绝，请求未到平台；它没有创建远端资源。将此精确错误分类为本地 `failed`，原 unknown 行按原回执结算为零分钟，并让成本报告使用 `deleted_at` 而非后续人工结算时间。其他网络超时、未知创建仍保留 unknown。

Matchgate 第二轮在 5 个已确认 CPU Job 内自行完成研究并封存。大脑第一次 `finish` 把真实 checkpoint ID 直接作为证据引用，控制器拒绝后即时复审，随后以可解析引用完成；没有人工替它决定科研答案。评分沙箱再次运行旧进程里的混流命令，因此原始完成回执经同一严格核对后只读恢复本地科学分 0，未租新资源。该轮尤其暴露跨 Trial 产物组合缺口：Q1、Q2 单题 Job 已独立重放出 F=0.8002394885、0.8031740248，但最后 Q3 结果包的完整 `outputs/submission.json` 对这两项仍是身份占位线路；评分器对实际封存包得到 Q1=0.0001128899、Q2=0.0000088118、Q3=0.6218737464、Q4=0.0000022921。Q3 的独立 Job 回放与评分器吻合。基线必须计最终包 0 分，不能用单题研究日志推定组合包分数；将封存前跨 Trial 候选哈希和完整包评分核对列为后续改进，不事后替换本次产物。


### CS-UP-06 原队列中断后收尾（2026-10-02）

2026-10-02 11:07 UTC实测后端PID30348及监控PID81657不存在，健康请求失败；最后监控记录为10-01 23:55 UTC。进程退出原因未判定，不将旧健康快照当作持续存活。Matchgate第二轮原截止为10-02 02:16 UTC；以原生控制器及eval advance执行到期收尾，封闭模型启动/恢复路径。11:12 UTC两层均complete_with_failures，Run cancelled；只读Job查询确已返回，该轮唯一无ID预约仍unknown，不重复创建或释放。开始时间、授权及冻结模型配置未改变，无额外Run/Job/沙箱/评分。第二轮墙钟42936.761秒包含后端停机及发现延迟，不能当实际科学计算时长。该基础设施缺分仍保留；原评分包恢复文件不升级为正式成绩。


### CS-UP-06 终态交付及费用保守分支（2026-10-02）

两组原评测和两次Matchgate均终态后，执行之前延期的评分器声明配置，科学score.py SHA-256为53622c39b2c39687f0865dfdd1bc85034cbfcab4fcaaa17fdb0b39db4b8a66a3不变，manifest由be94e007ffb5a126d216044d725495550e71de91c0c406cf6c6c2ccfefb3b19d变为0ace4370d00c16f2b96d05342cdceb02322ff1a41a7ad54ba97d42c6cdcb7fb4。这没有规避活动Run变更审批拒绝，也没有把新契约用于追溯改分。后端实际PID4789/健康200，没有模型或新算力启动。

新增通用Job条件估算：Job场景CPU SKU报价通过精确机型、非GPU、有限非负值与冲突检查；当前价格乘旧API spendTime暂按秒再乘节点数，时长单位没有独立验证，所以API、前端、Markdown明确保留duration_unit_verified=false/条件说明，旧cost币种与total_amount仍null。仅有终态/平台ID/明确源时长的自有Job参与，无ID/未终态/缺值不计零。不采用Sandbox或Node价格，价格事件只投影白名单字段与源哈希；报告只读且不租算力。fake覆盖同SKU冲突、非CPU、不合法时长、跨Run报价复用、未知预约及非账单边界。跨Run复用测试实际发现事件查询列名错误，修正为recorded_at/rowid后通过，未部署中间错误版本。

恢复服务后实际观察到cancelled的无ID预约被旧后台反复查询并追加事件。通用修复对非终态Run及已知ID的非终态Job作常规轮询，启动时仍按既有可靠性边界对历史预约查询一次，手动reconcile可用；不删除预约、不释放或推定未创建。fake覆盖finished/failed/cancelled无ID预约、运行中选择和已知ID仍在运行的Job；保留对已结束Run中仍可能计费的已知资源观察。此修复不改变科学决策或资源授权。

最新F3只读目录仍为空，完整分页回执SHA-256为05112965ee1925ab06edcada7fe51d4e56a26629dafe43a561d781f9327edc65。唯一创建尚unknown，不能把空列表作为不存在的权威结论。原预算已经到期，真实验收不通过追加科学评分弥补；报告保留8个真实Run、2个创建前失败、5个正式分/5个unknown。数据不支持将差异拆成模型或修复效果，也不把原运行内64.7854恢复文件升级成最终正式科学分。原始材料全留本机，未改科学策略或经验。

环境中断补证：当前/proc/uptime反推启动时间为2026-10-02 11:06:47 UTC，PID1为codex，晚于原Run和最后健康观测。这与执行环境重启一致，不能仅由进程消失判定应用自身崩溃；没有旧boot ID或重启触发日志，触发机制仍未判定。不增加守护框架或用新Run补旧授权，保留到期收尾。

用户补充事实：随后明确说明“是我手动关机了”。据此将Matchgate第二轮的中断原因更新为用户主动关闭执行环境，非应用崩溃、非未修复程序缺陷。保留之前观察与推断的历史记录，以最新用户事实为准；原截止已过，预算、Run次数或科学分不因此自动更改。

本阶段有界代码审查：估算与报告不会创建科学资源、改写科学分或将unknown补零；私有报价回执仅白名单字段投影。审查发现终态Run可能仍有已知ID的活跃Job，已保留这类资源的常规观察，只停止终态无ID预约的反复自动查询；新增三类终态fake确认不会遗漏仍可能计费的已知Job。确认源文件、迁移与原生授权边界未改变。最终验证、重载及推送结果在STATUS和v2报告记录。

### CS-UP-06 流程阻塞交回执行器（2026-10-02）

用户要求一次提交阻塞不应结束Run，而应由执行器尝试修复。fake在真实控制器边界复现：最终评分抛出INVALID_COMMAND，已有三条finish_rejected复审记录时，旧分支将Run设为paused且原执行器没有收到任何反馈；回归测试实测1 failed。根因为评分异常只唤醒大脑，计数达到两次即暂停，没有接回已交付Trial的执行器。

通用修复复用guidance持久化队列，source=controller。最终包预检/本地评分失败，以及原实验邮箱提交失败或状态未知，均记录原失败事件并向当前Trial返回阶段、错误及事件引用；done/reported_complete/stalled Trial可接回active，Run仍running。执行器忙时等自然检查点，空闲时投递到同一原生会话，必须ACK；queued/sending/sent/unknown反馈按阶段去重，unknown投递不重发，ACK后出现新的失败可再次反馈。反馈不自动执行评分、Job或Attempt，不替换产物、不决定科学方法；未知提交只读对账，原预约和幂等键保留。评测禁止提交、授权到期、用户暂停和显式大脑暂停等边界仍有效。删除的是“评分失败两次自动暂停”，科学分回退仍按F1交由大脑选择修正或明确确认，未增加强制读轨迹或反对流程。

最终评分前新增只读审计所需的完整输入快照：封存ZIP、科学ZIP、评分器ZIP及逐文件字节数/SHA-256、评分器版本。在租沙箱前保留finish候选，正式评分上传前也冻结操作输入；失败不登记科学分，重复输入复用，冲突或符号链接拒绝，不覆盖旧材料。真实Matchgate原评分科学ZIP SHA为08154868d0a3c33a9c20fbb4634edebc1d7fce2de7104180f5109c57c4644145；当前未封存包导出的科学ZIP哈希不同。只读逐成员对比实际发现原输入多一份provenance/data_inputs.json，其余成员哈希一致。完整旧封存ZIP仍缺，不能用相同科学输出或恢复文件冒充完整包已正式评分。新增快照用于后续失败恢复，不追溯伪造旧快照。

修复覆盖所有题目的同一控制器/评分器入口，未加入评测题的答案、算法、参数或路径特例。必要前端展示source及queued/sent/unknown状态，MCP描述允许系统反馈；大脑独立判断与稀疏监督方式不变。定向执行器/最终包/协作测试94 passed；评分器相关前一快照101 passed；前端41 passed并build通过。全量与部署结果另记STATUS，fake不当作真实模型或比赛验收。本次未创建新Run、模型调用、算力、比赛提交或经验修订。

最终回归803 passed/2 skipped，前端41 passed/build、compileall/diff check通过。11:57 UTC自有后端重载至37608，健康及静态资源、费用API真实核对通过；模型事件/算力预约/提交/经验数量、原授权及科学评分器均未变化，正常后台Job对账选择0。代码/测试/契约提交7ab1da4，原始材料留在忽略目录，未为当前终态Run追加模型或科学评分。F3唯一镜像请求仍unknown，无权威ID或失败回执，不扩大一次资源额度；W2历史未达到的门槛仍标明，不将全部验收记为完成。


## CS-UP-07

### W0 用户决定及边界（2026-10-02）

实际基线f54d0c4与任务卡一致，已跟踪代码无未提交改动，保留原有未跟踪任务卡和经验资料。按本轮明确授权，设计§5仅增加D-24～D-27，其余原文逐字节一致。执行器自主处理系统/环境问题，系统给事实、工具和可核验反馈；读取自有历史资料允许，因此重复非独立样本。W1推送后冻结后端commit，两层终态前不修改或重新部署；整层无法继续仅按任务卡有界例外处理。正式本地评分依据受控通道原始回执和固定输入核对，不接受执行器直接填写分数。

新授权覆盖一轮fast和一轮hard、每题两次、gpt-6.1-sol/xhigh。困难层每Run180分钟、Job≤20、沙箱同时≤4/累计≤600分钟、CPU≤16核、公开价格估算≤50元；快速层原额度不变。W1沙箱累计≤60分钟，Job0、真实Run0。禁止镜像/数据集/节点新建、比赛提交、评测经验写入和全局CLI更改；不追溯扩大旧v2授权。以前F3私有镜像unknown保留，不再作为v3的Run创建前置条件，也不再次创建资源。

W0验收命令：git状态/HEAD核对；Python验证去掉D-24～D-27后文件字节与HEAD原文完全一致；git diff --check。仅文档，无真实模型、Run、算力或提交。W1 A～D及v3尚未开始，不宣称完成。

### W1 给事实、工具和反馈（2026-10-02）

A：删除eval调度的未验证环境前置拒绝，保持真实Run机会。runtime_facts通过原授权与持久账本计算时间、Job余量、沙箱完整预约分钟/并发槽；价格沿用已捕获的CPU SKU报价、源哈希和观察时间。公共镜像只读搜索分别lean/mathlib实际为空，缓存明确查询词而非假设完整目录；未知Job/沙箱网络写unknown。环境配方、固定公开项目和版本要求是事实，不是已经准备好的环境；新增同次身份检查描述，不包含证明或题目答案。系统不再自动pip安装或搭建公开项目，执行器在已授权Job/沙箱内决定环境准备。

B：执行器评分prepare只冻结固定评分器、科学包及公开资源ZIP，返回文件传输契约、固定评分命令和依赖/公共项目声明，不租沙箱或写分。环境路径仅允许有限的工具链/库/项目绝对路径，身份检查来自后端只读配方。固定runner在同一次受控exec内核对输入ZIP及解出的评分器源文件哈希、环境身份与公开项目哈希；评分器stdout必须是单JSON，环境准备不会混入。register只接受本Run/Trial的评分计划和执行operation_id，读取通道自己记录的命令/回执哈希与原生退出码，拒绝缺证、篡改或版本变化；没有调用方可直接填分的入口。来源executor_verified沿用本Run科学输入与评分器哈希缓存、分项最佳登记、最终包对账和封存绑定，系统不替执行器选候选。fake复现系统传输失败后原沙箱64.79登记，以及科学/评分器/公开数据哈希、命令、环境、回执、退出码和多JSON拒绝；固定runner只用合成测试脚本做应用验证。

C：复用CS-UP-06的原Run持久反馈队列，不重写代理内核。最终传输/环境/时限失败和实验提交失败/unknown把工具、原因、可能远端生效、原事件引用及程序性可选操作交回原执行器；重开已交付Trial，不因单次拒绝结束Run。普通Job、下载、沙箱传输/执行通过工具响应返回同类事实，原生异常也记录unknown；远端不明不自动重发。MCP保留结构化错误并按原有有界执行/传输等待，避免合法长评分被180秒HTTP等待提前切断；等待不增加资源授权。科学依赖和镜像API预检改为advisory；256MiB/原1GiB输入门改为字节数事实，仍保留密钥、路径、CPU、时长、Job数和金额授权校验。unknown创建继续占用Job数、并发和金额，但额度有余量时允许执行器明确选择另一个operation_id，不自动重发原预约。

D与新额度：大脑审阅帧和执行器第一帧共用运行事实，另提供research_operating_facts只读刷新。评分预计耗时仅取声明estimated_seconds或可匹配的受控历史实测，没有就unknown；score_timeout明确是上限。价格、花费查询与条件估算分开，不把未知费用算零或把预约上限称为账单。金额预约按公开CNY单价×请求最长寿命原子预留，known已结束资源按账本时长结算，unknown保留完整预留；无有效单价时不能证明满足50元上限，不批准新的资源，并返回事实。新hard只改变任务卡列出的限额；未列出的旧内存/磁盘/Job并发上限不擅自扩大，分别保留16GB/10GB/2。v2快照没有新limits时严格沿用旧5Job/180沙箱分钟等原授权。

冻结与交付：服务启动捕获后端commit和运行源码/环境/评分器文件哈希，eval冻结配置和各Run marker记录同一身份；不匹配不继续调度。这个检查对应本卡明确的冻结约束，不是科研方法审查。W2两层终态前禁止后端改动或重新部署；有界例外只按原任务卡处理。历史读取允许并保持原生只读范围，前端显示正式科学分的两种来源和冻结版本。新增表/列幂等，备份先于迁移；真实原始数据仅保存在workspace/.package-checks中。

所有分支面向通用评分器声明、原生回执和既有授权，不按评测题ID分流，不新增科学方法、参数或答案。W1真实使用Run0/Job0/沙箱0，未扩大验证额度；有界代码审查重点核对回执信任来源、未知状态不重发、缓存/封存来源继承、共享金额预约、评测禁提交/经验写入以及原生会话隔离。全套验证及冻结部署结果按STATUS后续实际结果记载。

W1最终验证：`.venv/bin/pytest -q` 841 passed、2 skipped、exit0（241.94秒）；两项回环监听测试沿用现有沙箱限制跳过。`npm --prefix apps/web test -- --run` 42 passed，`npm --prefix apps/web run build`、compileall、git diff --check通过。前几次全套/定向回归暴露启动Git子进程与连接探针mock交互、普通回执长度兼容及旧handoff/自动依赖安装断言，均修复后重跑，不把失败快照计作最终通过；原始日志保存在忽略目录。实际迁移前后Run31、Job53、沙箱25、提交6、经验修订59均不变，W1未使用真实Run/Job/沙箱额度。Codex 0.159.3原生model/list与两种role thread/start重新核实gpt-6.1-sol/xhigh，模型turn0，未改全局设置。


### W2 冻结开跑与快速层实测（进行中，2026-10-03）

W1推送后部署并冻结df91723c518f61327695160d28c6fd3073abafcb，运行源码SHA-256为6714fcc655a88083aec2460578fb91c6e01f866ba9dab33844e4b2efa902955d。只执行一次原定fast和一次hard命令，评测ID分别为eval_bc60841fc279、eval_2d41d12345f0。期间没有后端修改或重新部署；本段只记中间事实，完整v3交付仍须等待困难层终态。

截至2026-10-02 16:36 UTC，快速层6/6完成且均有正式科学分，abc两次20、两道FigQA各两次100，来源均system；公开v6检查表C均100，不能解释为官方v8轨迹分。实际eval report导出的六行核心数值与数据库报告一致。前三项发生的传输故障、原状态unknown和原沙箱清理均有事件；执行器或大脑在原授权内选择后续通道，未自动重发未知操作。最终评分与handoff复用相同科学输入/评分器的缓存，没有为相同输入再租评分沙箱。

允许读取自有历史不等于盲测：首轮FigQA-0177在查看原图前读取了含标准答案的评分器重构README（run_6a1cfd461c#37、原生line33），其100不能当独立答案发现。其他Run的基线报告正文检索、封包示例、冻结经验和同Run跨Trial复用分别留档，不把文件名发现等同正文读取，也不从未发现匹配推导没有任何历史访问。

困难层首Run run_b5defc11b2已创建，初始环境unverified，帧明确给出版本、报价、unknown网络和180分钟/20Job/4沙箱/600分钟/50元上限。题面权威清单缺失的首次资源检查未终止Run；大脑自主创建第二Trial继续尝试，原授权不变。清单缺失的上游或本地包装原因尚未判定；尚无Lean编译或正式科学分，不能把文件预检计作成功。

真实固定执行器评分包装程序在Python3.10.6使用hashlib.file_digest失败（run_6a1cfd461c#191），保留为评测后修复项；原系统最终评分通道成功不等于该问题已解决。其他登记尝试没有固定执行回执时被SCORE_COMMAND_MISMATCH拒绝；截至本段没有真实executor_verified登记，fake验收与真实科学结果分开。六个快速Run的全部Job/沙箱终态已确认；评测期间提交与经验修订目前为0，十个Run整体验收仍待两层结束。

17:30 UTC困难层补充：run_b5defc11b2首CPU Job在Lean启动前PermissionDenied；提交前执行器原生line234明确chmod上传zstd为0755，compute输入冻结副本变成0644且哈希相同，定位到compute.py:341新建文件复制未保留执行位。远端小探针#468进一步观察上传文件0666，普通owner chmod及内置解压器均实测成功；不能把远端初始模式完全归因于同一个复制步骤。大脑自主继续第三Trial，执行器自行测试后改用镜像内置解压器，证明Job#621实际完成固定版本编译，#640固定评分器候选50。未登记正式科学分，Job结果与正式沙箱登记/最终包仍分开。原额度不变，应用缺陷只记录，不在冻结评测中热修复。该Run读取旧环境归档和评分器说明，不把历史文件名发现当证明答案读取；#735经验采用被拒，实际写入仍0。

18:51 UTC首Lean的最终评分#1727因ENVIRONMENT_PREPARATION_REQUIRED被拒，controller指导经原持久队列#1730送达、#1739 accepted ACK，target仍trial_72dcac76d7，idle_prompt接回原执行器。它只读核对指定沙箱后提出删除，引用原Trial25分钟已到；原Run仍有约1546秒。该事实证明最终评分阻塞能送回执行器，尚不能证明修复或正式登记成功。此前Job的90分JSON已取回核对，正式local_scores仍0，不能冒充system或executor_verified。阶段时限解释与准备方法属于待核实运行边界，当前不据此热修复或追加额度。

19:17 UTC首Lean原授权到期：大脑两次后续requested审阅指导分别经#1842/#1847和#2045/#2050送达同一执行器并ACK。第一次自行采用分块传输，四个64MiB块核对成功，但完整工具链尚未部署即到大脑选择的360秒准备时限，未执行固定评分命令或register，随后清理沙箱；第二次检查余量后不再创建资源。大脑#2107/#2110选择暂停，评测调度#2111原180分钟到期后收尾，保留候选90和恢复证据，正式分仍unknown。Run结束的资源账本为6个终态Job、0个unknown预约、3个deleted沙箱，共19.131分钟；总账单未知，不能把Job无币种cost或条件估算当作实际总费用。系统终态end_reason字段为通用user_terminate，但#2111和报告明确来源是评测授权到期，本次没有操作员终止请求。按冻结规则记录环境传输/准备未完成，不由开发者补部署、追加评分或扩充授权；原困难层队列已自动推进第二轮，未触发整层重跑例外。

2026-10-03用户关机后恢复：关机前明确请求暂停并下次恢复，原生暂停#364/#370、已创建的唯一沙箱#374删除、后端和只读观察器SIGTERM停止，保存一致SQLite备份与本机检查点。恢复时实际冻结代码及备份哈希通过；第二轮Lean原时钟已超过UTC 22:17:30截止，按本卡“不重跑”保留原Run、原授权与缺分，由原调度#375/#376/#377对账收尾，继续原队列的两轮Matchgate，没有增加eval或重复次数。启动等待35秒超时后核对同一后台进程与健康，再接回观察器，不因观察窗口结束而重复启动。后台重启是用户要求恢复同一冻结版本，非评测中途部署代码修复。

第二轮Lean的最终科学事实以#343为准：执行器在原CPU沙箱自行修正根目录，实际编译退出0，T2/T3可信公理检查通过，T1仍sorry；此前静态curl下载/缓存失败后来已恢复，不能把中间观察写成最终环境失败。证据封包#354路径混用的失败经#355送回，#367改用TAR成功，但用户暂停中断固定评分与登记；正式分unknown而非推算50。原报告墙钟65043.184秒包含暂停/离线，资源账本26.637沙箱分钟单列；不把二者混称计算用时或归因于模型能力。第二轮只确认读取封包历史示例与运行环境事实，原生输出中的旧Run ID分别来自operating facts与示例代码，不能仅凭ID出现就断言读取了历史证明。

2026-10-03 14:49 UTC Matchgate首轮中间观察：首次Job请求超时unknown，原预约保留且未自动重发；执行器自行核对不完整科学ZIP、按明确缺失区间补齐，#347完整哈希及干净重放成功，#367独立Q1重放一致。原Trial只留下合法基线和未验证假设，不把原生计算输出当正式评分。大脑#506在同一Run开始第二Trial，使用58,630字节的新派生输入；Job#565接受、#598 Failed，#656取回结果、#680日志明确公开镜像站numpy wheel HTTP 403，科学程序没有运行。这是外部依赖安装失败，不是科学假设的负结果，也未确认为新增应用缺陷。

执行器的日志命令缺输出目录被#578退回，它#587修正；空日志结果、CLI版本检查超时与后来实际结果下载成功分别记录，不把任一HTTP或退出码替代文件证据。#791封包admitted/路径ready，但派生子集未登记来源引用，仍proxy，正式local_scores仍0；该Run及后续重复未终态，不预判缺分或最终科学结果。两层冻结持续，开发者仅整理审计与文档，不给科学指导、热修后端、另建eval或追加额度。

2026-10-03 15:16 UTC：大脑#833自主开始同一Run第三Trial，保持锁定版本/科学代码，仅为本次Job安装调用指定官方PyPI，不改全局配置。Job#887接受、#917 Failed；#943日志及完整产物确认Python3.10.6/pip22.2.1已启动、NumPy wheel下载开始，外层290秒依赖准备上限退出124，无安装完成、导入或科学启动标记。日志无明确HTTP状态或兼容性错误，不能据此断言DNS/权限/版本不符；#1061以partial交接供大脑继续审阅。环境假设未在该窗口验证，不作为科学假设的负结果。原未知预约保留、无自动重发，开发者没有干涉。进行中v3报告已整理到正式文档路径，七行摘要与十行结果分别检查，余下两项及最终验收不宣称完成。

2026-10-03 16:10 UTC Matchgate首轮第五Trial：最终科学包传输#1530保持unknown、finish#1531被拒后，原反馈#1534经guidance_998ca02eff送回同一trial_c84288a926，#1563 accepted ACK。执行器受控只读核查#1620及后续定位未发现科学包，仅找到哈希匹配评分器；#1665 blocking检查点交回大脑，#1673继续审阅。查询时点无文件不能结算未知写入，执行器未自动重发、未新建或延长资源，正式分仍unknown。沙箱reconcile只覆盖创建记录、不能核对文件传输；job_group list被入口#1412 UNSUPPORTED_COMMAND拒绝，原生CLI支持未知。这些记为工具覆盖及对账能力缺口，不先外推应用根因；冻结期间不补接口、不由开发者代为传包或评分，也不因单次阻塞结束Run。当前后台和观察器实际进程、健康接口及冻结版本于16:09:42 UTC重新核对通过。

2026-10-03 16:25 UTC首Matchgate终态：大脑#1703结束本次修复尝试、#1742等待；#1765停滞检测再次唤醒，后续收尾指导#1783送原执行器、#1794 ACK。评分沙箱#1786实际删除；#1809原授权截止、#1816/#1817收尾，正式科学分与封存绑定仍unknown。两个无ID预约保持unknown，不能由只读部分列表无匹配推导未创建或无费用。已知Failed Job2、deleted沙箱2/44.709分钟，Job查询0.07币种unknown，沙箱查询0.42CNY未确认最终结算；条件估算分开。原困难层自动推进最后一项run_cc0251a839，没有扩大预算或整层重跑。十个Run冻结marker一致，20个原生角色模型gpt-6.1-sol/xhigh，9项终态/6个正式分；整体验收和W2 commit/push仍待最后Run终态。只记录故障及自主恢复事实，不将Job候选或合法基线公式结果替代正式分。

最后Matchgate新增事实传递缺陷：rev_9f51cb83f9的截止#78持久帧把#66 job.preflight passed投影为compute_jobs状态passed，尽管资源请求被拒且此operation没有compute_jobs行，remaining.jobs仍20。observation.job_states对相同截止做只读重投影与原帧完全一致，源码对所有job.*的payload.status无阶段区分。大脑#94正确保持远端执行unknown，成绩影响未确认；应用帧不能靠大脑自行识别含糊状态来保证正确。按D-26仅记录，评测后再隔离预检/生命周期并加fake，不把它外推为Job实际创建、模型科学失败或已被修复。

实际Job资源限额与帧交叉审计：该Run的job_limits_json经默认值合并为CPU16/内存16GB/磁盘10GB/Job并发2；初始rev_38b5133951与交棒rev_1acec727ce的持久ReviewPacket均未在authorization或operating_facts传入这些有效限额。报价包含大机型，不等于授权可使用。大脑#10/#248仍选32GB，首请求#77被正确拒绝，执行器#86只读入口后自行缩小。记录为事实遗漏，不能仅把违规机型归因科学决策，也不证明它是最终缺分的唯一原因。两层终态前不补运行帧、不扩大限额、不向代理加开发者指导；评测后通用修复应从冻结授权投影有效限额，并补fake。

最后Run自主恢复实测：原未知Job的partial查询不能证明未创建，大脑第二Trial先要求确认旧任务才新增；#408/#409自主调整为允许不同目的的独立轻探针，原预约保留，不是自动重发。新CPU Job#440接受、#532 Finished，#564结果下载请求超时；大脑#652/#653接续只读取回Trial，不新增资源，#680/#700成功恢复日志和完整7166字节输出。源probe、候选哈希与实际输出匹配，科学阶段及Q1独立回放得到证据，原请求和中间超时根因仍unknown。此恢复成功不等于固定评分、正式local_scores或旧未知资源已解决；#792交棒、原Run仍继续。原始回执与下载留忽略目录，只发布脱敏统计；四项新应用缺陷均保持冻结后处理，开发者未提供科学指导。


2026-10-03 17:46 UTC最后Matchgate第五Trial：大脑#811自行安排后续研究，执行器#858再次将32GB目标缩至有效16GB限额。完整公开归档与真实清单关联后，唯一新Job#892预约、#908超时unknown无ID，#910原失败事实返回；三页partial查询不能证明未创建。两条unknown保留预约，占用既有Job并发2，总次数余量不等于可新增并发。执行器#1018以blocking交棒，大脑#1039/#1041自主安排有界交接，#1044指导送达、#1050接受，不要求重复同样查询、不新增Job、不重发原请求、不结束Run。未出现新的科学回放、梯度、优化或正式评分结果，不当作科学负结果；#1019经验采用被拒。后端7777和观察器10743实际存活、健康及冻结身份于17:45:30核对通过；17:46:56十个marker/存储资源边界与经验0断言通过。两层尚未全部终态，继续原队列监控，原截止时间与授权不变。


2026-10-03 18:00 UTC新增调度竞态：run_cc0251a839#1154在旧回合未结束时先创建第六Trial为active/current，#1157原生投递rejected；旧回合#1162/#1163仍写第五Trial文件、#1165返回旧交接、#1167结束却归到新Trial。controller.start_trial先更新current再prompt，非限流rejected无持久待投递；原生事件也直接取current作归属，源码与现场相符。#1186既有停滞检测idle307秒，#1192大脑自主steer、#1195指导送达、#1197原生新回合启动、#1202执行器确认恢复，不重置Trial或Run时钟。记录第五项通用应用缺陷及实际自主恢复；科学执行和最终成绩影响尚未确认，没有开发者介入或热修复。两层尚未全终态，完整W2报告与commit/push仍待原最后Run结束。


2026-10-03 18:05 UTC第六Trial并发拒绝：执行器#1250自行读取持久授权并识别max_concurrent_jobs=2、两个unknown占满；#1282预检通过，45,082字节轻输入的唯一投递#1283被CONCURRENCY_LIMIT拒绝、无新增预约或compute_jobs行。#1288保存原始回执，H6未运行，不是科学负结果。第六项新诊断事实缺陷：compute._authorized在预约/原生调用前拒绝，但API ComputeError处理统一possible_remote_effect=unknown且丢失operation_id；该调用实际未投递，应与原两个远端unknown分开。原预约不清除，预算不扩大，后台代码不改；正式成绩影响未确认。证据preflight-rejection-feedback-gap.json仅本机，报告发布脱敏结论。


2026-10-03 18:09 UTC最后Run由大脑暂停：#1313第六Trial诚实交接后，#1334大脑自主pause、#1337确认无活动原生turn。原因是两个unknown占满Job并发；并非控制器因单次工具失败强制停止。rev_c5b8552b91实际持久帧仍有sandbox_minutes600/sandbox_concurrent_slots4/总Job剩余17，未尝试沙箱；记录为大脑的资源通道选择，不能写成所有授权通道都耗尽，也不推断沙箱必能成功。开发者不改变科研决定、不移除unknown、不扩并发；原时钟19:21:58UTC到期后由现有eval调度收尾，源码该分支已只读确认。18:09 DB审计比赛提交0、经验修订0；20个原生角色/模型/公开记录哈希核对通过，最后执行器280公开工具及实际历史阅读/写入假阳性已人工核对。九项终态六正式分，最后仍非终态，W2最终提交与报告未完成。


2026-10-03终态前文档审阅：已纠正STATUS未标日期的两轮Matchgate“均未终态”旧表述，保留首轮已终态、最后Run由大脑暂停和六项新应用缺陷。重新读取W1完整pytest/前端测试及构建日志，运行源码仍冻结；18:18执行compileall退出0、git diff --check通过。三份候选文档按已配置密钥值做本机比较，匹配0且不输出密钥；该检查不是整个Git最终暂存审计。最终CLI导出核对脚本仅在两层终态后执行，逐字段比对完整JSON与数据库报告，不以中间数值代替最终结果。原Run未终态，因此不提交W2或宣称整体验收通过。


### W2 最终收尾与审计（2026-10-03 19:13 UTC）

用户最新明确要求“去收个尾”，覆盖此前按原截止等待的安排。仅通过现有POST /api/v1/runs/run_cc0251a839/control的terminate动作结束最后一个暂停Run，19:12:48 UTC返回HTTP200/status confirmed；#1552 run.terminated、#1553 prime.session_aborted confirmed。操作ID及完整回执保存在本机忽略目录，不进入提交。原截止19:21:58未到，此次是用户要求提前结束，不写成预算耗尽；没有resume、额外模型turn、晚评分、新Run、新资源或科学指导。原eval队列自行结算最后一项，快速层complete、困难层complete_with_failures，十项全部终态。未知预约保留，本机终止不证明未知远端任务已取消。

最终10项正式结果为abc两次20/system、FigQA四次100/system，两次Lean及两次Matchgate均unknown。首Lean保留90分Job候选但环境准备/正式登记未完成；第二Lean受用户关机及原授权过期影响；首Matchgate最终包传输未恢复而到期；第二Matchgate已取回基线和独立回放，两个unknown占满Job并发后由大脑暂停，最终由用户要求收尾。执行器确有自主修复和持久反馈ACK，不能将反馈成功外推为环境、评分或科学目标全部解决；沙箱额度尚可用时选择暂停属于大脑的资源通道选择，不据此增加科学提示或经验。

实际执行两次eval report（eval_bc60841fc279、eval_2d41d12345f0）均退出0，完整JSON与当前数据库重建报告逐字段一致；最后Run墙钟10249.972秒、1个已知Finished Job/2个unknown、沙箱0。19:13只读全量审计确认十个Run/两层冻结身份相同、原资源边界通过、比赛提交0、经验修订0；20个原生角色模型gpt-6.1-sol/xhigh、Codex0.159.3及公开记录哈希稳定。费用查询、条件估算和未知总账单分开，spendTime单位和cost币种尚未独立验证。

报告完成逐Run历史读取、故障恢复、缺分及v1/v2/v3比较；读取自有历史、不同预算/模型/代码与用户中断使比较非单因素、重复非独立。六项新应用缺陷仅留证：Python3.10评分包装兼容、输入执行位丢失、Job预检混入生命周期投影、有效硬件/并发事实漏传、Trial忙闲投递及事件归属竞态、前置拒绝反馈阶段/操作身份缺失。本次任务以完成冻结评测和交付结论结束，不扩大为后续修复。W1测试证据在未改运行源码的条件下继续有效（pytest841 passed/2 skipped、前端42 passed及构建通过），交付再次执行compileall与diff检查。原始轨迹、回执、封存包、SQLite备份及费用观察只留本机忽略目录；只提交三份文档与脱敏统计。


交付有界审阅（19:31～19:32 UTC）：实际compileall与git diff --check通过；报告7行摘要、10行结果/10行用量逐行等于最终result_json，STATUS严格四类，三文档已配置密钥/已知私有平台ID匹配0。冻结前测试日志哈希重新核对，无应用代码改动，因此不追加重复科研或模型验证。旧后台检查脚本要求观察器PID继续存在而报ProcessLookupError；随后只读核对后端PID7777仍存活、健康与冻结身份正确，观察器19:13终态快照后按原代码退出。该审计工具限制不记为应用故障，不重启后端。
# CS-UP-08（2026-10-04）

- W1：比赛轮次复用 eval_runs/eval_results 持久队列表，采用普通 Run 模型覆盖与显式模板授权。分诊基于原生大脑只读角色任务，公开分布不可取回时记录 unknown。Run 默认上限为 6，已有显式设置保留；提供方默认 10，会话按角色计数，模型 429 独立退避。全局 Job/沙箱上限由用户配置，未设置时保留各 Run 原授权，不猜算力额度。旧评测的能力分支按 CS-UP-09 W1 统一删除。
- W1 有界审阅：检查了写锁内会话预约、关闭释放、不同提供方排队不互相封锁、暂停控制和追加 Run 的题目身份。旧测试的三槽容量场景改为显式 3，断言保留；新增默认 6 测试。平台轮次只读探针返回 rounds/seq/challengeIds，未查询其他人的提交内容。
- W0：依据用户任务卡，在 UPGRADE_DESIGN §1 更新 Lightchaser 第一目标，在 §5 追加 D-28–D-41，并保留 D-07/D-23 原文、标明替代关系。任务卡中本轮用户决定优先于设计中的历史决定，其余历史原文不重写。
- 开工 HEAD 为 5940418dfb5af9be53141904971bcf2cd33a7de7，main；未跟踪任务卡和经验文件保留。lightchaser-fallback-0 指向该提交并已推送。
- 迁移前使用 SQLite backup API 在 .package-checks/cs-up-08/ 保存一致性备份。历史 recovering Run 在部署前先对账；真实验证额度按任务卡独立记录，CS-UP-08 提交数为 0。

### W2 活动时钟和关机屏障

新增 Run 使用持久活动时间（15 秒心跳）；大于 45 秒的间隔视为离线，不扣科研 Run 时长。远程 Job/沙箱预约与费用仍按墙钟。旧时钟数据保持旧语义，避免将历史 recovering Run 自动启动。手动暂停不自动恢复；安全关机及意外中断的新 Run 先对账，再按原生 threadId 恢复。Codex 0.159.3 本机生成的 ThreadResumeParams/Response 已核实；Kimi/Prime 原生恢复仍未确认，不宣称内存恢复。

关机先停止队列新增，取得执行器安全点，再关闭两类本地原生进程、冻结时钟、用 SQLite backup API 保存一致副本。任何未确认暂停或进程关闭超时均返回 can_shutdown=false。远程资源列表保留 unknown 和继续计费提示，不取消旧资源。有界审查覆盖重复迁移、离线断档、原会话身份和未确认暂停，并补齐其他暂停出口的时钟冻结；未绕过授权或重复投递远端操作。

### W3 执行底座与有界审查

unknown 的首次时间持久化，十分钟后仅释放并发；总数和金额预约不变。查询发现远端 Running 时重新计入并发，查询不存在不重发。观测帧只消费明确 Job 生命周期，不把 preflight/价格/网络回执当远程状态。

Job 和沙箱共用同一输入／评分器／公开数据／环境身份核验。Job 计划固定命令和出分文件；后端下载原生结果并校验下载文件 SHA，不接受调用者分数或日志。复制保留冻结的模式，远端 bootstrap 再恢复执行权限，兼容上传通道剥离权限。新 Trial 在原生忙时持久排队；Codex turn ID 映射到旧 Trial，旧终态不结束新 Trial，缺少原生 turn 身份保持标记 unknown。

私有环境采用官方 image/private Dockerfile 构建，数量单独授权（默认 0）；冒烟写进构建步骤，只有明确 available 回执才登记已验证环境事实。HTTP 成功与业务 code=0 分开；未文档化数字状态保持未知。费用单价未核实时显示 unknown，有金额硬上限的 Run 不投递无法估价构建。保存未知时只读对账，不再次创建。真实构建与 W1–W4 三 Run 共用最多两个新资源，不另建科研 Run。

有界审查核对未知占位不放掉费用、Job 输出不能伪造、执行权限跨上传、旧 turn 迟到、新 Trial 队列和 API 前置拒绝身份。Bohrium 1.1.0 原生 help 与官方 v2 Dockerfile/check、私有镜像清单已做零计算最小探针：HTTP200、业务 code0，清单分页结构 items/page/pageSize/total；这不证明构建成功。

### CS-UP-08 W4：经验投递与候选

索引覆盖全部有效经验，正文才受相关性与角色筛选；中文双字片段和技术词匹配替代按空格切中文。默认及本工作区新 Run 配置改为 24,000 字符，历史 Run 快照保留。全局五份配方只写候选，不代替用户审批；依赖下载的替代步骤显式未验证。真实验证使用独立 SQLite/工作目录读取既有后端凭据，原历史 recovering Run 不启动，原远程资源不处理。

W4 有界审查：检查全局审批不被 read 绕过、当前题目作用域、过期与角色筛选、索引预算和正文截断、冻结修订采用归属、原生工具名单及公开环境 Dockerfile 密钥拦截。针对性测试通过；未扩大原生角色的写权限。真实暂停保持剩余时长和同一会话标识；这不宣称已实测断电后 IPython 内存恢复。


W4 联合验收：隔离比赛轮次的三只 Run 均 finished，FigQA-0177/0178 正式本地分100，ABC20，全部 system；比赛提交0，原生租约0，五只本卡沙箱均确认删除。ABC第二Job评分包装的输入目录缺陷保留 Failed 回执，修复后只以应用夹具覆盖，不多建第三个Job。建设助手发过一次有标签的执行底座诊断，未给科学答案，报告中保留介入事实。两次公开软件私有镜像构建 HTTP200/业务148888/rpc error，额度已用完；平台阻塞与镜像复用未验证明确保留。

W4 二轴有界审查纠正实际空目标投递、原生提供方/强度/逐题备注、并发分诊租约。重启顺序补齐提交对账；关机跟踪独立辅助会话，恢复和新辅助会话遵守持久屏障，取消整理落失败状态，原生关闭失败保持unknown并阻止“可以关机”。新评测入口用普通模板和轮次准入；报告读取普通正式分及来源，不依赖旧操作ID。重新导入的公开题面与资源按轮次封存，求解者与数据工具读取自身Run版本。全部旧评测能力分支留至CS-UP-09统一删除，历史记录不改写。

# CS-UP-09（2026-10-04 起）

W8 草稿续传：真实 ABC 首次包上传停在 draft/incomplete，平台明确指出 artifacts 字符串及 expected_outputs.type 缺项；原生求解者自行修正了 manifest。这是与 FigQA 下架404独立的问题。平台公开 /protocol 与 ARM v1 schema 经只读核查后，将已观察格式加入建议性预检；不替求解者改科学内容、不宣称完整 schema 验证。

普通提交入口新增已知草稿修复：只有新的显式意图、唯一当前 Trial 草稿、原邮箱有效、原授权有余额、平台确认归属／同题／draft/incomplete 时，才向原 Attempt 上传新封存包并提交。保留旧封存文件和一次 Attempt 额度；未知上传／提交不重发，不通过新增 Attempt 绕过旧草稿。写事务同时处理草稿查找、续传占位和普通预约；重启只把未结算意图记 unknown。查分及反馈用包身份 CAS，避免旧回执污染新包；后台 HTTP 线程持续登记到结束。

已过轮次的旧题仍接受新 ARM 提交，因此其新提交使用七天轮询窗口；轮内提交保留原轮末72小时规则。修复前停止标记清空，但旧时间保留在事件中。分数仍要按两次同值、至少600秒观察确认；没有缩短确认时间来制造自动收割成功。ABC 第二 Job 无平台 ID 的 unknown 已超过30分钟，再次只读对账仍无 ID，保留数量及可能费用，不重复创建。

W8 归档恢复修复：安全暂停后的原生 PI 会话在稍后重启时返回 -32600／指定 session is archived，三个 Run 如实记为 runtime_error；失败事件、Trial 中断、已消耗整理／复盘调用均保留。Codex 0.159.3 本机生成协议及一次真实零模型探针确认 thread/unarchive 返回原会话 ID，随后 thread/resume 恢复相同 ID、gpt-6.1-sol／xhigh。共享适配器只对该指定 ID 的明确归档错误取消归档一次，核对回执后用原参数恢复一次；其余错误传播，不创建替代会话、不修改全局 CLI 配置。二轴有界审查未发现实质缺陷。

施工恢复限于本卡隔离的三只失败 Run，先安全暂停第四只 Run、收尾所有辅助会话并备份；只在原授权剩余时间和资源额度内恢复原 ID，保留初始运行时快照并追加部署／恢复事件。不重置已经用掉的每 Run 两次维护额度。早期失败复盘不是后来完整科研轨迹的复盘，失败或被关机中断的复盘不能记作通过。

W0：08 最终版本 ec5e24b 已推送 main，fallback-0=5940418、fallback-1=ec5e24b 的远程引用已核对；仅原有未跟踪任务卡和经验文件留下，跟踪文件干净。追加 D-42–D-47，不改写历史决定。09 迁移前用 SQLite backup API 再留生产一致性备份；原历史 recovering Run 不启动。回退说明要求安全暂停、停止后端、另存当前数据库，再选择旧标签与匹配备份恢复。只恢复本地账本不表示远程资源或 Attempt 被撤销。

本轮严格不执行 CS-UP-10。DeepSeek 密钥或人工平台事项缺失时只记录待用户处理并继续；真实验证只用卡内旧题和额度，先核对结束事实再提交。

W0 实际校验：47条编号唯一、原41条决策逐行不变、回退备份SHA与SQLite integrity_check均通过。首次校验脚本遗漏D-01编号补零，且组合命令未启用失败停止，导致文档先提交；随后修正脚本并实际通过，补充提交保留该偏差。后续交付组合命令显式set -e，测试失败不继续提交。

### CS-UP-09 W1：单一路径和规则减法

按本轮明确授权，删除以评测标签改变提交、经验写入/采用/整理、环境事实和冻结清单的能力分支。旧标签只供报告读取；待排历史批次转入普通比赛调度，原提交额度 0 和旧计算额度保留。历史 eval_scoring 从已登记账本收尾，不追加远程评分；报告补评分入口仅刷新现有正式记录，不能给已结束 Run 租资源。已有固定评分输入、原生回执、评分器身份、单 JSON、退出码和哈希核验保留。

最终评分未知、缺少 achieved 证据、子项退步、弱轨迹和源码依赖猜测改为可见事实。无证据的 achieved 降为 unknown，PI 可结束或选择原执行器修复；缺少 prediction_md 不阻止已有授权内的提交。限流和停滞产生提醒，持续限流不永久停止执行器重试。提交授权时长统一使用活动时钟。研究判断和经验提议/观察项不再有任意三条上限；接口仍校验真实 Run/Trial 归属和稳定操作身份。

Prime 全局 models.json 渲染例外在本轮禁止修改全局 CLI 与新增密钥文件的要求下失效：删除启动、设置、密钥操作的全局渲染与回读。原生认证使用已有通道，本轮未执行 Prime 付费探针，认证如实显示 native_unknown。未改写、删除用户原生配置。

规则审计覆盖代码、协议和全部已跟踪提示词/skill/全局经验，并逐句区分记录义务和研究行动约束。旧运行与经验修订保留；本轮修改的全局经验不会绕过既有审批。Standards/Spec 审查发现残留的持续限流重试阻断、历史评测租资源许可及措辞矛盾，已逐项修正。原测试场景保留，按新决策更新断言并加上活动时钟、全局配置不落盘、普通提交授权及观察项测试。


### CS-UP-09 W2：科学简报与可行动通道

PI 首帧通过已有公开聚合接口读排行，不额外调用模型；同题策略正文不受普通经验注入预算截断。简报是可选协议字段而非新的能力门禁，实际 Trial 和 steer 自动附最新 PI 简报。根据冻结求解者模型与逐题备注判断是否需要六项具体工作包；未知排行仍允许研究。

可用通道按活动时长、共享金额、真实操作记录与冻结资源核对；不足一分钟不声称 Job 可启动。普通 PI stop 有未试授权通道时转为换路指导，用户手动暂停与安全关机不受影响。只读开局等待跨过手动暂停时，在开始模型调用前重新核对状态；显式恢复重新排作废首帧，避免无 Trial 的空等。

冒烟回执证明命令在当时环境成功，不能证明任意附加配方正确。系统记录 observed_command／输出／命令和回执哈希；recipe_proposal 和持久镜像为 unverified。登记用已有可重入锁串行化，相同操作去重、变更配方冲突。Standards／Spec 二轴有界审查发现并修复快照路径、实际工作包派发、停止旁路、并发去重和资源版本缺陷。


### CS-UP-09 W3：版本化策略卡

复用同一道题 ID，策略按 Run 保持稳定身份和不可覆盖修订；完整开局读取单独冻结，保证展示正文与采用上下文一致。路线和失败解释是 PI 假设，最佳正式验证分来自 system/executor_verified 账本，不接受 PI 自报分。实际普通 ReviewResult 与生命周期 Decision 都能更新，评分提交后立即刷新。

有界 Standards/Spec 审查发现并修复普通经验提议的跨 Run 覆盖、里程碑协议字段缺失、评分刷新遗漏、文件冲突中断派发、冻结正文错配和首次记录脱敏。知识维护失败显式记录 unknown，保留原修订并继续原授权任务。旧 SILENT、题内提议和更新测试仍验证原场景，额外开局卡不再被误算为普通审阅发布或重复提议；没有删除测试。

CS-UP-09 W4：结束先收尾，整理/复盘共用两次独立额度；终态原子排维护。完整公开文件允许全部真实引用，不限制在摘要范围。复盘教训为候选，环境事实继续由已有真实回执代码生成；两个原生停止路径都未知时不伪造终态。

### CS-UP-09 W5：原生提供方和费用

使用项目独立CODEX_HOME与env_key，按原生回读确认提供方；四角色独立，旧选择也显式规范化provider。条目只接受已有ID并冻结公开字段，不接受客户端伪造冻结条目。已观察token按session累计，不把缺用量／未知账单当零；官方时段未知报告上下界。Prime工具探针未核实则明确不可用，不改用Kimi。真实DeepSeek工具探针成功，证据留忽略目录。

### CS-UP-09 W6：审查者是可核查建议

PI-only工具创建新只读上下文，仅提供冻结Run题面、契约、封存包、已有正式分和轨迹诊断。使用稳定operation_id，调用中断保留unknown；并发只发一次turn，符号链接与压缩密钥不能导出。题面重导入不改本Run契约。提交不以审查通过作硬门；PI理由与实际提交源／封存哈希分别登记，包变化不能谎称已审。提交初读与封存源哈希不同则尚未产生远端效应即拒绝。

CS-UP-09 W7：自动收割为普通授权路径，两个提交角色共用 Run 总 Attempt 额度；不会对旧 Run 追溯新增不可逆授权。第二触发条件使用冻结平台目标的刷新榜单，等待同题所有当前实验及排队项结束；因授权到期／大脑额度耗尽不能声称实验做完。失败或未知只对账，不重交；已受理与评分／参赛有效性仍分别记录。

用户在本轮补充收割邮箱，平台只读 /auth/me 已确认既有操作者令牌归属匹配，验证及产品可以引用原有凭据，不写新密钥。用户随后明确 FigQA-0177/0178 已下架：W8 三个 FigQA Run 保留研究、正式科学评分与策略交接，提交额度0；仅 ABC 以两次总 Attempt 验证实验／自动收割。404 属于题目下架事实；按用户额外要求加入通用提交前存在性 GET 和明确提示，并不重写平台协议。未结束题提交仍受本轮冻结旧题授权约束。

CS-UP-09 W8 原生格式修复：初次 Flash 题目 PI 将 work_package 放在顶层，被结构校验拒绝；原系统随后在五分钟停滞审阅中自行启动 Trial。为消除首次拒绝与具体指导丢失，安全暂停三条实际 Run、确认原生会话关闭且尚无远端算力资源后停止独立后端；仅兼容移动该字段到 research_brief，并明确提示位置。动作／额度／提交校验保持原流程，冲突内容不覆盖。原拒绝、停滞恢复、暂停与后续部署版本分别记录，四个 Run 及额度不增加，科研评分器不变。

### CS-UP-09 W8 活动时限与原生关闭

最终ABC记录3644.191747秒，超过3600秒授权44.191747秒。原始活动账本、失败和部署版本保留，不截平时长或扩大授权。唯一迟延原因未证实；应用夹具复现旧快照错读新心跳、心跳等待远端后台维护、等待中的信号和审阅越过时限三类风险。安全停止独立后端后，独立15秒心跳、当前持久时钟与动态授权等待替换该依赖。

时限／手动暂停／配置超时／取消时先中断原生turn，再取消消费者并确认关闭。取消安全的owner保持追踪，重复取消不能提前清会话；accepted中断不等于停止确认。关闭失败保留原生进程／会话句柄，kill也等待退出；全部原生角色确认关闭后才清Run聚合unknown，历史失败事件不删。停止未知时不恢复重叠调用；已闭Codex按原线程恢复。Decision与普通审阅的迟到结果只能保留证据，不改写失效请求或新增提交／Trial。三处原直接接受夹具补真实running状态，原断言保留。最后两轴只读审查分别无剩余blocker；修复只有应用回归，没有新增真实Run额度证明长期效果。

### CS-UP-10

本轮明确授权CS-UP-10 W0–W5施工，取代上一轮暂不执行本卡的时间边界。W0先记录D-48–D-55；仅D-30附部分取代标注，其余原决定不改写。后续按W1基础设施、W2运行时、W3运维、W4现有ABC材料核查、W5证据交付推进；每项保留修复前复现与修复后对照，外部限制必须有已跑通替代方案。比赛无限能力配置不扩大本卡最小探针的明确数量额度。CS-UP-11及整轮彩排不在本轮授权中。

W1采用已实测bohr2.7.8的v4投递和镜像构建；其小型存储占位创建、独立对象上传、最终小型计算调度是三个阶段，不宣称所有create都在上传之后。旧1.1.0保留历史兼容。现代创建未知只有在完整分页确认缺席后，才能在原授权内以新ID重交原冻结输入；历史unknown不追溯重交。父Job找回优先于pending重交，取消等待者不等于native线程终止，所有可自动重交的后台对账参与安全关机。

同一最小Dockerfile的v2仍148888，v4已在Job和沙箱启动成功；采用已验证v4路线满足机制验收，不占用额外环境包存储。具体重型环境目录内容留待S4审计。原科研断言失败及脚本缺项保持原证据，不修改科学评分器来追求Job全成功。

W3c漂移检测独立读取公开原文，不复用上传前schema加载器：新协议本身可能已不符合旧加载器的假设。逐文档失败保留已确认变化及上次事实，漂移告警不等于适配器已兼容；上传离线验证继续使用自己的经验证快照。实际六份公开GET与字段变化/schema404对照均验证此边界。

W3d保留提供方全局退避硬边界，后备只调整新求解者而不绕开PI Astra的排队。请求模型的429不证明其他模型可用；恢复需要相关请求成功，或最近限流版本之后新开始且该版本未变的成功。并发旧完成不能清别人的持续失败。比赛资源预检与Run冻结采用一次投影，以免恢复/开关变化造成模型与条目事实不一致。

CS-UP-10 W3i：分诊导入只处理用户事务提示和排队配置，不验证科学事实或授予研究权限；原子全量校验并保留修订。可选助手三并行900秒超时，确认关闭后仅助手降档一次，不修改科研PI。助手调用/中断/未知持久记账；导入后手动模型选择以显式null取消条目。99项后端、88项前端/构建及隔离原代码16项对照通过，Chromium最终配置往返通过，无新科研Run/模型/提交。

CS-UP-10 W3最终提示回归：本地秒级许可不改变重计算入口，开关双态指令明确“Bohrium Job 或沙箱”，原有交付契约断言保留；51项回归通过。

CS-UP-10 W4只读核查：09 ABC已生成题面纪录作为控制，却交付排除控制例后的q≈1.488865候选，题面科学10；v1–v3五个已评分包均纪录三元组(q=q0)科学20，v2另一份unknown不补分。确认“未把已知纪录作为计分保底”，不是提交代码缺陷；09通用ARM确认分实际6.43，与科学档位分开。没有重跑计算/评分或提交。

CS-UP-10 W5回归边界：公开平台schema是上传硬门，旧EV测试夹具补齐paper和合法声明，但声明文件故意不产出，保留无工具/产物证据的blocked/advisory验证；不放松schema或修改原准入断言。系统分诊的source/attempts保存在独立持久账本，原模型六字段结果契约保留。CLI的urllib.parse导入统一到模块范围，避免新增ops分支让旧命令产生局部变量错误；本地秒级提示保持原契约词句及所有实际远端入口。

CS-UP-10 W5实际迁移：备份后两次主库初始化只加列/表，46张原表35695行及原列哈希保持；再次只读核验通过。旧recovering、手动暂停和冻结授权不自动恢复，未启动主库lifespan。Chromium最终往返与真实停用收割副本自检负例均通过，后者0模型turn；主邮箱配置没有停用。旧v2镜像错误保留、已验证v4作为当前路线，具体重型环境和新比赛满负荷检验留待用户另行启动S4/彩排。私有四份复盘远端身份已确认，不公开原始轨迹或回执。

CS-UP-10 W5最终验收：完整pytest1338项通过、0跳过、退出码0（737.99秒），两条既有测试依赖弃用警告保留；前端88项/生产构建、compileall/diff及9文件暂存检查通过，264个受测源码哈希不变。保留首次1329通过/9失败与中断现场，两轴只读完成审查无剩余阻断。交付标签lightchaser-fallback-2用于本卡最终版本，后续CS-UP-11与整轮彩排仍由用户另行启动。

### CS-UP-12

本轮以20069d7/lightchaser-fallback-2为实际基线，新增D-56–D-62并仅给D-53标注取代关系；其余原设计字节保留。任务授权限于针对性开发/测试及30模型探针、12个v4镜像构建、20Job（GPU最多4）、20沙箱和既有ABC冻结轨迹的维护复盘；不给新科研Run、比赛提交或整轮彩排授权，不执行CS-UP-11。新额度账本与主库一致性备份单独保存在.package-checks/cs-up-12；不重置10的历史额度或失败。

任务卡所举Codex0.159.x不是本机版本断言：开工实际LinuxCodex为0.148.0-alpha.15，fast字段以本机原生协议探测及平台接受证据为准，不改全局配置。用户限定无人值守，需用户核对/审批的内容记录到STATUS后继续施工。
