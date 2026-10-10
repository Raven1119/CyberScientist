# CS-UP-21 验收证据

## W1 凭据检查

- 已实现：原文、URL/二重URL、JSON转义及Base64编码的已存凭据硬拦截；形状只匹配至少20字符令牌及私钥块。普通英文 token、bearer、password 不触发。
- 已实现：形状命中持久化单项复核；`ops gates --target comp` / `ops gate resolve <id> --false-positive --reason ... --target comp` 人工放行，仅相同内容哈希和同项有效；已存凭据禁止放行。原生记录不改写。
- 已实际验证：`.venv/bin/pytest -q tests/test_native_log_privacy.py tests/test_credential_gate_cs21.py`：20 passed in 7.23s。涵盖 RH-02 普通词组、编码原文、硬拦截不可放行、形状复核与内容变化重新拦截。
- 已实际验证：对RH-02探索原生15,743,272字节扫描，SHA256 `5aebd2234dea75ed1ee2d9f452712e81c4188ec8a3f05750c8299df35fd0def9`；新分类器无命中，读取前后原字节相同。私有记录 `.package-checks/cs21/w1-native-classifier.json` 同时核对比赛实际存储凭据。
- 尚未验证：比赛发布后的端到端提交、复核后自动续接与前端复核（W5/W6）。

## W2 提示词 v3（含用户精度与评分补充）

- 已实现：从任务卡附录A–D原文提取角色、技能和用户模板，再合并用户追加：第一版按题面精度、评分检查项决定完成线、量级差异先排硬错误、复跑保持所选提交参数、执行者不自定更严目标。PI/执行者仍v3；技能逐项对照“评分在查什么”。
- 已实现：Codex/Kimi开局文字、旧协作文本和planning.startup的brief_instruction都说明acceptance_md写“评分在查什么”；无新增校验或拦截。
- 已实际验证：原提示词/角色/技能/比赛提示测试和新v3渲染回归：38 passed in 12.50s；原文哈希断言同步更新。
- 已实际验证：RH-02真实题面/Run数据库只读备份，以RunController._brain_spec/_lifecycle_packet、thread_params和CodexBrain._render_prompt生成原生会话开发者指令和首条消息。开发者指令18,183字节、SHA256 `825f5ee5ed13f84076aafe8e1a741f5d3e391c4638a9bf69dfcf24af59be95aa`；首条消息279,613字节。v3/题面精度/评分检查/量级硬错误/复跑参数五项新文字均在待发送上下文中，Ca3Co2O6题面保留；模型回合0。此项是实际代码渲染，不冒充已运行一个新PI科研会话。私有全文与检查：.package-checks/cs21/w2-pi-first-render.{md,json}。
- 已实际验证：通过比赛后端正常PUT /api/v1/rounds/round_a5637c86e9f9/prompt发布赛道建议版本2→3；数据库独立读回正文与v3模板逐字相同、SHA一致。未恢复旧Run。私有w2-prompt-publish.json。
- 已实际验证：模型上下文源范围src/cyberscientist、prompts、skills、templates搜索“最佳版本”“收敛或稳定性有证据”“实测收敛”“收敛参数由执行者”“最终收敛参数”；原冲突仅位于PI角色、提交技能、用户模板，已被v3替换。旧Run历史方法简报保留不改；新生成简报说明按评分检查项定内部目标。
- 尚未验证：W1–W4发布后的比赛原生参数渲染复核；W10全集将标记相对v2有改动。

## W3 PI主动唤醒与节奏

