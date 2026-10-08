# CS-UP-14 提交链路证据

仅交付阶段1与2；fallback-4已推送，阶段2只运行一道已结束LiSi题。
项目内官方CLI0.1.39及CLI/API开关已接入，全局安装与配置未改。
全新三相ABACUS弛豫、六输出和包内入口Bohrium重放已有真实原件。
公开科学契约代理两次100/low；它不检查隐藏科学参考，不能称科学100。
首次真实CLI调用未获Attempt ID，unknown预约保留；harbor_worker、正式分数及accept均未确认。
实际封存包本地轨迹检查0/review、cap39；此前另一包36分不能移作最终成绩。
已排查本地包路径、原生转换、CLI环境网络和只读账号列表；原CLI错误详情未保留，不能断言平台永久不可提交。
没有确认实验分，故没有触发收割；保留D-69，不启动彩排二或阶段4。

## W0

D-73原文已入UPGRADE_DESIGN§5；阶段2最多一个Run、2实验+1收割，不启动其他题、彩排二或阶段4。

## W1

官方tarball121215字节，SHA256与latest.json及安装脚本声明一致，版本命令实际0.1.39。解包于忽略目录.package-checks/playground-cli-0.1.39，未改全局0.1.33。AgentMaster只读查看host/submission.py及169个command.json的参数和环境键；不能据本地命令记录声称所有评分有效。原始安装来源/历史Worker环境配置unknown。

真实Terra/Astra/DeepSeek原生日志分别106494/105663/25192133字节，官方转换9/8/902步，工具配对1/1、1/1、423/423；SHA前后不变。旧event流合成反例加一条error，2步变1条error，丢掉执行证据，0.1.39仍有缺陷。原文件不编辑；另一条干净原生会话是替代。CLI新包会加envelope/脱敏，因此系统已有封存包模式必须预先装入原生字节，避免CLI重新打包。参赛过程§6列出源码位置、命令模板和故障处理。

原始转换输出及输入哈希在.package-checks/cs-up-14/conversion-probes.json；没有把原生日志、令牌或第三方原始轨迹加入Git。

## W2

已实现官方CLI一次调用、原生会话绑定与同包封存、实验/收割统一入口、CLI/API持久开关和冻结独立提交上限。CLI临时文件不包含令牌，环境仅向可信子进程传入。未知只读对账且不重发；缺服务器包哈希时不伪造匹配。官方CLI内部同Attempt上传重试行为见DECISIONS。

151项提交/收割/封包/门禁针对性回归通过（103.93秒）；初次收割fixture平台不匹配，修正fixture后通过。设置页16项通过，完整前端104项22文件通过；生产构建、compileall、diff-check通过。后端全量在后台继续，最终结果在W4登记。附加冻结额度投影/HTTP设置测试结果随后登记。原日志保存在.package-checks/cs-up-14，均为fake应用验证，不代替W3真实评分。

W2补验：36项CLI/设置持久化回归通过（46.16秒），包括冻结policy额度对PI可见并实际拒绝超额。阶段有界审查覆盖原字节归属、密钥传播、未知副作用、收割共用入口和回退；修正发送前GET失败须释放未发送预约、CLI响应显式error不得当上传成功。实际平台Worker契约留W3验证。

## W3 实际运行记录（按时间保留）

唯一赛道round_fab7e74ad784，唯一Run run_8a21b7d249，启动2026-10-08T02:28:20.346497Z。原生回执确认Astra xhigh0.161与Terra high fast0.148，priority；Run开始前后端重启总耗时123.698秒（包括安全关机等待，不计入本Run维护停机），旧Run resume_on_startup=0未恢复。单题有效计算授权为unlimited，冻结提交上限实验2、收割1。收割暂关，阈值100。

PI开局#115实测319.066秒、packet345950字节；#108简报明确cs13-abacus-v2、官方ABACUS、三相cell-relax、独立守恒校验、新环境干净复跑及技能；#43–61实际读取七技能，LKM/官方文档有真实GET回执。首个Trial trial_556df04fa9已绑定原生日志。Terra首轮#167称零计算额度，核对原始用户帧实际max_jobs=null/max_sandboxes=null/unlimited_resources=true；模型误读没有发生系统计算拒绝，记录保留。监控仅通过持久指导澄清授权事实；PI自行继续，真实冒烟Job20855311/平台ID23502045运行中。

全量首次1583通过1失败（920.42秒）：旧digest测试全文子串c2碰到随机round UUID，不是业务题目错误；改为行首身份，保留原语义与失败日志。全量复验进行中。

W2全量复验：1584 passed、2既有弃用warnings，885.75秒，日志full-pytest-green.log。真实HTTP设置api→cli往返恢复cli，project executable保留。当前科研原始快照未编辑，官方CLI转换185步、73调用72结果，1调用在途；这是在途探针，不是最终包完整配对或正式轨迹分。

W3根因追加：原生日志的完整授权确为null/true，但紧随其后的旧capabilities.summary又写max_jobs=0、max_sandboxes=0且没有unlimited_resources，提供矛盾事实；因此前述误读有系统摘要诱因，不能全归模型。摘要现在以同一有效授权显示null/true，保留2+1提交上限，完整列目录ID并优先展示已选及最新不同镜像，避免按字母顺序把材料/ABACUS和GPU全部截掉。实际摘要不超过2000字，18项CLI/内容回归通过。运行中的科学输入、评分器与原始记录未修改；仅按正常安全维护部署应用修复，仍只一个授权Run。

本Run已用官方镜像完成Si SCF冒烟Job20855412（平台23502146）到Finished；退出码/产物由执行者继续核实，不能仅凭Finished声称科学通过。指定PP目录不存在与Git源下载失败均保留；后续原点检查需要ASE，正在Bohrium准备依赖。

能力摘要部署真实exit0：停机121.824秒、维护134.645秒，自检warn无fail，代码digest匹配b736e7e、原生close无unknown。恢复的是同Astra/Terra会话，首Trial原生绑定不变。日志见.package-checks/redeploy/38f0e6ccfcc44bba9ef96939e54c1854.json。

恢复检查发现D66观察在相同反馈去重之前执行，旧事故会反复撤销显式恢复。已将屏障放到相同回执去重之后；23项CLI/门禁回归通过（11.48秒），同时验证变化回执仍暂停。旧事故与真实unknown均保留，未因此放宽新异常门禁。

