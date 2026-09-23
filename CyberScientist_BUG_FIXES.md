# CyberScientist Bug 修复方法

基线：`46bba5d0bc24a03ec1be889384442e6dbe36ced2`。本文件给出可施工修改与回归断言；**本包未修改应用代码，以下不是已应用补丁**。原始定位与证据见 `AUDIT.md`，函数级复现见 `reference/audit_46bba5d/`。

## 1. 一次修复的边界

先在副本中备份数据库、experience 与工作区。采用当前代码重新确认根因，新增失败测试后完成最小修复；不因文件名相同覆盖用户已修改源码。不运行付费模型、Job、账号注册或比赛提交来复现本地程序问题。

原审计为21组问题、20个隔离探针，14组至少一个症状动态复现，7组静态确认；组内部分子症状仍是静态判断。重跑探针出现预期缺陷是“缺陷复现”，不等于产品测试通过。下面的验收是修复后的目标，未冒充已经执行。

| 实施批次 | 合并交付 | 涉及问题 |
|---|---|---|
| A 保存/审批正确性 | 一个能创建、编辑、回滚、审批且保持版本一致的经验库 | B01–B08、B20 |
| B 控制/提交正确性 | 不越授权、不丢门禁、不误判副作用的可恢复流程 | B13–B19、B21 |
| C 一次可信学习 | 同一经验版本进入下一轮并连接实际行动与结果 | B09–B12 |

不要把21个问题拆成21套独立新架构；共享版本、投递和事务语义在同一批次一起接通。保持题内自动试用、全局人工审批、两角色不对称协作。

## 2. 逐项修复

### B01 · P1 · 中文标题和同名标题会覆盖另一条经验

**代码落点：** `experiences.save_experience / 首次创建 / 数据迁移`。

**证据状态：** 已隔离复现。

**修改方法：** 新建时先验证不可变 ID，以 `<id>.md` 定位，不再从 title 推导路径。在同一个写锁内核对目标文件所属 ID，采用独占创建，存在异主文件时返回冲突。普通更新沿用已登记路径。离线迁移先备份；按文件 frontmatter 与修订表恢复可确认条目，绝不能用清洗后的文件名猜身份。

**必须保留的语义：** 本包初次导入已经直接使用 ID 路径并登记匹配修订，因而不会走标题碰撞分支；应用的其他新建路径仍要修改。

**修复后验收：** 同目录新增两个中文标题、两个相同标题、两个清洗/截断后相同标题；四类场景都保留独立 ID，更新其中一条不会改变另一条字节。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L270)，`save_experience`。

### B02 · P1 · 回滚后的当前版本错误，再次保存还可能假成功

**代码落点：** `experiences.py / db.py / get_revisions / restore_revision / manifest`。

**证据状态：** 已隔离复现。

**修改方法：** 把内容哈希与修订操作身份分开：revision_id 每次操作唯一，revision_hash 只代表内容。新增 experience_heads，明确 head_revision_id 与 active_revision_id；修改原 `(experience_id,revision_hash)` 唯一性假设，使回滚可以创建新操作。unchanged 与实际当前已登记正文比较。所有读取、父修订选择、回滚、审批及冻结包从指针取版本，不能只修保存函数。

**必须保留的语义：** 迁移应在离线事务中重建修订表、复制原 ID、建立必要索引，再切换引用。可确认的文件与历史匹配才能建 head；缺失的回滚时刻不可捏造。重复请求用 operation_id 去重，不能用内容哈希吞掉真实回滚操作。

**修复后验收：** v1→v2→回滚v1→保存v2 后正文/指针/manifest 一致；历史有独立回滚事件；同 operation_id 重试不重复；相同内容的新合法回滚操作可以有不同 revision_id。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L91-L124)；[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L315)，`_scan_dir / save_experience / restore_revision`。

### B03 · P1 · 外部编辑进入使用路径，却未进入版本历史

**代码落点：** `experiences._scan_dir / get_experience / 外部编辑与 pending 写入恢复`。

**证据状态：** 已隔离复现。

