# CS-UP-13 修复证据

提交、收割的额度和排队保护已修复；不规范回执会暂停自动提交。
新经验、技能、能力清单和默认用户模板已接入。
轨迹门显示证据与unknown，不把弱规则说成正式分数。
材料镜像Job与沙箱通过；ABACUS Job和新沙箱均通过，旧TLS失败保留。
安全重部署在真实账本副本通过，停机126.69秒；自检有未确认项。
网络恢复后Astra简报和fast执行器通过原生零科研探针；科研闭环另验。
缺失经验、历史缺结果、留出可见性等硬验收缺口在下文逐项保留。
原始回执及第三方包只留本地忽略目录；阶段2另行验证官方CLI。

## W0

D-63–D-72 原文已加入 §5。开局 main 比 origin/main 落后 13 个 S4 文档/分析提交；rebase 的 STATUS 冲突已停止，原 W0 提交保留在 archive/cs-up-13-w0-before-sync，在最新 origin 上重新应用内容。使用已有 Windows gh 凭据 helper 单次调用推送，未保存凭据、未强推。

## W1

- 无上限收割统一调用 `run_limits.track_unlimited`，不会扩大历史独立 Run 的有限授权。红测试两种收割均失败；修复后覆盖一键确认→授权零计数→实验分确认→阈值/窗口收割。`w1-green-final.log` 82 passed；新增的一键完整链路等 `w1-integration.log` 10 passed。
- 两份彩排真实公开事件输入 5,600,974 / 2,446,981 字符，旧整段脱敏分别在 875,323 / 948,762 位置无法解析；字符串字段递归脱敏后 JSON roundtrip 均通过。`w1-real-redaction.json`。超长、转义引号测试已通过；历史 failed 维护记录未改写，不声称真实模型复盘成功。
- 三个环境文件与账本差异只有过期降级状态和固定待复核说明。新增受控登记只接受已登记 system_environment 旧修订的精确过期转换；文件正文或其他字段变化仍拒绝。三个文件字节保持不变，新修订为 candidate，不进入有效经验。`w1-environment-recovery.json`，原文件与 diff 已保留。写入来源的具体进程身份 unknown；不能用这些已过期观察当新鲜能力。
- 封包拦截真实平台拒绝的 `handoff.status=complete`，给出省略可选字段或诚实交接状态的提示；characterization 指针须存在且为 JSON 对象。公开 schema 的 complete 仍被允许，本次 GET 刷新后依然如此，DECISIONS 保留这一协议差异。现有预提交 public schema 验证继续保留；未编造 `modality` 必填字段。
- 沙箱创建超过 600 秒、请求 ID 404 且完整列表证明不存在时，添加列 unknown_slot_released 释放并发占位；对外显示 unknown_released，原 status unknown 和费用预约保留。总数不完整、字段不足、已有远端 ID 均不释放，不重发。仅新增列，未重建 CHECK 表。合成协议测试通过；旧真实 unknown 的列表证据不足时仍须保留 unknown。
- 叙述变体沿用真实引用事件时间或明确事后注释写作时间；任意耗时/token 字段仍被拒绝，未发现改写时间戳的路径。既有叙述和变体回归通过。
- 六 Run 全量投影的缺结果调用数依次 1/0/3/0/0/0，无缺调用、无重复配对。缺失的原事件只有 inProgress/exec_started，也没有对应完成回执；无法诚实补齐，保留 N08 风险（替代：下一轮干净复跑保留完整原生会话）。`w1-pairing-before.json`。两个未提交 Run 没有封存包，严格“六个封存包”验收无法满足，将在 W4 以四Run六个真实包和六 Run 投影分别核验。

证据根：`.package-checks/cs-up-13/`；只提交实现、测试和脱敏汇总。

## W2

