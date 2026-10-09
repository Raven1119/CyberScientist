# RH-02 单题彩排报告（进行中）

用户授权范围：一道已结束的旧题；沙箱总创建次数≤4，Job≤10，镜像构建0，真实提交总次数≤4；从 Run 启动计时≤10小时。首选题在导入前本方 Run/提交均0。比赛后端以候选3源码91ecfd3为基线，当前运行热修复494d0e8，开发后端停用；正常产品写操作通过 WebBridge 前端，HTTP完全卡死时的强制进程恢复见第2节。此报告尚不是彩排完成或科学正确性的结论。Run run_c726779523 已于2026-10-09T16:15:51.620907Z启动（+08次日00:15:51）；最多运行至2026-10-10T02:15:51.620907Z，赛道时钟结束02:15:40稍早。

## 1. 时间线

|阶段|UTC|+08|事实|
|---|---|---|---|
|导入赛道|2026-10-09 15:49:17.884|2026-10-09 23:49:17.884|round_a5637c86e9f9，仅首选题|
|发布提示词|2026-10-09 15:50:42.849|2026-10-09 23:50:42.849|新版本2，逐字等于已验收模板|
|启动Run|2026-10-09 16:15:51.621|2026-10-10 00:15:51.621|run_c726779523；PI Astra xhigh、执行者Terra high/fast，双方原生priority|
|题目分诊|2026-10-09 15:52:54.300 → 15:53:56.890|2026-10-09 23:52:54.300 → 23:53:56.890|62.590秒，一次实际调用完成；尚未启动科研Run计时|

题目：site-projected-magnetic-moments-and-spin-state-ass-9640ab85；本地ID local_a28928e48aae。题面实时读取成功，平台结束时间为2026-08-08 12:00 UTC；赛道练习时钟另设，不修改旧题或旧赛道的历史时钟。

## 2. 阻塞与修复

彩排前查清自动提交的旧链路保护并恢复：六次10-08非标准Worker告警，持久暂停标记1；版本24文件开关true与数据库门禁并不一致，后端同步后版本29为false。真实标准回执50211/27828及发送包/Worker哈希核对证实修复路径。前端恢复后版本30=true、暂停标记0、队列0，后续临时创建容量版本31仍true。未新建验证提交。

源码 main 和候选3标签已推送GitHub；补齐W9“同账户、不同刷新令牌、各端原生登录有效、不需重登录”结论。远端main最初9789931，后续仅文档补记及STATUS历史恢复后acd9cdf；源码候选标签保持91ecfd3，私有比赛快照标签保持301993e3。有一次STATUS文档移动误删旧段落，已从原提交逐字恢复并补推，没有改动数据库或科研文件。

真实分诊判断hard，推荐astra-fast，与卡中名义难度1不同；最初采纳Astra fast/high，用户随后明确要求Terra，现已在前端人工覆盖terra-fast（gpt-5.6-terra/high/fast），PI仍Astra xhigh。科学配置选择由PI继续提出，预算没有增加；分诊耗时和费用估计及数据完整性均unknown。

启动前发现第二次自动暂停：2026-10-09 15:57:25、15:57:29、15:59:06 UTC 三份旧反馈仅顶层status从缺省变scored，重复触发旧保护且未新增去重告警；此前“已排除”只覆盖完全相同回执，不覆盖该变化。正在做最小管线热修复，保留完整新反馈和状态投影，新的保护证据仍暂停。完整应用回归已在候选发布前完成；本次追加旧回执恢复去重专项4 passed/6 deselected（5.84秒）。

## 3. Codex 用量

16:52Z原生统计：PI累计输入1,518,859（缓存1,354,880）、输出18,981（reasoning3,238已含输出）；执行者输入7,262,635（缓存7,102,720）、输出14,766（reasoning4,706已含输出）。PI4轮，两个原生会话compaction0。按当前小时窗口记录，最终每小时及24小时并发估算在结束时更新。绝对Codex token配额未由供应商接口提供，不从百分比编造容量。

## 4. 算力与预检

