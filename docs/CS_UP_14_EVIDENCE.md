# CS-UP-14 提交链路证据

阶段1的fallback-4已推送，阶段2只验证一道已结束LiSi题。
已取得并校验项目内官方CLI0.1.39，全局安装与配置未改。
已复核三种模型真实日志可转换，旧error事件转换缺陷仍存在。
不编辑原始记录，保留失败；全新三相弛豫及六输出原件已验，评分仍待验收。
提交链路与真实Worker验收将在下文按实际结果追加。

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

## W3 进行中

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
|科学评分|08:05首次固定公开候选b25679e…ef8365，三文件哈希匹配；仅可在Bohrium执行|当前无已登记分，public_contract代理不能替代官方或全部科学有效性|
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

## W4 验收核对（进行中）

|要求|当前事实|直接证据或剩余步骤|
|---|---|---|
|W0 D-73|已实现|UPGRADE_DESIGN §5及9ab5cf9|
|W1 官方CLI与来源|已验证|0.1.39版本、官方latest/tarball哈希、9e2a0ab；历史安装来源仍unknown|
|W1 三模型原生转换|已验证所测样本|9/8/902步、工具配对及原SHA不变；旧error转换缺陷保留|
|W2 实验/收割CLI、保护与开关|应用验证通过|8a2d652及后续通用修复；fake覆盖和真实HTTP api→cli往返，不代替Worker|
|W3 单题/单Run/指定模型|实际运行确认|round_fab7e74ad784、run_8a21b7d249、原生Astra xhigh/Terra high fast线程身份；冻结实验2+收割1|
|W3 完整科研、科学评分、轨迹门、干净复跑|新三相原件/六输出已验；科学/轨迹评分尚未验证|74文件和23502801原归档逐项SHA匹配；已冻结公开代理，尚无登记科学分；k点/网格缺口保留|
|W3 CLI上传、harbor_worker、轨迹分和判定|尚未验证|当前0 Attempt；认证/分页通过不能证明POST或正式评分|
|W3 D-74|条件不满足，保留D-69|d74-two-hour-proof.json和UPGRADE_DESIGN评估；没有更改默认分诊|
|W3 CLI收割及阈值恢复|尚未验证|尚无确认实验分；当前auto_harvest=false、阈值100，不能提前触发|
|W4 全量、前端、构建|新原生分类源码全量进行中；其余已验证|1e026d8：1612 passed/2 warnings/941.11秒，5源码哈希复核一致；前端104 passed/22文件/19.64秒、构建通过且无后续前端修改；71项相关与16项初始化/unknown回归另通过|
|W4 密钥与原始证据隔离|已扫描版本通过；最终再扫|25改动文件基线与真实凭据逐字节无命中、0本地证据入Git；最终报告后须再扫|
|W4 最终报告、回退文档与fallback-5|尚未完成|本报告持续补证；须在实际闭环或有证据的替代交付后更新回退目标、封存标签并核对远端SHA|

阶段1完成复核：远端lightchaser-fallback-4剥离到ad9bb076128815f543a8519c10db4ca9b47c1038；授权调用账本实际模型15/20、私有镜像构建1/6、Job3/10、沙箱4/15；交付清单12个核心证据文件哈希全部匹配（stage1-completion-recheck.json）。该阶段无科研Run和参赛提交；缺失经验、历史缺结果和留出不可观测项保留在CS_UP_13_FIX_EVIDENCE，不能把标签解释为这些缺口消失。

## 开赛时监控要注意什么

先在单题获得真实harbor_worker轨迹分及判定，再按参赛过程分批启动其他题。以实际事件recorded_at和原始远程回执计算时间，不把手写checkpoint名称中的时间当时钟。科研超时、中间电子迭代和通用Finished投影不能代替弛豫终态；干净复跑必须重新验收真实文件与结果。原始会话不修改；转换失败时以新Trial产出完整执行证据。遇missing_worker_submission或非标准回执仍按D-66暂停新提交，unknown只读对账。正式链路经实际修复仍不可用时，按本轮用户补充要求明确交付科学验算和本地轨迹诊断及其来源，保留官方评分、accept和收割的缺口。