- 新增 submission_queue 表，实验、轨迹变体、原包重放与收割都通过既有 _perform_submission 的统一准入。默认同账号同题 30 分钟、跨题 30 分钟最多 4 次；队列保留封存哈希、授权与草稿续提身份。到点重检预算、题目存在性和收割窗口；优先发送收割。
- 队列 sending 在重启后转 unknown，不重放。真实 unknown 始终不入队自动重发；只读对账仍保留原路径。已受理草稿的明确 bundle 修复续提保留原 Attempt。
- resultsJson（含 JSON 文本）、scored_by、scoringDetails.source 的不规范回执立即设置 DB barrier、持久弹窗；配置 auto_submission 持久关闭，两个入口暂停，科研不中断。前端恢复通过专门 feature 接口清除 barrier。
- 前端设置可见队列、预计时间、暂停/恢复、三项间隔参数；ops digest 有队列与暂停状态。judge_replica_hint 默认 false。
- fake 后端提交/收割回归 `w2-tests-final.log` 81 passed；设置/功能/新协议往返 `w2-roundtrip.log` 87 passed；前端 `w2-frontend.log` 16 passed；`w2-build.log` 构建通过。这些不是正式 Worker 验证。
- 旧合成协议测试显式配置零等待，继续验证其既有语义；新增 D-64 测试恢复生产 30 分钟策略并推进注入时钟，没有删除或跳过旧测试。
- 有界审查修复了延迟收割触发上下文被回执摘要覆盖的问题；延迟发送仍重新核验原触发条件。

## W3 — 内容、技能和能力事实

输入实际为10个FILE块，全部走系统修订并按用户本轮代审批授权生效；没有捏造第11条。`observed_public_data`规范化为`observed`、`pi`为`brain`、全局`strategy`为`heuristic`，正文保留。15个指定旧ID已active；4个ABC标题精确匹配0项，未批准近似标题。其余候选清单保存在本机`w3-existing-approvals.json`。

新增submission-gate、替换/追加指定skill与提示词、导入参赛过程及可编辑赛道默认模板。全部仓库cyberscientist-*与17个bohrium-*默认注入执行器，受众不再挡掉这些必需技能。116个发现条目及来源、受众、读权限、启用状态见[清单](CS_UP_13_SKILL_INVENTORY.md)。受控dispatcher对17个只读help实际调用：10项有帮助回执；knowledge-base、mentor、paper-search、pdf-parser、scholar-search、sciencepedia、web-search在已装bohr中不存在。替代：已核实的research_lkm/research_web_*接口；没有声称全部API可用。此处验证后台受控分派，未声称已在新科研Run内通过HTTP代理；阶段1禁止科研Run。PI只读文件工具实际读到submission-gate（`w3-pi-skill-read.json`）。

能力清单实时读取目录、预热、机型和授权，<=2000字符，注入PI素材及每个Trial。分诊easy→DeepSeek、medium→Terra high fast、hard→Astra high fast；只标记一道数据齐全且预计最快的简单题，不自动启动。Terra/DeepSeek要求具体工作包。

原生零科研探针：Codex 0.148.0-alpha.15的Terra high fast真实完成，priority被回传确认，106.258秒；它实际读取submission-gate并选择镜像。Astra PI xhigh被服务端400拒绝（需要更新Codex），Astra执行器标准降级仍failed，不据握手声称模型可用。项目内独立0.161.0实际返回一次结构化简报（131.206秒），但技能工具因捆绑权限失败未满足；修正可执行权限后又遇网络路由错误，600秒探针仍超时。未改全局CLI，不能声称PI技能闭环全部通过。替代证据为能力清单/系统只读技能检查和原生Terra回执。

轻量锁定包已装项目.venv；11个模块实际导入累计1.567402秒（同进程顺序导入，非各自冷启动），版本/分项耗时`w3-local-imports.json`。pytest内容/技能/经验/赛道/分诊/PI组77通过（23.89秒）。

## W4 — v8轨迹门