屏障修复2f4948e实际安全部署exit0，停机121.093秒、维护133.944秒，preflight warn无fail，digest代码匹配、native_close_unknown=0；日记1ef269ad203c46a2bb5646471a2a2877.json。仅唯一授权LiSi Run活跃，正常HTTP功能接口恢复auto_submission后无屏障，收割仍关闭、阈值100；未绕过新异常暂停。能力修复版全量1585 passed/2 warnings（874.37秒），屏障版另跑完整回归。

Terra首个完整原生turn #116→#177为97.633002秒（含工具），维护打断的后续turn不编造完整延迟。w3-terra-turns.json保留原生turn ID与事件时间。实际原胞独立核查Job23502265通过，有限SCF试算v1脚本退出127已保留，v2正在运行；尚无最终科研输出、包或Attempt。

屏障修复版全量最终1585 passed、2既有warnings（892.75秒），原日志final-guard-pytest.log；没有删除或跳过测试。前端104项/22文件及构建已通过，后续未改前端。实际有限SCF v2的out.zip与shell日志已取回，日志记录收敛、275秒实际运行、赝势SHA及密度输出；生产候选LiSi cell-relax Job23502296 / bohr20855558正在32核环境运行。上述SCF不是最终弛豫，不据此声明本地科学分、正式Worker、accept或收割通过。W3/W4仍待完成，不打fallback-5。

科研反证与修正：#2523记录PI指导c2754eb957查出首个cell-relax Job23502296全部原子0 0 0，故为冻结原子的受限计算，不能使用为最终弛豫。原作业和输入保留。执行者新建LiSi开放原子v2 Job23502312 / bohr20855574，Li参考23502313 / 20855575，Si参考23502314 / 20855576；#2581列出并行设置。2026-10-08T03:42Z只读compute.reconcile(allow_retry=False)实际收到远端运行观察，没有重建在途操作。

取证入口.package-checks/cs-up-14/collect-w3.py --reconcile（只读远端）/--convert（仅官方转换封存原生快照），输出w3-acceptance-proof.json；当前0提交、0封存包，不推断分数。已完成Terra原生turn墙钟97.633002/900.411656/131.335583秒（含工具），维护打断的turn标not_observed，不编造完成耗时。后续封存包将核对原SHA、Trial绑定及原生日志前缀字节未改。

交付核查：audit-delivery.py在5142173对fallback-4后的25个受控改动文件按现有凭据值逐字节扫描，0命中；.package-checks/cs-up-14无跟踪文件。只输出文件路径/哈希，不输出凭据。该次检查src、apps/web、tests与已全量通过的2f4948e无差异；此后W3发现的续行修复须另跑完整回归，最终报告更新后须重新扫描。

Worker只读可达性：GET http://47.92.88.121:443/api/uploads返回404（2.012秒），/openapi.json和/api/openapi.json也404，没有公开schema可核实；没有发送POST、认证或Attempt。该结果只证明主机响应，不能推断POST是否可用，更不能当评分证据。原记录worker-reachability.json、worker-read-only-schema-probes.json均留本地忽略目录。

监控事实反馈cs14-midrun-ledger-facts-v1已queued：只列当前Job状态、实际开局及D74两小时截止、独立2+1额度和现有功能状态；没有科学答案、代码或降验收指令。D74时钟按Run.started_at连续计算，不能减去维护时间；两小时条件不会替代完整科研/评分/干净复跑要求。

用户补充方案已在2026-10-08T04:10Z持久投递，PI于#3803采纳条件性回退：实际提交经排查和修复仍不可用时，允许以任务科学评分器和本地轨迹检查交付，科学评分仍在Bohrium执行，保留正式Worker和收割缺口。04:10Z重新取得官方latest.json，仍为0.1.39且tarball哈希一致；GET404不作为提交失败证据。

截至04:16Z只读对账：20个Job中10 Failed、6 Finished、4 Running，0提交/0封存包。Li参考23502313归档原生日志实际含`Relaxation is converged!`和`!FINAL_ETOT_IS -392.0781205964211722 eV`，归档SHA256为1bdf4f3f6724e77982b928b049389ce5704f47bad081668cd504a65ac8658432；wrapper时间03:39:00–03:41:14Z，不等于调度/回收墙钟。旧受限LiSi23502296实际停止，归档未含完成终态，数据库通用Finished投影不能据此称弛豫通过。开放原子LiSi23502312、Si23502314、Li收敛23502436与电荷核查23502449继续对账，没有重建在途操作。原始取证留w3-reference-log-proof.json与w3-acceptance-proof.json。

D-74结论已经确定：04:28:32.877504Z（开局后7212.531秒）六项最终产物路径全部不存在，local_scores=0、submissions=0，#4384/4386原生回合完成自述尚无形成能、电压与合金电荷。两小时截止为04:28:20.346497Z，不扣两次维护；保持D-69，不调整默认分诊。证据d74-two-hour-proof.json，科学Run继续。

CLI前置真实只读探针：按产品当前选择逻辑确定实验邮箱及主邮箱，逐个GET /auth/me和完整分页该题attempts，分别13.673/13.861秒成功；当前实验账号0旧Attempt、主邮箱3旧Attempt。没有创建、上传或提交。证据cli-authenticated-baseline-probe.json。04:27:49Z对账中开放原子LiSi23502312、Si23502314、电荷23502469均为Failed，具体科学原因仍待原日志；Li收敛23502468仍Running。监控cs14-post-turn-status-and-cli-baseline-v1已持久排队，提供实际状态与空闲事实，不替代理研究。

## W3 通用续行与新科学终态

实际#5571 Terra回合04:42:46Z结束后，Si23502546于#5769观察Finished，仍有其他Job在途；旧check_liveness因此直接返回，直到监控事实指导#5983才续行。`test_idle_executor_reviews_completed_job_while_other_job_runs`隔离回归在2.87秒失败，调试器确认无忙会话/审阅，只改变另一Job的Running状态就恢复看门狗排队。修复为可信终态事件驱动的一次PI生命周期审阅，原事件序号、Job身份和当前Trial入帧；普通轮询不唤醒模型，unknown不重发。事务内排队和终态序号去重，保护显式等待、现有审阅/指导、门禁和忙会话。25项存活测试10.67秒通过，126项相关回归71.86秒通过；全量和生产部署仍待核实。红/绿/相关日志为idle-job-wake-red.log、idle-job-wake-green.log、idle-job-wake-related.log。