方法已批准，恢复后同沙箱启动真实FM SCF；截至16:53Z本题实际沙箱创建1、Job0、提交0。先前ABACUS输入解析失败由执行者纠正，远程wrapper退出0不能当科学成功；目前尚无收敛SCF或科学输出验收结论。模板预算：600分钟、10 Job、4总Attempt、4沙箱并发、环境保存0、沙箱累计2400分钟；另通过给PI的备注明确沙箱总创建次数≤4及镜像构建0。并发字段不冒充平台总创建硬限额，监控按实际创建账本核对总数。

## 5. 提交与回执

本题尚无提交，科学分、轨迹分、判定、扣分码及harbor事实尚未产生。旧题的标准链路回执仅用作彩排前修复复核，不算本题彩排成果。

## 6. 干净复跑

尚未进入该阶段。将保留四段交接全文，核对无探索结果数值/代码、新目录/新会话、提交包只含新线程，并核对科学输出和原生字节。

## 7. 原生注意力检查

新Run冻结的新赛道提示词version2的SHA256为43cf07c2deff67270e895949a6d4c7455b8833f11150ac1d6d4f966b20bc9b25，与模板原文完全一致。实际Run已冻结Terra high/fast与Astra xhigh/fast；双方首帧v2、priority已核对，同线程恢复也已验证。开发路径/平台协议/pg-*技能/内部编号/凭据路径的整轮命中统计在结束时更新。

## 8. 诚信事件

科研会话已启动，当前PI原生帧未出现指定他人仓库名；完整会话诚信观察继续。后续按协议观察并如实记录，不把尚未观察写成完整轨迹零命中。

## 9. 前端问题

- 历史持久告警积压阻挡入口，逐条通过UI确认，原告警和事件保留；三条无关全局经验选择“稍后处理”，未批准或驳回。
- 比赛总览先展示旧Run的大表，WebBridge可访问树截断后不含下方导入/模板控件。使用WebBridge evaluate读取真实DOM标签、滚动并定位缺失控件，随后通过fill/click操作；没有用裸API替代产品写动作。
- 保存模板请求未结束时，“分诊”按钮被禁用，第一次点击没有创建分诊账本。读回模板成功、确认分诊记录0及按钮可用后，再点击一次，实际账本started。不重复不明模型调用。
- 两条旧recovering且resume_on_startup=0的Run占应用上限2；仅通过前端临时调上限3，以便创建本题一条Run，其余默认字段相同。新Run创建后恢复2，不恢复旧Run。

原始UI操作、题面、设置读回和回执复核留在开发目录私有 .package-checks/rh02/，不将凭据、原生日志或用户简历入Git。

RH-02热修复commit37012a6已推送源码main，候选3标签保持91ecfd3。相关命令`.venv/bin/pytest -q tests/test_submission_gate_cs13.py tests/test_mailboxes.py tests/test_mailbox_platform.py`实测82 passed/30.58秒；完整新回执和终态投影保留，首次/真实变化的保护证据仍暂停。

发布初次prepare因监控shell未含npm而明确失败（尚未停止后端）；补齐本次命令的既有Node22 PATH后重新发布，原错误保留。只调整该命令环境，没有安装工具或修改全局配置。

热修复发布completed，preflight warn/0 fail；比赛PID1789906、loaded=37012a6，私有快照c2d6da00c638c89a1581d3591aa717fc86673dc9（252文件、22技能、扫描0）。135经验文件和比赛Codex配置SHA与发布前相同。前端恢复自动提交33=true、暂停记录清除；临时容量3→2后34=true，只有max_active_runs改变。当前沙箱/Job/提交均0，未恢复任何旧Run。

前端问题补记：发布时同端口后端冷启动约两分多钟，用户浏览器实际ERR_CONNECTION_REFUSED；健康与首页HTTP200后，WebBridge重新navigate实际渲染成功。模型草稿人工覆盖会随刷新丢失，因此启动前重新选择Terra并核对，实际Run配置已冻结为Terra。设置页面首次渲染使用默认值，待请求读回再操作；前端自检缓存仍显示发布前的自动暂停事实，实时开关读回已true，未把缓存当当前状态。

用量初查：控制事件里的PI native_log_path暂为null，按同一事件session_id定位唯一原生文件，使用W10脚本已有--session pi=FILE补入统计，不改原生记录或数据库。执行者尚未发起工作回合，记录文件暂不可用，其用量保持unknown。

