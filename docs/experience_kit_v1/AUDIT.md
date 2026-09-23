# CyberScientist 代码审计报告

审计基线：`Raven1119/CyberScientist@46bba5d0bc24a03ec1be889384442e6dbe36ced2`。本次只读审计，未修改远端仓库。

## 1. 结论与证据范围

当前优先风险是**经验数据覆盖、版本/使用证据失真、协作信息丢失和授权控制不一致**。这些问题会让系统积累错误的经验关联，甚至把未经确认的行为当作完成。应先修复可验证的数据与控制链，再增加学习算法。

**发现归并为 21 组：14 组至少一个症状得到隔离复现，7 组为静态确认、待完整应用联调。**20 个隔离探针全部观察到预期缺陷；20 不是独立 bug 数，也不是产品回归通过数。B04/B06/B10 等组包含未单独动态复现的子症状，下文分别标明。

### 阅读范围

| 范围 | 实际检查内容 |
|---|---|
| 经验存储与投影 | `experiences.py`、`observation.py` 全文；两个文件已逐字重建并验证 Git blob 哈希 |
| 运行与协作 | `controller.py` 相关完整函数链、`collab.py`、`db.py`、`config.py`、生命周期/静默审阅/提问/指导/检查点/终止恢复路径 |
| 反馈与提交 | `mailboxes.py`、`mailbox_platform.py`、`api.py` 的相关注册/提交/评分/审批路由 |
| 模型输入 | Kimi 大脑构造与提示词、执行器协作提示词；对 Codex/Prime 仅检查调用入口和既有契约，不声称独立验证其协议实现 |
| 前端与测试 | `ExperiencePage.tsx` 的加载、选择、新建、保存、审批与回滚链；`test_experiences.py`、测试目录及相关契约记录 |
| 科研上下文 | 仓库的 Aiyagari 复现打包脚本、LoRA 运行记录；未独立核验当前官网全部题面与评分细则 |

本次没有全仓库 pytest、前端构建/浏览器执行、真实 CLI/模型/Bohrium/比赛提交测试。仓库 STATUS 的历史测试数字不作为本次测试结果。未逐文件审计全部检查脚本和其他前端页面。

### 隔离复现方式

| 测试脚本 | 探针数 | 实际环境 |
|---|---:|---|
| `repro_experiences.py` | 11 | 原始 `experiences.py` + SQLite 经验表 + 临时目录/配置接口替身 |
| `repro_pipeline.py` | 6 | 原始 `observation.py` + 原始 controller/collab 函数摘录 + SQLite 测试夹具 |
| `repro_submissions.py` | 3 | 原始提交函数摘录 + 带锁 SQLite + 两线程/模拟平台故障 |

判定边界：原始模块行为与函数级竞态可以复现；替身依赖不能证明整个应用、浏览器和外部协议已联调。所有网络、副作用和真实凭据均未进入探针。

严重度：P1 为应优先修复的数据丢失、错误证据、授权或关键运行问题；P2 为影响范围较窄的输入/路径问题。严重度表示影响与修复优先级，不表示已经发生生产事故。

现有经验测试的关键缺口：`test_experiences.py` 的单条创建测试没有覆盖两个中文标题共存；回滚测试只检查恢复后的正文和唯一内容行数，没有检查当前版本清单及再次保存。现有通过记录因此不能排除 B01/B02。修复时应补行为断言，不能只更新测试数量。

## 2. 问题总表与逐项证据