05:06Z从本地归档直接读取原生日志：LiSi23502545含4次SCF收敛、`Relaxation is converged!`及`!FINAL_ETOT_IS -2429.5556910903378594 eV`；其平台失败来自后处理文件路径，归档SHA256 cd5829b3ce201a2b6a07c9ebd5bc98016ba8492eb32263acfb005b38bc4409e4。Si23502546含SCF/弛豫收敛及`!FINAL_ETOT_IS -857.9657519714776299 eV`，归档SHA256 8100e225cf1930698fa0a05bb1b6c6fb65fb6237a6af8774741006c547fc3ac5。这里只读取日志与文件哈希，没有本地科学计算；收敛扫参、密度/电荷校验、四JSON、干净复跑和正式评分仍待完成。证据w3-recovery-terminal-log-proof.json。

本题local_scoring.scorer_manifest在04:47:22Z实际返回SCORER_MISSING（尚无scorer目录），不是已调用后的科学0分。事实已交PI；现有local-scorer技能提供公开契约初建、冻结和prepare_job/register_job可信登记；已有评分器在Run中保持只读，隐藏规则保持unknown，不拿自报数字代替系统或Worker评分。

续行修复8a00b72全量1592 passed、2既有warnings（793.46秒），日志final-idle-job-wake-pytest.log。实际重部署journal 6707b999c1c34ca6ba4cb641107ebccd：基础设施exit0、停机132.311774秒、维护148.260191秒，digest匹配，自检warn无fail、native_close_unknown为空。然而原Run于05:12:34.837741Z失败，#7328记录codex-app-server读取协议ValueError；不能将基础设施成功称为科研恢复成功。

原生读取边界诊断：旧8MiB限制下9MiB完整帧回归实际失败（native-frame-red.log），修复后52项协议/控制器/存活回归通过（28.21秒，native-frame-reopen-green.log）。官方0.161.0生成schema后，以thread/read/includeTurns只读原Astra会话，05:32:21Z成功返回同一线程ID及59回合，序列化result为12,710,137字节、SHA256 4361a0f6c83a69ca804b9d0eaeeac3834baa7eaa3bb9f469fd22269784a3db61、墙钟1.471秒；这是重新序列化字节数，不冒充线缆原帧长度。没有模型turn、修改日志或存储响应正文（native-frame-read-only-proof.json）。新上限64MiB有界，超限明确失败且不重发；保留EOF唤醒。runtime_error限定reopen的红回归原INVALID_STATE，绿回归保留同一Run/原授权时钟/未知Job/失败事件，其他failed仍拒绝。完整回归及实际恢复另录；当前科研评分、干净复跑、CLI提交仍未完成。

部署c8c1e7f实际成功：journal 0652b67488104fcd9eff45abf4c97f23，exit0、停机123.299064秒、维护137.720778秒、自检warn无fail、digest代码匹配、native_close_unknown=0。正式控制接口05:36:48Z重开并恢复原Run；恢复前后对比同题Run数1、原授权auth_ae6a3df3f6、started_at、33个Job身份/状态、0提交及#7328失败事件均保留（native-frame-controlled-recovery.json）。#7387于05:37:00Z确认原Astra/Terra线程ID，#7390开始PI recovery审阅，不承诺IPython内存恢复。另64项Codex/协议漂移/安全部署/digest回归42.30秒通过；新增修复完整回归仍在运行。科研、评分与提交未因此宣称通过。

c8c1e7f完整回归结果：1596 passed、2既有warnings、1003.60秒，final-native-frame-pytest.log；native-frame-test-source.json的五个关键源码/测试哈希复核一致，后续仅报告修改。前端自104项测试及构建通过后无代码变化。05:38:55Z直接核对23502561回收的app/outputs六项文件及各SHA，public_contract_validation.json实际为PASS/issues=[]；只证明六件文件与公开契约，科学分和干净复跑仍未验收（candidate-six-files-proof.json）。PI #7431/7432在同Run启动承接Trial trial_de05641608，沿用原Terra会话、原授权及累计2+1额度；新环境冒烟首版失败保留，修正版23502592实际运行中。截至05:49Z，local_scores=0、submissions=0，不能提前宣称评分闭环。

恢复后原生日志转换补验：05:53:38Z取原Terra日志当前完整字节快照12,115,596字节（SHA256 aabce7510161963b22d3dfc6d4b06bee700a5d7999f84f19460d99b74f76c9bc），官方0.1.39在无认证临时HOME转换exit0，共1370步：observation18、thought224、tool_call564、tool_result564。临时快照字节及原文件相同长度前缀均未变化，没有过滤错误、切片或拼接。原会话仍在执行，因此不据此宣称最终工具全配对、最终Trial封存或正式轨迹分；封存后须按真实包再检验（active-native-conversion-proof.json）。承接Trial新环境冒烟23502592已Finished，23502607收敛诊断仍Running，评分记录与提交仍为0。

收敛对照新回执：23502607随后Failed，PI核对原日志为SCF前phase变量未定义；修正版23502608 / bohr20855867在06:05:11Z实际只读远端对账Running。06:09:02Z回收wrapper日志780字节、SHA256 312e426b6e08226440374699ebb941cc88e831c08bf83c5f381440084ba02763，实际包含Li_100Ry、Li_120Ry、Si_100Ry、Si_120Ry四个FINAL_ETOT标记（live-cutoff-markers-proof.json）。两个LiSi点与全部独立SCF日志尚未回收，因此完整收敛结论仍unknown。提前下载的JOB_FILES_EMPTY只记录retrieval_failed，不代表远程计算失败，也没有重复提交原操作。

