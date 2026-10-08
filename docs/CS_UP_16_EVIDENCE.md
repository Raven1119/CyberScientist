# CS-UP-16 验证记录

所有测试使用隔离临时账本；真实验证单列。原始日志和截图在本地忽略目录 `.package-checks/cs-night-1009/`，不提交原生会话、回执全文或凭据。

| 项 | 结果与证据 |
|---|---|
| W0 | D-75/D-80 已写入决定和升级计划。 |
| W1 | 方法关口持久化，审批与 PI 请求同事务；计算仍要求 open gate。8 项后端测试通过（cs16-w1-tests.log），4 项前端测试通过（cs16-w1-front.log），前端构建通过。真实 Chromium 140 按 aria-label 点击批准成功；HTTP 为明确的 synthetic fixture，实际渲染 MethodApproval 组件，cs16-method-playwright.json / cs16-method-approved.png。提示词附录原文加入 brain.md。 |
| W2 | 8 项闭环/早回执/账号测试通过（cs16-w2-tests.log）。fake 走实际 controller、提交和回执写路径：批准前无执行消息；批准后完整版本产物提交；等待期间新 Trial 可继续；final=false 的科学分唤醒 PI；第二完整版本轮换账号。提交路径未调用本地科学评分；现有轨迹诊断已为 advisory。没有真实计算或评分器探测。 |
| W3 | 14 项回归通过（cs16-w3-tests.log）；等待空闲、不 resume、旧日志不改、交接不含探索目标、封包只含新线程。已结束 LiSi 旧题账本副本真实最小 Trial trial_f694ba14df，新 Terra xhigh priority 线程 01a11cb8-50b5-7640-a467-6631a741406a 完成；169820 字节原生日志封包逐字节相等（clean-native/result.json）。无 Job/沙箱/提交。此绑定专用验证未接 MCP；旧 idle 线程未曾生成日志，旧日志保留由 fake 不变性测试覆盖。原生完成后验证消费者误等旧事件名，已停止并按真实 task_complete 及回执文本判定、封包；不把测试程序中断记作完整脚本通过。 |
| W4 | 实时逐题面板及全部控制接入真实接口并留审计；暂缓提交为持久门禁；档位覆盖保存在独立运行控制记录，冻结快照不改，仅新会话生效。19 项后端测试、34 项前端控制/审批/账号/旧页面测试通过，构建通过；真实 Chromium 截图 cs16-competition-panel.png（实际组件、明确 synthetic HTTP，page_errors=[]）。 |
| W5 | 渐进披露已实现，经验前8条标题/ID/一行摘要，正文按需读取；能力索引含名称/用途/位置；完整事实按哈希在facts范围分页读取。研究简报selected_capabilities在新版本Run强制非空。32项回归通过（cs16-w5-tests-3.log）。同一旧首包默认JSON由345938降至53424字节（15.44%），原题面不变；完整分项见cs16-context-comparison.json。真实Astra PI冷启动正在执行，耗时和所选能力最终在W8补录。 |

## W5 同输入字节对比

| 部分 | 瘦身前 | 瘦身后及方式 |
|---|---:|---|
| PI首包默认JSON | 345938 | 53424（原来的15.44%） |
| 完整题面 | 25628 | 完整保留一次；重复题面和目标段用明确引用 |
| 运行事实 | 30107 | 保留剩余授权摘要，完整JSON按SHA分页读取 |
| 环境目录 | 19927 | ID、用途、位置、验证状态索引 |
| 经验manifest / index | 12479 / 15674 | 前8条摘要；正文research_experience按需读取 |
| research_startup | 46231 | 不重复题面/环境；策略仅索引 |
| feedback | 134419 | 不重复上层授权、环境、题面、目标；保留研究变化与真实分 |
| 执行者首条历史原生用户消息 | 135595 | 当前同题完整生成器40473字节（不含另附简报）；这是生成器测量，原生新帧将在迁移验证核对 |

原始完整首包落到本Run事实文档；没有截断科学题面来追求目标。上下文测试读取全部分页并还原原JSON，包括跨UTF-8边界的base64分页。

## W2–W5 有界审查与真实冷启动结论

两轴审查发现并修正7处生产问题：正常提交通知自动等分、真实扣分字段、无消费者的复跑策略、初始方法摘要不更新、简报缺能力导致Run异常、旧会话关闭未知仍开新线程、实际提交模型身份取旧配置。18项修正回归、12项旧等分兼容、实际HTTP闭环1项和面板10项通过，证据cs16-review-fixes.log、cs16-score-wait-review.log、cs16-w2-http-regression.log、cs16-review-fixes-web-2.log。旧测试明确选择旧协议政策，没有删除或跳过。

真实Astra xhigh/priority会话01a11cc1-32cc-77a3-8af4-236c89a805b6握手19.763秒，到Decision465.605秒；方法提案存在、selected_capabilities非空，零Job/提交。此次JSON紧凑口径336039→52795字节（15.71%，验证附加指导包含在后者）。证据pi-cold/result.json；完整原生记录只在私有本地。**耗时目标不通过**：相比旧319秒未下降，更未达到79.75秒；上下文目标通过。替代为保留压缩和真实失败证据，后续按供应商延迟/工具调用分项诊断，不追加科研Run或重跑取最好值。

## W6 模型档位

分诊简单/中等Terra fast，难题Astra fast；空roster不回退DeepSeek，显式采纳时写入本题模型选择。未知难度仍unknown。新配置默认Terra xhigh fast，用户已有选择不覆盖。29项测试通过cs16-w6-tests.log，前端20项通过cs16-w6-web-4.log（旧默认断言与标签修正，保留失败日志）。