新增九类检查与900 UTF-16字符可见性统计；各项给出通过/风险/无法判定及依据。N17列出代码文件写入信号并对最近100条其他Run提交做代码哈希比较；相同字节可能是通用工具，不能推断题目解答复用。N18只有明确科学成功回执才计数，否则unknown；不把工具成功充当科学计算。缺失证据使用CS-UP-11冻结的18类分类，只列相关项。

按最新1097样本校准快照修正旧63样本分级：所需项只有N11为提示性；N07也为提示性但不是本卡主要检查。N06/N08/N09等旧分级撤回，不用于平台结论；已知v6封顶只能作源码事实，不能当作v8可靠上限。判定不输出预测分。可选复刻开关默认关闭，开启显示54–62%限制；实际复刻仍为独立工具，本包没有预测时明确standalone_only，未接入自动模型调用。

六个真实封存包来自四个Run（另两个Run未提交），均实际检查；不再将“六Run无六个包”误述为没有六包。五包中原始配对数与公开解析器可识别配对数不同：转换未丢选中行/配对，公开解析器会排除无工具名或畸形schema。报告分别保存两个计数与discrepancy，不把这一差异全归为丢轨迹，也不改原包。

|提交|检查状态|选中配对|公开解析器配对|
|---|---|---:|---:|
|sub_2527934c74|ready|206|201|
|sub_db174aa31c|ready|264|259|
|sub_1d1cf9e790|ready|138|138|
|sub_753c90b6e4|ready|19|13|
|sub_442b1b0348|ready|37|31|
|sub_2e9104ed4e|unavailable|unknown|unknown|

独立留出使用24个非空公开轨迹，与CS-UP-11 selected及selection_additions所有ID不交叉，冻结后再取回；结果见[独立留出报告](CS_UP_13_TRACE_HELDOUT.md)。N06一致率58.33%、N09 16.67%，印证不能可靠移植；N08 95.83%主要由阴性组成，未据此提升分级。N11缺产物、N17/N18缺worker可见输入，三项一致率无法判定，是未满足的硬验证项；替代为六个真实封存包的产物/配对/哈希自查。首批24个公开空轨迹保留为覆盖失败，不零填或算作通过。

前端轨迹门和开关可见；14项前端测试与TypeScript/Vite构建通过。后端诊断与提交/评测集完成检查，最终数字见STATUS和w4-final-green.log。原始证据w4-rehearsal-packages.json、w4-heldout-summary.json及冻结输入哈希保存在忽略目录。

## W5 — 材料与 ABACUS

私有材料镜像172212固定五模块版本，实际Job20845219与沙箱退出0；ABACUS官方镜像Job20847482退出0、SCF收敛。首个ABACUS Job因检查标记写错退出1，保留失败后独立修正重跑。两个起点已通过后台不可覆盖登记，沙箱创建成功时间进入runtime_observations；前端读取目录。脚本、版本、赝势来源、哈希和分层耗时见environments/cs-up-13/README.md。

硬验收缺口：ABACUS沙箱两次TLS handshake timeout，没有计算回执。替代为已通过的同镜像Job，沙箱创建成功不代替exec成功。未删除已有资源；新沙箱设20分钟自动到期。

## W6 — CLI只读调查

参赛过程第六节已按安装源码位置逐条填写，核实官方更新清单0.1.39及tarball声明哈希。全局npm安装初始命令unknown。已有ZIP不会被--raw-messages参数重写，原生记录必须在封存前进入；旧error事件转换优先级缺陷明确保留。未修改提交代码、未安装CLI、未做真实提交。

## W7 — 运维与前端

新ops redeploy严格顺序执行安全关机/PID启动tick与cwd绑定/SIGTERM/目标commit核验/启动健康身份/resume/真实preflight/digest，失败停留当前状态。不能覆盖经验的旧目标拒绝；不恢复旧SQLite。测试105 passed（运维、自检、功能、目录）+40 passed（失败停止、设置往返、队列）。103前端测试与构建通过。

