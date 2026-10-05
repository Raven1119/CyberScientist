# 当前状态（2026-10-05）

进度：2026-10-05 21:48 北京时间 · CS-UP-10 · W2d/W2m 完成并推送 · commit 032ef5ce79db43564f0e62ee95c8f078e37afd5c

## 已实现

- CS-UP-10 W2e：已验证公共/私有Python起点登记到实际环境目录；首轮PI选择、简报和实际执行器恢复指令接通，冒烟失败可换起点；Run不保存新版本，关闭开关保留旧通路/数据。真实目录只读API、迁移保留71Job/41Run、134项相关测试、前端56项及构建通过，重型依赖仍未准备。

- CS-UP-10 W2d/W2m：新PI严格Codex/Astra/xhigh，历史配置及比赛队列只投影不改快照；正常PI收到LKM正文，双角色共享有来源/哈希的后端公开读取工具。四角色真实零科研工具探针均通过，PI/求解者各三项联网回执received；99项相关回归、前端54项及构建通过，未开科研Run或提交。

- CS-UP-10 W2c：D-49统一到实际PI/执行器共享提示和架构；执行器本地秒级计算留命令/输出/耗时/来源，PI只读审阅，重计算仍远端。项目numpy/scipy/sympy锁定并安装，冻结离线同步通过；实际秒级代码→事件→封存→admitted回归及其余99项通过。

- CS-UP-10 W2b：显式GPU Job和沙箱授权接通，PI接收带来源/时间的真实GPU目录；不完整目录保持unknown且不覆盖。两个T4小Job输出取回，第二次干净Finished，4090沙箱exec退出0并仅删除本轮新资源；97项回归通过。

- CS-UP-10 W2a：新比赛显式不限资源授权贯穿Job、沙箱、PI审阅、Trial与维护账本；旧Run默认有界，时间/提交/速率及GPU拒绝权限保留。前端整轮和逐题独立配置与不限用量显示接通。W2其余小项仍在施工。

- CS-UP-10 W1：已配置现代CLI时使用bohr2.7.8/v4 Job及镜像路线，区分平台/native ID域；唯一名称与原冻结清单/权限绑定，独立对账释放现代unknown并发。完整无错分页证明缺席后，在原授权中以新操作ID重交；父Job找回优先，所有可重交后台线程持续登记到真正结束并参与安全关机。非法结果盘和命令占位符预约前拒绝，连续失败事实经原执行器指导队列建议授权沙箱。历史unknown不追溯重交。

- CS-UP-10 W0：追加D-48–D-55，D-30明确被D-52部分取代；其他原决定保持原文。本卡只做针对性修复和卡内最小真实探针，不开科研Run或比赛提交，不执行CS-UP-11及彩排。

- CS-UP-09 W8 时限补修：独立15秒活动心跳不等远端维护；读取当前持久账本、按动态授权约束等待中的信号和审阅。暂停／超时／主循环取消先中断原生turn，再收尾消费者并确认关闭；失败保留原session／process句柄及unknown，全部原生角色确认关闭才清当前unknown。已关闭Codex按原线程ID恢复，停止未知不能恢复重叠调用；失效请求的迟到结果不能新增动作。

- CS-UP-09 W8 草稿修复：明确 bundle_blocked 且归属、题目、未提交状态经平台确认的草稿，可由新的显式提交意图续传修正包，复用原 Attempt 和额度；未知上传／提交不重发。原封存字节保留，新包单独封存；并发意图、迟到查分与重启按同一提交身份对账。实际 HTTP 线程参与安全关机，旧题新提交有独立七天轮询窗口。已观察的 ARM 格式错误在预检显示事实，仍由 PI 决定修复。

- CS-UP-09 W8 归档恢复修复：Codex PI／执行器只在原 ID 的明确归档错误后取消归档一次，再恢复相同会话；未知／其他失败不换会话。原运行快照、额度和失败证据保留。

- CS-UP-09 W8 修复：真实 PI 顶层 work_package 可无损归一到 research_brief，提示明确嵌套位置；冲突不覆盖，仍走原结构／状态／授权校验。首次拒绝与原五分钟停滞审阅恢复证据保留，不追溯声称第一份工作包已恢复。

- CS-UP-09 W7：确认评分后按阈值／同题实验结束且不低于刷新榜首自动收割；两角色共用总 Attempt 额度，旧 Run 不追溯触发。冻结目标／触发依据／同包哈希再次核对，未知或失败不重发，晚到回执可恢复；HTTP 重复取消及关机 drain 保持实际线程追踪。公开错误、暂停、最佳分、长期限流和时间余额产生持久弹窗，确认／指定 Run 跳转和三个收割参数已接前端。用户要求的题目存在性 GET／404 明确提示已实现。

- CS-UP-09 W6：PI-only研究工具调用独立只读审查会话，冻结本Trial源包／封存哈希、Run题面和契约、正式评分与轨迹诊断；问题清单返回PI且非门禁。PI照常提交的理由与实际提交哈希匹配情况入账；started审查重启unknown不重发，辅助会话参与安全关机。

- CS-UP-09 W5：项目独立 Codex DeepSeek 提供方、四角色选择、具名求解者条目／冻结交接、原生工具探针、累计 session token 及可配置来源价格已接通。密钥只读取环境／根目录 .env，统一持久化脱敏；提供方限流独立。

- CS-UP-09 W4：所有结束路径持久排整理／新上下文复盘，合计两次独立调用；终态与队列、调用与结果原子落库，已开始 unknown 不重发。Trial 自动补记真实账本引用；完整公开轨迹排除私有笔记和原始模型 JSON，复盘候选不覆盖 active 经验，报告三部分齐全。双重原生停止／关闭未知时保留 pausing 并记录维护。

- CS-UP-09 W3：同题追加 Run 复用题目 ID；每个 Run 拥有独立版本化 strategy 经验，PI 开局／普通审阅／生命周期里程碑可更新。正式评分提交后立即补最佳分；开局完整策略投递冻结上下文，实时读取最新修订，跨 Run 覆盖被拒，损坏卡片不阻断研究。

- CS-UP-09 W2：PI 首帧读取公开分布、完整同题策略卡和资源，保存科学简报并把弱求解者具体工作包送入实际 Trial／指导。PI 暂停和普通 stop 在尚有可用未试授权通道时改为换路提示；手动暂停保留。冒烟只按后端原生回执／命令／哈希登记，配方提议和持久镜像明确未验证。

- CS-UP-09 W1：普通比赛／目录批次使用同一运行能力；评测标签仅供报告，历史结束评分不再租资源。评分未知、缺证 achieved、分项退步、轨迹/依赖诊断改为可见事实；预测和经验观察条数不设任意三条门禁。限流/停滞提醒不停止重试，提交采用活动时钟。Prime 全局配置渲染删除；规则审计逐位置/逐句覆盖1702条。

- CS-UP-09 W0：两个回退标签已推送并核对，追加 D-42–D-47；数据库再次一致性备份，回退操作步骤已记录。CS-UP-10 不开工。

- CS-UP-08 W4：每个角色提供全部有效经验索引，按题面／Run目标／Trial目标进行中文片段与技术词排序，默认及工作区新 Run 注入预算 24,000 字符；原生只读经验工具可读最新修订并冻结采用上下文。五份环境／传输／路径／评分配方保持全局候选，证据与失败边界保留。

- CS-UP-08 W3：unknown Job 十分钟后不占并发，保留总数和金额预约并继续对账；Job 固定评分命令／系统下载 ZIP 或单 JSON／哈希与身份／退出码核验后登记 executor_verified。新增环境保存数量授权、只含公开软件的私有镜像构建／回执对账／自动环境事实；未知价格不冒充零，金额硬上限存在时拒绝无法估价的构建。六个 v3 缺陷分别修复：Python3.10 哈希、冻结模式和远端恢复、预检隔离、有效资源信息、Trial 延后与原生 turn 归属、本机拒绝的远端效应与 operation_id。

- CS-UP-08 W2：持久活动时钟、15 秒心跳与离线断档排除；原生 Codex 会话 ID 保存与 thread/resume；安全关机 HTTP/CLI/前端入口、暂停确认屏障、SQLite backup、一览远程任务；启动先远程对账，再恢复有意自动恢复的新 Run，手动暂停保持暂停。

- CS-UP-08 W1：比赛轮次公开导入、原生模型分诊、整轮与逐题模板、确认授权、持久优先级队列、追加 Run、总览面板已接通。提供方会话租约和 429 退避持久化；全局 Job/沙箱并发在写事务内检查。新默认 Run6/提供方10，原显式设置保留。

- CS-UP-08 W0：Lightchaser 第一目标与 D-28–D-41 已写入设计文档，D-07/D-23 保留原文并标注替代关系。

- CS-UP-07 W1 A–D：取消未验证环境的Run创建前置门；首帧与只读工具提供授权剩余时间、评分耗时声明/可匹配实测、环境身份/公开镜像观察、网络未知或已观察状态、CPU报价与费用估算。执行器prepare/受控exec/register路径按后端计划、ZIP哈希、原生命令/回执哈希、退出码、单JSON及同次环境身份登记executor_verified；缓存、F1对账和封存绑定保留来源。普通工具失败即时返回事实，最终评分及提交阻塞通过原持久反馈队列交回同一执行器，不按失败次数结束Run。

- CS-UP-07通用额度与审计：困难层新评测采用180分钟/20Job/4沙箱并发/600沙箱分钟/CPU≤16核/50元估算上限，共享原子金额预约；unknown占用原额度、不自动重发，但不封锁有余量的其他明确新操作。科学依赖预检、大输入提示仅为事实，环境安装由执行器决定。冻结后端commit及代码哈希入评测与每个Run，前端显示正式分来源与冻结版本，旧评测保留旧授权。迁移仅加列/表，事前SQLite备份在忽略目录。

- CS-UP-07 W0：按用户授权在UPGRADE_DESIGN的决策清单仅新增D-24～D-27，明确执行器自主、允许读取自有历史、评测期间冻结代码及执行器评分经系统核对登记。新任务卡禁止新建镜像/数据集/节点；W1真实验证额度为沙箱60分钟、Job0、真实Run0。

- CS-UP-06流程阻塞修复：最终包预检/评分、实验邮箱提交失败或未知，交由原执行器通过持久guidance队列接回同一Trial修复，失败次数不自动暂停。保留原授权/门禁、用户及大脑显式暂停；未知投递或提交不重发。评分前冻结完整封存包、科学包、评分器和哈希清单，失败不登记分数；前端显示系统修复反馈及投递状态。无新增迁移。

- CS-UP-06 W0逐Run审计完成，系统缺陷与科学决策分开，原生证据引用及严重程度见docs/EVAL_V1_RUN_AUDIT.md。原有用户文件保留。

- CS-UP-06 W1通用修复：最终完整包与分项候选哈希对账、明确确认事件、相同输入/评分器缓存、双路径产物契约、授权/objective事实、题目级模型冻结、原生回执脱敏、预约分页精确匹配、256 MiB输入提示和固定环境注册表；不加入评测科学方法或答案。

- CS-UP-06运行中修复：旧Job -1终态映射、完整科学包对象存储传输、原授权到期收尾、128 MiB有界轨迹证据、临时签名URL脱敏、各评分命令按当前Run/沙箱剩余时长收缩。结束Run的未知预约仅启动时对账，常规后台轮询非终态Run及已知ID的非终态Job；账本unknown保留。

- CS-UP-06 F1单调输入声明在受影响两次Run及两组评测均终态后配置，原科学score.py不变；不能追溯声称本轮已受新声明保护。

- CS-UP-06 F4前端及eval report分别显示沙箱查询费用、沙箱估算、Job条件估算及未定价项；旧Job spendTime暂按秒、单位未独立验证，cost币种/总账单不强行确认。报价投影保留原观察时间和来源哈希，不含账号余额。

- CS-UP-06模型更新：项目内Linux Codex0.159.3，原0.155.1保留；两个应用原生路径与五题选择gpt-6.1-sol/xhigh，默认及全局CLI配置/认证不变。

- CS-UP-05 W0–W2：设计约束已同步；目录收录 abc、FigQA-0177/0178、Paired-block Lean、Matchgate/SWAP，新增两道科学评分器。评测可用 `cyberscientist eval run --suite fast|hard --repeats 2` 启动，SQLite 持久队列按现有 Run 容量创建 connected Run，历史实现曾冻结经验、模型、监督和 skills 快照并限制能力；CS-UP-09 W1 已统一普通运行能力，保留原授权（批次提交为0）与报告快照。`eval report <eval_id>` 重建 Markdown/JSON；前端评测页显示进度、分数区间与状态。原始评测包和回执仍留本机忽略目录。
- CS-UP-05 W3：公开题目当前 GET 不可取回时，评测可导入仓库中按文件和题面哈希固定的历史公开题面快照；Run 与结果记录题面内容哈希和来源。此回退仅用于目录内预先固定的题目，不替代当前平台状态确认。

- CS-UP-04：W1 为 63 份历史原生轨迹生成固定 CLI、单条件补丁 CLI 和原生直读三种转换与哈希；W2 用公开 v6 原函数对照本机 63 份 v8 可见回执及 71 份旧组上限，逐代码保留不可观察与两种未列出解释。W3 在封存和平台选行后加入离线确定性诊断，只有 N06/N08/N09/N11/N14 的条件达标项形成真实补救建议；失败返回 unavailable，不改变既有准入。前端展示全量详情，提交事件与同 Trial 审阅帧只传达达标摘要；skill 加入对应证据补救动作。公开 MIT 源码与许可证按固定哈希 vendor；Playground CLI 只复制临时补丁，不改全局安装。见 `docs/TRACE_CONVERSION_VARIANTS_CS-UP-04.md`、`docs/TRACE_CHECKLIST_V6_V8_AGREEMENT.md` 和 `docs/DECISIONS.md` 的 CS-UP-04 节。
- 本轮相邻缺陷按严重程度修复：高，项目旧 H7 轨迹 43 组配对工具事件被 v6 误读成 0 调用/43 结果，投影补真实适配器来源字段，旧包只在临时诊断输入中补标签，解析配对数不符则 unavailable；高，执行器包预检工具原可收到只应进入前端详情的低一致性代码，现输出限定为达标建议及可归因上限；中，包路径变更时前端旧预检哈希与结果未清除，现清除并拒收迟到响应；中，审阅帧可能混入无充分历史一致性代码的上限或其他 Trial 的诊断，现按达标归因和 Trial 过滤。

- 第二轮故障检查：按严重程度修复提交页默认选错题目的 Run、研究页旧请求覆盖新选择、启动失败重试重复创建 Run、迟到默认预算覆盖授权输入，以及指导回执误报、跨页面丢失选题、终态 SSE 不关闭。提交页增加明确 Run 选择，切换清除旧包路径和额外许可；指导按 operation_id 确认进入审阅队列；Demo 服务退出有界。详见 `docs/DECISIONS.md` 的「第二轮界面与运行生命周期故障修复」。

- 修复 skills 勾选后点击“保存设置”未落盘，以及单独保存技能造成整页设置版本过期的问题：三个保存入口共用一份设置草稿和一次带版本检查的写入。保存期间禁用编辑；冲突保留草稿并提供明确的放弃重载入口；设置和技能目录加载失败可重试。技能目录遇到单个非 UTF-8 文件不再整页失败，生效说明区分新建 Run 的常驻技能、本题后续 Trial 绑定和独立大脑。

- Linux 日常入口 `./start.sh`：加入项目 Linux CLI 和用户本地 CLI 路径，先重新构建前端，再执行原生后端 `cyberscientist start`。后端同端口提供前端与 API；浏览器等待健康接口就绪后再打开，WSL 无 Linux 图形浏览器时尝试 Windows 默认浏览器。沿用现有连接模式和授权设置。