06:22:26Z，23502608已实际Finished（#10225，平台spendTime1380秒）；原归档23,535,737字节、SHA256 14de774e66bd2e9e537152a2247de1d15fd85886da85e6b521f89dfbe595aacc。独立读取六个running_scf.log，均有ABACUS原生`#SCF IS CONVERGED#`和FINAL_ETOT，六个chg.cube、INPUT/KPT均存在（static-six-terminal-archive-proof-v2.json；v1误查其他软件的英文收敛短语，旧探针与原件均保留）。这是固定最终几何的100/120Ry静态诊断，不是新cell-relax或干净复跑。23502646 / 20855908实际Bohrium后处理JSON给出形成能−0.40968212392795067/−0.4096656762675934 eV/f.u.，对应电压0.40968212392795067/0.4096656762675934 V；只读取远端JSON，没有本地科学计算，尚非系统登记科学分（remote-static-energetics-proof.json，归档SHA256 056cf390643cab82153d2bbdf47084714a859f371b9e7d9002f41ce613298f8b）。执行器口头能量差声明待单位/归一化审计，不将其直接当验收结论；独立审计23502648 / 20855910已接受并调度。

续行修复的真实验收：#10256于06:23:08Z确认执行器回合结束；另一后处理Job23502646在#10242仍accepted。控制器#10258于06:23:14Z引用终态#10225自动排队一次job_result_available，#10260于06:23:15Z启动PI生命周期审阅。06:29:36Z复查同terminal_event_seq排队计数为1，原操作未重发（idle-job-wake-production-proof.json）。该场景实际覆盖“一个Job终态、另一个在途、执行器已空闲”，不再仅有fake回归证据。本次完整Terra回合包含计算等待共2422.799394秒；纯模型响应延迟未单独测量，不能用此数值冒充纯推理耗时。

23502648审计在第一份日志因正则转义失败，原始记录保留；修正版23502658 / 20855921已Finished。06:45:20Z直接读取Bohrium日志中的JSON：截止差Li −0.07635134701899915、Si −0.004427028585496373、LiSi −0.03216535762362582 meV/atom；形成能差0.016447660357243876 meV/f.u.。先前执行器口头Si −4.43与这份远端数值不一致，未作为验收依据；数值由Bohrium计算，本地只读JSON和哈希（audit-v3-live-numeric-proof.json，日志SHA256 01cfd72c65b0474688e16c4df55638b5057042daf4660a6d5d029055d840d927）。完整电荷/映射判定及k点/展宽对照仍另验。

06:36Z实际再查scorer_manifest仍SCORER_MISSING、local_scores=0、submissions=0。监控把连续墙钟和原赛道截止、原2+1额度及剩余硬性验收事实经cs14-halfway-required-gates-facts-v1持久送PI，没有科学代码或答案；PI #11493采纳并安排在当前Trial并行补验证、可信评分、新沙箱复跑与第一提交封存，#11634于06:46:02Z已送达执行器。该事件证明指导送达，不证明尚未生成的评分/复跑/包通过（halfway-required-gates-guidance.json）。

### 当前科研验收账本（09:12Z）

|环节|已实际核实|尚未验收|
|---|---|---|
|全新三相复跑|新沙箱06:46创建，06:52开始实际重新运行；74个回收文件bytes/SHA与受控传输回执逐项相符，三份原生日志含SCF/Relaxation is converged!|完整设置与全部收敛维度仍须分开审查|
|六项新输出|23502801 Finished；六文件+独立验证JSON全部与原归档SHA相符，归档77c757b9…7397|官方隐藏参考误差未知，非科学100证明|
|截止能对照|23502608六点终态；23502658独立数值单位已核实，Si截止差−0.004427028585496373 meV/atom|不能据截止收敛推出k点/展宽/密度网格全部收敛|
|几何/电荷独立验证|23502801的原始JSON：三相cube/STRU映射通过，周期全空间Voronoi分区逆序原子差0，总电子数残差真实保留|双网格原始日志已补验，k点仍有缺口；执行者报告Si k8→k10约−5.655 meV/atom，未达约1 meV内部目标|
|科学评分|公开候选b25679e…ef8365固定；监控/执行者真实Bohrium各登记public_contract=100、low；执行者Job23507438|代理不能替代官方、隐藏参考或全部科学有效性；占位轨迹预测不用作验收|
|原生封存/轨迹|凭据误报已修复；3d5bdeb8…74f2实际只读封存通过，官方缓存schema valid，完整30,407,474字节原件未改|最终轨迹门、正式CLI上传/Worker评分和收割尚未验收|

清洁输出的Bohrium原件记载形成能−0.40966867032834386 eV/f.u.、嵌锂电压+0.40966867032834386 V、LiSi残余压力0.135078 kbar、最大力0.003918 eV/Å。电荷方法为周期最近原子Voronoi全空间分区、并列边界等分，Li/Si分别3.2424932073301336/3.75751675108192电子，公开定义下transfer分别+0.24249320733013358/−0.24248324891807993电子；不将该方法结果解释成隐藏Bader参考。上述数值直接抄自远端JSON，本地没有执行科学计算。fresh-independent-science-remote-proof.json记录独立JSON SHA ab2e1b9b…3b7；原始几何、电荷网格、能量定义和未收敛项不因契约通过而豁免。

## 缺失评分器的权限冲突与一次初始化

2026-10-08T06:55:59Z，官方原生0.148 command/exec按实际执行器workspace-write策略探测两个唯一空目录：Trial下可创建并删除，workspace/challenges下被errno30拒绝。探针未启动模型回合、未改实际评分器或原始会话，两个目录均已清除。原件`scorer-write-scope-native-proof.json`及脚本留本地忽略目录。

新增受能力令牌保护的initialize动作：执行器在当前Trial编写公开规则草稿，后端仅验证和冻结源字节、source_directory及文件哈希，不执行科学代码。已有评分器（含空目录/链接）、历史初始化或评分记录不可覆盖/删除后重建；越界、链接、凭据、非当前Trial、关闭门、重复操作冲突均拒绝。冻结后的科学评分沿用prepare/register可信Bohrium通道；本地候选标尺不能声称官方科学分。原缺失事实和科学自校验仍保留。相关57 passed/24.65秒，初始化/API/技能25 passed/6.16秒（2既有warnings），全量回归与实际部署尚待完成。

d471686已推送main并安全部署，停机124.972829604秒、维护137.547986269秒；preflight warn无fail，digest实际loaded=checkout，native_close_unknown=0。#13135于07:08:13Z恢复原Astra/Terra线程及Trial，原started_at未变；指导cs14-scorer-initialize-available-v1仅queued，不能提前宣称使用。新沙箱Li原生exec回执含Relaxation is converged!/FINAL_ETOT及压力，原回执SHA和8条标记留clean-li-raw-terminal-proof.json；Si仍运行、LiSi未开始，完整复跑待验收。