- 已实现：Job终态和沙箱后台命令终态形成compute.finished；当前Trial契约文件齐全/已有文件更新形成deliverables.ready；回合完成立即检查交付目录。后端独立观察后台命令，15秒巡视，Job对账后立即通知；不依赖检查点。
- 已实现：距最近已完成PI审阅/有效唤醒满1800秒后排异步审阅；设置与前端可调pi_review_interval_seconds（60–86400）。多触发复用同一pending请求，进行中的审阅只排一条后续合并请求，按计算操作身份去重。
- 已实现：决策/审阅/回答执行者提问的PI输入带节奏；计实际submitted次数和真实harbor_score，不由展示分推断科学分。批准90分钟、文件齐、实际提交0时生成前端“首次提交待办”。计算退出码/耗时/文件未被真实回执提供时保留unknown。
- 已实际验证：PI唤醒与原协作全组 `.venv/bin/pytest -q tests/test_pi_wake_cs21.py tests/test_collaboration.py`：67 passed in 48.10s。含三触发、合并、重复终态不再唤醒、文件更新、30分钟计时、真实字段合成的提交数/回执/剩余时间、90分钟告警及旧协作回归。协议fixture证据不冒充真实PI科学运行。
- 已实际验证：Linux PATH加入已有~/.local/bin后前端SettingsPage测试16 passed；无全局配置修改。
- 尚未验证：比赛目录发布后真实后台计算和native PI唤醒；本卡不新增科研Run，等待工具的有界真实验证仅在W8执行。

## W4 紧急指导直达

- 已实现：stop、改向（intent=reframe/change_direction）、提交前交付（deliver_before_submit）使用既有Prime.steer/Codex turn/steer，在busy当前回合插入，不等待检查点；普通补充仍排队。显式生命周期steer视为改向。
- 已实现：送达仍以原生accepted记sent/busy_insert；未知送达不冒称成功、不自动重放；ACK协议不变。停止先关受控动作门，再投递停止指导并请求原生abort。忙时插入不覆盖当前回合/Trial的归属。
- 已实际验证：紧急指导及协作全组67 passed in 46.70s；补充实际ACK回归5项另跑通过。隔离fake原生长命令仍等待时，紧急指导在同一忙回合投递并ACK，重复投递0；普通说明留queued。原生真实turn/steer协议为既有已验证机制，本卡未额外发科研模型回合。
- 尚未验证：W1–W4比赛发布与W5真实旧题提交；不以fixture回归代替真实提交。

## W5 真实补提准备（尚未发送）

- 已实现：ops submit的旧题有界授权入口可直接接收PI批准的outputs-only包；先经同一mailboxes.preflight_submission封存/准入/凭据检查，再进入原生绑定校验、冻结和同一官方CLI发送路径。已有合法封存包继续保持原字节。
- 已实际验证：旧题运维授权/原生隐私/凭据/官方CLI协议回归39 passed in 14.75s；新增fixture确认原候选包不变、复用普通封存、Run不恢复。
- 已实际验证：批准候选SHA256 `282461195c1287624238b85e2869e5134dff3ff475364599ea74f91990757387`，三份科学输出3949/383/130字节，私有w5-ready.json列逐文件SHA。读取未改科学产物或原生记录。
- 尚未验证：W1–W4发布后的正式发送、Worker哈希、科学分/轨迹分/判定/扣分码/评分耗时/harbor字段；真实发送0，未消耗≤2次授权。

### W2 全组检查发现的旧断言同步

- 已实际验证：全组检查的两项失败是test_content_import_cs20固定v2提交技能/用户模板哈希及roles/pi/executor v2标记；依用户追加要求同步为授权v3，其他技能正文哈希断言保持。包括该旧组在内的全部提示词/角色/技能回归40 passed in 49.73s；没有删除或跳过测试。

### W4 忙时改向补充复核

- 已实现：PI停止当前路线但仍有已授权未尝试通道时，既有换路转换明确使用change_direction，确保也走当前回合忙时插入。
- 已实际验证：PATH=/home/wmywb/.local/bin:$PATH .venv/bin/pytest -q tests/test_urgent_guidance_cs21.py tests/test_content_import_cs20.py tests/test_output_only_package_cs20.py：14 passed in 9.92s；保持原ACK和原生字节规则。
- 已实际验证：首轮全量1912 passed、3 failed，原因分别为两项v2固定断言和测试PATH缺Linux Node；已修正断言及测试启动环境，完整重跑中，不跳过测试。

### P0 发布前完整检查