| ID | 级别 | 问题 | 证据等级 |
|---|---|---|---|
| B01 | P1 | 中文标题和同名标题会覆盖另一条经验 | 已隔离复现 |
| B02 | P1 | 回滚后的当前版本错误，再次保存还可能假成功 | 已隔离复现 |
| B03 | P1 | 外部编辑进入使用路径，却未进入版本历史 | 已隔离复现 |
| B04 | P1 | 经验作用域与实际目录不一致，模型更新缺少题目归属检查 | 作用域问题已隔离复现；target_id 问题为静态检查 |
| B05 | P2 | challenge_id 的路径校验接受点目录段 | 已隔离复现 |
| B06 | P1 | 启用操作改写证据强度，模型更新还会丢元数据 | 审批改写已隔离复现；提议元数据问题为静态检查 |
| B07 | P2 | 非法 frontmatter 类型可绕过受控错误边界 | 已隔离复现 |
| B08 | P1 | “新建经验”与自动选择副作用冲突 | 静态确认；未进行浏览器复现 |
| B09 | P1 | 收尾才产生的经验也被算作本轮使用过 | 已隔离复现 |
| B10 | P1 | 检索、证据标签和实际注入没有统一契约 | 选择与标签丢失已隔离复现；其余为静态检查 |
| B11 | P1 | 只读取 400 条事件，却推进到更大的“已审阅”范围 | 已隔离复现 |
| B12 | P1 | 正式评分没有直接进入大脑反馈帧 | 已隔离复现 |
| B13 | P1 | 阻塞检查点重试返回 continue，违反当前门禁 | 已隔离复现 |
| B14 | P1 | Run 模式与实际运行时选择分离，存在授权绕过路径 | 静态确认；未启动真实模型 |
| B15 | P1 | 时长用尽只改 paused 状态，没有停止执行器 | 静态确认；未启动真实执行器 |
| B16 | P1 | 提交预算检查不原子，两次并发可穿透单次授权 | 已用真实线程与本地 SQLite 隔离复现 |
| B17 | P1 | 回执丢失被当作确定失败，额度释放后可能重复提交 | 已进行隔离故障注入 |
| B18 | P1 | 执行器启动失败处于主清理边界之外 | 静态确认 |
| B19 | P1 | 手动提交和批量注册在 async 路由内执行同步网络 | 静态确认；未进行实时延迟测量 |
| B20 | P1 | 全局审批没有绑定用户实际看过的版本 | 静态确认 |
| B21 | P1 | 空闲指导通道缺少另一通道已有的 Trial 过期检查 | 静态确认 |

### B01 · P1 · 中文标题和同名标题会覆盖另一条经验

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L270)，`save_experience`。**证据：**已隔离复现。

**触发与根因：**新建两条不同 ID 的经验，标题分别为“数值误差诊断”和“认证状态检查”。文件名由标题经过 `[^A-Za-z0-9_.-]+ → _` 生成，两者都写入 `experience/global/_.md`。

**影响：**第一次和第二次保存均成功，但当前目录只剩 `exp_b`，`exp_a` 无法按正常当前条目路径读取。旧修订仍可能在 SQLite 中，不能把这描述成全部历史均已丢失。英文同名、清洗后相同或截断后相同的标题也存在同一问题。

**本次证据：**`B01-title-collision`：预期两个 ID，实际只剩一个；两个保存回执的路径相同。

**最小修正：**新文件一律用校验过的不可变经验 ID 命名，标题仅作展示。创建时检查路径所有者，不覆盖别的 ID。迁移前备份目录和数据库；从旧修订恢复时逐条确认，不按文件名猜身份。

**验收断言：**同目录中不同 ID、中文标题、同名标题均能独立读写；更新 A 不改变 B 的字节与当前版本。

### B02 · P1 · 回滚后的当前版本错误，再次保存还可能假成功

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L91-L124)；[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L315)，`_scan_dir / save_experience / restore_revision`。**证据：**已隔离复现。

**触发与根因：**执行 `v1 → v2 → 回滚 v1 → 保存 v2`。代码用“按创建时间最新的修订”推定当前版本，又以 `(experience_id, revision_hash)` 去重内容；回滚复用历史内容，不产生新的当前指针。

**影响：**回滚后文件正文是 v1，列表的 revision_hash 仍是 v2。随后保存 v2 返回 `unchanged=true` 和 v2 哈希，磁盘却仍是 v1。调用方可能相信修改已生效，运行快照也可能引用错误版本。回滚动作本身没有独立历史记录。