**修改方法：** 为外部编辑增加统一 reconcile：合法新字节先写 external 修订；全局只更新草稿，已批准版继续可用。非法草稿留在磁盘供用户修正，但运行时从已登记 active 版本取内容。扫描与保存共用写保护；待应用写入要核对真实字节和父版本后再推进 head。

**必须保留的语义：** 不要把未知文件自动配上“最新历史 hash”。先登记 applied=0，完成文件写入后切换指针；崩溃时只完成能够证明属于同一操作的写入，出现不同字节进入冲突。不要在每次查阅时触发 LLM 审核。

**修复后验收：** v1→外部修改→v3 可完整读回三种内容；非法编辑不会使旧批准版从运行时消失；文件和数据库之间任一点故障后不会读出正文 r2 搭配 hash r1。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L91-L189)；[docs/EXPERIENCE.md](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/docs/EXPERIENCE.md)，`_scan_dir / get_experience / save_experience`。

### B04 · P1 · 经验作用域与实际目录不一致，模型更新缺少题目归属检查

**代码落点：** `experiences.save_experience / controller._apply_experience_proposal`。

**证据状态：** 作用域问题已隔离复现；target_id 问题为静态检查。

**修改方法：** 普通更新固定 id/scope/challenge_id；题内 target_id 必须属于当前 Run 的题目。全局推广创建新的派生条目并保留 derived_from；全局提议不能通过 target_id 改写其他题内条目。目录归属与字段冲突直接报告，不只改 frontmatter。

**必须保留的语义：** 需要重定位历史条目时使用单独迁移操作，先决定归属再同步目录与数据库路径。不要在普通编辑 API 中隐式移动实体。

**修复后验收：** CH1 的模型不能更新 CH2；在 CH1 保存 scope=global 不会留下伪全局条目；显式推广创建新全局候选而保留原题证据。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L197-L270)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`save_experience / _apply_experience_proposal`。

### B05 · P2 · challenge_id 的路径校验接受点目录段

**代码落点：** `experiences._exp_dir / 所有接受 ID 或路径的读写入口`。

**证据状态：** 已隔离复现。

**修改方法：** 字符检查后另行拒绝 `.`、`..`。resolve 目标并确认位于预期作用域目录，读取与写入采用同一验证。拒绝跨边界符号链接/路径段；使用用户路径时不要把异常吞掉后当成不存在。

**必须保留的语义：** 只检查当前子目录包含关系，不新增不必要的通用路径权限系统。经验 ID 和 challenge_id 不互相替代。

**修复后验收：** 点目录段、绝对路径、分隔符和外部符号链接拒绝；普通含连字符/下划线的 ID 可用；失败不留下文件或修订。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L80-L88)，`_exp_dir`。

### B06 · P1 · 启用操作改写证据强度，模型更新还会丢元数据

**代码落点：** `experiences.approve_experience / controller._apply_experience_proposal / schema`。

**证据状态：** 审批改写已隔离复现；提议元数据问题为静态检查。

**修改方法：** 审批仅切换 active 版本，不改变 evidence_status。题内新提议允许 active+hypothesis；模型没有给证据等级时默认 hypothesis。更新从旧 frontmatter 拷贝再覆盖明确字段，保留 tags/expires_at/derived_from/来源。正文的结论发生实质变化而没有新验证时降回适当证据级别。

**必须保留的语义：** 元数据保留不等于允许模型设置系统维护的 revision_id/operator。证据状态变化必须携带可核查依据；用户启用 contradicted 时仍显示反驳标签。

**修复后验收：** 批准 contradicted/hypothesis 不变 observed；只改正文不丢扩展字段；新结论不能无依据继承 validated；题内自动启用政策不被改成全面人工审核。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L273-L295)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`approve_experience / _apply_experience_proposal`。

### B07 · P2 · 非法 frontmatter 类型可绕过受控错误边界

**代码落点：** `experiences.parse_experience / 扫描容错 / API 错误转换`。

**证据状态：** 已隔离复现。