新初始化源码全量1610 passed、2既有warnings（816.05秒）；5个测试冻结源码哈希复核一致，compileall/diff-check通过。范围审查：API身份来自能力令牌，当前活动Trial和门禁、源路径/链接/凭据/大小、一次冻结、原评分器只读及失败清理/操作冲突均受测；没有新增科学实现或改变既有标尺。PI #13871于07:17:45Z采纳入口，尚无初始化/科学分，不据指导声称验收。

07:24 checkpoint实际投递guidance_649336ff10，随后acknowledged；初始化仍待执行。07:25 Si新沙箱原生exec回执含三个完整SCF步、对应压力23.208648/−15.207451/−0.019365 kbar、Relaxation is converged!和最终能量−857.9657600601652803 eV；clean-si-raw-terminal-proof.json保存原回执SHA及标记。LiSi已开始但无终态，尚不能宣称完整干净复跑或科学出分。23502690实际Failed/143，原件保留并待诊断；0提交/0收割。

初始化真实调用#14274/#14280/#14287均在清单验证拒绝，未冻结；原通用反馈误称远端副作用unknown，执行器停止盲重试。API回归0.85秒复现后，只对initialize的受控拒绝明确none及原操作ID，其他执行unknown不变，技能补整数1示例。71项相关回归28.78秒、16项初始化/unknown保持回归7.55秒（2既有warnings）通过；新源码全量进行中、实际部署待验。草稿仅作公开低置信度契约代理，不解释成完整科学正确性；实际科学自校验另取Bohrium原件。

1e026d8已推送并于07:51安全部署，停机123.598986783秒、维护136.514518152秒，preflight warn，digest匹配、native_close_unknown=0；#14569恢复原Astra/Terra线程。fixed-draft-manifest-validation.json记录只读清单验证及真实源哈希，没有执行科学代码或冻结。新指导cs14-scorer-validation-no-remote-effect-fix-v1已queued；仍0评分/0提交。

反馈修复1e026d8全量1612 passed、2既有warnings（941.11秒），5个冻结源码哈希复核一致，compileall/diff-check通过。全新沙箱受控取回74文件逐一bytes/SHA256一致，Li/Si/LiSi三份未过滤running_cell-relax.log均含SCF与Relaxation is converged!，最终原文标记与文件清单留clean-three-phase-raw-files-proof.json。这只验收新原件/三相弛豫终态，独立几何/电荷检查、最终六输出、评分和提交另验。07:55原生重试后16,808,089字节快照经官方0.1.39转换2145步，867调用/866结果（一个在途），输入快照和原日志前缀未改，active-native-after-retry-conversion-proof.json留证；不当最终轨迹门结果。

08:05:19Z #16079首次成功初始化（trial_de05641608_initialize_public_proxy_v4），固定版本b25679e12141b492c5af029801105c6336ed547280d901dc0678cbe009ef8365；三文件哈希与初始化回执逐项一致，scorer-initialized-production-proof.json留证。COVERAGE明确直接公开契约、独立科学验证及隐藏评分unknown的范围；public_contract=100不等于科学/官方100，原评分器不能改写。清洁输出Job23502801 Finished，六要求文件和独立验证JSON与原归档哈希逐项相符，fresh-six-output-files-proof.json记录归档SHA和各文件SHA；登记科学分、轨迹门、CLI仍待验收。

## 原生凭据误报的真实修复

CS-UP-14 W3 原生凭据误报修复：实际成果包3d5bdeb8…74f2的封存被ValueError拦截；原日志精确已存密钥匹配0，展示脱敏器误匹配task-specific中的sk-、供应商reasoning密文字段和公开YOUR_BOHR_ACCESS_KEY/Bearer省略示例。现按原生JSON语义分类，只忽略供应商reasoning.encrypted_content的形状匹配，已存密钥在整个原文及编码中仍拒绝；用户同名字段不豁免。原始字节不变、不脱敏、不截断；CLI同用此分类，封存失败返回有界脱敏真实原因。真实28,063,693字节原始快照保留，成果包只读封存成功19,451,843字节/1347投影步（native-privacy-actual-snapshot-proof.json、native-privacy-seal-preview-proof.json）；这不是提交/分数。53项相关回归16.14秒通过；完整新源码回归进行中。检查仅改原生分类/错误呈现，评分规则、科学源码、原时钟/2+1额度及unknown不重发保持。

W3修复生产验收（d21d708 CS-UP-14）：安全重部署completed，停机132.608秒/维护145.627秒，preflight warn，digest loaded=checkout、native_close_unknown=0。原Run/Trial/started_at保持，#20141 recovery审阅已启动，cs14-native-privacy-classifier-fix-d21d708-v1持久queued。实际只读封存19,724,468字节/1412投影步、完整native30,407,474字节，官方缓存schema valid且CLI文件准备通过（native-privacy-schema-preview-proof.json）；没有POST/分数。新源码全量仍在运行。

W3密度网格真实验收：23503322/20856555 Finished，归档c0547748…271c1与STDOUTERR哈希留density-grid-remote-proof.json。直接远端JSON给出90³→96³平均分区电子差Li −0.0002862553858209438 e、Si +0.0002031416088872362 e；总电子残差+0.0006046227565548179/−0.000060287458907737346 e。三个输出JSON因未登记backward_files没有作为独立成员回传，完整内容与SHA在未过滤STDOUTERR中保留，不能声称已独立下载文件。实际轨迹门#20698拒绝源包内保留traces/trace_narrative.jsonl路径；这区别于先前不带narrative的只读schema探针。执行者修正版23506181已Finished，最终预检/评分/CLI尚待验收；原包、失败23504906和原日志保留。

W3/W4原生修复完整复验（d21d708 CS-UP-14）：完整1624 passed、2既有warnings，887.50秒（native-privacy-full.log）；4个冻结源码/测试哈希逐项一致，前端与已验证版本无差异，104项前端/构建既有通过仍适用。53项相关回归、compileall/diff-check与34改动文件凭据字节扫描0命中/0原件入Git已通过。该全量只证明应用回归，不证明科研或真实CLI完成；Run仍在原截止前继续评分与提交验收。