**本次证据：**`B02-rollback-head`、`B02-redo-false-success`、`B02-rollback-audit`。最后一项检查操作历史缺口，不将其重复计为独立 bug。

**最小修正：**区分内容哈希和修订操作 ID，维护显式当前版本指针。回滚新增操作并指向恢复内容；是否 unchanged 与实际当前内容比较，不能与历史最新创建行比较。

**验收断言：**回滚后正文、当前指针、清单哈希一致；再次保存 v2 后确实读回 v2；历史保留回滚操作且重试同一操作不重复。

### B03 · P1 · 外部编辑进入使用路径，却未进入版本历史

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L91-L189)；[docs/EXPERIENCE.md](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/docs/EXPERIENCE.md)，`_scan_dir / get_experience / save_experience`。**证据：**已隔离复现。

**触发与根因：**保存 v1 后直接编辑 Markdown 为 external，然后列出经验并继续保存 v3。目录扫描只读取文件，没有把外部修改追加到修订历史。

**影响：**新正文可能配上旧 revision_hash；后续修订历史只有 v1/v3，external 消失。外部文件变成无效 frontmatter 时，该条目直接从列表消失；文档约定的“保留上一份已认可版本”没有实现。

**本次证据：**`B03-external-head`、`B03-external-history`、`B03-invalid-edit-fallback`。

**最小修正：**在检索与编辑入口统一扫描外部改动。合法改动先登记来源为 external 的新修订，再提供给新决策；非法草稿保留并显示错误，继续使用已登记的可用版本。不得给未登记正文配旧哈希。

**验收断言：**外部修改被实际展示前有可恢复的修订；非法编辑不会破坏旧可用版本；新 Trial 能说明采用哪一版。

### B04 · P1 · 经验作用域与实际目录不一致，模型更新缺少题目归属检查

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L270)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`save_experience / _apply_experience_proposal`。**证据：**作用域问题已隔离复现；target_id 问题为静态检查。

**触发与根因：**已存在的 CH1 经验修改 frontmatter 为 global，保存逻辑继续使用原文件路径。另一路径中，模型提供 target_id 后，控制器继承目标条目的 challenge_id，没有核对其是否属于当前 Run。

**影响：**改为 global 的条目仍在 CH1 目录，全局列表看不到；范围声明和读取路径相互矛盾。若模型错误引用另一个题目的经验 ID，可更新那个题目的经验。后一项没有执行端到端复现。

**本次证据：**`B04-scope-move`：更新成功，但 global 列表为空。跨题更新依据 `_apply_experience_proposal` 的 target_id 分支判断。

**最小修正：**正常更新固定 ID、scope 和 challenge_id。推广全局采用显式派生新条目；题内模型更新强制校验目标属于当前题。需要迁移作用域时走单独原子操作，不只修改 frontmatter。

**验收断言：**普通更新不能改变归属；跨题 target_id 被拒绝且不修改目标；合法全局派生保留原条目和来源链接。

### B05 · P2 · challenge_id 的路径校验接受点目录段

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L80-L88)，`_exp_dir`。**证据：**已隔离复现。

**触发与根因：**`challenge_id=".."` 满足当前字符正则，并被拼入 `experience/challenges/../`。

**影响：**题内经验可以写到 challenges 子目录之外，后续目录扫描无法按预期找到。此处复现的是经验存储边界错误，没有证明任意路径写入或远程代码执行。

**本次证据：**`B05-dotdot-scope`：保存被接受，回执含 `experience/challenges/../Alpha.md`。

**最小修正：**拒绝 `.`、`..`；对 resolve 后路径做目录包含校验；读取与写入共用相同 ID 校验。

**验收断言：**点目录段被清晰拒绝；正常 CH1、带连字符的合法 ID 不受影响。