- 已实际验证：PATH=/home/wmywb/.local/bin:$PATH .venv/bin/pytest -q：1916 passed, 2 warnings in 1237.94s，完整重跑无跳过；日志.package-checks/cs21/p0-pytest-corrected.log。前端25文件126项全部通过、npm run build通过；compileall及git diff --check通过。
- 已实际验证：正常/api/v1/mailboxes/claims/refresh读回5个已配置账号confirmed；平台GET目标题结束时间2026-08-08T12:00:00Z。旧题验证授权max_submissions=2；当前真实发送0。旧Run保持paused，其他旧recovering Run resume_on_startup=0。
- 尚未验证：本次比赛发布和旧题发送；W6–W10尚未交付。

### W5 真实发送及提前科学回执

- 已实际验证：W1–W4完整1916项检查后ops release 91b0faf001f25db0187cb250407d4f49e200832d completed；比赛健康身份PID1990018、同版本/比赛根目录，WebBridge前端成功打开。开发main已推送91b0faf；私有快照d2687fc6cc7ad3a7ca8e3b9f6b4549481c0f79f8、254文件密钥扫描0命中。
- 已实际验证：正常ops submit入口、封存/清单/凭据检查/官方CLI试构建/正式发送完成：sub_dfe4af1401，Attempt 50633，Worker 28223，账号mbox_fdc3509fc3（cyberscientist-exp-89b8dd）。真实发送1/上限2，首次成功，不使用第二次。
- 已实际验证：实际包SHA 7c0d6ab7d4afcb9b00c0588696cf6612eadfe965b5b85c38a4df5a9dfd59d36f，49,770,733字节；Worker receipt bundle.sha256一致。原候选三份科学输出逐字相同；native_trace/native.jsonl逐字哈希5aebd2234dea75ed1ee2d9f452712e81c4188ec8a3f05750c8299df35fd0def9，Worker native_trace哈希一致；原生记录未改。CLI试构建包哈希因时间字段不同，按既有接受例外核对实际包。平台未提供可核验同源下载URL，保留unknown，以Worker核对为证。
- 已实际验证：03:59:44.673564Z应用submitted；04:06:29.555943Z提前科学事件submission.science_observed，harbor_reward=1、harbor_score=100、scoring_source=harbor_worker；轨迹分和判定仍null，score_is_final=false，平台仍evaluating；首个科学回执约6分45秒。回执英文摘要称未找到完整可信解答，与数值100并存，原样留证，不将其解释为最终accept。
- 尚未验证：最终轨迹分、判定、扣分码与最终评分耗时；阶段回执未给扣分码。旧Run持续paused，所以科学事件供PI下一帧读取，未另开模型回合来演示实际PI唤醒；未恢复科研Run。私有w5-cli-receipt、w5-actual-package-check、w5-latest-receipt留存。

## W6 统一拦截复核与续接

- 已实现：未来凭据、封包/平台schema、Job强制预检、准入与明确拒收事件进入同一队列；源文件/原生行或event位置、规则、打码前后文、风险与已存原文标记。旧事件不回填，不自动恢复旧unknown。
- 已实现：原提交意图单独持久化、按原意图+内容哈希隔离；前端设置页逐项填误报理由，CLI/API审计后排原流程续接。未发送项复用原幂等键；明确失败、预约释放且无平台ref的项使用可审计续接键，仍重新检查授权/额度；已发送/unknown禁止重放。内容变化不续接，已存原文始终不能放行。Job预检批准绑定完整输入/权限/spec摘要，不影响另一包。
- 已实现：复核与续接结果只送PI的异步帧，执行者轨迹不接收监控开发指导；真实原生文件不改写。不可封存的损坏结构仍无法变成有效包，续接失败如实记录，不能伪造通过。
- 已实际验证：W6/原生凭据/旧题授权/PI唤醒回归39 passed in 13.56s；覆盖真实存储夹具硬拦截、误报后同原意图自动继续、候选变化停止、四类事件同队列、明确失败续接与unknown不重放、原文件不变及PI通知。前端复核+设置18 passed，含已存原文无操作按钮和显式理由提交。隔离fixture未进行额外真实发送。
- 尚未验证：最终比赛发布后的前端操作读回和完整全组检查，随W7–W10完成后发布。

## W7 监控等待