## 实际阶段耗时（可重叠，不相加）

以持久事件recorded_at或原始wrapper时间为界；Job预约至首次观察终态含调度/轮询，不冒充CPU或模型推理时长。首次真实CLI调用发生于10:14:23.188Z，距Run开局7小时46分2.842秒；上传、远端Attempt创建及首次成功提交时间仍UNKNOWN。

|环节|真实边界/耗时|限制|
|---|---|---|
|PI冷启动|319.066秒|#115，已含简报/工具过程|
|首次环境冒烟23502045|02:37:40.991→02:39:51.643Z，130.651秒|实际Failed，不是环境通过|
|有限SCF修正版|wrapper03:25:22→03:29:57Z，275秒|实际电子收敛，不等于三相弛豫|
|六点截止对照23502608|05:55:31.325→06:22:26.146Z，1614.821秒|首次观察Finished，原日志另验|
|新环境三相弛豫|wrapper06:52:39→07:40:59Z，2900秒|原日志SHA留clean-rerun-runtime-timestamps-proof.json；Li06:55:06、Si07:24:49、LiSi07:40:59Z|
|六输出独立组装23502801|08:00:51.259→08:04:39.143Z，227.885秒|首次观察Finished，六文件哈希另核|
|首ARM/v3构建|192.194/230.474秒|不含后续封存/叙述失败修复时间|
|实际双网格审计23503322|192.987秒预约至首终态；平台执行132秒|完整远端日志和残差已留证|

其余完整Terra回合含工具等待时间在w3-acceptance-proof.json逐条列出；维护打断回合标not_observed，纯模型响应延迟UNKNOWN。runtime-phase-observations.json保留每段起止事件及当前/首次终态区别，不把停止作业的原始SCF终态和平台Failed混为一谈。

W3嵌套文档占位符误报修复（本提交 CS-UP-14）：#22923完整封存再次拒绝，不能沿用旧探针成功；原日志35,295,895字节精确已存凭据命中0，唯一形状匹配为公开BOHR_ACCESS_KEY占位符后接字面转义换行/python3，ENV正则把它们合成一个值。0.43秒红回归复现；仅将转义边界作为赋值值终止符，未知真实赋值和已存凭据仍拒绝。54项相关回归15.78秒通过；实际35,782,930字节完整快照现在通过、耗时4.502秒/SHA991357bf…8461e（native-nested-placeholder-actual-proof.json），原文未改。新源码完整回归进行中，尚未部署/提交。另执行者实际轨迹检查admitted，但正式评分仍unknown；原失败/草稿保留。

W3新修复生产验收（d512eab CS-UP-14）：安全部署completed、停机141.033秒/维护154.865秒、preflight warn、digest匹配且native_close_unknown=0；同Run原时钟保留。真实完整preflight source3d5bdeb8…74f2通过error_code=null/admitted，封存20,949,873字节（native-nested-placeholder-full-preflight-proof.json）。本地public_v6_deterministic检查表36/review、762工具配对、N11风险、N17/N18 unknown，v8-advisory-1不预测分数；artifact路径声明因评分器无verified input-path声明为unavailable，不误作输出缺失。新指导已queued，科学登记评分/真实CLI仍未验收；全量新源码进行中。

W3监控独立评分操作（本提交 CS-UP-14）：在现有当前Trial内，通过既有executor_scoring.prepare/channel=job冻结已初始化公开候选b25679e…ef8365，受控compute.submit实际accepted Job23507427/Bohrium20860659，操作cs14_monitor_frozen_public_score_v1_job，10分钟上限、c2_m4_cpu、已冻结声明镜像。没有修改科学/评分源码、原始native或扩展Run/提交额度；local_score.monitor_execution_requested明确来源controller，不冒称Terra原生执行。实际终态及register_job可信评分尚待验收，当前未声称分数。

W3/W4当前源码完整复验（d512eab CS-UP-14）：完整1625 passed、2既有warnings，880.09秒；4个冻结源码/测试哈希一致，前端未改、104项与构建既有通过仍适用，compileall/diff-check与34文件真实凭据扫描均通过。监控评分23507427 Finished，经register_job核对系统固定命令/输入/镜像/回执后，10:00:33Z登记ls_87fbad7fd37e，score_source=executor_verified（通道历史名称，实际操作者controller另记事件）。数值100仅public_contract公开代理，不是官方/隐藏科学100；trace-placeholder-v1的predicted_display_score100不作轨迹验收依据。本地实际public_v6检查表仍36/review、N11提示，尚无正式Attempt。

W3执行者真实重放/评分验收（本提交 CS-UP-14）：v8候选源SHAf7c45651…921d5，补入原Trial可见科学脚本后，23507424/20860658 Finished，真正从包内密度重跑入口；未过滤日志SHAa0b4bfff…d68e，回传replay_comparison.json pass=true/mismatches={}。六项要求输出哈希同时匹配清洁原件、v8 ZIP及远端重放；附加independent_validation.json新SHA不同，未声称七文件相同（v8-entry-replay-actual-proof.json）。Terra随后通过原生工具执行冻结评分Job23507438/20860672，10:01:11Z可信登记ls_c78bde13a6ae，公开契约代理100/low，非完整科学/官方100；与监控先行评分分开归因。#25985已请求trial_complete提交前审阅，尚无正式Attempt。

## W3 唯一真实CLI调用及排查结果

同一Run `run_8a21b7d249` 从02:28:20.346497Z连续计时；原轮次截止10:28:07.166031Z，没有扣除断网或维护时间。科学生产Trial为`trial_de05641608`，两个后续Trial `trial_6d593e0e0a`、`trial_04dc15406d`只承接交付，均属于原Terra线程。它们不能冒充重新完成科学计算的干净Trial。`stage=trial_complete`按设计触发生命周期审阅，曾两次造成交付转Trial；提交前审阅应使用`stage=progress, review=async/blocking`，由PI明确请求提交。