### B06 · P1 · 启用操作改写证据强度，模型更新还会丢元数据

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L273-L295)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`approve_experience / _apply_experience_proposal`。**证据：**审批改写已隔离复现；提议元数据问题为静态检查。

**触发与根因：**approve_experience 无条件写 `evidence_status=observed`。控制器题内提议也固定为 active+observed，并重建 frontmatter，只带部分字段。

**影响：**一条 contradicted 的候选经过“批准启用”后变成 observed；启用与证据状态的独立语义被破坏。模型更新还可能丢掉 tags、expires_at、derived_from 等字段。题内自动启用是用户已选择的策略，本审计不把自动启用本身列为 bug。

**本次证据：**`B06-approval-evidence`：预期保留 contradicted，实际 observed。其他症状来自提议落库代码。

**最小修正：**审批只改变可用版本，不隐式提高证据等级。保留未知元数据并显式更新字段；允许 active+hypothesis，用真实证据支持状态升级。模型的解释不自动成为 observed。

**验收断言：**启用/驳回不篡改证据强度；单字段修改不丢失适用条件、有效期和来源；无新证据不自动升级。

### B07 · P2 · 非法 frontmatter 类型可绕过受控错误边界

**位置：**[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L50-L77)，`parse_experience`。**证据：**已隔离复现。

**触发与根因：**传入 `status=[]`，代码直接对 set 做成员判断，抛出 unhashable TypeError。id、title、tags 等类型也没有完整检查。

**影响：**格式错误不能稳定地转换为 ExperienceError；编辑或扫描调用可能异常中断。前端还依赖 tags 为数组和 title 为字符串。

**本次证据：**`B07-invalid-frontmatter-error`：预期 ExperienceError，实际 TypeError。

**最小修正：**先做轻量字段类型和长度检查，再做枚举判断；每个错误绑定文件和字段。只校验结构，不增加科研语义审批器。

**验收断言：**列表/对象型枚举值、非字符串标题、非数组 tags 均返回受控错误，其他合法条目仍能列出。

### B08 · P1 · “新建经验”与自动选择副作用冲突

**位置：**[apps/web/src/pages/ExperiencePage.tsx](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/apps/web/src/pages/ExperiencePage.tsx)，`startCreate / selectedId effects / loadDetail`。**证据：**静态确认；未进行浏览器复现。

**触发与根因：**startCreate 设置 creating=true、selectedId=null 和新表单。自动选择 effect 在 selectedId 为空且列表非空时立即选择首条；另一个 effect 在 selectedId 为空时清空表单。

**影响：**已有条目时，新建状态可能马上被首条经验的异步详情覆盖，loadDetail 又设置 creating=false。空列表场景中，新建 ID 和模板也可能被清空。快速切换条目时，旧详情响应还可能覆盖新选择。

**本次证据：**检查了组件中相互作用的状态赋值和 effects；没有运行 React 或模拟浏览器，因此不把 UI 实测写为已完成。

**最小修正：**creating 时禁用自动选择和详情重载；表单重置由明确进入/退出操作执行；loadDetail 用请求序号或取消机制忽略过期响应。

**验收断言：**空库和非空库都能新建；快速 A→B 切换不显示 A 的迟到内容；刷新列表不吞掉未保存草稿。

### B09 · P1 · 收尾才产生的经验也被算作本轮使用过