- 已实现：ops wait-alert --target comp --timeout 1800，经异步服务器长等待监听调用之后的新告警/待复核项，返回摘要；原有告警不会立即结束等待，超时明确“无新事件”。CLI HTTP时限为请求等待+30秒，不会按原30秒中断。
- 已实际验证：等待/运维/目标选择回归23 passed in 7.74s；新告警和复核项均在2秒内唤醒，超时无新事件，未发模型调用。
- 尚未验证：最终发布后CLI真实超时读回。

## W8 服务器端计算等待（实现）

- 已实现：research_job/research_sandbox action=wait一次调用，服务器只读观察至终态或1200秒上限；无模型调用、无自动提交/重交；操作归属检查、超时与安全关机中断如实返回。读取线程在协调器登记，HTTP等待超时不把在途读取误作结束。
- 已实现：桥接HTTP 1260秒且不自动重试wait，Codex会话系统MCP tool_timeout_sec=1500；已在比赛0.161.0二进制确认此配置字段存在。工具说明明确用wait，避免反复poll。
- 已实际验证：服务器等待/MCP/原生配置/沙箱协作回归23 passed in 10.61s；一次客户端wait多次服务器观察到终态、退出码、所有权、客户端时限及挂起读取受1秒期限限制。首轮两项分别为协调器不接受关键字转发和沙箱操作表无trial_id，已按真实接口/所有权表修正后完整相关组通过。
- 尚未验证：最终比赛发布后真实等待工具；本卡当前新增沙箱0、Job0，不把fixture称真实平台验证。

## W9 外置发布缓存（实现）

- 已实现：发布releases/history/previous/journal/aliases及暂存树均使用比赛目录同级CyberScientist-comp-cache；旧缓存rename迁移，冲突旧版本另存history，不删除证据；版本/原生HOME/数据/经验仍留比赛目录。nogit缓存SHA/标签回退和私有快照读取同步外置位置，迁移前旧格式仍可读。
- 已实际验证：缓存迁移/发布/私有快照回归32 passed in 8.37s；迁移前后逐字保留、目标冲突两版本均保留、重复迁移幂等、旧发布移除路径保留于外置previous、快照密钥边界通过；更新旧快照提交消息断言为本卡CS-UP-21。
- 已实现：旧协作文本的D-49/D-52开发编号去掉，实际规则正文保留。字面扩展预扫描发现旧经验历史有287处开发编号（含中文相邻），不改写已审批/退役正文，也不临时扩大发布规则导致历史数据阻断；既有发布规则保持，《提示词全集》将按字面列出实际active命中供审阅。不能将既有边界匹配0说成全文0。
- 尚未验证：真实比赛目录发布/回退各一次及缓存目录不存在，需最终全组通过后完成。

## W10 导出器实现与初步验证

`ops prompts dump --target comp` 从运行中的比赛后端调用该版本自带的生成器。生成器在独立进程备份数据库、复制经验后渲染，不修改在用令牌、运行事实或原生记录，不启动模型。v2 比对基线为开发提交 `d6140cb`，补入比赛 v2 `b327babb0aaf32c83663e53cae029936efad33af` 的技能文件哈希；只记录哈希，不复制凭据。五个角色分别给出开发者指令、真实 RH-02 首条和代码模板、协议/事件/指导、工具、技能、经验、赛道提示。全部启用技能和 active 全局经验正文在共用附录完整收录。

`tests/test_prompt_book_cs21.py`、原角色文本和内容导入回归合计 **14 passed**。全集实际生成、推送和最终版本证据将在发布后补记。供应商内建工具的隐藏定义不由应用代码提供，全集列出所有应用 MCP 定义，并明确此限制；不编造供应商文本。

### W8 实际 MCP 等待证据

比赛 `f967096` 经 stdio MCP 初始化、工具目录和一次 `research_job wait` 调用返回真实 RH-02 Bohrium Job **23515296** 的终态：`operation_id=triala_sigma0025_pair_cpu_v1`，`Finished`，`terminal=true`，`timed_out=false`，`waited_seconds=0.006`，请求上限 1200 秒。该 Job 在调用前已完成，所以此项验证真实 API/MCP 路径及终态返回，不声称验证了真实远端长耗时中途等待。运行中至终态和挂起读取硬超时见 23 项等待/MCP/协议回归。为验证等待未创建新 Job 或沙箱，模型调用 0；临时能力令牌验证后撤销。原始证据 `.package-checks/cs21/w8-real-wait.json` 保留在私有目录。