|时间UTC / 事件|实际结果|边界|
|---|---|---|
|10:11:00 / #26155|授权指导的自动发送先因当前Trial缺少canonical package.zip报NOT_FOUND|发生于本地路径解析，尚无预约或平台调用；通用修复反馈误标unknown|
|10:13:53 / #26250|监控核对实际失败代码、零提交/零远端操作与硬链接同SHA，通过正常提交API使用原`auto-guidance_23433e6039`修复|使用已有PI提交授权，没有绕过门禁或重放未知远端调用；原失败记录保留|
|10:14:00 / #26251|本地`sub_ccc1b19416`及实验预约创建|本地记录不等于远端Attempt|
|10:14:23.165 / #26253|实验账号身份和完整分页baseline成功，旧Attempt列表为空|只读认证及列表成功|
|10:14:23.188 / #26254|官方0.1.39 CLI实际被调用一次，create_sent|距开局7:46:02.842，不等于成功上传时间|
|10:14:25.879 / #26255|CLI未返回可确认上传回执，status=unknown，platform_ref=NULL|未知是否创建远端Attempt/上传；没有harbor_worker、轨迹分或判定|
|10:18:27|相同封存包官方dry-run exit0，转换3350步，sealed/native字节不变|无凭据、无网络请求、无Attempt；只验证离线处理|
|10:19:29|相同Node/CLI环境公开GET HTTP200|只证明当时读取网络可用，不能定位原POST错误|
|后续只读完整分页|absence_observed，candidates=[]、matches=[]、retry_allowed=false|列表没有新增不是权威未存储证明；不释放unknown预约、不重发|

原生产代码丢弃CLI返回码/stderr，首次调用的具体上游错误无法追溯；不得推断为403、Worker404或确定不可能提交。新修复保留有界脱敏退出诊断，但不能补造旧证据。另修复`poll_scores`引用未导入BohriumPlaygroundPlatform、被异常捕获后跳过对账的问题；对应红回归实际2 failed/0.64秒。实际读取对账已通过显式现有reconciler完成，返回空列表仍保留unknown。

当次原件仅留本地忽略目录：`first-cli-local-path-repair-proof.json`、`first-cli-submission-result.json`、`first-cli-readonly-reconciliation.json`、`first-cli-offline-dry-run-proof.json`、`cli-node-readonly-network-proof.json`。原始CLI stderr未保存是一项证据缺口，不以修复后的fake输出冒充真实旧响应。

### 实际同一封存包与最终轨迹

|身份|SHA256 / 实际内容|
|---|---|
|v8科学源包|f7c45651b2b94106814784b510db11c70fb5b527993e1e9fbf4bb63fff2921d5|
|实际CLI封存ZIP|6e1a39f9de5ce6b9639675774ffd460116d75263bbace66c025ae969586bee97；21,238,386字节|
|完整Terra原生记录|197ecbfc45fc65ffc4a94f95cdc46ddd059901f0ea8047b4d384258b2fe257c9；38,149,791字节；与原日志前缀逐字节相同|
|ARM指针所选轨迹|traces/cyberscientist_merged.jsonl；56行、8工具配对；SHA fe26d4664ea4a703654fc7db7d72882f4773a495823fc93e5bfeddc4382c1f5e|
|本地公开v6检查|0/review、cap39；N06/N09/N10/N11触发，其中N11为indicative，其余相关v8对应关系不足，不能当官方扣分码|
|v8-advisory-1|conclusion=risk；N17/N18 unknown；score_prediction=null|
|官方v8|科学分、轨迹分、判定、扣分码、缺失证据及missing_worker_submission状态全部UNKNOWN|

证据`first-cli-sealed-native-proof.json`与`first-cli-sealed-trace-diagnostic.json`来自实际被CLI读取的封存字节。完整原生转换3350步与ARM所选56行是不同输入；承接Trial的投影没有展开科学生产Trial，存在真实证据可见性风险。此前3d5b源包的36/review只是较早候选，不能覆盖这次0/review；评分脚本的trace-placeholder-v1 70或predicted_display100也不作验收。没有改写原生日志、替换已封存字节或择优汇报。

后续处理方案：保持未知提交只读对账，先查平台是否有同包哈希权威记录，再决定后续授权内的动作；开赛前在新产物形成的同一Trial连续完成科学执行、入口复跑、证据核验和提交前审阅，避免只交handoff投影。本轮原截止及unknown不重发保护不允许以再次创建Attempt来试探。第二实验未执行，收割未执行：没有已确认实验分，不满足真实收割前提；阈值从未下调，当前仍100。没有拿到正式accept或轨迹≥60，D-74两项条件均不成立，保留D-69。

### 科学验算的范围和剩余风险

清洁三相、结构/对称性、能量/电压、全空间周期Voronoi守恒及90³→96³网格对照有真实Bohrium输出。六要求输出在真实包内重放中逐项SHA一致。它们是实际计算和有限自校验，不证明隐藏参考一致或全部数值收敛。Si k8→k10约−5.655 meV/atom未达到约1 meV内部目标；Li展宽敏感性+1.652239 meV/atom；LiSi k6补验失败/不完整；元素逐原子电荷差异、截断能与网格联合改变而非独立网格控制、ABACUS E0未提供等限制保留。电荷是公开允许的周期Voronoi定义，不解释成Bader参考。

公开候选评分器没有官方隐藏参考，其authority=`local_candidate_not_official`，两次100/low仅为public_contract结构契约。监控Job23507427与Terra原生Job23507438分别归因，只有后者使用v8科学源；正式科学正确性UNKNOWN。按用户允许的替代方向，交付上述实际科学原件/自校验和本地轨迹检查；不宣称满足原硬性Worker验收。

完整Terra回合已观察22次，9.150–2541.632秒，包含工具和远端等待；另5段被维护打断、没有完整结束观察，纯模型响应延迟UNKNOWN。逐回合及PI耗时在`w3-acceptance-proof.json`，不把这些墙钟时长当模型推理速度。

## W3 终态、设置恢复与修复审查

#26375于10:28:17.979Z确认Run finished/end_reason=authorization_expired，ended_at=10:28:17.972237Z；调度观察较轮次截止晚10.806秒，没有延长授权。累计Job69个（36 Finished、33 Failed）、本轮唯一新沙箱已删除，无本轮在途Job；失败与unknown原件完整保留。没有删除用户原有Bohrium资源。历史其他Run不属于本卡，没有把它们恢复为新增科研。

