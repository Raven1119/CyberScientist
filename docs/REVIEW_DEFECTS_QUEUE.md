# 四份冻结复盘的开发者队列

CS-UP-12 W6逐条核对。A=run_482630519a，B=run_fae47dfe99（ABC），C=run_7afaa0f2ca，D=run_a429539f91。原始四份报告保留在cs-private/reviews，原私有HEAD dafc0499affde07f9873494a8b8b215be3e8291b。下面的event编号属于对应Run的冻结公开轨迹。系统缺陷不作为代理经验；科学或环境建议仍须反事实分析及现行D-24–D-61核对。

| 旧报告项目 / 证据 | 结论 | 实现或理由与对照证据 |
|---|---|---|
| A1 e954/955、B7 e1204、C1 e675/721、D1 e638：完整复盘输入过大 | CS-UP-10已修复 | maintenance.native_materials完整分块及逐块回执SHA核对；test_post_review_versions_cs10完整/缺块/纠正测试。四次原生分别读取205/108/139/109块，均done。不能从这些证据推断理解质量。W6保留大材料中的新反事实/决定指令。 |
| A2 e539：python3 -I -c把-I判为入口 | 现在修复 | shlex识别解释器选项、-c/-m、bash-lc、绝对解释器和声明entry；test_review_defects_cs12六种写法及长选项回归。 |
| A3 e539/569、B2 e429/430：结果路径或占位符提交失败 | CS-UP-10已修复 | compute在预约/HTTP前拒绝非法result_path和未替换占位符；test_job_reliability。W5 Job规格skill补知识。 |
| A4 e607/613、C6 e283/330、D2 e388/390：大文件传输失败 | CS-UP-10已修复已覆盖通道 | Run挂载及对象通道；test_sandboxes覆盖。任意大文件全部可传未被证明，未知回执保留；W5补分块与SHA操作知识。 |
| A5 e147/177、C5 e40：封存原生thread后不能恢复 | CS-UP-10已修复 | 同IDunarchive/resume，test_codex_runtime原thread恢复与失败不新建。 |
| A6 e137/141、C5 e31/32：accepted/unknown暂停长期pausing | 现在修复 | abort不确认时关闭实际原会话，确认关闭才paused；失败屏障保留，晚终态触发原关闭重核。test_review_defects_cs12完整循环涵盖四组合与首关失败→晚终态→第二关成功→thread/resume继续原Trial，无thread/start。 |
| A7 e947、C4 e664/667：已登记评分/审查引用被拒 | 现在修复 | objective resolver支持Run所属local_score和done package_review（带前缀或旧bare ID）；同测试跨Run、缺失与unknown审查均拒绝。引用存在不等于科学正确。 |
| A8 e853/858：采用声明拒绝导致checkpoint整体丢失 | 现在修复 | 同一checkpoint事务内逐声明独立校验；研究正文/合法采用保留，非法冻结版本明确警告且不入账；同测试重放不重复警告、有效/无效混合。原事件未含完整采用参数，不能断言旧声明本应合法。 |
| A9 e176：中断复盘结果未知 | 不算缺陷 | 原生调用开始与unknown持久化，禁止盲目重复维护turn；test_post_review_versions_cs10重启对账/旧额度保留。用户显式新授权为另一版本。 |
| B1 e234/235/266/267：旧CLI Job命令panic或下载缺失 | CS-UP-10已修复当前通道 | v4原生Bohr ID解析和结果下载；test_job_scoring/test_job_reliability。旧丢失的结果仍unknown，不声称恢复。 |
| B3 e762：manifest字段/类型不合规范 | CS-UP-10已修复 | platform_contracts在额度和HTTP前校验必需对象及类型；test_platform_contracts_cs10。 |
| B4 e940：bundle_blocked无就地修复路径 | CS-UP-10已修复，W6复核 | mailboxes允许原blocked草稿修正文案/包后继续；test_draft_continuation验证原字节、同额度、unknown和并发，不新建竞赛提交。 |
| B5 e555：checkpoint多了五字段被拒 | 不算缺陷 | 真实工具契约additionalProperties=false；不能容忍模型自报分数/状态。W6五额外字段回归证明未写checkpoint；保留准确格式反馈。 |
| B6 e464：沙箱删除后prepare拒绝 | 不算缺陷 | 新prepare必须有活沙箱；已完成的原执行可从持久回执register。W6删除沙箱fixture验证登记正式分、去重且不新租资源。 |
| B8 e1045/446：cost=0、currency=null | 不算缺陷 | 原始成本事实不等于免费；compute费用保留部分/unknown，test_job_costs/test_sandbox_costs。 |
| B9 e402/595：准入成功但轨迹分不同 | 不算缺陷 | 准入、上传、平台评分是不同事实；test_executor_scoring/test_job_scoring固定输入回执核对，不能以准入保证分数。 |
| C2 e699：contact额外字段被拒 | CS-UP-10已修复反馈 | 严格schema有效；structured_output给字段级纠正，test_post_review_versions_cs10额外字段/受限纠正调用。 |
| C3 e12：研究简报root字段不匹配 | CS-UP-10已修复 | research_brief契约与提示一致，test_pi_planning。 |
| C5 e37/66：运行中代码/版本变化 | 不算产品缺陷 | 当时有明确建设恢复历史；冻结代码边界和恢复版本检查test_control_integrity保留，不能靠代理自改内核处理科研失败。 |
| C7a e408：三页列表没查到Job | CS-UP-10已修复完整列表路径 | test_job_reliability分页和完整缺席判断；不完整结果仍unknown。D-31十分钟后另新操作、原费用/后台对账仍保留。 |
| C7b e348/405：PIL与Pillow名称差异被判缺依赖 | 现在修复 | 需求包归一及PIL/sklearn/yaml/cv2别名，不依赖笔记本安装状态；test_review_defects_cs12本地find_spec全部空仍识别已声明远端依赖。 |
| C7c e422、D9 e151/160：科研脚本或预测断言失败 | 不算应用缺陷 | 原失败/反例继续作为证据；不修改评分器或强迫预测与平台一致。 |
| C8 / D环境路径观察：复盘cwd与Run cwd不同 | 不算已证明缺陷 | 独立新上下文目录合法；完整冻结内容/SHA绑定不依赖cwd相同。test_post_review_versions_cs10不可变快照和材料读取。 |
| D1重复公开事件 | 不算数据完整性缺陷 | 保留完整轨迹；大材料已分块，不删重复失败证据来缩减输入。 |
| D3 e390→394/396：unknown后继续科学路线 | 不算缺陷 | D-28记录从严、行动从宽；固定评分器hash不符仍拒登记正式分。不加任务DAG或科研行动禁令。 |
| D4 e27/35/146：cwd/-o路径边界拒绝 | 不算缺陷 | 受控路径边界有效；不给越界写权限来规避反馈。 |
| D5 e494/507/513：沙箱destroying后再次删除 | CS-UP-10已修复 | sandboxes以完整list缺席确认终止；test_sandboxes延迟终止仅一次DELETE。单次404不当作完整缺席。 |
| D6 e351/357：archive内重复answer被拒 | 不算缺陷 | 评分契约按exact/suffix匹配计数，真实两个答案就是重复。W6回归展示archive路径且保留全部原文件，不自动删除。 |
| D7 e251/169/329：失败Job引用仍合法 | 不算缺陷 | 失败也是合法公开证据；代理结论与正式分分离。不要求所有引用成功或抹除失败。 |
| D8 e56–63：实际中断终态时paused | 不算缺陷 | 与A6仅accepted不同，原生终态可证明turn停止；若既有close未知，W6仍必须重核关闭屏障。 |
| D10 e601/608/637：旧两次额度外另授复盘版本 | 不算缺陷 | 用户显式单次版本授权不重置旧历史，test_post_review_versions_cs10授权与旧账本不变。 |

ABC反事实的对照事实：旧轨迹已重现q=1.6299116841的(2,6436341,6436343)，但最终选择q=1.4888653961的另一三元组，放弃了已知纪录这个保底。题面科学分档分别20与10；旧通用ARM平台分6.43是另一口径。新的维护复盘必须指出保底，不能许诺ARM分一定增加，也不能把复盘建议当作新增科学验证。

ABC新复盘第6条原要求修改控制器生成的预留标记及重复回执，已由开发者证据审查撤回候选，仅保留开发者报告。D-31名额释放由代码负责；原始事件完整保留，不删重复证据。后续日志性能建议不视为已证明功能缺陷。最终5条代理候选仍为假设，1条开发者项没有进入经验。