**位置：**[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_experience_usage / _record_experience_snapshot`。**证据：**已隔离复现。

**触发与根因：**效果回联对 at_start 与 at_end 的经验 ID 取并集，再给每条关联整轮的 MAX(score)；不区分修订和实际采用时间。

**影响：**在得分之后才整理出的经验，也会得到“本轮使用、最好分数 86”的回联。这种记录无法代表实际使用，更不能证明贡献。用户原本选择“不自动评分”并无问题，缺陷在于可用清单被命名和消费为使用证据。

**本次证据：**`B09-retroactive-use`：at_start 为空，只有 at_end 的新经验仍出现在 usage 中并关联 86。

**最小修正：**历史起止清单标为 availability_only；新增明确的版本化采用记录。仅关联采用后实际动作与结果，整体 Run 分数可以展示为背景，但不能赋给每条经验作收益。

**验收断言：**得分后的新经验不产生此前使用记录；采用 A@r1 后更新到 r2，结果仍指向 r1；未采用条目不被记为 adopted。

### B10 · P1 · 检索、证据标签和实际注入没有统一契约

**位置：**[src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py#L115-L136)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[prompts/collaboration/executor.md](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/prompts/collaboration/executor.md)，`_selected_experiences / _memory_manifest / start_trial task text`。**证据：**选择与标签丢失已隔离复现；其余为静态检查。

**触发与根因：**观测帧取前六条 active，且先扫描全局；manifest 使用另一套数量截断；执行器又直接读取可变目录。观测帧渲染丢弃 evidence_status、applicability、expires_at 等元数据。

**影响：**六条全局经验可完全挤掉本题经验。被反驳、过期或仅适用于另一环境的条目会以没有这些警告的正文进入帧。冻结清单只有 ID/hash，无法保证执行器随后读到的文件是同一版本。配置的总字符预算也没有统一执行。

**本次证据：**`B10-challenge-starvation`、`B10-lost-applicability`。生命周期帧主要是经验标题/hash，普通生命周期提示词禁工具；shadow/requested 帧则确实有正文，不能笼统说“大脑完全看不到经验”。

**最小修正：**一个选择与渲染入口服务所有角色；保留适用范围和证据状态，执行统一预算并避免固定全局前缀饿死题内内容。在决策边界冻结实际正文和版本；不再把实时目录读取当作冻结上下文。

**验收断言：**相关题内条目有进入候选的机会；适用条件/反例标签保留；总预算可检查；运行中编辑不改变已交付包。

### B11 · P1 · 只读取 400 条事件，却推进到更大的“已审阅”范围

**位置：**[src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py#L139-L263)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`build_frame / _apply_review_result`。**证据：**已隔离复现。

**触发与根因：**build_frame 从 from_seq 开始读取最多 400 条，但保留调用方传入的 through_seq；接受结果时 covered_seq 按 through_seq 推进。

**影响：**超过 400 条的尾部可能永久跳过。探针中第 401 条为 prime.error，未进入帧，quality 仍声明没有截断和省略。如果结果被接受，游标会跨过该错误。

**本次证据：**`B11-event-coverage`：through_seq=401、notable 不含错误、truncated=false、omitted_count=0。探针直接验证帧，游标后果由接受结果代码确认。

**最小修正：**按页处理全部声明覆盖的事件后再推进游标，或仅推进到实际处理的末条。摘要可以有界，覆盖账必须真实；单纯把 400 调大不能解决问题。

**验收断言：**401/1000 条积压中的尾部关键变化不丢失；未读取范围明确保留；重启与重试不会跨越未处理证据。

### B12 · P1 · 正式评分没有直接进入大脑反馈帧

**位置：**[src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py)；[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`poll_scores / event_excerpt / build_frame / shadow triggers`。**证据：**已隔离复现。

**触发与根因：**poll_scores 已落库正式分数并记 submission.scored，但该事件不在 notable 列表；metrics 固定为空，official_score 固定出现在 unknown_fields。生命周期事件摘要也不给该类型的 payload。

**影响：**正式得分 86 已在本地数据库，大脑的常规审阅仍可能只看到事件类型或“不知道”。评分事件也没有直接唤起路径。执行器手动报告、后续整理读取 usage 仍可能传入得分，因此不宣称任何路径都无法获知评分。

**本次证据：**`B12-official-score`：有 scored 记录和事件，帧无评分数据，event_excerpt={}。

**最小修正：**从已登记提交读取评分 delta，附 submission/trial/提交包哈希和最终性；更新未知字段，必要时进入现有审阅队列。Run 已停止时只保存待整理信息，不自动追加付费调用。

**验收断言：**正式得分入帧一次且可追溯到提交包；pending 不伪装 final；迟到评分不自动重启取消的 Run。

### B13 · P1 · 阻塞检查点重试返回 continue，违反当前门禁

**位置：**[src/cyberscientist/collab.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/collab.py)，`submit_checkpoint duplicate branch`。**证据：**已隔离复现。

**触发与根因：**首次 blocking checkpoint 返回 yield 并设置 gate=yielding。相同 key 和内容重试时，幂等分支固定返回 review_id=None、next_action=continue、guidance=[]。

**影响：**首次响应丢失后的合法重试会告诉执行器继续，尽管系统仍在等待大脑；同时丢失关联审阅收据。若首个响应携带指导，当前重试语义也无法重放同一指导。

**本次证据：**`B13-blocking-retry`：首次 yield，重试 continue，而 actual_gate=yielding。探针使用合法消息并替换了无关 schema/outbox 依赖。

**最小修正：**持久化原检查点收据与关联 review；重试返回同一身份和当前真实门禁，不在阻塞时允许 continue。指导重投保持原 ID，并依靠 ACK 去重。

**验收断言：**响应丢失后重试不绕过阻塞；不新建审阅；已投递指导可用同 ID 对账，不能因重试重复执行。

### B14 · P1 · Run 模式与实际运行时选择分离，存在授权绕过路径

**位置：**[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)，`create_run / start_async / _make_brain / _make_prime / _run_loop`。**证据：**静态确认；未启动真实模型。

**触发与根因：**Run 保存自己的 mode；allow_model_calls 检查只在 run.mode=connected 时执行。运行时工厂和主循环却依据实时 settings.app.mode 选择真实或 Demo 适配器。

**影响：**创建 Demo Run 后将设置改为 connected，再启动时可选择真实运行时而跳过 connected 授权检查。反向切换则可能把 Demo 运行标成 connected。恢复路径同样从实时配置重建，缺少等价授权复核。

**本次证据：**由模式来源和授权分支的代码直接确认可达风险；未用用户凭据、未发生测试付费调用。

**最小修正：**明确每个 Run 的有效模式与运行时，创建/启动/恢复统一读取；切换需显式记录并校验授权，真实调用点不以客户端标签作为绕过条件。模式入参采用合法枚举。

**验收断言：**Demo 标签不能触发真实 runtime；未授权调用在启动/恢复/配置变更后仍被阻止；结果来源与实际运行时一致。

### B15 · P1 · 时长用尽只改 paused 状态，没有停止执行器

**位置：**[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_run_loop time-limit branch`。**证据：**静态确认；未启动真实执行器。

**触发与根因：**主循环在等待队列前检查时长；无事件时 q.get 最长等待 3600 秒。超时分支直接把 phase 写为 paused，未调用执行器 abort，也不等待原生停下确认。

**影响：**超时可延迟发现；UI 已显示暂停，执行器仍可能继续原回合和工具调用。这个问题与“远程 Job 不一定被取消”应分开表述，前者是本地执行状态失真。

**本次证据：**检查了超时分支、手动暂停分支和 loop 等待行为；没有把已有文档中的旧超时事故当作本次实测。

**最小修正：**将截止时间纳入队列等待上限，超时走统一暂停路径：停止新动作、请求取消、收到状态证据后才标 paused。远程计算的运行/计费状态单独记录。

**验收断言：**持续无事件也按授权截止触发；未确认停止时显示 pausing/unknown；暂停期间无新的受控模型/提交动作。

### B16 · P1 · 提交预算检查不原子，两次并发可穿透单次授权

**位置：**[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)，`_check_budget / submit_experiment`。**证据：**已用真实线程与本地 SQLite 隔离复现。

**触发与根因：**Run 预算在事务外检查，且只统计 status=submitted。邮箱预占虽在事务内，但在途 unknown 提交未占用 Run 配额。

**影响：**max_submissions=1 时，两次并发提交都可通过检查并进入平台适配器。单个邮箱的原子计数不能替代 Run 级预算预占。

**本次证据：**`B16-submission-budget-race`：两个线程在 fake platform 屏障同步，最终两个回执均为 submitted；没有真实平台请求。

**最小修正：**同一事务内校验并预占 Run 与邮箱配额，同时登记幂等操作。在途和待对账的 unknown 保留预占；幂等键检查也放入受保护写路径。

**验收断言：**授权 1 时任意并发量最多一个新提交副作用；重复操作 ID 不二次占额；确认未受理后才释放。

### B17 · P1 · 回执丢失被当作确定失败，额度释放后可能重复提交

**位置：**[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/mailbox_platform.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailbox_platform.py)，`submit_experiment / BohriumPlaygroundPlatform.submit_package`。**证据：**已进行隔离故障注入。

**触发与根因：**适配器的草稿创建、bundle 上传、正式提交在一次函数调用中完成；中间 attempt_id 未持久化。任意异常被服务层转为 failed，并释放邮箱额度。

**影响：**远端已受理但响应丢失时，本地会误判确定失败；新 operation_id 能再次发出副作用。未知远端状态需要对账，不能因为本地异常就认为额度未被消耗。

**本次证据：**`B17-unknown-treated-failed`、`B17-retry-after-unknown`：fake platform 先增加模拟远端受理计数再抛异常；本地标 failed、预占归零，第二次调用使模拟副作用增至 2。这是故障注入，不是生产平台事故记录。

**最小修正：**分阶段持久化 attempt_id 和已完成步骤；区分明确未受理、已受理、结果未知。unknown 保留额度并复查原 attempt，不自动以新身份重提。

**验收断言：**在创建/上传/提交后分别注入响应丢失，恢复能挂回原 attempt；没有“未知 → 释放 → 新提交”的自动重复链。

### B18 · P1 · 执行器启动失败处于主清理边界之外

**位置：**[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_run_loop startup / finally`。**证据：**静态确认。

**触发与根因：**brain.open 的错误有处理；随后 prime.start(_prime_spec(...)) 在后面的主循环 try/finally 之外。此处抛异常时不会进入完整清理。

**影响：**Run 可能停留 running，已开启的大脑会话和映射残留，事件循环任务已退出。启动成功前的错误不能靠正常运行收尾逻辑覆盖。

**本次证据：**检查初始化到 try/finally 的控制流；没有执行真实 CLI 启动故障。

**最小修正：**一个最外层 try/finally 覆盖两端会话启动和循环；部分启动失败也清理已获得资源，写明确 failed/blocked 及原因。

**验收断言：**分别在 brain.open、prime.start、pump 创建处注入失败，均无 running 僵尸、会话引用或未登记错误。

### B19 · P1 · 手动提交和批量注册在 async 路由内执行同步网络

**位置：**[src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)；[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/mailbox_platform.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailbox_platform.py)，`submit_experiment / register_experiment / harvest_submit HTTP handlers`。**证据：**静态确认；未进行实时延迟测量。

**触发与根因：**这些 async def 路由直接调用同步服务，底层 urllib 执行网络 I/O；评分轮询与部分自动提交已采用 to_thread，但手动路径没有。

**影响：**平台延迟可能阻塞同一个 asyncio 事件循环，影响暂停、状态查询与 SSE。批量注册会串行累积等待。

**本次证据：**由调用链确认；没有声称测得生产停顿秒数。

**最小修正：**将同步网络服务卸载到线程或采用异步适配器。数据库短事务仍保持在服务层，先修 B16/B17 的预占和未知结果语义，避免仅提高并发放大竞态。

**验收断言：**fake platform 延迟期间 health/control/SSE 仍响应；并发增加不越过提交预算。

### B20 · P1 · 全局审批没有绑定用户实际看过的版本

**位置：**[apps/web/src/pages/ExperiencePage.tsx](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/apps/web/src/pages/ExperiencePage.tsx)；[src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)；[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L273-L295)，`approve UI / approve_exp / approve_experience`。**证据：**静态确认。

**触发与根因：**前端只提交经验 ID；后端读取“当前文件”并批准，没有期望修订号。用户看到候选后，该条目可被其他编辑或整理更新。

**影响：**点击批准可能激活用户未审阅的新内容。另一个已存在的行为是全局 active 条目被模型更新后整条退回 candidate，旧批准版也退出默认使用。

**本次证据：**审批请求与服务签名没有 base_hash/expected_revision，静态确认版本绑定缺失；未执行 UI 并发复现。

**最小修正：**批准/驳回携带被展示的 revision_id 或 hash，事务内比较；陈旧审批返回冲突。全局候选更新保留独立的旧 active 指针，批准新版本后再切换。

**验收断言：**看到 r1 后条目变 r2，批准 r1 不得激活 r2；候选编辑不自动撤掉已批准版；用户明确停用仍即时作用于后续决策。

### B21 · P1 · 空闲指导通道缺少另一通道已有的 Trial 过期检查

**位置：**[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[src/cyberscientist/collab.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/collab.py)，`_deliver_queued_guidance / deliver_via_checkpoint_return`。**证据：**静态确认。

**触发与根因：**检查点返回通道核对 target_trial_id 与当前 Trial，不匹配就 superseded；空闲 prompt 通道只检查 running/open/not busy，取第一条 queued 指导后发送。

**影响：**目标是旧 Trial 的排队指导，可能在新 Trial 的空闲边界被投递。两个渠道的同一业务约束不一致，会污染协作与后续经验归因。

**本次证据：**对照两个实际投递函数；没有运行全控制器场景复现。

**最小修正：**两个渠道共用最小投递资格函数，在认领时检查目标 Trial、运行/门禁状态及适用的监督代次；过期指导记 superseded/invalidated，不发送。

**验收断言：**旧 Trial 指导在两通道均不会送达新 Trial；有效指导仍只选择一个投递通道；重复回执不重复执行。

## 3. 修复边界与实施顺序

### 第一阶段：可信版本与受控运行

优先修复 B01/B02/B03/B06/B20 的数据与审批链，及 B13/B14/B15/B16/B17 的协作/授权链；同时使启动失败可清理、手动网络调用不阻塞控制。验收目标是“保存、回滚、批准、暂停、重试和提交”都具备真实且可重建的状态。该阶段不新增学习算法。

### 第二阶段：一次可证明的经验复用

统一经验选择与冻结内容，补上实际采用记录、关键事件覆盖和评分反馈。用一条经验完成“第一轮提炼 → 第二轮采用指定修订 → 后续证据回联”，验证 B09/B10/B11/B12 修复后确实能支撑学习。详细设计见 `EXPERIENCE_PLAN.md`。

### 第三阶段：受控的增量学习

沿用当前大脑和题内/全局策略，根据真实结果更新适用条件与反例；不引入常驻第三代理、强化学习训练或大型经验图。再做固定初始经验与在线更新的等预算对照。

### 不应作为本次 bug 修复悄悄改变的决定

题内经验自动启用、全局经验人工审批、科研判断交给模型、执行器自主实施，均应保留。局部自动启用可以与 hypothesis 证据状态共存。现有 max_model_turns/max_jobs 未实现全面硬拦截属于明确存在的能力缺口，应在产品中真实显示；不能因有预算字段就宣称硬约束已经成立。

历史上的“可用清单”不可迁移成“实际使用证据”。没有记录的外部编辑、回滚时刻和原始响应不可凭模型补写；将未知历史标为 legacy/unknown，并保留可恢复的原始文件与修订。
