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
