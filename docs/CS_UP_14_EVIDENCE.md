# CS-UP-14 提交链路证据

阶段1的fallback-4已推送，阶段2只验证一道已结束LiSi题。
已取得并校验项目内官方CLI0.1.39，全局安装与配置未改。
已复核三种模型真实日志可转换，旧error事件转换缺陷仍存在。
不编辑原始记录，保留失败并使用新干净会话。
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

唯一赛道round_fab7e74ad784，唯一Run run_8a21b7d249，启动2026-10-08T02:28:20.346497Z。原生回执确认Astra xhigh0.161与Terra high fast0.148，priority；后端重启123.698秒，旧Run resume_on_startup=0未恢复。单题有效计算授权为unlimited，冻结提交上限实验2、收割1。收割暂关，阈值100。

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

交付核查：audit-delivery.py在5142173对fallback-4后的25个受控改动文件按现有凭据值逐字节扫描，0命中；.package-checks/cs-up-14无跟踪文件。只输出文件路径/哈希，不输出凭据。src、apps/web、tests与已全量通过的2f4948e无差异，后续改动仅文档。最终报告更新后须重新扫描。

Worker只读可达性：GET http://47.92.88.121:443/api/uploads返回404（2.012秒），/openapi.json和/api/openapi.json也404，没有公开schema可核实；没有发送POST、认证或Attempt。该结果只证明主机响应，不能推断POST是否可用，更不能当评分证据。原记录worker-reachability.json、worker-read-only-schema-probes.json均留本地忽略目录。

监控事实反馈cs14-midrun-ledger-facts-v1已queued：只列当前Job状态、实际开局及D74两小时截止、独立2+1额度和现有功能状态；没有科学答案、代码或降验收指令。D74时钟按Run.started_at连续计算，不能减去维护时间；两小时条件不会替代完整科研/评分/干净复跑要求。

用户补充方案已在2026-10-08T04:10Z持久投递，PI于#3803采纳条件性回退：实际提交经排查和修复仍不可用时，允许以任务科学评分器和本地轨迹检查交付，科学评分仍在Bohrium执行，保留正式Worker和收割缺口。04:10Z重新取得官方latest.json，仍为0.1.39且tarball哈希一致；GET404不作为提交失败证据。

截至04:16Z只读对账：20个Job中10 Failed、6 Finished、4 Running，0提交/0封存包。Li参考23502313归档原生日志实际含`Relaxation is converged!`和`!FINAL_ETOT_IS -392.0781205964211722 eV`，归档SHA256为1bdf4f3f6724e77982b928b049389ce5704f47bad081668cd504a65ac8658432；wrapper时间03:39:00–03:41:14Z，不等于调度/回收墙钟。旧受限LiSi23502296实际停止，归档未含完成终态，数据库通用Finished投影不能据此称弛豫通过。开放原子LiSi23502312、Si23502314、Li收敛23502436与电荷核查23502449继续对账，没有重建在途操作。原始取证留w3-reference-log-proof.json与w3-acceptance-proof.json。