### W9 实际迁移与首轮发布

`ops release --commit 0b012a1 --target comp --timeout 240` completed，代码 manifest SHA `3eeb64f7c6e8d4f109afbe6afe117087823072864dae678b7d7220ffaa66df42`，私有快照 `0ed31de13bda477af208a96844da81e24f137985` 已推送。`.runtime/{releases,release-cache-history,previous,release-journal,release-aliases.json}` 五处均不存在，迁移后保留的全部缓存版本位于兄弟目录 `CyberScientist-comp-cache`。随后发布 `f967096` completed；回退和恢复证据后补。

### W10 实际导出错误及修正

首轮 `ops prompts dump` 返回 422：RH-02 事件的 `brain.raw_output` 只有 2000 字符摘要，完整交接在原生 PI 记录中，生成器未取得四段。修正为从该 Run 登记的 PI 会话 ID 在比赛原生目录唯一定位原始记录，只读解析完整已批准决定；不改记录，也不补造交接。

全量回归发现 5 个原有本地计算开关断言失败：W9 删除开发编号后，旧替换仍只匹配 `按D-49`。同步匹配无编号的实际段落，保留全部原有测试。失败记录保留，不计通过；修正后的结果另记。

修正后的 `tests/test_prompt_book_cs21.py tests/test_features_cs10.py`：**58 passed / 85.56 秒**；再次运行完整交接文本提取测试：**4 passed / 5.72 秒**。无 Git 的比赛目录按设计只接受完整缓存 SHA 或缓存标签；短 SHA 的回退在 prepare 阶段被拒，未停服务。随后用完整缓存 SHA 执行真实回退，结果后补。

### W5 最终平台回执（补测已完成）

正常应用路径的一次正式发送 `sub_dfe4af1401` / Attempt **50633** / Worker **28223**，账号 `mbox_fdc3509fc3`（cyberscientist-exp-89b8dd）。平台最终回执于 **2026-10-10T04:10:07.126869Z** 已观察到：`harbor_reward=1.0`，`harbor_score=100.0`，展示科学分 **100.0**，`trace_score=82.8`，`trace_decision=accept`，`scoreIsFinal=true`。科学分提前观察时间 04:06:29.555943Z，距发送约 6 分 45 秒；最终状态距发送约 10 分 22 秒。最终分数读取记录 04:10:11.682056Z。

原始最终回执 `trace_low_score_reasons` 仍列出 **N11_OUTPUT_NOT_CAUSALLY_SUPPORTED** 和 **N14_METHOD_SUBSTITUTION_OR_FALLBACK**；其解释、score_effect、remediation 完整保留，不因最终 accept 删去。`scoringDetails.gradable=true`、`counts_toward_season=false`：这是已经结束旧题的有界补测，不声称具备 Lightchaser 或当期正式参赛有效性。平台字节无法下载的既有例外仍采用 Worker 实际发送包及原生轨迹哈希逐项一致作为证据。最终平台响应、数据库快照保存在 `.package-checks/cs21/w5-final-platform-response.json`、`w5-final-receipt.json`，均未入 Git。第一发送成功，第二次发送条件未触发，真实提交总数 **1**。

### W7 / W9 实际命令验证

`ops wait-alert --target comp --timeout 1` 实际阻塞至超时并输出 **无新事件**；新事件几秒内返回的回归见 23 项测试。缓存回退用无 Git 的比赛目录执行：`ops redeploy --commit 0b012a1e0648cc92fabc53bfa899eb0ba5612c90 --target comp --timeout 240` **completed**；恢复最新版和最终清单后补。整个过程旧 RH-02 未恢复科研执行，未知外部操作未重发。

### W2 最新补充在 W10 中的实际送达证据