真实一致性副本基于6ad9479，SQLite backup保留完整账本、复制全部经验和现有秘密存储；只在副本关闭派发/收割、清除旧Run恢复意图并设置独立端口，变更清单在redeploy-copy-manifest.json。全流程exit0，停机126.685606788秒，总维护142.334019334秒。账号、Bohrium、DeepSeek目录、公开研究工具、协议、经验/skill、代码身份通过；Codex路由、历史时钟和旧镜像创建观察等warn，不能声称全绿。真实复刻提示开关往返恢复，两新镜像目录可读。原后台及历史Run未被恢复。

## W8 — 验证与剩余边界

全量初次1568 passed/3 failed，三项为新默认提示版本和分诊附加字段的旧fixture预期，修正测试使用真实当前版本，不放宽冲突检查；分诊仍核实同一原生会话格式重写两次。最终全量1571 passed、2项既有弃用warnings，933.47秒（final-pytest-green.log）；前端103 passed、构建通过；compileall与git diff --check通过。W0 SQLite quick_check=ok。迁移为新增列/表，W0一致性before.sqlite及关机副本保留；未重建数据表。每阶段有界审查已核实队列身份、延迟收割上下文、原始配对与parser差异、进程身份和失败停止。

硬验收无法完成与替代：输入只有10条新经验，4个ABC标题无精确匹配；已启用实际10条及指定15旧ID，不猜测额外内容。7个bohr帮助命令不存在，用已核实受控研究工具替代。Astra旧CLI被400要求升级，项目内0.161.0收到一次真实简报，但技能工具未成功；后续600秒原生探针WebSocket/HTTPS均网络失败，保留unknown，阶段2仍使用指定模型尝试，不换模型冒充。两Run无封存包，以六Run投影及四Run六包补充验证；缺失原始结果不可补造。独立留出N11/N17/N18没有产物/Worker输入，以真实封存包机械检查替代，不报准确率。ABACUS旧沙箱TLS失败已在网络恢复后以新沙箱真实执行补验，目录新增v2而不覆盖v1。自检warn逐项保留。

## 开赛时前端操作

核对赛道时钟、邮箱身份、模型连接和加载标签；在单题最小闭环看到harbor_worker正式轨迹分前保留提交资格unknown。核对10条新经验及15个指定旧ID，ABC标题缺失仍需来源才能审批。需要恢复自动提交时用设置页专用恢复按钮，核对队列及unknown后再开；复刻裁判提示默认关闭。每次计算前选环境并实际冒烟，镜像创建时间不保证缓存。按参赛过程§6配置官方CLI，unknown只读对账，不能重发试探。

### 网络恢复补验

用户告知断网已恢复后，公开协议与更新清单均HTTP200。项目内Codex0.161.0 Astra xhigh原生探针18.6057秒，实际cat submission-gate退出0并返回结构化规则；不再把旧网络失败当当前不可用结论。ABACUS独立新沙箱create24.039秒、exec11.102秒，原脚本Si SCF收敛、退出0，原生回执有CS13_SI_SCF_PASSED。登记cs13-abacus-v2（Job与沙箱证据），保留v1及两次失败。证据network-restored-public.json、abacus-sandbox-network-restored.json和w5-abacus-v2-registration.json均只留本机。

网络恢复后的完整W3原生补验：Astra xhigh PI30.190933秒，实际只读submission-gate并选择cs12-sci-py-v1、CPU，确认模板和新增经验；Astra high fast执行器25.567871秒，priority由原生线程回传确认。输入sha及active IDs在授权调用账本对应回执内，零科研。项目设置brain executable指向0.161.0，未修改全局CLI配置。此前600秒超时是历史失败，不能继续当作当前不可用结论。

最终边界：历史缺原始结果、4个ABC来源缺失、7项bohr原生命令缺失及独立留出语义不可观测仍保留；新的Astra原生启动与ABACUS沙箱已实际补验通过。fallback-4只证明此提交的实现及所列证据，不证明正式Worker链路或比赛资格。阶段1零科研Run、零真实参赛提交。