初始方法：2026-10-09T16:23:24.271415Z提案version1，前端完整复制并以monitor批准于2026-10-09T16:25:04.138985+00:00。核对四项均满足：题面固定方法/数值下限和FM/链内AFM、三个输出与全部字段/单位、无其他参赛者解答、已登记环境与CPU沙箱/Job合理。具体最终数值由批准后的实测决定，监控未添加科学参数或改写产出。

方法提案原文：
```json
{
  "method_md": "批准后由执行者按 research_brief.work_package 独立实现：生成并验证 22 原子实验原胞，按配位识别 Co_oct/Co_pris；在 ABACUS 中进行无 U、无 SOC 的自旋极化 PBE 平面波 FM 与指定链内 AFM 自洽计算；实测确定配对收敛参数；从两自旋 cube 做带周期边界的球积分和全胞积分；解析同一定义的总能并生成题定 JSON。先验证科学和契约，再请求真实提交，之后按回执改进并完成新的干净会话复跑。",
  "parameters_md": "结构参数与方法严格采用题面。ecutwfc≥100 Ry，Γ 中心 k 网格≥3×3×3，展宽≤0.02 Ry；具体最终数值、混合参数及收敛阈值由获批后的首轮实测决定。Co_oct/Co_pris 使用不同非零初始磁矩，AFM 只反转一枚 Co_pris，不固定最终总磁矩。两构型同赝势、晶胞、截断、k 网格、展宽及能量定义。球半径先由非重叠几何规则冻结。CPU 为首选，长计算使用同镜像 Job，遵守 16 CPU/16 GB/10 GB 及两个并发限制。",
  "basis_md": "最高依据是 ReviewPacket.challenge.content。已读来源论文 [Eyert 等](https://arxiv.org/html/cond-mat/0401004) 支持配位导致自旋态差异与氧极化；其 LDA/ASW 与链间磁序不替代题面要求。已读 [ABACUS 电荷密度文档](https://abacus.deepmodeling.com/en/latest/advanced/elec_properties/charge.html)、[自旋文档](https://abacus.deepmodeling.com/en/latest/advanced/scf/spin.html) 和 [STRU 文档](https://abacus.deepmodeling.com/en/latest/advanced/input_files/stru.html)，据此安排输入和积分检查。初始批准要求来自 PI 流程及用户提示词；本次仅进行了只读检索，没有代码实现或科学试算。原始中子论文全文、镜像本题冒烟及最终数值参数仍为 unknown。",
  "outputs_md": "/app/outputs/structure_report.json 保存原胞与配位证据；/app/outputs/magnetic_moments.json 包含 Co_oct:{moment,mean_Co_O,radius_bohr}、Co_pris:{moment,mean_Co_O,radius_bohr}、O:{moment,radius_bohr}、total_moment；/app/outputs/magnetic_stability.json 包含 E_FM、E_AFM、dE_AFM_minus_FM、ground_state。磁矩 μB、键长 Å、半径 Bohr、能量 eV/22原子胞。附带真实输入、日志、密度积分与收敛证据以及自旋态说明。",
  "capabilities": [
    "competition-materials-assets-20261009",
    "ABACUS-materials-offline",
    "research_environment",
    "research_sandbox",
    "research_job",
    "cyberscientist-sandbox",
    "cyberscientist-job-spec",
    "cyberscientist-trace-writing",
    "cyberscientist-submission-gate",
    "cyberscientist-clean-rerun"
  ]
}
```

格式异常：首份决策的method_proposal在根层，被既有schema拒绝；一次原生格式重写将其移到research_brief内，16:21:46→16:23:24约98秒自动修正。没有热修改提示词、科学内容或原生记录；未通过格式验证前审批门禁始终关闭。

探索启动：Trial trial_3d3c35213d创建于16:25:44Z；CPU常驻沙箱2c4g在16:26:51Z确认active，实际expires_at=2026-10-10T02:10:31Z。首个环境调用HTTP422因choice形状缺必填，被执行者自行纠正；实际运行烟测通过可执行/MPI/Python依赖，随后题面示例赝势目录不存在导致停止，执行者正按批准的方法核验镜像内实际PBE赝势。科学值尚未产生，监控未修科学脚本。

