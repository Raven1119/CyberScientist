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