- 新增第四季公开科学评分规则核查报告 `docs/SEASON4_PUBLIC_SCORER_FEASIBILITY_2026-09-28.md`：逐题区分完整公开计分、科学量自检和隐藏输入依赖；未修改运行时、评分器或经验。

- CS-UP-03R 本地评分器切片：新增 FigQA-0177 的规范答案科学评分器、独立历史回放脚本和隔离的无模型分析上下文；兼容现有评分器 JSON 契约。Paired-block Lean 后续已完成 4 份历史证明和 8 种反例的真实验算，增加按依赖准备环境、分批回放及未尝试样本记录。详见 `docs/LOCAL_SCORER_REPLAY_2026-09-28.md` 与 `docs/PAIRED_BLOCK_SCORER_REPLAY_2026-09-28.md`。

- CS-UP-03R 新增 `checks/audit_public_trace_scorer.mjs` 与公开评分源码逆向报告：固定源码 SHA、使用原函数进行离线行为检验，可选检查当前 CLI 的纯文件转换；区分公开 v6 与历史 v8，不将前者替换为生产预测器。结论见 `docs/TRACE_SCORER_SOURCE_REVERSE_ENGINEERING_2026-09-28.md`。
- 新增官网评分契约与三道“早期非满分→最终满分”同题轨迹对照报告 `docs/OFFICIAL_SCORING_AND_FULL_SCORE_TRANSITIONS_2026-09-28.md`；原始官网响应和逐 Attempt 证据只留本机忽略目录，未改运行时评分器或经验。
- 新增 8 次历史总分 100 提交的脱敏逐案审计报告 `docs/FULL_SCORE_ATTEMPT_CASE_AUDIT_2026-09-28.md`；完整 Attempt ID、原始评分回执与逐文件哈希仅保存在本机忽略目录 `.package-checks/full-score-case-20260928/`。
- 增补 AgentMaster 历史评分诊断审计器 `checks/audit_agentmaster_grader_diagnostics.py`：只读核对未遮蔽的本地评分回执、提交命令、封存输出和原始轨迹路径，逐 Attempt 证据留在本机忽略目录；脱敏结论并入 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`。
- 历史评分规律审计：新增只读脚本 `checks/analyze_agentmaster_trace_scores.py` 和 `checks/audit_agentmaster_science_outputs.py`，在本机忽略目录中保存哈希核对后的结构特征、按题留出结果及科学输出清单；脱敏结论见 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`。未修改产品预测器、评分器或经验。
- CS-UP-03R AgentMaster 本地补证：新增 `checks/match_agentmaster_traces.py`，按精确 Attempt ID、提交状态、题目参数和 `--trace` 路径配对历史评分表与 AgentMaster 封存迭代；分别记录原始事件、CLI 上传副本和本地投影轨迹的哈希及结构计数。逐 Attempt 对照仅写入本机忽略目录，脱敏汇总见 `docs/AGENTMASTER_TRACE_SCORE_PAIRS_2026-09-28.md`。
- CS-UP-03R 全账号轨迹审计：新增只读离线分析器 `checks/analyze_owned_traces.py`，对本人账号列表、API 轨迹、直接代理视图和 bundle 的本机原始文件逐个核对 SHA-256，分开统计列表声称、实际取回、包内选中行与分数配对；不输出原始轨迹正文或凭据。完整结论见 `docs/OWNED_TRACE_ANALYSIS_2026-09-28.md`。
- CS-UP-03R 补充：只读历史评分审计新增预设 70 分界的分段展示分候选核查，输出误差及能区分公式的相邻轨迹分范围；生产预测器和评分契约未改。
- CS-UP-03R W3–W5：新增历史展示分双公式核查和轨迹证据充分性检查，均从 W2 的哈希核验数据表重建本机审计结果。`score_calibration.source` 以只加列迁移区分 `realtime` / `historical`，受控校准写入可指定来源，前端显示来源；两个项目 skill 与一条待审批全局经验候选记录本轮配对证据边界。真实历史数据缺同包本地评分，所以未创建新题目评分器或轨迹预测器权重，也未伪造校准行。
- CS-UP-03R W2：`checks/build_scorer_dataset.py` 从本机忽略目录内逐文件 SHA-256 核验的回执、题目快照与 bundle 重建 `dataset.jsonl`；按轮次窗口、状态和评分字段区分历史双分项、赛后通用评分及未确认评分。轨迹选行复用生产 `trace_selection`，科学产物仅摘要及哈希入表。匿名背景分数另建 `background.jsonl`，逐页校验总数、字节数、哈希和字段白名单；两张表均不提交。
- CS-UP-03R W1：新增 `checks/inventory_own_attempts.py`，只对已核验作者列表执行 GET；缺账号专属凭据时严格只保存公开分数和元数据，带直接凭据时逐条保存详情、评分、轨迹及可用 bundle；账户计数、内容缺项、本地 Submission 关联和每个原始文件 SHA-256 写入本机清单。测试使用 fake 响应核对作者隔离和内容门禁。
- CS-UP-03 abc 科学评分器：项目内 `challenges/local_a619cdef/scorer/` 按题面验算三元组、素因子、radical 与分档；超出确定性素性或数值精度范围时返回未验证错误，不伪造 0 分。项目源码优先于历史工作区评分器，生成的 `__pycache__`/字节码不参与文件哈希或版本。Codex 执行器白名单现包含产品已实现的沙箱、包预检、本地评分、叙述预检和数据工具；这些入口仍受后端 Run 能力令牌与授权门禁约束。
- CS-UP-03 沙箱评分链路修复：`cpu` 规格在创建前校验为 `2c4g` 形态；明确的 HTTP 400 `INVALID_ARGUMENTS` 记为失败，历史此类 unknown 只有在原 request ID 查询为 404 时才释放预留。MCP 桥对可能持续执行的沙箱/评分调用延长等待且不自动重放；网关在沙箱执行或文件传输未完成时拒绝删除，并在执行/传输登记时重新核对 active 状态。
- CS-UP-03 生命周期证据修复：v2 `finish(achieved)` 现在解析产品自身使用的 `event:run_id:seq` 与 `checkpoint:id` 引用，核对其确属当前 Run；保留既有裸 event ID 和 `run_id#seq`。跨 Run 引用仍拒绝。
- CS-UP-03 W3 创建表单兼容：行内轨迹的带时区长时间戳按同一时间点投影为 UTC `Z` 记法，超过平台 300 字符的 `title` 截短至 300 字符并把全文保存在 `body`；ARM 封存包不改。只有创建接口 HTTP 400 的脱敏回执明确包含 `nothing was stored` 时，才认定未产生远端 Attempt；既有同类 `unknown/create_sent` 记录可经受控、单次对账转为 `failed` 并释放预留，其他未知记录保留。
- CS-UP-03 W4 准备：已预登记轨迹评分器的单因素对照、噪声优先、三条留出提交和停止规则。轨迹变体可选择 `projection_only=true`，从已确认来源的真实事件重新投影；普通叙述变体与投影专用变体均固定来源封存轨迹的事件引用截止序号，避免后续事件混入对照。科学产物逐文件哈希校验、提交预算与邮箱门禁不变。尚未执行 W4 的真实对照或拟合。
- CS-UP-03 W3：新增已确认普通实验基线的原样重交入口，冻结包逐字节复用、记录 `replay_of`，沿用 Run 提交预算、邮箱额度、幂等与校准绑定；前端标出重交来源。明确声明无输入的 abc 题面不再因平台额外登记的公开资源被误判为代理证据；其他需数据题仍保留原门禁。平台适配器后续 HTTP 拒绝会保存截断、脱敏的响应原因，仍不自行判定无副作用；创建 Attempt 的行内轨迹现从 ARM `step_type` 映射到平台文档的 `type`，完整封存轨迹不变。
- CS-UP-03 W2：题目 `scorer/` 的 `scorer.json` 声明 Python 入口、镜像与契约版本，全部文件哈希导出评分器版本。当前 Run/Trial 镜像匹配的 Bohrium 沙箱网关执行科学评分，固定 JSON 结果入 `local_scores`；本地只提取封存轨迹结构特征，轨迹分暂用低置信度占位模型，展示分按已观察公式计算。最终实验提交封存 SHA 若因轨迹事件变化，会在非轨迹字节和评分相关 manifest 一致时派生本地记录。平台分数 confirmed 后按最终封存 SHA 自动写 `score_calibration`，预测文本可引用 `local_score:<id>`；修订为非 confirmed 时配对失效。题目页显示当前评分器版本、每次提交的本地预测与平台分数偏差。新增 `cyberscientist-local-scorer`（both）和 `cyberscientist-trace-writing`（executor）两个项目 skill。
- CS-UP-03 W1：Trial 可写 `trace_narrative.jsonl`；封存前逐行校验本 Run 事件引用、工具 ID、原文输出、退出码、时间、包内 artifact 哈希及费用，返回 `INVALID_TRACE_NARRATIVE` 的逐条原因。合法叙述与未覆盖的事件投影合并；大脑和执行器有只读 MCP 预检。已确认的实验提交可生成仅改轨迹的变体；来源包按哈希冻结，非轨迹成员逐文件比较，新提交记录来源、叙述哈希和科学产物一致性；前端提交列表显示变体来源和一致性。
- CS-UP-03 W0：活跃 Trial 的执行器原生 usage、reasoning、消息片段会维持“正在思考”的活性窗口，私有正文不写公开事件，高频片段限频记无正文标记；超过 `stall_seconds` 完全无原生事件时排队重建执行器会话，不自动重放提示词或远程任务。带时长的大脑 `wait` 按设置上限保护等待窗口，到期恢复检测；无时长按默认静默窗口处理。无活跃 Trial 的空闲 Run 继续接受原有检测。前端可编辑 `max_brain_wait_seconds`。
- CS-UP-02 W7：大脑专用 `platform_scores` MCP 工具通过无凭据公开 GET 分页聚合本题尝试总数、作者数、displayScore 分档、harbor/trace 分位数、前 10 成绩和本机已确认最佳分数；10 分钟缓存，分页不完整或请求失败返回 unknown。后端拒绝执行器令牌，原始作者和提交内容不进入工具输出。
- CS-UP-02 W6：新 Run 的 submit 指导和手动实验提交均要求预测并持久化到指导与提交；收割继承预测。已确认评分在下一审阅帧与预测配对，提供可得的 displayScore、harbor_score、trace_score 和相对前次确认成绩的变化；大脑可记录 confirmed/refuted/unclear 判定，评分修订时当前判定失效。前端手动提交表单要求填写预测，提交列表展示预测与判定，整理输入包含配对。旧 Run 不受预测准入限制。
- CS-UP-02 W5：经验受众 `brain/executor/both` 进入提议协议、版本化 Markdown、前端编辑和两种冻结投递；旧条目缺省 both。控制器依据受控回执事件生成全局环境事实，内容变化保留修订，七天未刷新则转待复核候选并停止注入；环境条目在代理协议、后端写入和前端编辑处均不可手工创建或修改。
- CS-UP-02 W4：Run 级沙箱授权增加同时数量、累计分钟及独立 GPU 开关；隔离 bohr 2.x 网关提供创建、按 request ID 对账、执行、文件读写、删除、只读查询，Run 专用 bohr 代理与 `research_sandbox` MCP 共用校验。创建前预留、跨 Run 禁止操作、当前 Trial/题目路径约束、脱敏截断回执及文件哈希入账；执行事件成对映射至 ARM 工具轨迹。Run 终止/结束与到期清理沙箱，启动时只删除本系统已登记且所属 Run 已终态的沙箱，未知归属只报告。前端显示沙箱、镜像、状态、到期和累计分钟，提供手动删除；两个项目技能默认给执行器。
- CS-UP-02 W3：评分轮询把 Attempt 回执的分项与评分回执分别脱敏、去重入账；科学分和轨迹分写入提交账本并进入收割候选与审阅帧，缺失时保持 unknown。旧 Job 与新 Wenyon/沙箱客户端的主机覆盖可分别配置，兼容旧平铺配置并保护旧客户端不被误导到新主机。
- CS-UP-02 W2：后台每 15 秒逐 Run 检查有效研究进展；无活跃 Job/沙箱执行/模型退避时，默认静默 300 秒触发带组件诊断的生命周期审阅，连续两次未恢复进展则记录 `run.needs_attention` 并暂停。大脑审阅有界超时后重建会话，执行器会话失联重建但不重放远端 Job。模型 429/明确限流/额度耗尽按角色落 SQLite 重试状态，遵循 Retry-After 或 60–900 秒指数退避；限流尝试不扣大脑判断额度、不计审阅失败或执行器中止。前端可设置三项时限并显示暂停原因。
- CS-UP-02 W1：每个 Run 独立的大脑/执行器会话、队列、事件和 Run 目录；活跃 Run 上限由 `run_defaults.max_active_runs` 控制，新安装默认 3，前端可编辑。题目的大脑/执行器运行时、模型 ID 和思考强度可在导入或题目详情中设置，创建 Run 时冻结；前端“本轮总览”按 Run 展示状态、门禁、Trial、最近得分及 Job/沙箱数量。模型可用性可经原生会话检查，不发起模型 turn。
- CS-UP-01 U1–U4：共享 ARM 轨迹选行、封存合并与准入报告；按邮箱和平台题目 ID 从提交预留计数；评分暂定/确认、异常/分项一致性与赛后复评停止点；任意已出分实验提交的收割选择与逐条警示确认。前端显示题目邮箱用量、评分可信度和收割候选。完整取舍见 `docs/DECISIONS.md` 的 CS-UP-01 节。
- CS-EV-01b 后续根因修复：旧 bohr 1.1.0 Job 子进程及连接检查默认指向仍提供旧 Job 路由的 `https://openapi.dp.tech`；Wenyon 新客户端保持 `https://open.bohrium.com`。配置仅作用于应用子进程，不改全局 CLI。受控下载现可从 bohr 1.1.0 的 `<job_id>/out.zip` 内有界读取 `results/facts.json` 并登记镜像事实，不解压不可信路径。
- CS-EV-01b：Job 下载与日志按操作保存最近一次回执，并保留曾成功下载的证据；后续取回失败仍追加失败事件，不覆盖已下载结果的账本汇总。研究帧、轨迹和前端沿用同一汇总语义，旧单字段回执在下一次受控取回时转成分操作记录。
- CS-EV-01a：非 ZIP 提交也执行同一代理证据门；放弃待处理 Trial 意图后在 running 阶段唤醒大脑；预算等待中保留用户显式审阅并在帧中标明门禁；日志锚点按协议快照的完整修剪行长度判定。Job 账本增加结果取回状态，受控下载/日志操作按实际文件及 SHA-256 留痕，研究帧、轨迹文本和前端远程任务列表显示该状态。
- CS-EV-01 已接入数据物化登记/独立授权/冻结输入校验、ARM 事件轨迹封存与提交准入、bundle 上传回执闸、Run 生命周期 v2、Job 依赖与镜像事实预检、交付状态保留及大脑审阅指标；前端展示数据、六项信号、预算等待、用户目标状态和交付标签。新增迁移只加表/列，旧 Run 保留 v1 语义。
- Wenyon 下载可单独选择项目隔离的 bohr 2.7.8 与 Wenyon 1.36.0 扩展，HOME/XDG 会话目录均隔离；现有 Job 客户端保留 bohr 1.1.0。未安装扩展的回执归类为 `WENYON_CLI_UNAVAILABLE`。已识别 v1 公开清单按原文字节哈希、声明文件哈希/大小和总字节数核对，匹配才标 `verified`。测试进程对沙箱 socketpair 唤醒限制做条件兼容，回环监听不可用时明确跳过对应 CLI 测试。