正式命令 `ops prompts dump --target comp --output docs/PROMPT_BOOK.md` 成功。生成源为比赛 `ed22d25ab1807d2640221398b2e5911192f66f93` 的实际模块，使用真实 RH-02 题面和后台配置，模型调用 **0**。PI 实际开发者指令 **18,400 字节**，首条消息 **324,202 字节**。数值设置第一版采用题面给定取值/界限、评分检查项、量级差异硬错误检查、干净复跑参数沿用要复做的提交均已进入开发者指令；首条消息中的简报协议也要求“评分在查什么”。PI 开发者指令及投稿技能在《提示词全集》中明确标为**相对 v2 有改动**，角色文件仍为 **v3**。完整历史交接只读提取，书中将历史昂贵设置单列为历史材料，不修改已批准方法或原生轨迹。

### W10 正式生成结果

[docs/PROMPT_BOOK.md](PROMPT_BOOK.md)：**2,653,012 字节**，SHA256 **a34935f6aa8d93ae6455466bfce3c3a434bc0e8ffcc1c2f9de2357ccdc421ee5**。112 个片段，22 个启用技能全文、41 个 active 全局经验全文；五个角色按送达时机组织，源文件/函数、可编辑位置、字节和 v2 对照逐段列出。2408 条疑似冲突扫描命中逐项列出全集行列及修改位置；包括历史交接、旧经验和模板源码，不自动改写这些材料。全局经验的后续改变仍须前端审批。

以比赛已存凭据原文及编码形式检查完整全集，**0 命中**。供应商完整隐藏内建工具定义不由应用代码提供：本书导出全部应用 MCP 清单/说明并写明限制，不假造供应商工具文本。重新生成使用 `ops prompts dump --target comp --output docs/PROMPT_BOOK.md`；运行事实、时间和回执字段随实际状态变化，比较时应区分动态数据与静态指令。

### W9 恢复及全量检查进行中

完整 SHA 回退后，`ops release --commit ed22d25 --target comp --timeout 240` **completed**，私有比赛快照 **b4eb0f773817722e74e9ebc3d74c7f1ae4668ef4** 已推送。旧缓存位置保持不存在。

第一轮全部后端测试 **1934 passed / 5 failed / 2 warnings / 1275.16 秒**；五个失败均是移除开发编号后开关替换的原有断言，修正后的相关 58 项通过。现重新运行完整套件，不跳过或移除失败测试。前端全量 **128 passed / 26 files**，构建通过；compileall、diff 检查通过。最终全量结果与推送标签另补。

全集初次生成有两行由本地计算策略替换产生的尾随空格，`git diff --check` 命中；已修正替换源的多余空格并安排重新发布、导出及完整回归。上述初次全集哈希作为历史生成结果保留，最终文件哈希以最终清单为准。所有原生记录保持不变。

去掉替换源多余空格后的原提示词/开关与导出回归 **58 passed / 24.77 秒**。完整套件重新从头运行；前轮中断结果保留但不计作通过。

### W10 最终全集 / W6 前端实际读回

空格修正版 `550f8854951ebbc1d2eedf6ff346755f862050df` release completed，重新通过比赛 `ops prompts dump` 导出。最终 [PROMPT_BOOK.md](PROMPT_BOOK.md) **2,653,024 字节**，SHA256 **c877d43bb443d4dbe322a9544ce3fb57b305b750d9c06e82d6ccd6ccb0930804**；PI 首条 **324,205 字节**。v3 新评分/精度约束检查 true；112 片段、22 技能全文、41 active 全局经验全文，已存凭据精确及编码检查 **0 命中**，模型调用 **0**。静态提示不变，时间、事件和节奏等真实字段使两次导出的总字节略有差别；前述旧文件哈希是历史生成事实，最终以本节为准。`git diff --check` 通过。

WebBridge 通过自有标签读回 `http://localhost:8765/` 的真实比赛工作台，连接与设置页面显示 **拦截复核 / 没有待复核项** 和 **自动提交已启用**，API `/api/v1/settings`、`/api/v1/ops/gates` 均 200。浏览器后台标签的被动渲染导致初看“正在加载”，启用该自有标签的虚拟焦点后完成，非后端或接口故障。没有写设置、审批经验、放行真实拦截或恢复科研。真实页面证据在私有 `frontend-settings-confirmed.json`；操作行为及同原意图续接由原 W6 回归覆盖，不借演示再发平台 Attempt。