10:31:12Z经Settings API按revision22→23恢复临时Terra选择、执行器路径、DeepSeek fallback与实验提交授权/目标范围；默认执行器恢复原Sol配置，D-69保留。原空fast/provider按全局fast=true、provider=codex显式表达，API拒绝null的第一次恢复请求返回422且没有保存。CLI默认/项目路径是本卡交付保留项；local_calculation=false服从AGENTS的Bohrium-only边界；auto_harvest=false在真实CLI/Worker未验证前继续保留，不能盲目恢复自动主邮箱投递。阈值实读100，原Run授权/started_at/config_snapshot逐字未变，未知提交预约保留。证据`w3-settings-restored-proof.json`。

本阶段有界代码审查：CLI只增加失败可观测性，先对整个输出做形状/当前实际凭据/本次令牌脱敏，再截4000字符/字段；stdout仅诊断，不冒充回执，异常仍unknown、不再次调用CLI。轮询仅补导入使既有只读reconcile执行，不放宽匹配/重发。相关命令`.venv/bin/python -m pytest -q tests/test_cli_submission_cs14.py tests/test_native_log_privacy.py tests/test_tool_feedback.py`实际33 passed/46.20秒；skills检查11 passed/15.01秒；compileall与diff-check通过。新源码完整1627 passed、2既有warnings、886.60秒（cli-live-diagnostics-full.log），4冻结源码/测试SHA一致；前端无改动，不重复用构建替代后端测试。

## W4 验收核对

|要求|结论|直接证据或替代|
|---|---|---|
|W0 D-73|已实现|UPGRADE_DESIGN §5、9ab5cf9|
|W1 官方CLI与来源|已实际验证|0.1.39版本/latest/tarball哈希、9e2a0ab；历史安装来源unknown|
|W1 三模型原生转换|所测样本通过；旧error缺陷未解决|9/8/902步及原SHA；实际封存原生3350步，原字节未改|
|W2 实验/收割CLI、保护与开关|应用测试/HTTP往返验证通过|8a2d652及后续回归；fake收割不等于真实收割|
|W3 单题/单Run/指定模型|已实际验证|唯一run_8a21b7d249、Astra xhigh fast/Terra high fast；原线程/时钟及2+1额度保持|
|W3 科学/评分/干净复跑|部分通过|新三相/74原件、六输出和v8入口Bohrium重放；公开契约100/low；科学收敛和隐藏参考缺口如上|
|W3 最终本地轨迹门|未过|实际封存包0/review、cap39；风险提示不能预测真实v8|
|W3 CLI/harbor_worker/正式轨迹和判定|硬性验收未满足|真实CLI一次、unknown预约1；0确认远端Attempt/正式分数。已排查并补错误诊断与对账；不能证明永久不可提交|
|W3 D-74|不启用|两小时首版未交，最终无官方accept/轨迹≥60；保留D-69|
|W3 CLI收割/阈值|硬性验收未满足；阈值保持100|没有确认实验分，不触发真实收割；应用fake路径通过不作真实证据|
|W4 完整测试/前端/构建|当前源码通过|aaa4133：1627 passed/2 warnings/886.60秒，4冻结源码/测试SHA一致；前端104 passed/22文件/19.64秒及构建通过，无后续前端修改|
|W4 密钥与原始证据|最终字节扫描通过|改动字节与当前真实凭据比对0命中、0本地原件入Git；原件仅留本地忽略目录|
|W4 报告/过程/fallback-5|实现与证据交付；正式链路缺口保留|报告/回退文档已更新；fallback-5作为代码基线，不宣称Worker验收通过，标签推送另录|

阶段1完成复核：远端lightchaser-fallback-4剥离到ad9bb076128815f543a8519c10db4ca9b47c1038；授权调用账本实际模型15/20、私有镜像构建1/6、Job3/10、沙箱4/15；交付清单12个核心证据文件哈希全部匹配（stage1-completion-recheck.json）。该阶段无科研Run和参赛提交；缺失经验、历史缺结果和留出不可观测项保留在CS_UP_13_FIX_EVIDENCE，不能把标签解释为这些缺口消失。

## 最新范围与链路实测

用户最新指令为“把提交链路打通就停止吧，不用继续了”。后续仅定位/验证提交链路，不再推进科研、收割、彩排二或阶段4。

代码aaa4133安全部署completed，停机146.336秒、维护180.924秒，preflight warn；digest loaded=checkout=aaa4133、matches=true、native_close_unknown=0。生产#26377/#26378真实cli_reconciled仍absence_observed，只读修复已执行。Node同凭据和API base真实GET /auth/me HTTP200、身份匹配；题目status=open，实验agent operatorConfirmed=true，排除了当时读取认证/身份错误；这些都不能证明创建POST/Worker上传成功。原始失败详情缺失与unknown预约继续保留，不将应用回归1627通过写成真实提交链路打通。

进一步只读核查：10:47:45Z全局author视图返回该实验账号10个历史Attempt，最新为10-07，没有本题10-08的新记录；题目完整分页同样没有匹配。10:49:54Z对真实官方CLI和同一封存字节执行网络拦截预演，唯一请求为正确中央题目POST、带认证、multipart4822字节；fetch在发送前一律中止，没有新增Attempt/网络投递。该探针仅确认本地预处理/请求构造，不复现未知的上游错误，CLI的通用“无法连接worker”文案也不能定位中央POST与Worker步骤。原件cli-global-author-readonly-proof.json、cli-shadow-create-request-proof.json保留在本地。

当前阻塞事实是：首个真实create_sent没有Attempt ID或可恢复的上游错误详情，完整列表无新增仍不能证明权威未存储。没有改写状态、释放预约、延长原轮时钟或通过第二次相同投递试探；后续只可在出现可核对远端记录/权威创建失败证据后继续对应操作。科研和其他阶段已停止，真实提交链路尚未证实打通。

## 开赛时监控要注意什么

先在单题获得真实harbor_worker轨迹分及判定，再按参赛过程分批启动其他题。以实际事件recorded_at和原始远程回执计算时间，不把手写checkpoint名称中的时间当时钟。科研超时、中间电子迭代和通用Finished投影不能代替弛豫终态；干净复跑必须重新验收真实文件与结果。原始会话不修改；转换失败时以新Trial产出完整执行证据。遇missing_worker_submission或非标准回执仍按D-66暂停新提交，unknown只读对账。正式链路经实际修复仍不可用时，按本轮用户补充要求明确交付科学验算和本地轨迹诊断及其来源，保留官方评分、accept和收割的缺口。