- Linux 工作台已接入 Kimi、Codex 和 Prime 的可选大脑/执行器路径，提供运行控制、技能、经验、提交和可审计的事件记录。
- Bohrium 计算由后端网关准入和对账；创建结果不明时保留占位，不盲目重试。
- 前端已连接真实后端，提供运行监督、设置、经验管理与操作界面。
- TBMA 运行后的准入、恢复、审阅和经验整理改动已纳入本次代码更新；含账户和实际任务标识的运行记录保留在本机忽略目录。
- CS-SB-01 新 Run 稀疏研究大脑已实现：开放研究回答、按需只读轨迹、研究级唤醒、自然边界全文投递与 ACK；前端显示回答、交付和读取。旧 Run 保留原协议。详见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。
- CS-SB-01 稀疏输入与唤醒修复：可选短研究摘要独立存储；新 Run 普通检查点不唤醒 shadow，Job/Trial 研究级重复状态按 ID 去重。详见 `docs/SPARSE_BRAIN_INPUT_WAKE_FIX_2026-09-24.md`。

## 已实际验证

- CS-UP-10 W1：27/27真实CPU Job拿到ID、Finished并取回证明（必需20极小＋5个24MiB，另有私有镜像和阶段计时各1）。tiny CLI耗时4.690–5.182秒，大输入26.475–29.817秒；实际对象上传与665字节计算调度分开。私有镜像v4构建、列表、Job、沙箱exit0/Python3.10.6均确认；本卡新建沙箱已清理。v2仍HTTP200/148888，使用已跑通v4替代。26历史异常逐项保留输入/首回执时长/原错误和网络未知，科学失败不算运输失败。详见docs/CS_UP_10_FIX_EVIDENCE.md；原始材料只在忽略目录。

- CS-UP-10 W1回归：原代码前后对照5项通过；分页、冻结损坏、竞态、取消/关机及现代下载域边界60项通过。两轴只读最终无剩余blocker。最终源码全量1057 passed／586.78秒，前端50项及构建通过，compileall／diff通过；实际脱敏回执离线重放27通过，数据库副本两次迁移保留71条原Job、完整性ok。

- CS-UP-10 W0：决定校验脚本通过，55个编号唯一；移除D-48–D-55并还原D-30后，整文件SHA-256与基线一致：`01d03ee5dd6df59297374953a9956499d06dc24f106214a582e81a65254b07d4`。两轴独立只读审查通过，`git diff --check`通过；没有科研Run、模型或远程资源调用。

- CS-UP-09 W8最终回归：`.venv/bin/pytest -q` 1023 passed／472.28秒，前端50项与构建通过；compileall／diff／15文件暂存区密钥和私有文件检查通过。末次时限／底层关闭相关76通过、唤醒回归55通过；原停止确认测试不改。失败全量1失败／1021通过保留，重复唤醒修复后重新完整验收；两轴最终无剩余blocker。

- CS-UP-09 W8最终真实核对：比赛模式原四Run均finished，三个FigQA最新正式本地分100／executor_verified、ABC10／executor_verified；FigQA提交0。第二个0177真实开局收到第一张策略卡并记录不同路线。ABC原草稿续传、实验confirmed6.43、自动同包收割且confirmed6.43，全链路实际完成，总Attempt2；阈值0已恢复100。Chromium验证真实持久弹窗。8个Job为5Finished／2Failed／1unknown，六只本卡沙箱已删除；最终safe_shutdown可关闭、错误0、原生租约0，独立后端已停。原unknown Job不因本地关闭而消失。详情及证据SHA见 docs/OVERNIGHT_REPORT_2026-10-05.md。

- W8真实时长偏差：ABC活动账本3644.191747秒，授权3600秒，超44.191747秒后authorization_expired；原记录不截平、不提高授权。修复相关风险的应用测试76通过，其中主循环与延迟中断／重复取消、迟到Decision／ReviewResult、手动暂停、底层关闭失败保留句柄均覆盖；三处原夹具补真实running状态而保留原断言。两轴只读复核均无剩余blocker；唯一真实延迟原因未知，修复未追加真实Run复测。

- CS-UP-09 W8 草稿修复阶段：全量 `.venv/bin/pytest -q` 990 passed／497.43秒；针对性206通过，审查补修后59通过；前端50测试和构建通过，compileall／diff／十文件暂存区密钥及私有文件检查通过。两轴复核无剩余实质缺陷。当时真实草稿续传与收割待恢复；后续已实际完成，见本节最新核对。

- W8 归档恢复阶段：真实零模型探针确认取消归档／恢复同 ID、模型与强度；原生适配器27项、关机／恢复10项通过。真实浏览器暂停弹窗／刷新保持／确认／跳转成功。三只Run重启错误留证，当次关闭原生与辅助会话、远端资源0。全量968 passed（445.44秒），compileall／diff通过；该阶段不含后续科研及提交验收，最新结果见本节首条。

- W8 格式修复阶段：先确认三条Run安全暂停、原生租约0、远程Job／沙箱0，再停止独立后端；相关46项通过，完整962 passed（468.28秒），compileall／diff通过。两轴无新增阻塞；六字段落盘／执行器接收同时覆盖根与嵌套写法。该阶段尚未全链路验收，后续结果见本节首条。

- CS-UP-09 W7：完整 pytest 961 passed（499.35秒），前端50项与构建通过，compileall／diff检查通过；81项收割／邮箱／比赛／关机／排行回归通过。初次完整套件2处旧provider断言失败后保留原场景修正；日志保留。两轴有界审查发现的并发／评分修订／重复取消／晚回执／同题结束／冻结榜单问题均修复并新增回归。存在性404仅验证fake协议，真实只读GET下架事实已核实。

- CS-UP-09 W6：155个审查／提交／自修／协作／评分／控制测试通过（123.17s），覆盖新上下文问题返回、PI带理由实际Demo提交、并发幂等、符号链接拒绝、重导入冻结题面、压缩包密钥、未知不重发、实际提交哈希变化。compileall与diff通过；无真实审查者模型调用。

- CS-UP-09 W5：相关后端188通过（65.96s），原生／密钥／配置最终24通过（14.01s）；前端48通过及构建成功，compileall／diff通过。真实 DeepSeek Codex0.159.3/high 完成一轮读取工具探针，completed／exit0／内容匹配，累计24564输入、12160缓存输入、123输出；之后零turn回读确认DeepSeek提供方。未创建科研Run或远端资源。

- CS-UP-09 W4：控制器及保留的协作场景74通过；维护／结束／重启／安全关机30通过；针对性维护17通过。完整 `.venv/bin/pytest -q`：924 passed，453.12s；前端45通过，构建／compileall／diff检查通过。单元测试使用协议 fake，维护调用不发现开发机真实模型。

- CS-UP-09 W3：完整 `.venv/bin/pytest -q`：914 passed，413.66s；前端 `npm --prefix apps/web test`：45 passed，构建／compileall／diff 检查通过。双普通 Run fake 实际首帧选择不同路线、普通 PI 里程碑更新后第二 Run 工具读到新修订、正式分登记立即刷新、版本采用、归属拒绝及嵌套脱敏均覆盖；没有真实模型、Job 或 Attempt。前两次针对性测试暴露自动卡影响旧等待条件和新 ZIP 夹具缺参，修正后原场景与全量均通过。

- CS-UP-09 W2：`.venv/bin/pytest -q tests/test_pi_planning.py tests/test_controller.py tests/test_collaboration.py tests/test_competition.py tests/test_codex_runtime.py tests/test_kimi_executor.py tests/test_mcp_bridge.py tests/test_sandboxes.py tests/test_environment_saves.py tests/test_decision.py`：155 passed，54.94s；覆盖首帧材料、六项工作包实际派发、两种 PI 停止入口、手动暂停、冻结资源、时长／金额、并发回执去重和密钥备注拒绝。均为应用夹具，没有模型或远端调用。compileall／diff 检查通过。首轮 Demo 恢复失败已保留并修复，后续同场景通过。

- CS-UP-09 W1：`.venv/bin/pytest -q` 全量899通过（413.66秒，日志留忽略目录）；规则/技能最终15通过，原生/评分最后46通过。前端 `npm test` 45通过，`npm run build` 成功；`compileall`、`git diff --check` 与46个暂存文件的密钥/体积/私有路径检查通过。Standards/Spec 两路有界审查的可操作项已修正。

- CS-UP-09 W0：远程 main/fallback-1 均为 ec5e24b，fallback-0 为 5940418；基线跟踪文件干净，原未跟踪资料保留。SQLite backup、哈希核对、SQLite integrity_check通过，47条编号唯一、原41条决策不变；首个校验脚本编号错误导致先提交的偏差已记录并补做验证。哈希清单仅在本机忽略目录。

- CS-UP-08 W4：`.venv/bin/pytest -q` 最终实测 894 passed（452.84 秒），修复核心专项64 passed、队列／报告44 passed、目标／额度事实5 passed；前端45 passed 与 `npm run build` 通过，compileall、diff check、暂存秘密与私有文件扫描通过。三题真实分诊完成，全部 finished；正式本地科学分 FigQA100/100、ABC20（system），提交0、原生租约0，五只本卡沙箱均确认 deleted。ABC两Job为Finished/Failed，后者暴露输入目录缺陷；修复只以应用夹具验过，未追加真实Job。真实回执自动生成环境事实已生效。同一真实 Run 暂停 45 秒，剩余时长差 0，恢复确认且原生会话 ID 保持。

- CS-UP-08 W3：相关后端 171 passed；有界复核 79 passed、原生／队列 86 passed、环境／工具 15 passed，最终环境／Job 类型检查 10 passed。前端 44 passed／构建通过，compileall 与 diff --check 通过；六个 v3 缺陷均有对应 fake 复现。Bohrium version/help、Dockerfile check 和私有镜像只读分页真实返回成功；HTTP 与业务状态分开，尚无真实构建／科学 Job 出分证明。

- CS-UP-08 W2：.venv/bin/pytest -q → 856 passed in 472.32s (0:07:52)；新增关机远程状态矩阵另有 7 passed，前端 44 passed／构建通过；compileall、diff --check 通过。活动时钟断档／暂停／SQLite 备份／恢复意图与原会话 ID／关机前停止排队均由 fake 回归覆盖，真实原生恢复仍待额度内验证。

- CS-UP-08 W1：.venv/bin/pytest -q → 851 passed；前端 43 passed，构建通过；compileall 与 git diff --check 通过。10 题合成轮次覆盖限额、429 退避、重建调度器续跑、追加 Run、优先级与暂停；迁移两次初始化幂等。有界审阅补齐经验整理会话的提供方额度及释放。指定三旧题已在独立状态目录真实导入为 draft，模型/计算/提交未启动，历史远程账本为空。

- CS-UP-08 W0：HEAD/main 与工作区已核对；fallback-0 指向 5940418 并已推送；SQLite backup API 一致性备份已留在 .package-checks/cs-up-08。设计验收脚本、compileall、git diff --check 通过；前端 42 passed，构建通过。完整后端基线为 843 passed。

- CS-UP-07 W2最终收尾（2026-10-03 19:13 UTC／北京时间10月4日03:13）：用户要求现在收尾，原生控制接口结束已由大脑暂停的run_cc0251a839，HTTP200/status confirmed，#1552终止、#1553会话abort确认；原截止未到，未记为预算耗尽。原fast组complete、hard组complete_with_failures，10项全部终态、6项正式科学分（abc两次20/system、FigQA四次100/system），两次Lean与两次Matchgate均unknown。最后Run墙钟10249.972秒、1个Finished Job、2个unknown预约、沙箱0；全部原始证据保留，未追加Run/评分或重发未知操作。

- CS-UP-07最终只读审计：10个Run和两层冻结身份均为df91723／运行源码SHA-256 6714fcc655a88083aec2460578fb91c6e01f866ba9dab33844e4b2efa902955d；20个原生角色gpt-6.1-sol/xhigh、Codex0.159.3，稳定公开记录及哈希核对通过。实际资源请求和预留未超原授权；平台提交0、经验修订0，没有新建镜像/数据集/节点、运行中后端修改或例外整层重跑。用户关机后只恢复原版本及队列，第二Lean原授权过期，不重置时钟。

- CS-UP-07最终数值再生成：实际执行 `.venv/bin/cyberscientist eval report eval_bc60841fc279` 与 `eval report eval_2d41d12345f0` 均退出0，完整导出JSON逐字段等于数据库报告（6+4行）。`docs/EVAL_V3_2026-10.md`记录10项正式结果/用量、v1/v2/v3条件差异、逐Run历史阅读、实际恢复、四项缺分和六个新应用缺陷；候选90、基线fidelity、ACK及准入标记不替代正式科学分。

- CS-UP-07交付检查：2026-10-03 19:31 UTC实际执行 `.venv/bin/python -m compileall -q src tests` 与 `git diff --check` 通过；三份文档逐行核对十项结果/用量，摘要7行、四类STATUS事实、六项缺陷保留，已配置密钥和已知私有平台ID匹配0。W1测试日志哈希与冻结源码仍相符，本轮只改文档，未追加重复测试或科学探针。19:32原后端PID7777健康和冻结身份通过；观察器最后快照19:13已确认两层终态并按设计退出，旧检查要求观察器存活的误报不是后端故障。

- CS-UP-07真实恢复：首Lean最终评分失败通过#1730/#1739及两次后续指导到达同一执行器，环境仍未准备完而到期；第二Lean编译T2/T3成功后用户关机中断正式评分。Matchgate首轮最终传输unknown未恢复而到期；第二轮#680/#700成功取回7166字节基线归档及独立回放，第六Trial投递竞态由#1192/#1195恢复，但两个unknown占满Job并发后大脑选择暂停，沙箱额度仍可用。反馈送达与最终修复成功分别记录，没有操作员科学指导或额度扩大。

- CS-UP-07 W1：Linux `.venv/bin/python -m compileall -q src/cyberscientist tests`、`git diff --check`通过。`npm --prefix apps/web test -- --run`为42 passed，`npm --prefix apps/web run build`通过。完整 `.venv/bin/pytest -q` 最终审阅版为841 passed、2 skipped，退出0；两项回环监听测试按现有沙箱限制显式跳过。W1真实Run/Job/沙箱均0，无真实模型turn、比赛Attempt或经验写入。只读 bohr 2.7.8 `image search lean` 和 `image search mathlib` 均ok=true/exit0/items=[]；仅表示该两次关键词搜索为空，不外推目录不存在或版本不兼容。完整回执仅在本机忽略目录，运行事实缓存只投影公开字段与源哈希，未改历史研究事件。

- CS-UP-07开工HEAD为f54d0c4，已跟踪工作区无未提交改动；原有未跟踪任务卡和经验资料保留。W0逐字节检查删除新增四行后与HEAD原设计一致，git diff --check通过；没有模型调用或新科研/算力/提交。

- CS-UP-06原计划两层各一轮、每题两次，10项均终态，8个实际Run；两次Lean创建前EnvironmentUnavailable。正式科学分5项：FigQA-0177/0178各两次100，abc第二次20；其他5项unknown。未补跑快速题或扩大W2额度；详见docs/EVAL_V2_2026-10.md。

- CS-UP-06原队列进程中断：10-02实测旧后端/监控进程不存在，用户确认手动关机，原Matchgate第二轮授权已过期；通过原生控制器收尾，封闭模型启动/恢复，原开始时间、授权、配置不变。最终测试后11:57 UTC将自有后端4789重载为37608，健康200、前端构建资源及评测费用API核对通过；原授权、科学评分器、模型事件、算力/提交/经验数量不变，常规Job对账队列0。这是观察时状态，不保证持续存活。

- CS-UP-06评测原始SQLite核对：平台提交记录/事件0，W2开始后经验修订0，经验写入拒绝事件21；自有W2活跃沙箱0。W1额外真实验证Run0、CPU Job0、科学沙箱0分钟。