原生初查：双方v2首帧与priority已实际确认；PI前八帧技能出现两份比赛清单，共43条列项、唯一22技能，没有比赛外技能，重复展示作为注意力事实保留。全局~/.codex/AGENTS.md实测0字节，不能以空字符串全文搜索制造验收；实际开发AGENTS标题、开发路径和比赛外技能均未进入当前角色记录。此后还需完成整轮全文抽查。应用review packet发生context.compacted（254873→44527字节），W10原生统计当前compaction=0；二者分别记录，不混为供应商上下文压缩。

前端中断2：2026-10-09T16:32:04Z之后无新事件，首页和health连接后无响应，比赛PID1789906主线程futex等待，数据库只读可用。代码存在策略更新config→DB与告警事务DB→密钥读取config的锁逆序；两项受控并发测试在旧代码复现失败，取消只读load_secrets锁后通过，写入仍串行并原子替换，另验证并发更新不漏键、读到完整版本。未取得现场Python栈，具体现场持锁线程unknown，不把静态和复现实验当现场栈证据。相关回归52次通过/18.64秒，含两项重复收集，共50唯一用例。原失败日志保留。

GUI和安全关机HTTP均无响应，按热修复授权采用精确进程恢复：确认最后trial3_write_stru_repair及所有沙箱操作completed、无Job/提交，再核对PID/cwd/进程组，TERM后仍不退出才KILL。136经验文件、配置SHA与两个原生线程标识已留证，未改DB恢复意图或重做已完成写入。没有can_shutdown=true或原生关闭ACK，明确作为强制恢复边界；正常ops release待端口确实释放后进行。科研脚本/参数/已保存输出未由监控修改。

锁修复已发布494d0e8，私有快照da086f555363818434c0c70784992b704eb1fbd4，自检warn/0 fail。比赛唯一后台PID1799503，136经验文件/比赛Codex配置SHA不变；2026-10-09T16:49:18.583725Z同Run恢复，16:49:24Z health200，浏览器真实研究页渲染且可见running/原沙箱1。PI线程01a12173-11bc-7a62-b6f4-513fe56bbca4、执行者01a12173-2392-74e0-8c75-f8ca76960cc8均与恢复前相同。事件中断约17分20秒，没有重做已完成的files.write。新增并发写保护3 passed/1.12秒；连同原50唯一回归，共51唯一用例实际覆盖。有界代码审查和diff检查通过，未做科研决定。

前端模型标题原显示本题默认Sol，不代表已有Run冻结配置；已通过前端“编辑本题模型”保存Terra/high/fast，PI仍Astra/xhigh/fast，与实际Run对齐。ops digest实测版本匹配、自动提交true/队列0/暂停false、告警0、原生关闭unknown持久标记0。后者不能补作强制关闭时原生ACK。全局旧沙箱unknown账本一条保留，不属于本RH，未重试创建。

Job准入阻塞：16:59:23Z预检拦未登记abacus.stdout，执行者补登记后16:59:40Z及下一次预检将run.sh中的独立( )误当镜像命令，镜像真实abacus/bash/mpirun/time和赝势路径均有成功探测回执。预检明细只留数据库，工具响应details为空，执行者因此反复登记和核验环境，未创建Job或费用预约。监控修复仅将独立( ) { }列为shell语法，并保留ComputeError异常明细；组内实际程序仍检查，网络、输出、授权和预约门禁不变。原分组回归2 failed/0.70秒；修复初次回归2 failed/108 passed来自fixture无同镜像沙箱，应判IMAGE_FACTS_MISSING而非IMAGE_REQUIREMENT_MISSING；更正测试后相关三模块110 passed/33.97秒。一次误写不存在测试文件，no tests ran记录保留。有界审查、compileall及diff检查通过。

远端科学状态：执行者16:58Z自行停止约8分钟单核FM性能烟测，无收敛结果；17:02Z自选同一沙箱双rank运行SCF。监控只观察并修管线，不替换赝势、参数、脚本或结果。137经验文件/Codex配置及原线程发布前指纹已留；本题仍沙箱1/Job0/提交0。阻塞60分钟检查起点为16:59:40Z，当前仍能推进管线修复。