**修改方法：** 先检查字典、字符串、列表及元素类型，再做 set 枚举成员判断。对必需字段、ID、合理长度与 scope 绑定做结构校验；未知合法元数据继续保留。把单文件格式错误转成 ExperienceError，目录扫描记录该文件错误后继续其他条目。

**必须保留的语义：** API 将可预期的格式错误映射为受控 4xx；I/O 权限问题与格式问题分开，不把整个库异常包装成空列表。

**修复后验收：** status=[]/title={}/tags="x"/evidence_refs=[{}] 均受控失败；合法条目仍可列出；没有 TypeError 泄漏或静默覆盖。

**原始定位：** [src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L50-L77)，`parse_experience`。

### B08 · P1 · “新建经验”与自动选择副作用冲突

**代码落点：** `ExperiencePage.tsx / startCreate / 自动选择 effect / loadDetail`。

**证据状态：** 静态确认；未进行浏览器复现。

**修改方法：** 进入 creating 时不运行自动选择首条和 selectedId=null 清空 effect；表单重置只由明确的新建/取消/切换操作驱动。loadDetail 加请求序号或 AbortController，响应只在对应选择仍有效时提交。列表刷新保留正在编辑的草稿。

**必须保留的语义：** 保留现有页面，不因本 bug 重建状态管理架构。异步保存后刷新也要核对目标 ID，避免把 A 的保存结果载入 B 表单。

**修复后验收：** 空库/非空库均可稳定新建；快速 A→B 只显示 B；慢请求期间新建不被覆盖；刷新和审批其他条目不吞未保存内容。

**原始定位：** [apps/web/src/pages/ExperiencePage.tsx](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/apps/web/src/pages/ExperiencePage.tsx)，`startCreate / selectedId effects / loadDetail`。

### B09 · P1 · 收尾才产生的经验也被算作本轮使用过

**代码落点：** `controller._experience_usage / _record_experience_snapshot / curation`。

**证据状态：** 已隔离复现。

**修改方法：** 将旧起止清单保留为 availability_only。新增 experience_uses 或等价的版本化采用投影；只有明确声明采用时关联具体冻结 revision 与时间/事件序号。结果连接采用后的行动与提交；Run 最高分只作为背景显示。所有旧“usage”不能自动迁移为 adopted。

**必须保留的语义：** 在现有事件表追加 presented/adopted/result_linked 事实；投影可重建。大脑或执行器的采用声明标 reported，因果贡献仍需要对照，不能由脚本自动分数分摊。

**修复后验收：** 只在 at_end 出现的经验不会被计为先前采用；采用 r1 后更新 r2，结果仍指向 r1；未采用但展示过的经验不产生收益记录。