- CS-UP-06独立原生审计27个rollout、11604条JSONL/44391466字节，证实存在自有历史资料复用，重复非盲态独立。不得把得分差归因单一模型或修复。

- CS-UP-06最终交付回归：.venv/bin/pytest -q实测803 passed、2 skipped（376.56秒，沙箱禁回环相关测试明确跳过）；执行器修复/最终包/协作定向94 passed。npm --prefix apps/web test -- --run实测41 passed，npm --prefix apps/web run build、compileall、git diff --check通过。原始测试日志留本机忽略目录。

- CS-UP-06 F3最新只读image list成功total0/has_more=false，回执SHA-256 05112965ee1925ab06edcada7fe51d4e56a26629dafe43a561d781f9327edc65；空目录不能证明异步未知创建已失败，无第二次资源创建。

- CS-UP-06 Job场景报价55/55：c2_m2_cpu/c2_m4_cpu 0.16、c4_m8_cpu 0.32元/小时，官方费用页提供单位；这是报价而非旧cost币种确认。原报价仅离线投影已有自有Run，无额外科学算力。

- CS-UP-05 W2：迁移前 SQLite 已备份到本机忽略目录 `.package-checks/cs-up-05/pre-eval-migration.sqlite`（22,241,280 B），原库连续两次 `db.init_db()` 后 `eval_runs`、`eval_results` 均存在且初始 0 行。fake 两题×两次验收覆盖容量、重启续跑、去重、报告与零提交/零经验修订；评测提交和经验写入拒绝会记事件。`.venv/bin/pytest -q`：622 passed、2 skipped；`PATH=/home/wmywb/.local/bin:$PATH npm --prefix apps/web test -- --run`：40 passed；同一 PATH 下 `npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests`、`git diff --check` 通过。W2 未启动真实模型、Job、沙箱或 Attempt。
- CS-UP-05 W3 真实基线：快速层 `eval_3630add80ac7` 6/6、困难层 `eval_34ef954c5c78` 4/4 Run 完成；6/10 次有本地科学分。abc 两次均 20，FigQA-0177/0178 各一次 100、一次因封存路径不在已验证评分范围而 unknown；Paired-block Lean 两次 unknown（评分环境传输失败或封存缺入口）；Matchgate 两次 0（按最终封存包评分），后者两次轨迹 C=100。两次 Matchgate 本地分 0 的差及样本方差均为 0；Lean 和 FigQA 的缺失重复不按 0 处理。全表、耗时、模型 token、Job、沙箱分钟、证据边界见 `docs/EVAL_BASELINE_2026-10.md`，可由 `eval report` 重建。
- CS-UP-05 W3 资源与隔离验收：10 个有平台 ID 的 CPU Job，另 2 个无 ID 的远端状态 unknown 预约；所有已创建评分沙箱均为 deleted/failed，无活跃残留。10 个 Run 的平台提交 0；评测开始后的经验修订 0，拒绝经验写入事件 64。Bohrium 实际金额无可靠账单接口，全部记 unknown。Matchgate 第二轮 Q1/Q2 单题 Job 曾独立重放至 F=0.8002394885/0.8031740248，但最终封存包仍含占位线路；实际评分 Q1/Q2 近零。这是跨 Trial 科学产物组合遗漏，不能用单题日志代替最终包。
- CS-UP-05 W3 修复与验证：FigQA 当前公开 GET 404 时只回退哈希固定的公开题面；修复稀疏审阅拒绝反馈、授权帧、恢复会话、Job 冻结/超时与预约状态、评分前路径、报告异步成本、Matchgate 评分 stdout 混流和本机 DNS 失败结算。两次 Matchgate 原评分均在 Bohrium 完成且 stdout 末行有结构化 JSON；经原封存包、评分器、公开资源、执行事件和沙箱生命周期核对，只读恢复本地分数，没有追加 Job/沙箱。`.venv/bin/cyberscientist eval report eval_3630add80ac7` 与 `eval_34ef954c5c78` 均重建本机 Markdown/JSON。最终 `.venv/bin/pytest -q`：640 passed、2 skipped；前端 `npm --prefix apps/web test -- --run`：40 passed，`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests`、`git diff --check` 通过。

- CS-UP-04：固定源码 SHA-256 `afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46`、CLI 原文件 SHA-256 `d231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03`、补丁副本 SHA-256 `52b85b55e038e383d0350b153b648c45269e5ff9a98edb5b5454d181f7d5c065` 均核对。63/63 三种转换成功；E008 原转换仅 1 条 error、修复转换保留 27 事件与 10 组配对。公开 v6 对可见 v8 代码的闭世界不一致为原 CLI 3/818、修复 CLI 10/819；主集和 71 份旧组未见 v6 上限被实际轨迹分超过，此项不证明 v8 与 v6 上限相同。E008 原转换触发 N04/cap20，修复版无 N04；E010 触发 N09，E011 不触发 N09。只读 H7 abc 已封存包 111 行、43 组工具配对，经临时适配器标签的本地诊断仍识别 43 组；原包未修改。
- CS-UP-04 回归：`.venv/bin/pytest -q` 为 576 passed、2 skipped（既有回环监听限制）；定向提交/封存回归 130 passed；`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` 为 39 passed；前端 TypeScript/Vite 构建、`.venv/bin/python -m compileall -q src checks tests`、`node --check` 和 `git diff --check` 通过。转换与对照的原始资料仅留本机忽略目录。本轮没有模型调用、新科研 Run、Job、沙箱、Attempt 或平台账号操作。

- 第二轮回归：`.venv/bin/pytest -q` → 568 passed、2 skipped（沙箱禁止回环监听）；这两项 `.venv/bin/pytest -q tests/test_cli_shutdown.py` 在允许本机监听的环境中另行通过（2 passed），覆盖正式 CLI 和隔离 Demo 服务在 SSE 客户端仍连接时退出。`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` → 38 passed；前端 TypeScript/Vite 构建、`.venv/bin/python -m compileall -q src tests checks/serve_ui_demo.py` 与 `git diff --check` 通过。
- WebBridge 验收第二轮修复：较早题目 B 被选中时，提交页使用 B 的 Run；手动切换清除包路径和额外许可，返回研究页保留 B。对已有 created Demo Run 从页面授权启动，两个合成 Run 总数保持 2，目标 Run 到 finished。SSE 返回完整 32 条事件（与 SQLite 一致）后 EOF，页面显示“事件流已归档”；隔离账本 compute_jobs、submissions、compute_sandboxes 均为 0。原始断言、失败回归及 Demo 数据保留于 `.package-checks/bug-audit-20260928-round2/`，不提交。

- 本次 skills 修复：`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` → 25 passed（含新增 7 个保存/加载回归）；`npm --prefix apps/web run build` 成功。`.venv/bin/pytest -q` → 563 passed、1 skipped（沙箱禁止回环监听）；随后获准本机监听执行 `.venv/bin/pytest -q tests/test_cli_shutdown.py` → 1 passed。`.venv/bin/python -m compileall -q src tests` 与 `git diff --check` 通过。
- WebBridge 在隔离 Demo 工作区真实复现修复前“勾选→保存设置提示成功→后端列表仍空”，修复后主保存、卡片保存、连续保存、整页刷新回读均通过；同时保留其他设置修改。前端导入 Demo 题目、绑定另一技能、以模型/Job/提交/沙箱/下载均未授权的设置启动原生 Demo；Run 正常结束，`trial.skills_enabled` 包含常驻与本题技能，独立大脑记录 `skills_injected=false`，compute_jobs 为 0。原始界面/请求断言及 Demo 数据保留于忽略目录 `.package-checks/ui-bug-audit-20260928/`。

- 一键启动真实验收：`BROWSER=/bin/true ./start.sh` 构建前端通过；从本机只读 GET `/api/v1/health`、`/`、前端 JS 资源均返回 HTTP 200，健康回执仍为已有 `connected` 模式；测试后以 Ctrl+C 正常停止。`bash -n start.sh`、新增就绪时序测试与 `compileall` 通过。
- 本轮回归：`.venv/bin/pytest -q` 为 562 passed、1 skipped（既有回环限制）；`npm --prefix apps/web test -- --run` 为 18 passed；一键入口实际执行的 `npm --prefix apps/web run build` 通过，`git diff --check` 通过。

- 第四季公开资料核查：匿名 GET 官方赛季/轮次和 16 道不同题目正文均成功；赛季清单为 60 道、6 轮各 10 道。原始响应及 SHA-256 留 `.package-checks/s4-scorer-public-review/`；本轮仅文档和文件核对，无认证下载、模型、科学计算、Job、沙箱或 Attempt。
- 本轮文档验证：本机 Python 标准库核对赛季 ID、轮次计数、16 题报告覆盖及来源 SHA-256 通过；确认当前评分元数据为 15 条通用 ARM、1 条 LLM（DPA4C）。`git diff --check` 通过；没有应用代码改动，未重跑 pytest、前端测试或构建。

- Lean 复验后最终回归：`.venv/bin/pytest -q` 为 561 passed、1 skipped（现有回环限制）；`npm --prefix apps/web test -- --run` 为 18 passed；`npm --prefix apps/web run build`、所改文件 `compileall` 和 `git diff --check` 通过。

- Paired-block Lean 后续复验：固定 Lean 4.32.2、Mathlib 与 8 个配套依赖，在 Bohrium 实际回放 E002/E005/E009/E013，4/4 与平台科学分一致，MAE=0、最大误差=0；8 种合成反例实际分数分别为 90/96/90/0/70/70/70/0，全部符合公开规则预期，未向平台提交反例。完整编译、公理依赖与评分记录已取回。
- 本轮新增两个 CPU 沙箱，均已通过原生删除对账确认回收，分析 Run 为 finished；累计四个沙箱从创建到回收确认的保守时间上界约 157.063 分钟，未超过原 180 分钟授权，始终并发 1，无模型、Job、Attempt。该上界不是平台账单。

- FigQA-0177：通过原生 Bohrium 沙箱网关实际回放 11 份已核对包绑定的历史答案，11/11 与平台科学分一致，MAE=0、最大绝对误差=0；另 1 份生成/接收包不一致记录排除。网关执行退出 0，评分结果已取回；后续只读列表已无该沙箱且 describe 返回 404，原生删除对账完成，两个分析上下文的沙箱账本均为 deleted、Run 均为 finished。完整回执与科学文件留 `.package-checks/figqa-replay-20260928/`。
- 本地评分器本轮执行 `.venv/bin/pytest -q`：`557 passed, 1 skipped`（现有回环限制跳过）；最终限定复查两组新测试：39 passed；`npm --prefix apps/web test -- --run`：18 passed；`npm --prefix apps/web run build`、所改文件 `compileall` 和 `git diff --check` 通过。Node 使用已安装 Linux Node 22，仅修改当次进程 PATH。
- Lean 首次尝试的历史记录：准备真实验证到固定版本 `Lean 4.32.2`、锁定源码传输、缓存程序编译与约 43% 缓存下载观察；没有完成候选证明评分。原沙箱到期后已确认 404 且列表无该资源。首次分析占用时长的保守上界 127.551 分钟，随后 FigQA 上下文限 15 分钟，合计仍在用户原 180 分钟授权内；并发始终为 1，无模型、Job、Attempt。

