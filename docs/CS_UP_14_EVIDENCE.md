# CS-UP-14 提交链路证据

阶段1的fallback-4已推送，阶段2只验证一道已结束LiSi题。
已取得并校验项目内官方CLI0.1.39，全局安装与配置未改。
已复核三种模型真实日志可转换，旧error事件转换缺陷仍存在。
不编辑原始记录，保留失败；最终干净复跑仍待验收。
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

## W4 验收核对（进行中）

|要求|当前事实|直接证据或剩余步骤|
|---|---|---|
|W0 D-73|已实现|UPGRADE_DESIGN §5及9ab5cf9|
|W1 官方CLI与来源|已验证|0.1.39版本、官方latest/tarball哈希、9e2a0ab；历史安装来源仍unknown|
|W1 三模型原生转换|已验证所测样本|9/8/902步、工具配对及原SHA不变；旧error转换缺陷保留|
|W2 实验/收割CLI、保护与开关|应用验证通过|8a2d652及后续通用修复；fake覆盖和真实HTTP api→cli往返，不代替Worker|
|W3 单题/单Run/指定模型|实际运行确认|round_fab7e74ad784、run_8a21b7d249、原生Astra xhigh/Terra high fast线程身份；冻结实验2+收割1|
|W3 完整科研、科学评分、轨迹门、干净复跑|尚未验证|等待最终科学终态与六项产物；当前0本地科学评分，必须在Bohrium执行科学验算|
|W3 CLI上传、harbor_worker、轨迹分和判定|尚未验证|当前0 Attempt；认证/分页通过不能证明POST或正式评分|
|W3 D-74|条件不满足，保留D-69|d74-two-hour-proof.json和UPGRADE_DESIGN评估；没有更改默认分诊|
|W3 CLI收割及阈值恢复|尚未验证|尚无确认实验分；当前auto_harvest=false、阈值100，不能提前触发|
|W4 全量、前端、构建|基线通过；续行修复全量进行中|2f4948e：1585 passed/2 warnings/892.75秒；前端104 passed/22文件/19.64秒、构建通过；新增controller修复已过25/126项相关回归，完整回归待结果|
|W4 密钥与原始证据隔离|已扫描版本通过；最终再扫|25改动文件基线与真实凭据逐字节无命中、0本地证据入Git；最终报告后须再扫|
|W4 最终报告、回退文档与fallback-5|尚未完成|本报告持续补证；须在实际闭环或有证据的替代交付后更新回退目标、封存标签并核对远端SHA|

阶段1完成复核：远端lightchaser-fallback-4剥离到ad9bb076128815f543a8519c10db4ca9b47c1038；授权调用账本实际模型15/20、私有镜像构建1/6、Job3/10、沙箱4/15；交付清单12个核心证据文件哈希全部匹配（stage1-completion-recheck.json）。该阶段无科研Run和参赛提交；缺失经验、历史缺结果和留出不可观测项保留在CS_UP_13_FIX_EVIDENCE，不能把标签解释为这些缺口消失。

## 开赛时监控要注意什么

先在单题获得真实harbor_worker轨迹分及判定，再按参赛过程分批启动其他题。以实际事件recorded_at和原始远程回执计算时间，不把手写checkpoint名称中的时间当时钟。科研超时、中间电子迭代和通用Finished投影不能代替弛豫终态；干净复跑必须重新验收真实文件与结果。原始会话不修改；转换失败时以新Trial产出完整执行证据。遇missing_worker_submission或非标准回执仍按D-66暂停新提交，unknown只读对账。正式链路经实际修复仍不可用时，按本轮用户补充要求明确交付科学验算和本地轨迹诊断及其来源，保留官方评分、accept和收割的缺口。