**原始定位：** [src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_experience_usage / _record_experience_snapshot`。

### B10 · P1 · 检索、证据标签和实际注入没有统一契约

**代码落点：** `experience_context.py / observation._selected_experiences / controller._memory_manifest / task_text`。

**证据状态：** 选择与标签丢失已隔离复现；其余为静态检查。

**修改方法：** 统一候选获取与冻结渲染。从明确 active_revision 读取，保留 evidence_status/applicability/反例/过期信息，按当前任务选择并控制总字符预算。全局和题内都进入候选，避免固定全局前缀挤掉题内。在 Trial 或新指导边界保存实际交付正文与 hash，执行器只读取该冻结版本。

**必须保留的语义：** 自由文本适用性仍交给模型判断；机械逻辑只处理可确认的状态/归属/预算。候选不足可以返回空，不补无关经验。不能只把数字 6 改大，或另起向量库而不统一读取链。

**修复后验收：** 相关题内经验可以入选；hypothesis/contradicted 不丢标签；总预算受控；运行中编辑不改变已交付包；大脑和执行器视图能追到同一源 revision。

**原始定位：** [src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py#L115-L136)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[prompts/collaboration/executor.md](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/prompts/collaboration/executor.md)，`_selected_experiences / _memory_manifest / start_trial task text`。

### B11 · P1 · 只读取 400 条事件，却推进到更大的“已审阅”范围

**代码落点：** `observation.build_frame / controller._apply_review_result / covered_seq`。

**证据状态：** 已隔离复现。

**修改方法：** 选择一种语义并贯穿：分页处理到声明的 through_seq，或者把实际覆盖边界限制到本批真正读取的末条，再安排下一批。摘要可以丢掉低价值细节，但未读取事件不可算已覆盖。接受结果时只推进实际 processed_through_seq，区分展示省略与尚未读取。

**必须保留的语义：** 固定审阅上界，排除审阅创建之后的新事件；后续事件在下一批处理。checkpoint/score 投影也标真实来源时间/引用。不要只把 limit=400 改成更大常数。

**修复后验收：** 401/1000 条积压中尾部错误/评分可到达；暂停/重启不跨越未读事件；重复接受不会倒退或越界推进游标。

**原始定位：** [src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py#L139-L263)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`build_frame / _apply_review_result`。

### B12 · P1 · 正式评分没有直接进入大脑反馈帧

**代码落点：** `mailboxes.poll_scores / observation.build_frame / event_excerpt / 审阅唤醒`。

**证据状态：** 已隔离复现。

**修改方法：** 从已登记的 submissions 读取 score delta，携带 submission_id、trial_id、package_sha256、score_status 和最终性依据。把 submission.scored 纳入相关摘要/通知；已知字段从 unknown_fields 移除，pending 保持未知。运行中的相关变化走现有审阅队列合并。

**必须保留的语义：** Run 已终止或预算不足时只记待整理引用，不恢复 Run、不额外调用模型。评分量程/满分上界来自题目契约，不能自动假设100。平台后续更正分数时追加更正证据，不抹原记录。

**修复后验收：** 本地已有 final 分数时不再显示未知；相同轮询不会重复产生分数事件；迟到分数绑定原提交并且不复活取消 Run。

**原始定位：** [src/cyberscientist/observation.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/observation.py)；[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`poll_scores / event_excerpt / build_frame / shadow triggers`。

### B13 · P1 · 阻塞检查点重试返回 continue，违反当前门禁

**代码落点：** `collab.submit_checkpoint / checkpoints schema / outbox`。

**证据状态：** 已隔离复现。

**修改方法：** 保存检查点收据（含原 review_id 和投递指导 ID）。同 key 同内容重试返回同一身份，并结合当前门禁给出安全 next_action：仍阻塞/暂停就不得 continue。同 key 不同内容维持冲突。返回丢失的指导使用原 ID 对账，由 ACK 去重。

**必须保留的语义：** 不要简单把所有重试永远设为 yield：阻塞经有效裁决解除后，应反映当前状态。收据/检查点/审阅队列在同一事务建立，避免先返回再登记。

**修复后验收：** 首次响应丢失后重试不绕过 blocking；不新增审阅；已解除阻塞时不永久挂起；指导重复 ID 不引起重复执行。

**原始定位：** [src/cyberscientist/collab.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/collab.py)，`submit_checkpoint duplicate branch`。

### B14 · P1 · Run 模式与实际运行时选择分离，存在授权绕过路径

**代码落点：** `controller.create_run / _make_brain / _make_prime / start_async / recovery`。

**证据状态：** 静态确认；未启动真实模型。

**修改方法：** 定义每个 Run 唯一有效 mode 与固定运行时配置，工厂、启动和恢复都用它。真实模型调用必须检查真实运行时对应的 allow_model_calls 与有效授权，不能靠客户端 Demo 标签跳过。合法模式用枚举校验；运行时切换走明确变更与授权核对。

**必须保留的语义：** 不要因为读取了 config_snapshot 就冻结用户已支持的预算调整；运行时身份和可调整预算分开。无凭据时真实路径报缺项，不回退 Demo 冒充真实成功。

**修复后验收：** Demo Run+实时 connected 设置仍不会调用真实 runtime；反向切换不污染来源标签；恢复和配置变化后未授权调用仍被拒绝。

**原始定位：** [src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)，`create_run / start_async / _make_brain / _make_prime / _run_loop`。

### B15 · P1 · 时长用尽只改 paused 状态，没有停止执行器

**代码落点：** `controller._run_loop / control pause / runtime cancel confirmation`。

**证据状态：** 静态确认；未启动真实执行器。

**修改方法：** 队列等待上限取“下一个授权截止时间与原等待上限”的较小值，避免无事件时延迟发现。超时走同一暂停流程：关闭新增受控动作、置 pausing、请求取消，得到原生终态/状态证据后才 paused。大脑在途结果不得于已暂停边界发起新动作。

**必须保留的语义：** 区分本地代理停止与远程 Job 继续运行/计费。保留原时长计费语义，若从墙钟改为活跃时长需显式设计而非本 bug 顺手更改。

**修复后验收：** 无事件也按截止触发；取消只有 accepted 时仍显示 pausing/unknown；确认停止前不伪报；暂停后无新增受控模型/提交。

**原始定位：** [src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_run_loop time-limit branch`。

### B16 · P1 · 提交预算检查不原子，两次并发可穿透单次授权

**代码落点：** `mailboxes._check_budget / submit_experiment / submissions 操作幂等`。

**证据状态：** 已用真实线程与本地 SQLite 隔离复现。

**修改方法：** 同一短事务内：检查 operation_id 及请求指纹，校验 Run 授权，统计/预占 Run 和邮箱配额，写在途提交。unknown/在途保持预占。重复同 ID 同请求返回原记录；同 ID 异请求冲突。网络调用放在事务外，不持数据库锁等待平台。

**必须保留的语义：** 并发线程数增加之前先完成此修复；不能以邮箱计数替代 Run 限额。配额释放必须由“确认没有产生计费/占额副作用”的状态转移触发，释放本身幂等。

**修复后验收：** 授权1时并发2/多次最多一次平台副作用；重复 ID 不二次占额；不同载荷同 ID 拒绝；unknown 不释放。

**原始定位：** [src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)，`_check_budget / submit_experiment`。

### B17 · P1 · 回执丢失被当作确定失败，额度释放后可能重复提交

**代码落点：** `mailbox_platform.submit_package / mailboxes 提交状态 / 恢复对账`。

**证据状态：** 已进行隔离故障注入。

**修改方法：** 将提交分为创建草稿、上传包、正式提交三个持久阶段；拿到 attempt_id 立即落库，发送前冻结实际包字节/哈希。错误区分明确拒绝、已受理、结果未知。回执丢失时保留 unknown 与预占，围绕原 attempt 对账，不自动用新操作身份重提。

**必须保留的语义：** 创建草稿的响应丢失且没有 attempt_id 时，只有官方支持的幂等键/客户端引用查询才能自动恢复。接口不支持则保持 unknown 等待人工/平台对账；不得声称凭本地日志保证远端 exactly-once，也不得编造查询接口。

**修复后验收：** 创建/上传/正式提交各阶段注入丢回执；有 ID 时恢复原 attempt；无可定位 ID 时不自动新建；只有明确未受理可释放；包 hash 等于实际上传字节。

**原始定位：** [src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/mailbox_platform.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailbox_platform.py)，`submit_experiment / BohriumPlaygroundPlatform.submit_package`。

### B18 · P1 · 执行器启动失败处于主清理边界之外

**代码落点：** `controller._run_loop / 会话部分启动 / finally`。

**证据状态：** 静态确认。

**修改方法：** 一个最外层 try/finally 覆盖 brain.open、prime.start、pump/worker 创建与主循环；初始化资源引用为 None。部分失败写明确 failed/blocked 和原因，关闭已取得的会话，取消并等待已创建任务，撤销相应能力令牌并清理映射。

**必须保留的语义：** 清理逻辑需要幂等；主错误保留，清理错误另记，不能遮盖根因。不要在用户已终止后把 Run 再写回 running/failed 覆盖终态意图。

**修复后验收：** 分别在两个会话启动、pump 创建和首轮请求处故障注入；没有 running 僵尸或孤儿映射；清理重复调用安全；原始错误可追溯。

**原始定位：** [src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)，`_run_loop startup / finally`。

### B19 · P1 · 手动提交和批量注册在 async 路由内执行同步网络

**代码落点：** `api.py 手动提交/注册/收割路由 / 同步平台服务`。

**证据状态：** 静态确认；未进行实时延迟测量。

**修改方法：** 将完整同步网络服务通过 asyncio.to_thread 卸载，或采用真实异步适配器；保持数据库事务短小。先修 B16/B17 再提高并发；异步路由的用户取消不等于远端提交已取消，必须保留在途状态。

**必须保留的语义：** 网络卸载后要保护共享 secrets/settings 的读改写及批量部分成功记录，避免把原先串行路径改为新的覆盖竞态。不要在 worker 线程复用错误线程绑定连接；沿用现有 thread-local DB 接口。

**修复后验收：** fake 平台阻塞期间 health/control/SSE 仍响应；并发提交不越权；请求超时后在途仍可对账；批量处理已成功结果不因后项失败消失。

**原始定位：** [src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)；[src/cyberscientist/mailboxes.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailboxes.py)；[src/cyberscientist/mailbox_platform.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/mailbox_platform.py)，`submit_experiment / register_experiment / harvest_submit HTTP handlers`。

### B20 · P1 · 全局审批没有绑定用户实际看过的版本

**代码落点：** `ExperiencePage 审批 / API 请求 / experiences active pointer`。

**证据状态：** 静态确认。

**修改方法：** 批准和驳回必须携带用户看到的 revision_id（或过渡期 current_hash）；同一写事务核对期望版本后切换 active。旧审阅不能批准新内容，冲突返回可读的新旧版本。全局候选更新只更新 head，保留旧 active；显式退役单独清 active。

**必须保留的语义：** 审批不改变 evidence_status（与 B06 同时验收）。前端显示当前草稿与可用版并刷新冲突；不能用后端即时读当前 hash 代替客户端看到的 hash。

**修复后验收：** 看到 r1 后出现 r2，批准 r1 不激活 r2；编辑候选不撤销旧批准版；用户明确停用影响后续选择但不改旧冻结包。

**原始定位：** [apps/web/src/pages/ExperiencePage.tsx](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/apps/web/src/pages/ExperiencePage.tsx)；[src/cyberscientist/api.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/api.py)；[src/cyberscientist/experiences.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/experiences.py#L273-L295)，`approve UI / approve_exp / approve_experience`。

### B21 · P1 · 空闲指导通道缺少另一通道已有的 Trial 过期检查

**代码落点：** `controller._deliver_queued_guidance / collab.deliver_via_checkpoint_return`。

**证据状态：** 静态确认。

**修改方法：** 两个投递渠道共用资格检查：当前 Run/phase/gate、target_trial_id、适用的 shadow_epoch。认领 queued 时在同一事务复核，旧 Trial 记 superseded，失效代次记 invalidated。有效指导只认领一个渠道，发送失败按真实回执记 unknown/queued，不能盲目重发。

**必须保留的语义：** 检查目标 Trial 必须在取消息后、发送前，不只在创建指导时。业务状态与网络投递不可能天然跨系统原子；保留操作身份与回执对账。

**修复后验收：** 旧 Trial 指导在两个通道都不送新 Trial；暂停/切代后不投递失效内容；有效指导只走一个渠道；重复 ACK 不计作重复执行。

**原始定位：** [src/cyberscientist/controller.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/controller.py)；[src/cyberscientist/collab.py](https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/src/cyberscientist/collab.py)，`_deliver_queued_guidance / deliver_via_checkpoint_return`。

## 3. 交付检查

每个批次提交：源码 diff、迁移脚本及回滚边界、新增回归测试、实际执行命令/输出、已验证与未验证事项。任何迁移不得把旧可用清单变成采用记录，或补造缺失的外部编辑/回滚事件。

基线探针只用于证明旧行为。修复后的测试应断言期望行为，不能直接要求 `reproduced=true` 的旧探针仍通过。参考代码是证据副本，不导入生产替换当前模块。

包内离线导入测试只覆盖导入器；不能替代以上21项应用修复回归。持续学习代码接入与等预算实验见 `INTEGRATION.md` 和 `EXPERIENCE_PLAN.md`。