- 本轮取得公开 `trace-score-cli@81c434907e7b0a2feccc79236f6601f7abbc1d84`（v6），18 项离线断言通过，核实 0.55/0.25/0.20 合成、上限、70 分界、抽样和解析；未调用评分模型。三份本人 FigQA 轨迹先按接收回执 SHA 配对，再作 6 次 native/转换文件检查：当前固定 CLI 将 E008 的 43 事件丢成 1 条 error，最小合成对照同样复现；E010 的转换文件触发公开 N09/cap 49，E011 检查表无负项。公开 npm 元数据 GET 返回 404，未取得 v8 包。
- 本轮 `.venv/bin/pytest -q`：518 passed、1 skipped（沙箱禁用回环监听）；`npm --prefix apps/web test -- --run`：18 passed；`npm --prefix apps/web run build` 通过；`.venv/bin/python -m compileall -q src checks`、`node --check checks/audit_public_trace_scorer.mjs`、`git diff --check` 通过。Node 为 Linux 22.17.0，当前 shell 通过 `.local/bin` 使用；没有修改全局配置。
- 2026-09-28 官网契约审计阶段：无凭据只读 GET `/api/docs`、`/api/docs/getting-started`、`/api/docs/arm-bundles`、`/api/docs/reading-a-trace`、`/api/protocol` 和 Lean 题详情均返回 HTTP 200；协议 21194 字节、SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`。只读复核 AgentMaster 封存的 Lean、FigQA-0177、FigQA-0178 早期与最终提交，核对科学分、轨迹分、判定、答案/证明及输出目录；未创建 Run、模型调用、Job 或 Attempt。该阶段仅修改文档，`git diff --check` 通过，当时未运行代码测试；后续源码审计阶段的全套验证见上一条。
- 本轮对 8 次历史满分提交核对平台接收包哈希、题目标识、命令轨迹与平台原生轨迹哈希，8/8 一致；7 次有封存输出、1 次仅能读取原输出目录。无凭据官方只读 `GET /api/attempts/{id}/score` 返回 6 次 HTTP 200 且 `score=100`/`scoreIsFinal=true`，两道 FigQA 返回 HTTP 404；另一个非满分对照返回 HTTP 200、`score=0`。本轮未调用模型或创建 Job/Attempt，逐案结论见 `docs/FULL_SCORE_ATTEMPT_CASE_AUDIT_2026-09-28.md`。
- 本轮离线复核 63 份历史双分项回执及 AgentMaster 封存输出：剔除错包后，FigQA-0177 的 10 份 B 答案科学分均为 100、1 份 C 答案为 0；separable-covariance 的 5 份结构有效答案均给出 `1/35`，科学分仍有 62/70/78 三档。三组跨题同 SHA-256 原生轨迹的分数各不相同，且每组较晚的 Attempt 都有 `N01` 诊断。只做历史文件读取，未调用模型、平台、Job 或 Attempt；推断边界见 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`。
- 本轮用 `python` 对 AgentMaster 148 份已有 `submission/stdout.log` 做只读包哈希与题目标识交叉核对：145 份生成/接收哈希及目标一致，3 份同时发生哈希与清单题目错配；三条可读科学分均为 0。两份错配的接收哈希逐字节等于另一道题同期 Attempt 的生成哈希。完整依据及限制见 `docs/HISTORICAL_SCORER_PATTERN_AUDIT_2026-09-28.md`；本轮未访问平台或创建 Run/Job/Attempt。
- 本机另有与先前 71 条不重叠的 63 份已评分 AgentMaster 回执，直接含 `trace_decision`、`trace_factor`、原因代码和引擎版本；其中 1 份在单独 `harvest/` 目录。旧组 71/71 上传副本与回执原生轨迹哈希一致；新组 57 份命令所指文件直接匹配，3 份从同迭代副本、3 份从其他迭代副本按哈希找回，故两组共 134 份原生轨迹字节可核对，文件来源差异单列。回执哈希确认 3 组跨题复用，和 3 条 `N01` 诊断相符。新组 62 份 `--outputs` 与封存快照逐文件一致，`harvest/` 那份无输出快照；63/63 的历史因子为 `accept→1`、`review→trace_score/100`、`block→0`，展示分乘法最大误差约 `1×10⁻⁷`。封存组 48 个同题输出树组中 1 组同字节答案出现 0 与 100 两种科学分，原因未知。本次 `.venv/bin/python -m pytest -q` 为 `518 passed, 1 skipped`，前端 `18 passed` 且构建通过，定向 fake 测试为 `6 passed`，所改 Python 文件 `compileall` 与 `git diff --check` 通过。
- 本轮只读审计对 71 条 AgentMaster 提交逐文件核对 `--outputs` 与封存科学输出，71/71 一致；58 条具有最终双分项。轨迹事件数与失败命令数的单特征阈值在整题留出时，≥70 和 ≥80 的普通准确率均未超过训练折多数类。`.venv/bin/python -m pytest -q` 为 `512 passed, 1 skipped`；脚本定向测试 `5 passed`，前端 `npm --prefix apps/web test -- --run` 为 `18 passed`，前端构建和所改 Python 文件 `compileall` 通过。当前 shell 初次未找到 `npm`，随后仅为本次命令把已安装 Linux Node 22 的 bin 加入 PATH 后成功；没有改全局配置。
- CS-UP-03R 配对代码验证：`.venv/bin/pytest -q` 为 507 passed、1 skipped；`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` 为 18 passed，`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src checks tests`、`git diff --check` 通过。配对表 `pairs.jsonl` SHA-256 为 `71fa7fad213fc4855b039d3dee5436d70b5f5f1a7268fa0fce73234a9fe5ba9a`，汇总 `summary.json` 为 `463474755db98db2abecbc8f61069295c92aabbeab6a9dac88dc867d7680670d`；二者仅本机忽略保存。
- CS-UP-03R 经验校正：本机 SQLite 在线备份 22,241,280 字节到 `.package-checks/agentmaster-pairs-20260928/pre-experience.db` 后，通过系统原生 `experiences.save_experience` 修订既有全局候选 `exp_cs_up03r_pair_before_fit_20260927`，加入本地 71 条配对及 58 条最终分证据；回读仍为 `candidate`，未激活。
- CS-UP-03R AgentMaster 配对（2026-09-28）：只读扫描 `../AgentMaster/store/T0` 的 148 个有 Attempt ID 的本地提交记录，与先前 75 条旧轨迹分记录精确相交 71 条；71 条均为 `submitted`、题目参数一致、`--trace` 指向本迭代 `raw.upload.jsonl`，且原始事件、上传副本、本地投影轨迹三个文件齐全。58 条轨迹分最终确认，13 条 `score_is_final=false`；本地 grader 65 条同分、2 条异分、4 条无本地轨迹分。65 个上传副本与原始事件字节相同，6 个经过滤。`.venv/bin/python checks/match_agentmaster_traces.py --dataset .package-checks/scorer-re-20260927T132218Z/dataset.jsonl --agentmaster ../AgentMaster --output-dir .package-checks/agentmaster-pairs-20260928` 重建本机配对；合成测试 `3 passed`。此前“全机 0 条旧分项轨迹配对”的推论已撤销；平台 API 可见性观察仍成立。
- CS-UP-03R 全账号扩查（2026-09-28）：当前操作者 `/auth/me` 与 `/agent/register` 核验 15 个关联代理，数据库为 1 个实验、0 个收割邮箱；已确认作者列表共 89 条可见提交。89 次 `/trace` GET 均有 HTTP 成功响应，17 条列表声称有轨迹，实际用现有身份取回 8 条、165 步；9 条声称有却返回空数组，逐条 `/export-arm` 均 HTTP 403，详情无其他内容字段。直接实验邮箱取回 3 条轨迹共 147 步与 3 个 bundle，另一代理可下载 2 个 bundle；合计 5 包、4 个不同 SHA。`PYTHONPATH=src .venv/bin/python checks/analyze_owned_traces.py --root .package-checks/trace-all-20260928` 输出 75 条旧轨迹分、0 条有轨迹内容配对。新分析器合成测试 4 passed；全套 `.venv/bin/pytest -q` 为 504 passed、1 skipped，前端 `npm --prefix apps/web test -- --run` 为 18 passed，前端构建、`compileall`、`git diff --check` 通过。原始文件、失败回执及 SHA-256 清单仅在忽略目录，未建 Run、模型、Job、沙箱、Attempt 或平台写请求。
- CS-UP-03R 本人轨迹复查（2026-09-28）：只读获取当前 `GET /api/docs/dev/AGENT_API.md` 46,268 字节，官方列出 `GET /attempts/{id}/trace`。既有实验邮箱 3 条提交的轨迹曾取回 10、6、131 步；本轮以其直接凭据再取其中一条，HTTP 200、10 步。对操作者已确认关联的 3 个历史代理，当前操作者凭据逐条只读查 72 条详情，72 次 HTTP 200、`traceCount>0` 为 0、内容非空为 0、bundle/raw messages 可用为 0。每个代理各抽 1 条：匿名与操作者 `/trace` 均 HTTP 200、0 步；操作者 `/bundle` 和 `/export-arm` 均 HTTP 403。审计汇总 SHA-256 为 `9b9a24799ce83c42cb1528240ec3b0ab542aed5880c3a94b217e2660a4ad2be2`，原始回执只在本机忽略目录 `.package-checks/trace-self-20260928/`。仅发生官方文档与已确认本人提交的 GET，无模型、Job、Run、Attempt 或平台写请求。
- CS-UP-03R 分数层补充核查：`PYTHONPATH=src .venv/bin/python checks/analyze_historical_scores.py --root .package-checks/scorer-re-20260927T132218Z` 对本人 58 条完整实时记录试算 70 分界下的替代分段计算，0 条误差大于 0.001，最大绝对误差约 0.000048；可区分的低分样本最高为 69，高分样本最低为 75.925。70 分界来自主办方告知，样本不能独立验证它；替代计算不能解释 10 条记录为何违反告知的 30–70 规则。`.venv/bin/pytest -q` 为 500 passed、1 skipped；`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` 为 18 passed，`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src checks tests` 和 `git diff --check` 通过。没有新 Run、模型、Job、沙箱、Attempt 或平台写请求。
- CS-UP-03R 补充核查：同一批 71 条实时双分项回执的 `harbor_reward` 与 `harbor_score` 全部满足 `harbor_score=100×harbor_reward`，最大绝对误差 0；71 条的回执字段 `harbor_replay_executed` 均为 1。`checks/analyze_historical_scores.py` 已将此关系逐条核验并保留本机审计结果，合成反例测试确认不匹配会被计数。它只证明奖励值到百分制分数的换算，不证明从缺失的科学产物计算奖励值的规则。本次 `.venv/bin/pytest -q` 为 499 passed、1 skipped；前端 18 passed、构建成功，`compileall` 和 `git diff --check` 通过。
- CS-UP-03R W3–W5：71 条实时双分项中 58 条有完整展示分；按误差 ≤0.001，30 条仅符合任务卡公式、18 条同时符合两种公式、10 条仅符合 `harbor × trace/100`，其余 13 条缺展示分。当时仅查平台和 CyberScientist 时，实时组可配对原始科学包和轨迹均为 0，故当轮科学评分器及 ≥70/≥80 轨迹预测的验证误差不可计算；同包重复噪声 unknown。匿名背景 3406 条有轨迹分，2004 条低于 70。迁移前 SQLite 在线备份 22,241,280 字节于本机忽略目录，`db.init_db()` 重复两次后来源列仅 1 个、校准行仍 0。原生经验接口写入的全局候选回读为 `candidate`，未审批激活。最终 `.venv/bin/pytest -q` 为 498 passed、1 skipped；前端 18 passed、构建成功，`.venv/bin/python -m compileall -q src checks tests` 与 `git diff --check` 通过。本轮无新科研 Run、模型、Job、沙箱、Attempt 或平台写请求。
- CS-UP-03R W2：`PYTHONPATH=src .venv/bin/python checks/build_scorer_dataset.py --root .package-checks/scorer-re-20260927T132218Z` 从哈希核验的本机原始资料生成 75 条本人记录和 3809 条独立匿名背景记录，模式计数为实时双分项 71、轮次外历史分项 1、晚交通用 2、待复核 1；实时组分布于 7 题且可取回 bundle 为 0。本人表 SHA-256 为 `f4186803bb61838af62e67adb8021c112451a24c0f37c5f2ee441392f6e531fe`，背景表 SHA-256 为 `3d329d73a5fa8b8d602bd6badd2001240d26c5c922da64604543e52bff6b4260`。fake 数据集重建测试 4 passed；全套 `.venv/bin/pytest -q` 为 493 passed、1 skipped，前端 18 passed 且构建成功，`.venv/bin/python -m compileall -q src checks tests` 和 `git diff --check` 通过。仅发生匿名与本人授权的只读 GET，没有新 Run、模型、Job、沙箱、Attempt 或平台写请求。
- CS-UP-03R W1：官方 Agent API 文档只读核对了 Attempt/score/trace/bundle GET；本机 4 个指定范围账号由 `/auth/me` 或操作者已确认的关联清单核验。作者过滤列表共 75 条：有直接凭据的 1 个账号 3 条、3 个无直接凭据的历史账号 72 条；后者内容为 unavailable。已发现的 10 道题公开分页总数逐页核对，0 页错误、0 已知题目内作者计数差异。直接凭据账号的 3 个 bundle 均取回，详情/评分/轨迹无失败；历史账号的 72 条公开详情元数据和评分回执也全部 GET 成功。忽略目录 `.package-checks/scorer-re-20260927T132218Z/` 的 `inventory.json` 记录 173 个原始文件 SHA-256，回算全部一致，清单自身 SHA-256 为 `b2a35bc035aacf40c1bc72f90bdcc131983417e0e82b80d4036fc3b80988fc2e`。本包 0 新 Run/Job/沙箱/Attempt、0 模型调用、0 平台写请求。
- CS-UP-03R W1 回归：`.venv/bin/pytest -q` 为 489 passed、1 skipped；`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web test -- --run` 为 18 passed，`PATH="$HOME/.local/bin:$PATH" npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src/cyberscientist checks/inventory_own_attempts.py tests/test_inventory_own_attempts.py` 和 `git diff --check` 通过。首次无 PATH 前缀的 npm 命令因 shell 找不到 npm 退出 127，随后仅在命令内补 Linux 路径并通过，没有改全局配置。
- CS-UP-03 进一步排查：本机 H7 两份回执的嵌套字段也无旧 `harbor_score`/`trace_score`；无凭据 GET 的三个当前开放题目分别采用人工评审或题目专用 LLM 评分（可回退通用 ARM），`open` 不保证旧契约。经 `experiences.save_experience` 原生写入全局经验候选 `exp_cs_up03_scoring_contract_20260927`，回读状态 `candidate`，审批前不注入；写入前 SQLite 备份仅在忽略目录 `.package-checks/cs-up-03-experience-backup-20260927/`。本次未建 Run、Job、沙箱、数据下载或 Attempt。
- CS-UP-03 评分契约再核对（2026-09-27 12:11 UTC）：无凭据 GET `/api/protocol`、主选 abc 与备选 MCM 题目详情及公开尝试首页均为 HTTP 200；两题仍为 `arm_v1_1_generic`、`grader_name=null`、轮次 2026-08-29 12:30 UTC 截止。两题可见晚交 scorecard 仍只有通用五项。公开 GET 既有 H7 Attempt `46889` 及其 `/score` 均无 `harbor_score`/`trace_score`，前者状态仍 `late_scored`。仅保存字段名与状态的脱敏摘要于忽略目录 `.package-checks/cs-up-03-contract-refresh-20260927T121144Z/summary.json`，SHA-256 `b427b1826f28f108094bda1c7f547335f7bb29c7b9111c6728ca159bf275e88a`；未创建 Run、Job、沙箱、数据下载或 Attempt。
- CS-UP-03 真实本地评分验收：`run_ed3e28c12a` 以 Codex `gpt-6-sol/xhigh` 大脑及执行器、0 Job/0 Attempt/0 数据下载授权，在当前 Trial `trial_a68a42964f` 通过产品预检和 `research_sandbox` 创建 1 个 `2c4g` CPU 沙箱，在声明镜像中经 `research_local_score` 得到 `local_scores.id=ls_cc04d41aabb1`、科学分 20、`radical=15042`、评分器版本 `83c33775ee2e8b33c8241e117492e6aa03d31e583268986e22fae25523f3a071`；封存包 SHA-256 `a9def16e7de7f3a6cdab088a775dad7eacedeeea78b295b7e5ac0a3bf75f2703`。沙箱先收到删除请求，后经只读列表确认为 `deleted`，账本时间 11:22:32–11:24:27 UTC；实际计费金额未知。Run 最终 `finished/achieved`，系统原生 curation 审阅为 `done`，题内经验 `exp_6bdc973e0c` 已更新并经产品 API 修正标题。脱敏回执与包仅在忽略的 Trial 目录。
- CS-UP-03 验收回归：`.venv/bin/pytest -q` 为 485 passed、1 skipped；`npm --prefix apps/web test -- --run` 为 18 passed，`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests challenges/local_a619cdef/scorer` 与 `git diff --check` 通过。沙箱失败/恢复、Codex 工具白名单和结束证据格式的定向测试均通过；前端未改动。
- CS-UP-03 失败路径：`run_06316b6fa6` 的 `cpu=2` 被平台 `INVALID_ARGUMENTS` 拒绝，原 request ID 只读查询为 `RESOURCE_NOT_FOUND` 后账本改为 failed，未创建远端实例；`run_c118eaee44` 的旧 Trial 路径在本地 `INVALID_PATH` 被拒，远端创建数为 0；`run_312f38ada6` 暴露 Codex 工具白名单缺口及 MCP 10 秒重放/评分执行与删除竞态，曾真实创建 1 个沙箱，评分失败、无 `local_scores`，实例最终 `deleted`。这些失败未产生 Job 或 Attempt。最终成功 Run 的完整链路见上条。
- CS-UP-03 当前评分契约只读复核（2026-09-27 10:15 UTC）：对主选 abc、备选 MCM 各调用一次题目详情及公开尝试首页，并读取一次 `/api/protocol`，只保存无作者信息的字段摘要到本机忽略目录 `.package-checks/cs-up-03-score-contract-20260927T101535Z/contract-summary.json`（3874 字节，SHA-256 `0ae71dadb4c9bda97b7b732187e29652f43afd99ce8451537df716ea59f5feb4`）。两题轮次均于 2026-08-29 12:30 UTC 结束，当前策略同为 `arm_v1_1_generic`、无题目专属 grader；公开晚交样本的 scorecard 字段只有通用五项，无独立 harbor/trace 分项。当前协议说明 `trace_quality` 在轨迹提取后按步骤数取 0/0.5/1，不等于旧 0–100 轨迹分。未创建新 Run、Job、沙箱、数据下载或 Attempt。
- CS-UP-03 经验：大脑在 `run_b1ba85d4fb` 结束前按原生生命周期更新题内经验 `exp_a8640e677f`；结束后经原生 `POST /api/v1/runs/{id}/curation` 的请求 `curation_5dac77f2f9` 作一次整理，状态 `done`、1 条题内修订已应用。分数二次观察确认后再次原生整理 `curation_0ce224953c`，状态 `done`、同一经验修订 1 次，最新文本仍标 `hypothesis`，引用本 Run 的检查点和事件，并把 41.43 写为本地 `confirmed`。经验明确区分外部适配器修复、执行器动作、历史 provisional 与当前 confirmed、原 H3 unknown，不把经验采用归因为得分提升。没有提议或自动批准全局经验；原始回执和实验包没有写入经验文本。
- CS-UP-03 W3 H5–H7：同一 Run `run_b1ba85d4fb`、同一科学来源包 `9c0ade1ec556b90890dc6e69b1996f1ada20a860e6b67fa83f665c006b16d5ba`。H5 创建 HTTP 400 指出轨迹 `timestamp` 超过 30 字符且 `nothing was stored`；备份本机 SQLite 至忽略目录 `.package-checks/cs-up-03-h5-reconcile-20260927T093742Z/before.db` 后，仅将 `sub_b8c82e4cc9` 对账为 `failed` 并释放预留。H6 创建 HTTP 400 指出第 3 步 `title` 超过 300 字符且 `nothing was stored`，新分类器自动将 `sub_1064e20791` 记为 `failed` 并释放预留。H7 新意图 `sub_2d30d5b21d` 经平台创建 Attempt `46889`、bundle 回执 `ready`、submit 成功；平台首次返回 `scoreIsFinal=true`、41.43，本地先记 provisional，10 分钟后同值第二次只读观察将其确认为 `confirmed`。三个 Trial 的脱敏审计与原始产物只在忽略的 `workspace/`；没有新增 Bohrium Job、沙箱、数据下载或收割。原 `sub_5f0ec08d05` 仍为 `unknown/create_sent`、无远端 ID、预留未释放。H7 后全套 `.venv/bin/pytest -q` 为 477 passed、1 skipped；前端 18 passed、构建通过，`compileall` 与 `git diff --check` 通过。
- CS-UP-03 W3 H4 诊断：用户要求停止等待后，通过现有 Run 的 `control/steer` 立即唤醒大脑；大脑新建只读诊断 Trial `trial_4773fb7c9e`，执行器完成字段审计和检查点 `cp_13cae7e0b3`，大脑随后决定暂停 Run。原历史适配器会把 ARM `step_type` 原样放进 Attempt 创建表单的 20 条行内轨迹；官方表单要求 `type`，离线重建显示 20 条都缺该字段。当前适配器对同一 20 条步骤的离线字段检查为 0 错，但未重新 POST。原包的 ARM trace-step schema 为 0 错，manifest 与 characterization 共 10 项官方 JSON Schema 错误；这些内容在创建失败时尚未上传，不能解释创建阶段的 HTTP 400。诊断 Trial 在本机忽略目录保存脚本、回执摘要、报告和仅修正元数据的交付包；修正包的官方 schema 离线检查为 0 错。本次未创建新 Job、沙箱、Run 或 Attempt，原 1 个 CPU Job 已完成并取回，真实计费金额未知。
- CS-UP-03 W4 准备：fake 平台回归覆盖普通与纯投影轨迹变体的来源截止序号、科学产物哈希、幂等及 API 门禁；尚无真实变体或平台分数。`.venv/bin/pytest -q` 为 470 passed、1 skipped；`npm --prefix apps/web test -- --run` 为 18 passed，前端构建、`.venv/bin/python -m compileall -q src/cyberscientist` 与 `git diff --check` 通过。本轮核对真实 `run_b1ba85d4fb` 仍为 `running/open`：1 个已完成且取回的 CPU Job、1 条 `unknown/create_sent` 提交、0 个 confirmed 分；最近大脑决定为等待 1800 秒。此核对没有新建 Job、Attempt 或 Run。
- CS-UP-03 W3 行内轨迹协议修正：公开 Agent API 文档列出 Attempt 创建表单步骤必填字段 `type`/`title`；本次真实失败包原适配器送出的末 20 步约 19,882 字节且只有 `step_type`。改动后同一冻结包的本地投影仍为 20 个真实步骤、17,614 字节，均有 `type` 且无 `step_type`；封存包未改。`tests/test_mailbox_platform.py tests/test_submission_integrity.py` 定向 33 passed；全套 `.venv/bin/pytest -q` 为 468 passed、1 skipped；前端 18 passed、构建通过，`compileall` 和 `git diff --check` 通过。未对平台再次 POST，故不能把字段差异断言为原 HTTP 400 根因。
- CS-UP-03 W3：真实主选题 `local_a619cdef`、Run `run_b1ba85d4fb`，大脑与执行器均为已检查可用的 `gpt-6-sol/xhigh`；授权 180 分钟、最多 5 CPU Job、1 个沙箱累计 120 分钟、2 次实验提交、无 GPU/数据下载/收割。实际创建 1 个 CPU Job `23436974`，状态 `Finished`，受控下载 `out.zip` 1573 字节且 SHA-256 为 `ad53cde5b87b58b8724ff2c07faa97719edd0ca2fcc75f3bb3eb32aee54f2bad`；0 沙箱、0 本地科学评分、0 收割。原包默认预检 `admitted`、`not_applicable`、`error_code=null`。大脑指导的第 1 次实验提交 `sub_5f0ec08d05` 在平台创建 Attempt 时收到 HTTP 400；本地为 `unknown/create_sent`，无远端 ID、无分数，保留预留。执行器只读核对可见非草稿列表未发现匹配记录，不能排除私有草稿；大脑先暂停同一 Run，后端升级重启后的 recovery 审阅决定等待权威对账，没有重试、没有第二个 Job/Attempt。真实计费金额未知，原始回执和包仅留在忽略的 `workspace/`。W3 迁移前 SQLite 备份 14,254,080 字节于忽略目录 `.package-checks/cs-up-03-w3-20260927T075649Z/`，`replay_of` 列已存在。fake 回归覆盖原样重交、无输入门禁及 HTTP 400 详情脱敏；最终 `.venv/bin/pytest -q` 为 466 passed、1 skipped；前端首次 Vitest 进程段错误，重跑两次均 18 passed，`npm --prefix apps/web run build`、`compileall`、`git diff --check` 通过。
- CS-UP-03 W2：迁移前本机 SQLite 备份 14,213,120 字节于忽略目录 `.package-checks/cs-up-03-w2-20260927T074036Z/`；连续两次 `db.init_db()` 后两张新表存在，随后新增评分器文件哈希列并再次重复迁移，题目 4、Run 7、提交 2、Job 28 行不变。fake 题目镜像/沙箱验收覆盖评分器文件变化引起版本变化、镜像不符时不触远端、固定格式评分入账、轨迹预测确定性、封存 SHA 变化后的科学结果派生、科学文件变化后禁止派生、平台两次评分观察 confirmed 后自动校准及撤销确认。两份项目 skill 经 `.venv/bin/python /home/wmywb/.codex/skills/.system/skill-creator/scripts/quick_validate.py` 验证。定向 `tests/test_local_scoring.py tests/test_mailboxes.py tests/test_polling.py` 为 46 passed；全套 `.venv/bin/pytest -q` 为 463 passed、1 skipped（既有回环监听限制）；`npm --prefix apps/web test -- --run` 为 18 passed，`npm --prefix apps/web run build`、`compileall`、`git diff --check` 通过。
- CS-UP-03 W1：迁移前本机 SQLite 备份 14,213,120 字节于忽略目录 `.package-checks/cs-up-03-w1-20260927T0725Z/`；连续两次 `db.init_db()` 后新增四列，题目 4、Run 7、提交 2、Job 28 行不变。fake 测试覆盖八种指定违规加缺失引用、确定性合并、只读预检、变体非轨迹逐文件字节一致、幂等与双角色 MCP。定向 `.venv/bin/pytest -q tests/test_trace_narrative.py tests/test_mailboxes.py tests/test_submission_integrity.py tests/test_ev_upgrade.py` 为 126 passed；全套 `.venv/bin/pytest -q` 为 457 passed、1 skipped（既有回环监听限制）。`npm --prefix apps/web test -- --run` 为 18 passed，`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests`、`git diff --check` 通过。
- CS-UP-03 W0：fake 回合覆盖 20 分钟持续原生活动、不泄露思考正文、完全静默后只排一次会话重启、显式 1800 秒等待到期、无活跃 Trial 仍触发检查；原运行时证据用例更新为“240 秒流告警不提前裁决”。`.venv/bin/pytest -q` 为 444 passed、1 skipped（既有回环监听限制）；`npm --prefix apps/web test -- --run` 为 18 passed，`npm --prefix apps/web run build` 通过。尚未用真实 Codex/Kimi/Prime 回合验证这一边界。
- CS-UP-02 W6 后续验收修正：临时数据库与 fake 平台覆盖新 Run 的手动提交空预测被拒且不预留、有效预测经 API 保存、旧 Run 可继续空预测；前端覆盖必填提示和预测传递。定向 `.venv/bin/pytest -q tests/test_mailboxes.py tests/test_submission_integrity.py tests/test_learning_integrity.py tests/test_ev_upgrade.py tests/test_polling.py` 为 125 passed；全量 `.venv/bin/pytest -q` 为 438 passed、1 skipped（既有回环监听限制）；`npm --prefix apps/web test -- --run` 为 18 passed；`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests` 和 `git diff --check` 通过。前端首次构建发现测试断言使用了不支持的 `exact` 参数，改为锚定正则后重跑通过。所有验证均未调用真实模型、创建 Job 或提交 Attempt。
- CS-UP-02 W7：本机保存的官方 API 文档列出尝试列表 `page`、`limit`、`sort` 参数，历史公开回执示例含 `attempts`、`total`、`scorecard` 和 `scoringState`。fake 分页测试覆盖分档、分位数、匿名、缓存、平台失败与执行器拒绝；`.venv/bin/pytest -q` 为 436 passed、1 skipped（既有回环监听限制），前端 17 passed、构建通过，`compileall` 与 `git diff --check` 通过。
- CS-UP-02 W6：迁移前本机 SQLite 备份 14,213,120 字节至忽略目录 `.package-checks/cs-up-02-w6-20260926T215854Z/`；连续两次 `db.init_db()` 后提交三列、指导一列存在，题目 4、Run 7、提交 2、Job 28 行保持不变。fake 测试覆盖新旧 Run 提交指导、预测冻结/收割继承、已确认分项变化、判定入账、评分修订失效和整理输入。最终 `.venv/bin/pytest -q` 为 432 passed、1 skipped（既有回环监听限制），前端 17 passed、构建通过，`compileall` 与 `git diff --check` 通过。
- CS-UP-02 W5：临时 SQLite + synthetic 回执测试覆盖角色注入、环境事实创建/冲突修订/到期、代理与用户拒写；`.venv/bin/pytest -q` 为 429 passed、1 skipped（既有回环监听限制），`npm --prefix apps/web test -- --run` 为 17 passed，`npm --prefix apps/web run build`、`compileall`、`git diff --check` 通过。未据 synthetic 回执推断真实平台环境。
- CS-UP-02 W4：联网前置检查两域名解析、公开首页返回 HTTP 301。本机 SQLite 迁移前备份 14,184,448 字节到 `.package-checks/cs-up-02-w4-20260926T213030Z/`，两次 `db.init_db()` 后沙箱两表和三列存在，题目 4、Run 7、提交 2、Job 28 行不变。首次真实创建被本地计费确认拦截，回执明确未执行/未计费，原 request ID 查无实例。加入 `--yes` 后仅实际创建一个默认 `sdbxagent` 沙箱（2 CPU、4096 MB），沙箱内执行 `print(1)` 为退出码 0，小文件写入/读回一致；删除后先观察到 `destroying`，稍后只读列表确认目标消失，探针账本最终为 `deleted`。全部脱敏回执、夹具数据库及文件只在本机忽略目录。fake 网关测试覆盖授权、禁用参数、跨 Run 所有权、路径、未知创建对账、执行轨迹、终止回收、启动孤儿处理、回执脱敏与异步删除。全量 `.venv/bin/pytest -q` 为 425 passed、1 skipped（既有回环监听限制）；随后针对异常终止回收的代码补丁，`tests/test_controller.py tests/test_sandboxes.py` 复测 27 passed。前端 16 passed；构建、`compileall`、`git diff --check` 通过。
- CS-UP-02 W3：经平台适配器各读取一次公开 Attempt 36189、历史 Attempt 46231 及其 `/score`；36189 的回执中 `harbor_score=100.0`、`trace_score=70.525`、`displayScore=80.0`，分项一致性判为 0。46231 两接口均无科学分/轨迹分，未推断数值。旧客户端第一次受控 `job list` 因无 `/dev/tty` 失败；第二次受控只读 `job list --json` 返回退出码 0、`ok=true`，确认 `openapi.dp.tech` 的列表查询。迁移前备份 14,184,448 字节数据库至本机忽略目录，连续两次 `db.init_db()` 后新增两列，题目 4、Run 7、提交 2 的行数不变。脱敏探针审计存 `.package-checks/cs-up-02-w3-20260926T211157Z/`，未创建 Job。全套 `.venv/bin/pytest -q` 为 414 passed、1 skipped（既有回环监听限制）；前端 15 passed，构建、`compileall`、`git diff --check` 通过。
- CS-UP-02 W2：迁移前 SQLite 在线备份存本机忽略目录 `.package-checks/cs-up-02-w2-20260926T210140Z/`；`db.init_db()` 重复执行后新增每 Run/角色限流表及 `state` 列，题目 4、Run 7、提交 2 的数量不变。fake 测试覆盖静默唤醒与修复、第二次无进展暂停、Running Job 长时豁免、心跳/usage/重复 job list 不续命、大脑超时重建、执行器失联重建、大脑和执行器连续 429 后成功、超过限流时限暂停，以及非终态阶段唤醒/超时映射。最终 `.venv/bin/pytest -q` 为 410 passed、1 skipped（既有回环监听限制）；前端 15 passed；构建、`compileall` 和 `git diff --check` 通过。
- CS-UP-02 W1：迁移前 SQLite 在线备份保存于本机忽略目录 `.package-checks/cs-up-02-20260926T202708Z/`；连续两次 `db.init_db()` 后，`challenges` 新增两列，原有题目 4、Run 7、提交 2 的行数均保持不变。fake 运行时 3 个并行 Demo Run 的会话/令牌/事件隔离、暂停/恢复/完成、独立启动恢复、Job 占位恢复失败隔离、模型快照与 modelTag，以及 HTTP/前端总览均有自动化测试。W1 最终 `.venv/bin/pytest -q` 为 399 passed、1 skipped（既有回环监听限制）；前端 15 passed；构建、`compileall` 与 `git diff --check` 通过。
- CS-UP-01 已在迁移前以 SQLite 在线备份保存本机数据库到忽略目录 `.package-checks/upgrade-20260926T190730Z/`，随后执行两次 `db.init_db()`；新增 7 个评分列，原有 2 条提交按迁移前列逐值保持一致，`exhausted` 邮箱数为 0。首次校验脚本因比较 `tuple` 与 `sqlite3.Row` 而在断言处失败；修正校验类型后通过，迁移本身没有失败。
- CS-UP-01 最终回归：`.venv/bin/pytest -q` 为 392 passed、1 skipped（沙箱禁止回环监听的既有测试）；`npm --prefix apps/web test -- --run` 为 14 passed；`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests`、`git diff --check` 均通过。前端命令使用项目 Linux Node 22 路径。此前全套曾得到 385 passed、1 skipped、2 failed；测试对错误包根的断言及迁移事务嵌套均已修正后重跑全套通过。
- CS-EV-01b 根因对照：同一 USCT Job、同一只读 `GET /openapi/v1/job/{id}`，在 `open.bohrium.com` 返回 HTTP 404，响应 `error` 为对象且说明旧路由不匹配；在 `openapi.dp.tech` 返回 HTTP 200、`code=0`。仅覆盖旧 CLI 子进程 host 后，`job download` 返回 `ok=true`，取得 `out.zip`（1,900,228 字节，ZIP 校验通过）；24 个文件条目中 22 个与此前由日志 ZIP 恢复的同名文件 SHA-256 一致，另 2 个旧目录没有。原始脱敏回执及逐项哈希仅存本机 `.package-checks/job-debug-*`。
- PR-4 Job `23433560` 使用修复后的受控 `compute.cli` 再次取回 `out.zip`（582 字节），账本 `retrieval_status=retrieved`，`image_facts` 已登记；归档内 `results/facts.json` 与 `results/data-proof.json` 均存在且 ZIP 校验通过。`job describe --json` 给出 `statusStr=Finished`、`webStatus=2`、`exitCode=0`、无 `errorInfo`；数据证明引用的物化记录为 `verified`，其内容哈希与本机已登记目录一致。此为文件与运行回执验证，不代替平台评分或科研结论。审计文件留在 `.package-checks/pr4-download-correct-host-20260926T161824Z/` 及忽略的 Run 工作区；未创建新 Job、Run、Attempt，未切换客户端或修改全局认证。
- CS-EV-01b 根因修复后的最终回归：`.venv/bin/pytest -q` 为 366 passed、0 skipped；定向 `.venv/bin/pytest -q tests/test_compute_gateway.py tests/test_bohrium_connection.py` 为 44 passed；`npm --prefix apps/web test -- --run` 为 12 passed，`npm --prefix apps/web run build` 成功；`.venv/bin/python -m compileall -q src tests` 与 `git diff --check` 均通过。前端命令使用项目 Linux Node 22 路径。本轮没有新模型调用、付费 Job 或比赛 Attempt。
- CS-EV-01b 联网前置检查：两个 Bohrium 域名均解析成功，`curl -sS -o /dev/null -w '%{http_code}' https://open.bohrium.com` 返回 301。只读 D1 探针选 USCT 接续 Run 的 Finished Job `23424706`，旧目录有 22 个文件；本次仅调用一次 `compute._native(job download)`，进程退出码 0、`ok=false`，stdout 为 `RespErr.error` JSON unmarshal 错误、stderr 为空，新目录 0 文件，无同名文件可作哈希比较。脱敏回执在本机忽略目录 `.package-checks/job-retrieval-probe-net-20260926T160849Z/`；未重试、未新建 Run/Job/Attempt。
- CS-EV-01a 最终回归：`.venv/bin/pytest -q` 为 355 passed、1 skipped（回环监听受沙箱限制的既有跳过）；`tests/test_ev_upgrade.py tests/test_compute_gateway.py` 定向测试 86 passed；`npm --prefix apps/web test -- --run` 为 12 passed；`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests` 和 `git diff --check` 均通过。前端测试和构建使用项目 Linux Node 22 路径。
- CS-EV-01a 迁移前 SQLite 在线备份保存在本机忽略目录 `.package-checks/upgrade-20260926T154308Z/`，随后在本机数据库执行 `db.init_db()`，实际只追加 `compute_jobs.retrieval_status` 一列。获授权的 D1 单次只读旧 USCT Finished Job 下载探针保存在 `.package-checks/job-retrieval-probe-20260926T154546Z/`：bohr 1.1.0 进程退出码 0，后端回执 `ok=false`，输出文件 0 个；脱敏输出明确显示当前沙箱在 DNS 查询时因 socket 权限拒绝，请求未到平台。探针未创建 Job、Run 或 Attempt，也未重试。
- 提交前将依赖真实 Wenyon 文件/回执的测试改为运行时生成合成样本，并把 8 个未跟踪的真实实验文件移入本机忽略目录 `.package-checks/cs-ev-01-real-fixtures-unpublished/` 后重跑：`.venv/bin/pytest -q` 为 337 passed、1 skipped；前端 `npm --prefix apps/web test -- --run` 为 11 passed，`npm --prefix apps/web run build` 成功。测试和构建未再次访问账号服务或创建 Job/Attempt。
- 真实 Linux connected Run 已从同源前端启动并于 2026-09-26 07:53:46 UTC 结束，目标状态 `partial`；Codex 大脑和执行器 inspect 版本 0.155.1，随后完成 6 次大脑审阅和首个 Trial 的原生模型往返。开局 v2 Decision 因解析器只认 v1 而暂停；修复后恢复**同一 Run**，没有创建替代 Run。完整回归验证 337 passed、1 skipped。
- 本 Run 的官方 Wenyon 公开数据经受控 API 物化为 `verified`；2 个文件共 1148 字节，逐文件哈希及公开清单原文字节哈希通过。缺失本地模块的预检在预留 Job 前返回 `MISSING_LOCAL_MODULE`。
- 唯一获授权的 PR-4 Job 由普通 `compute.submit` 网关创建，平台创建回执成功；账本中的数据引用指向本轮已验证的物化记录，冻结输入包含官方文件、物化清单及探针。配置为 `c2_m2_cpu`、2 核/2 GB、10 GB 磁盘、最长 5 分钟、无 GPU/重调度。远端列表观察到 `Finished`，不将此状态冒充进程退出码或结果成功。本 Run 有 193 条事件、1 个 Job、0 个 Attempt、0 条镜像事实；前端返回 HTTP 200。原始标识、回执、检查点和结果包仅在本机忽略目录 `.package-checks/real-acceptance-20260926T073421Z/` 与 `workspace/runs/`；可提交的结果概述见 `docs/CS_EV_01_REAL_RUN_ACCEPTANCE_2026-09-26.md`。
- PR-3 在用户新增授权下，于项目隔离 HOME 原生登录一次；Wenyon 本地 `auth whoami` 随后通过。只下载一次登记的公开数据集，CLI 回执退出码 0、2 文件、1148 字节、无失败文件。第四季本机题目快照的 `public_manifest_sha256` 与下载的 `public-manifest.json` 原文字节 SHA-256 一致，清单内资源文件哈希/大小和题目登记总字节数也一致。完整回执与真实下载文件留在本机忽略目录 `.package-checks/wenyon-pr3-login-authorized-20260926/` 和 `.package-checks/wenyon-pr3-download-after-login-20260926/`；不提交真实数据 fixture。该 PR-3 探针当时无新 Run、模型调用、Job 或 Attempt。
- PR-3 后曾用真实公开文件作离线回归，验证有效清单、登记哈希错误和资源文件被改写；当时 `.venv/bin/python -m pytest -q` 为 336 passed、1 skipped，前端测试 11 passed，构建、`compileall`、`git diff --check` 均通过。为避免提交实验文件，可提交的测试现改为运行时生成合成 v1 清单；真实授权探针的结果仍由本机审计目录保留。
- 本轮只读 PR-1：`GET /api/protocol` 返回 200、21194 字节，SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`；PR-2：本机 SQLite 的 USCT bundle/score 两条回执已脱敏冻结，确认 `bundleStatus=needs_review`、`validation.trace_admission.admitted=false`、`violations[].rule=trace_admission_blocked`。PR-3 已按单次授权执行固定 `bohr wenyon dataset download`，本机 CLI 报 `unknown command "wenyon"`，无文件下载。
- 迁移前源码、工作树补丁与 SQLite 备份已保存在本机忽略目录 `.package-checks/upgrade-20260925T161211Z/`；该目录未纳入公开 fixture。
- CS-EV-01 初次实施时，`.venv/bin/python -m pytest -q tests/test_ev_upgrade.py` 为 35 passed；测试进程定时唤醒包装下，EV/计算/提交相关测试 69 passed，Python 全套 `pytest -q -k 'not test_cli_sigterm_exits_with_sse_client_still_connected'` 为 330 passed、1 deselected。原始 `.venv/bin/python -m pytest -q` 当时在 90 秒后超时，仅输出 4 个通过点；直接组合运行 EV/提交相关三组测试在 30 秒后于 42 个通过点处仍未退出，手动中断。两者都未记为通过。
- 本次修复后，项目本机数据目录的 bohr 2.7.8 npm 归档 integrity、二进制哈希以及 Wenyon 1.36.0 manifest 哈希均核对通过；隔离 HOME 下 `extension list` 返回 `status=ok`，`wenyon dataset download --help` 返回 0，后端 `_native` 入口同样成功且回执不含密钥。`.venv/bin/python -m pytest -q` 不再需要包装：332 passed、1 skipped（沙箱禁用回环监听）。`apps/web` 的 `npm test -- --run` 为 11 passed，`npm run build` 成功；没有新增模型调用、Job 或 Attempt。
- 新授权的 PR-3 单次重试已执行：bohr 2.7.8/Wenyon 1.36.0 返回退出码 3、服务 `401 Not authenticated`，没有数据文件。回执与空文件清单在本机忽略目录 `.package-checks/wenyon-pr3-authorized-20260926/`。离线 `bohr auth status` 只确认环境中存在 AccessKey；离线 `wenyon auth whoami` 返回 `not logged in (no state)`。这不能证明 AccessKey 有效或账号拥有该数据集权限。
- 当时针对专用 CLI、扩展缺失和 401 分类的 Python 定向测试为 3 passed；前端测试 11 passed，构建与 `git diff --check` 通过。当前提交的 401 测试使用合成回执，不携带真实实验回执。
- 本轮 Linux `apps/web` 执行 `npm test -- --run`：11 passed；`npm run build` 成功。`compileall` 与 `git diff --check` 通过。上述新增科研流程测试均使用临时数据库、fake CLI/平台，未发起真实模型、Job 或 Attempt。

- 本次 Linux 项目虚拟环境执行 `.venv/bin/python -m pytest -q tests/test_collaboration.py -k 'not test_t13b_submit_guidance_failure_marks_failed and not test_t13_submit_guidance_auto_submits_without_executor'`：55 passed、2 deselected；其中 fake runtime + HTTP MCP + outbox 闭环证明零读取第三路线、可选读取、全文交付和 ACK。
- 本次在测试进程临时增加事件循环定时唤醒、未改产品代码或断言后，Python 全套除本机回环监听用例外 283 passed、1 deselected；回环 CLI 关闭用例单独获准本机监听后 1 passed。确切入口与局限见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。
- 本次执行 `.venv/bin/python checks/evaluate_sparse_brain.py`：3 个离线样例加载，0 次真实模型调用。
- 本次 `apps/web` 执行 `npm test -- --run`：10 passed；`npm run build` 成功。
- 代码与资源提交前已核查大文件、归档、数据库和已知密钥；本次公开提交不包含实际运行状态文件。
- 本轮测试进程定时唤醒包装下，协作及 Kimi/Codex 相关回归 95 passed；排除 CLI 关闭测试的 Python 回归 285 passed。默认协作测试曾以 120 秒超时退出，未记为通过。

## 尚未验证

- CS-UP-10 W2–W5仍待按序施工；没有开始CS-UP-11或彩排。真实现代Job探针均首次确认，没有真实制造创建超时；恢复机制由fake覆盖，未来平台稳定性与历史unknown最终计费仍不可保证。

- CS-UP-09：最后时限／底层关闭补修未新增真实Run复测，ABC原44.19秒超限的唯一原因unknown；Kimi／Prime本轮原生恢复与真实工具探针未新增核实，不由Codex恢复结果推广。DeepSeek真实求解者已完成，独立审查者已返回问题；模型／Bohrium完整用量、计费时段和最终账单unknown，观察到的0.00无币种不能视为免费。

- CS-UP-09 W4：模型是否通读全部复盘文件仍不能由自报确认。四份三部分报告文件已存在，原三个Run维护调用在归档失败时已耗尽两次，早期复盘不覆盖恢复后完整科学轨迹；ABCfailed／0177done／0178unknown保留，第四0177正常done。

- CS-UP-08 W3：真实私有镜像已尝试两次但业务RPC错误、没有确认ID，未完成构建／持久冒烟；额度用尽且30分钟后只读复查未找到本卡资源。08真实Job评分已调用：一个完成、另一个包装输入布局失败；修复后未追加第三Job复测。

- CS-UP-08 W2后续验证：09真实Codex同ID恢复成功，归档错误和修复分别留证；Kimi／Prime原生恢复仍unknown，不能由schema／fake或Codex推广。

- CS-UP-08 W1–W4 的三个真实快速层 Run 已完成验收：本地正式分 FigQA-0177／0178 各100、ABC20，提交0；当前未验证项是私有镜像服务及已失败 Job 的修复后真实复评，不是三个 Run 尚未开始。

- CS-UP-07真实executor_verified登记仍未观察到：fake的64.79恢复、可信回执核对与拒绝伪造不等于真实通道已完整验收；实际六项正式分均system。四项缺分及六个新缺陷未因收尾解决；最后Run按用户明确要求提前终止。未知Job身份/费用、Job计费单位/币种及最终模型/算力账单仍未确认。

- CS-UP-07 W1 A～D已实现并经fake测试；v3首Lean已在CPU Job中自行完成固定版本环境与证明编译，第二轮Lean沙箱T2/T3编译实测通过，两轮正式评分登记均未完成；Matchgate第二轮已实测成功取回基线，但正式评分未执行。旧v2缺分和CS-UP-06真实预置环境缺项仍保留，未被新Run或单项恢复成功追溯解决。

- CS-UP-06新执行器修复闭环已fake验证，尚未在新的真实Run/模型中验收；本轮原评测授权已到期，没有为验收追加真实调用。历史Matchgate评分科学包比当前原始产物多provenance/data_inputs.json，其余成员哈希一致；完整旧封存包缺失，64.7854恢复文件不计正式最终分。

- CS-UP-06 F3固定Lean4.32.2/锁定Mathlib缓存尚无verified环境；两次新沙箱及两次CPU Job离线构建、历史已验证证明重评分均未完成。

- CS-UP-06 F1新单调声明及评分缩时分支尚缺真实完成包科学验收；Matchgate首轮恢复文件64.7854未对应正式local_scores/最终封存包，正式分仍unknown。新声明仅下次Run可用。

- CS-UP-06 W2未达到基础设施缺分为0：abc首轮传输deadline、Lean两次环境失败、Matchgate首轮命令时间缺陷；第二轮因用户手动关机未完成（非程序缺陷）。用户已确认手动关机，当前环境11:06:47 UTC启动；该中断非应用崩溃或未修复程序缺陷，不把墙钟停机延迟当计算时长。

- CS-UP-06完整金额未确认：Job时长单位独立验证、旧cost币种、最终账单、两个v1及一个v2无ID预约状态/费用仍unknown，不将局部条件估算当完整金额。

- CS-UP-05 W2 的真实模型、Bohrium 沙箱/Job、Matchgate 全规模计时和 Lean 项目准备尚未验收；这些属于 W3 基线任务。公开 v6 轨迹检查表仅对历史 v8 可见代码作条件比较，不能给出官方展示分保证。Bohrium 金额无可靠接口时记录 unknown。

- CS-UP-04 没有取得完整 v8 评分器、服务端最终归一化轨迹或模型裁判值；条件分级与本地上限不能当作新题目的官方得分保证。只有现有 Linux CLI 0.1.33 与 Node 22 的本机离线诊断已测；其他安装环境的打包轮子、CLI 版本和真实平台新包尚未验证。诊断缺少固定依赖或匹配哈希时返回 unavailable。

- 第二轮修复只验证本地应用、隔离 Demo 及受控异步/失败回归；未发起真实模型、科学 Run、Bohrium Job、沙箱或 Attempt。真实平台中断的长时间行为未新增验收。上一轮后台标签页偶发停滞的唯一原因仍未判定，不能由本轮 SSE 修复倒推出其原因。

- 本次 skills 修复未启动真实科研或真实模型，也未验证新的远程 Job/Attempt。WebBridge 曾出现一次设置加载停滞及命令超时；后端只读设置请求约 7 ms 返回 200，刷新并开启网络诊断后未再复现，根因未判定，不能作为已修复的产品缺陷。

- 本轮实际浏览器窗口自动打开未做 GUI 验收；在 WSL 中已实现 Linux opener 失败时的 Windows 浏览器回退，窗口可见性待用户桌面环境验证。无新的模型、Job 或 Attempt 验收。

- 第四季新增候选只完成规范可复刻性判断：Matchgate 实例/schema、DPA4C 的公开检查与计时源码本轮未取回执行，未验证新的官方分数一致性；Paired-block 的既有回放证据仍以原报告为准。

- FigQA 仅验证规范答案及两种实际答案内容，不声称完整复刻隐藏解析器、ARM 可执行性/封包准入或轨迹评分。Paired-block Lean 已验证 4 份历史提交与 8 种本地反例；E000 仍未完成真实回放，中间分数的官方反例回执、隐藏资源限制及所有异常输入的等价性尚未验证。

- 公开 scorer 是 `evidence-checklist-v6-contextual-signals`，历史 63 回执是 `v8-process-evidence-sufficiency`；尚缺 v8 完整源码、双裁判原始数值和服务端最终输入。E008 的转换缺陷已在固定本机 CLI 复现且与旧诊断吻合，但历史服务端唯一根因与修复后的真实评分效果未验证。新增工具是源码审计，不是已验证的 ≥70/≥80 内容预测器。
- 历史赛季外部/专属评分 worker 与当前题目详情的 `arm_v1_1_generic` 元数据何时切换、旧轨迹的最终归一化行、每项科学验算和同包重评分噪声仍未知。当前官网通用 ARM `executability` 的结构分不能证明 Dockerfile 真正构建或代码实际运行；不能用它预测旧轮次的 `trace_score`。
- 两道 FigQA 历史满分提交当前无凭据查分 404 的原因未判定；其历史分数仍由本地真实回执支持。Paired-block Lean 某条早期本地 0 分与较晚平台最终 100 分的差异原因不可见。历史满分题的隐藏科学逐项验算、平台最终归一化评分轨迹以及独立同包重评分噪声均未取得；CNVkit harvest 满分提交没有独立封存输出，本轮只核对当前原路径。
- 63 份未遮蔽回执可确认历史展示分合成系数和若干诊断代码，但不能复刻从输入轨迹到 `trace_score/trace_decision` 的完整引擎，也不能确认当前平台仍沿用 `trace-score-cli/0.3.0-beta.1`。其中 6 份命令路径当前不能证明输入字节，但已由回执哈希在其他封存副本中找到相同内容；评分器内部投影仍不可见。`harvest/` 回执没有可核对的封存输出快照。FigQA 同本地答案不同科学分的异常已发现接收包错配，具体零分机制缺逐项科学验算仍未知；共享可变包路径是否由并发竞态导致也未证实。
- AgentMaster 上传输入由官方 CLI 如何归一化、平台最终对哪几行打分，当前不可从旧 Attempt 的 API 轨迹或 bundle 复核。58 条最终分已做探索性的整题留出结构特征检查，但特征是看过样本后选择，不能当作独立前瞻验证；连续轨迹分预测误差和同轨迹重复噪声仍未知。另 4 条旧分项没有在 AgentMaster 本地提交记录中找到精确配对。
- CS-UP-03R 全账号轨迹扩查：9 条列表有轨迹却读到空数组的记录是否能由代理本人 token 或平台后台归档恢复，未知；当前项目凭据库没有这些代理的直接 token。`GET /attempts` 不提供 total，不能确认私有草稿完整性。API 轨迹与包内选中轨迹的差异已确认，但平台对每条旧提交实际采用哪个输入评分、以及重复包的评分噪声，仍无可配对最终回执。75 条旧轨迹分缺内容，≥70/≥80 预测误差不可计算。
- CS-UP-03R：上述 72 条旧提交在平台后台是否另有仅代理本人可读的归档，本轮不能判定；三个历史代理的直接 token 不在项目现有密钥库。30–70 轨迹因子门槛由主办方告知（用户转述），但这批历史分数中的 10 条低分段冲突尚无权威解释；分段替代计算只是样本内描述。
- CS-UP-03R W3–W5：10 条旧实时展示分为何违反主办方告知的公式，现有回执无法判定；逐题科学评分器的验证仍缺经核对的科学输入；轨迹预测器已补回本地 CLI 输入，但还缺最终评分轨迹核对和留出验证。下一实时轮次的同包重复、单因素对照和留出实验尚未执行；全局经验候选也未获用户审批。
- CS-UP-03R W2 的历史状态：当时仅查平台 API 和 CyberScientist 来源，71 条实时轮次双分项记录可取得的原始 bundle、轨迹和科学文件数为 0；3 个可下载 bundle 属赛后通用评分或待复核。创建表单的行内 trace 未见于已收回的详情或本地提交账本，保持 `unavailable_not_in_receipt`。后来 AgentMaster 的 71 条本地配对已补上提交输入和科学输出；仍缺平台最终归一化轨迹与逐项评分回执。
- CS-UP-03R W1：作者过滤接口没有返回平台全局 `total`，当前 75 条只能证明与已发现题目的公开分页一致，不能证明没有其他题目或私有草稿。72 条旧双分项记录缺原始轨迹与科学文件，后续 W3/W4 的可验证性须在规范化数据集后单独判定。
- CS-UP-03 H7：Attempt `46889` 的展示分 41.43 已按两次同值观察确认为 `confirmed`；但平台没有返回独立 harbor/trace 分项。H7 原 Run 没有本地评分记录；后续独立验收 Run 已在真实沙箱记录题面科学分 20，但没有与 H7 相同的最终封存 SHA，也没有可比的双分项平台回执，因此不能把 20 和 41.43 当作一对校准样本。同包重复噪声、W4 对照和 W5 留出验证仍未得到。
- CS-UP-03 H4 原请求：真实 wire 字节、HTTP 400 正文和服务端 request ID 均未留存；离线重建只能证明字段契约不符，不能证明原 400 的唯一根因。后续 H7 已被平台接收并评分，但不能据此判定原 H3 的远端副作用；W3 的两条 confirmed 基线、W4 对照和 W5 留出验证仍未完成。
- CS-UP-03 的 abc 题面科学评分器已在真实 Bohrium 沙箱运行并记录 20 分；这只验证题面分档，不验证当前平台 `arm_v1_1_generic` 的展示分公式。轨迹预测器仍只有占位值与低置信度。H7 有一条 confirmed 展示分，但没有旧双分项基线或原包重交；W4 受控对照、W5 留出验证与校准均未执行，不能声称达到第三阶段退出标准。
- CS-UP-03 W1 的叙述变体尚未在真实平台提交与评分；包内科学产物哈希一致不等于平台科学分必然一致。本包没有模型调用、科研 Run、Job 创建或 Attempt 提交。
- CS-UP-02 W1 的多个真实 Run 并行及真实所选模型的原生会话检查尚未验证；W2 的真实 Codex/Kimi/Prime 错误文案、限流重试效果和长时看门狗仍未在真实 Run 验证。W3 的真实 `job submit` 仍未验证。W4 沙箱在真实科研中的用途与平台实际计费单位/金额未验证；W5 的真实环境事实自动采集尚未通过新的外部回执验收。W6 的真实预测与评分因果效果尚未验证；W7 的当前平台真实分页与长期缓存行为尚未实测。本包没有新模型调用、科研 Run、Job 创建或 Attempt 提交。
- CS-UP-01 的新封存包尚未经真实平台准入验证；真实评分器的复评时间线也未经真实环境验证。本卡未进行真实 Run、模型调用、Job、沙箱、Attempt 或平台账号访问。
- CS-EV-01a 的第一次 D1 探针曾受沙箱网络权限阻断；CS-EV-01b 已定位并修复旧 CLI 的 API host 错配，真实历史 Job 与 PR-4 Job 均已成功取回。仍未验证平台对 PR-4 科学结果的评分或比赛有效性；本卡未创建新的生产 Job。
- PR-3 的这个 v1 样本已下载并核对，且经真实 Run 物化与 Job 输入冻结；其他 Wenyon 清单格式及不同数据集的哈希语义未验证。已验证输入清单和数据证明，不等于验证所有远端读取行为。真实平台对封存包的准入结论及科学结果仍未验证。

- 原 CS-EV-01 验收时仅确认 Job 终态，未确认退出码和产物；本轮已取回 PR-4 产物及远端 `exitCode=0` 回执。远端运行环境的完整状态仍未核实。
- 经验改动对科研结果的因果效果尚未证明。
- CS-SB-01 的真实 Kimi/Codex 双会话往返、模型独立判断效果和原生内建工具完全禁用能力尚未验证；本轮按要求未启动真实模型或科研。
- CS-SB-01 当轮未重跑 CLI 关闭测试，也未验证未经包装的完整 pytest；该轮未修改 UI，故未重跑前端测试与构建。本轮 CS-EV-01 的前端测试与构建结果见上方。

## 阻塞项

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新确认：本地前置拒绝被反馈为远端unknown。run_cc0251a839#1283的CONCURRENCY_LIMIT在compute._authorized、预约及原生调用前拒绝，无新Job行或预约；API ComputeError处理统一possible_remote_effect=unknown、operation_id=null。原两个真实unknown保持不变，不能把本次反馈错误作为清预约的依据；科学分影响未确认，评测后修正失败阶段与操作身份。

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新确认：新Trial先active/current再投递，旧回合忙时投递rejected后无持久待投递，旧尾部事件错归新Trial（run_cc0251a839#1154/#1157/#1162/#1167，controller.start_trial/_handle_signal）。本次原停滞检测#1186空闲307秒后，大脑#1192经持久指导恢复，非永久失联；应用竞态仍未修复，评测后补通用投递及事件归属测试。

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新确认：有效Job硬件及并发限额未进入大脑运行事实。run_cc0251a839实际job_limits_json为16核/16GB/10GB/Job并发2，首帧与后续交棒ReviewPacket的authorization/operating_facts均遗漏这组字段；三次目标仍提出c8_m32_cpu，首请求被正确门禁拒绝后执行器自行缩小。实际成绩影响未确认。按冻结规则记录，留作评测后事实投影修复，不扩大授权。

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新确认：Job帧状态投影混入预检（observation.py::job_states）。run_cc0251a839#66预检passed后资源请求被拒、该operation没有compute_jobs行，但截止#78的持久审阅帧仍把它列为Job状态passed。只读重投影与原帧完全一致；大脑#94没有把它认作执行成功，科学成绩影响未确认。遵守冻结规则，记录为评测后修复项，不热修运行中后端。

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新发现：固定执行器评分包装程序在已实测Python3.10.6中调用hashlib.file_digest报AttributeError（run_6a1cfd461c#191，scoring_runner.py:15）。该通道兼容问题尚未修复；首轮通过系统最终评分取得100，整层仍继续。遵守W2冻结规则，仅记录，评测后再修。

- 历史记录，已由 CS-UP-08 W3 修复并经测试；原回执保留：CS-UP-07 W2新暴露：Job输入冻结丢失执行权限（compute.py:341），源zstd在提交前原生line234已chmod0755；冻结副本0644、字节/SHA-256相同，首Job在Lean启动前PermissionDenied。远端探针另观察到上传文件0666，平台后续模式变化也存在。执行器在原授权内绕过并成功编译，但应用冻结缺陷未修复，遵守两层终态前冻结规则保留为后续修复项，不构成整层无法继续。

- CS-UP-06 F3唯一私有镜像请求无ID/code148888 rpc error，创建结果unknown，占用本卡唯一环境资源预约。目录复核仍不能权威释放，不重复创建、改建数据集或新增节点；固定环境验收受阻。

- CS-UP-06 W2原队列已终态、原时长预算到期；剩余真实科学验收不能用追加Run/评分补齐。本轮如实交付非干净结果，不标成全部验收完成。

- CS-UP-05 W2 代码与 fake 流程无已知阻塞；W3 真实评分是否能取得各题科学分，须由授权内的真实 Run 核实。未取得结果时保持 unknown，不补造分数。

- CS-UP-04 本地离线诊断与提交准入无新增阻塞；完整 v8 判定可识别性仍受上节缺失的私有评分与归一化输入限制，不影响 advisory-only 运行。

- 第二轮应用修复无新增阻塞；既有科研/评分契约阻塞保留如下。

- 仅凭已读公开资料，USCT/FWI/XAS/Pancreas 的隐藏评测输入，以及 CNVkit/TBMA/Deep BSDE/堆积等题未完整披露的计分细节，阻止宣称完整官方科学分复刻；不妨碍实现已公开的独立科学检查。该项是评分可识别性限制，不是当前运行故障。

- Paired-block Lean 剩余 E000 回放未完成：全量 Mathlib 的 5 个缓存文件部分下载后停滞，600 秒期限到达；这 5 个文件经本机匿名 GET 补齐后，最后补验又在依赖包上传阶段失败，未进入证明验算。既有 4 份历史回放与 8 种反例不受影响；原始失败回执保留，两个新增沙箱均已回收。网络唯一根因未定位，未将环境故障写成科学 0 分。

- CS-UP-03R 评分器剩余阻塞：AgentMaster 两组已找回 71 条旧分项提交和 63 份未遮蔽历史诊断，134 条均有回执原生轨迹哈希相同的本地字节；旧组 58 条有最终双分项。历史展示分合成系数已可核对，公开 v6 轨迹评分源码及确定性合成已验证；但历史 v8 完整实现、平台最终归一化轨迹、双裁判原始数值和其他题目的逐项科学验算仍缺失，同包评分噪声未知，不能发布已验证的从内容预测 ≥70/≥80 的模型；科学评分已验证 FigQA-0177 的规范答案接口和 Paired-block Lean 的上述样本范围。另 4 条旧分项当前没有 AgentMaster 本地精确配对。
- CS-UP-03 W3–W5 的目标评分契约当前不可重现实测：主选与指定备选题均已过轮次，晚交回执采用通用 ARM 评分；当前协议无法给出任务卡要求的独立 `harbor_score` / `trace_score` 及其 ≥70/≥80 轨迹阈值。公开历史双分项和本轮通用分不可混合作受控拟合；任务卡要求的同包双基线、W4 对照和 W5 留出标准尚未达到。继续在备选 MCM 付费计算或提交不能解决该契约缺口，需有能产生目标分项的当前平台轮次/契约，或明确变更研究目标。
- CS-UP-03 当前 Run 授权最多 2 次实验提交，原未知创建与 H7 已提交各占 1 次；在原创建的远端副作用无法权威确认前，不能释放其预留。即使 H7 得分确认，本 Run 的同包原样重交仍受授权上限阻止；后续须在产品授权边界内另行安排，不能直接改账本或重复未知意图。
- CS-UP-03 H3 原 `sub_5f0ec08d05` 仍是 `unknown/create_sent`，无 Attempt ID、无 confirmed 分且预留未释放。带失败邮箱凭据的 `GET /attempts?author=<own-id>` 与匿名结果一致，均未包含私有 draft；公开列表不能充当权威对账。需平台按原账号、题目和创建时间确认是否产生私有 draft，才可对原意图释放预留或重试。H5/H6 的明确无存储回执仅适用于各自请求；H7 成功也不能为 H3 对账。额外 CPU Job 对此无诊断价值。
- CS-UP-03 W3–W5：H7 已得到一次真实平台展示分，但当前 abc 回执只有五项 scorecard，没有任务卡假设的独立 harbor/trace 分项，且本 Run 因原 unknown 预留已用满两次提交额度并结束。W3 的原包重交及 W4–W5 的受控评分实验尚不能在这个 Run 内继续；备选 MCM 需要另行明确数据物化与 Run 授权边界，不能由本次 abc 回执推断其评分契约。
- 此前 PR-3 登录与单次数据下载授权已用完，后续数据服务访问仍须单独授权。本轮只读历史 Job 诊断已完成；未计划额外请求。

### 待用户处理

- 五份 CS-UP-08 全局配方候选需在前端审批，施工没有代为批准。
- 历史CS-UP-08私有镜像两次HTTP200／148888未有ID；本卡按新授权复核v2仍失败，v4已构建并在Job/沙箱跑通。旧接口故障可向平台反馈，当前已验证替代路线不阻塞后续施工。

- CS-UP-09无ID Job的远端身份／是否计费及最终模型／算力账单需平台核查；超过30分钟只读复查仍unknown，没有重复创建。
- 历史09三个恢复Run的复盘缺陷和额度耗尽保留；本轮CS-UP-10已另行授权对四个旧Run完整复盘，将在W2l修复后执行，不重置旧调用账本。
