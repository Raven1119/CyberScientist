# CS-UP-18 运行时隔离验收证据

本卡按01:50汇总补充实施，替代01:25版本。全部步骤均须有实际结果；账号缺失、原生记录字面搜索等硬性缺口保留为不通过，不把后端启动等同于迁移验收完成。真实回执、原生记录和秘密不入Git；下列私有文件均在 `.package-checks/cs-night-1009/` 或比赛 `.runtime/validation/`。

| 项 | 实现和实际结果 | 证据 |
|---|---|---|
| W0 | D-79已记录；先审计10-08两角色原生前帧，再决定切换HOME。全局AGENTS文件为空，但项目施工约定各1次、原生技能索引各1次，出现比赛外技能来源；未发现系统桥之外的实际MCP服务器 | DECISIONS.md、CS_UP_18_ACCEPTANCE_PLAN.md；native-first-frames-baseline.json |
| W1 | 比赛目录创建前完成8条具体候选和去重。没有导入，策略冲突等待设计助手审阅 | EXPERIENCE_CANDIDATES_1009.md；cs18-candidate-scan.json |
| W2 | 指定提交白名单导出、指定提交前端构建、内容拒绝、无Git版本文件、comp运维target、独立锁环境、安全停机/启动、缓存回退均实现。经验/数据库/设置/认证不随代码发布替换 | runtime_release.py、runtime_layout.py、start-runtime.sh；发布manifest与release-journal |
| W3 | 一致备份29GB；48旧Run独立归档；8设置路径和177活动DB路径行迁移，原值新增表保留。比赛48 Run/14提交/163历史Job，秘密3份且文件SHA一致；开发后端停止、正常启动入口禁用、全部resume_on_startup关闭 | CS_UP_18_MIGRATION_INVENTORY.md；cs18-migration-result.json、cs18-development-shutdown.json |
| W3 经验 | 原经验全文备份，60文件仅技术引用迁移，61派生修订保留原修订/审批及122活动经验。既有原始历史不改。发现旧Run评分对账会回写19处历史路径，已修复归档Run不再重建笔记；再次技术映射后扫描为0 | runtime_reference_migrations、runtime_migration_originals及reference-map；cs18-migrate-references-4.log |
| W4 配置 | 专用进程HOME/CODEX_HOME，复制完整相关配置后删除无关项目并禁用5内置无关技能；23启用比赛技能含17bohrium整目录。全局配置/认证不改；登录档位、模型目录、service_tier、模型/effort、features、memories逐项一致 | cs18-native-before.json、cs18-native-after.json、cs18-native-invariants.json |
| W4 原生初验 | 实际Astra xhigh PI及Terra xhigh fast，均原生priority/task_complete；cwd在比赛目录；开发路径、施工约定、全局AGENTS路径0；官方试构建成功，提交14→14 | native-sessions-recovered.json、cs18-official-preview-2.json |
| W4 隐藏依赖 | 不通过完整标准；06:05:30–06:19:07实际隐藏源目录，全部步骤已尝试并恢复原名。真实前端、两角色priority、20工具、试构建、重部署/回退已执行。脚本三处错误保留，沙箱/CLI/只读归档审计分别补证；账号与字面零命中缺口未通过 | scripts/cs18_hidden_dependency_smoke.sh、scripts/cs18_validation；比赛.runtime/validation/hidden |
| W5 | 《参赛过程》技术命令/第六节更新；监控留开发目录，修复测试提交后发布，监控指导只进PI；内容走发布，经验经接口。前端/WebBridge仍localhost:8765 | LIGHTCHASER_PROCEDURE.md；cs18-procedure-technical-diff.patch、cs18-procedure-check.json |
| W6 | 最终后端1757 passed，2依赖弃用警告，1170.19秒；前端25文件122项、构建、compileall、Bash语法、diff检查通过。候选标签及推送交付，不等同于硬标准全部通过 | cs18-full-frozen-suite-2.log、cs18-web-final.log、cs18-build-final.log；CS_NIGHT_1009_REPORT.md |

## 发布白名单与数据边界

白名单为 `src/cyberscientist/`、`prompts/`、`skills/`、`environments/`、`challenges/`、`contracts/`、`vendor/playground_contracts/`、`evals/`、`templates/`、完整官方 `tools/playground-cli/0.1.40/`，以及pyproject、uv.lock、配置模板、启动脚本；前端从指定提交构建后只放dist。外部17个bohrium比赛技能从迁移后的完整目录保留。每个实际文件的SHA清单在 `.runtime/releases/<SHA>/manifest.json`，版本文件为 `.runtime/version.json`。

不导出AGENTS、STATUS、DECISIONS、docs、任务卡、S4分析、开发验证目录或Git。完整CLI目录是实际完整性检查要求，首次仅dist导出导致缺tsconfig的启动失败已留证并修正。UV生成的空 `.git` 缓存标记已移出比赛目录，不把它称为项目Git仓库。

发布前扫描提示词、所有技能附件、当前经验、能力索引；拒绝本地docs/、.package-checks、开发绝对路径、CS-UP编号和D编号，报告文件/行/原因。公开文档URL保留。真实旧笔记回流触发拒绝19处，未停机覆盖；修复后重新检查。开发旧Run快照、事件、原始回执、检查点及原经验修订作为历史例外保留，活动路径和新会话分别验收，不伪造历史零命中。

并发发布用flock排他；缓存哈希/路径先核查；代码、原生技能和版本元数据异常可恢复。普通comp运维必须核对后端工作区和PID，避免误操作开发实例。旧fallback-8缺比赛发布协议，在停机前拒绝；首次修正后的兼容基线为 `lightchaser-runtime-base-1009-v2`（d044a44），此前试验基线不作为可用回退。

经验技术映射是引用替换，archived-reference定位符不是科学产物SHA；有实际文件时另记真实文件SHA。没有编辑科学策略或引入候选，也没有伪造新的用户审批。历史原文在完整备份及原修订中保留。

## 隔离方法与原生证据边界

Codex0.161实际支持 `project_doc_max_bytes=0`；比赛启动环境和每次thread配置均关闭项目文档自动加载。应用技能扫描仅比赛skills，原生HOME也仅23个启用技能；供应商自动展开的5内置技能用原生skills.config明确禁用。系统桥保留，PI仍只读工具，执行者仍有本题工具；不改供应商内核。

初验PI会话 `01a11d6d-cc52-79a2-a8ba-4b4b75c4647c`、执行者 `01a11d6e-1d4e-7930-834a-6865bdc44333`。监听器首次错误等待旧事件名而被中断，真实task_complete从原生记录独立确认；修正完成事件后用于隐藏依赖测试，原失败不删。

对80个比赛外技能名使用词边界逐词搜索：初验PI的供应商 `session_meta.payload.base_instructions` 有普通词resume1次，执行者有worktree1次；这些不是启用技能条目。**字面全文零命中不通过**。替代为保留原生记录，分别报告技能索引零额外启用、正文命中字段与次数，交验收方确认合理口径；不删除原生字段、重写base instructions或篡改记录求零。全局AGENTS为空，检查路径及项目“施工约定”内容；空串不能作为内容命中标准。

## 有界审查与失败保留

按code-review技能两轴审查，修复并发发布混合版本、版本元数据异常未恢复、comp普通ops误触开发端口、不兼容标签先停机四项。之后对原生技能同步和归档笔记冻结做最终只读两轴复核，均无新增阻断。

78项机制定向回归通过69.48秒；发布/DeepSeek33项通过46.14秒；运行时专项23项通过37.19秒；另33项控制回归通过10.92秒。首次全量因真实笔记回流修复主动中断，210通过后KeyboardInterrupt，不能当完整通过。比赛首发及后续发布都已实际启动，但experiment_mailbox自检因两新账号无凭据失败；没有禁用账号或更换凭据造通过。

隐藏冒烟只在已结束旧题做最小模型会话、工具调用、试构建及一次有界沙箱/Job预检，不建新科研Run、不发Job、不提交。受保护写工具调用明确拒绝路径，单列结果，不宣称执行了真实评分/提交。账号认证必须逐个报告；无法认证的新账号保持缺失。整体只有全部硬性标准通过才可称迁移验收完成。

## 隐藏依赖实际结果与补验

实际执行 `bash scripts/cs18_hidden_dependency_smoke.sh /home/wmywb/CyberScientist-comp /home/wmywb/CyberScientist`。脚本冷启动、同版本重部署、回退、恢复当前版分别得到PID1517220、1519840、1520893、1521725；每次健康检查和resume均成功，最终自检均仅experiment_mailbox失败。回退版本d044a44，当前验证版本5ff4a6c；二者运行文件相同，验证的是旧提交缓存/SHA、PID切换和运行数据保留，未宣称跨功能回退。

| 检查 | 实际结果 |
|---|---|
| WebBridge | cs-night-1009会话打开localhost:8765，真实工作台标题/树存在；browser.json |
| 两角色原生 | PI01a11d8f-d37e-7742-83ec-5b2c8c9a15a8；执行者01a11d90-0b26-7972-a307-2698816b8a8a；均xhigh、原生observed_tier=priority、正常完成；native-sessions.json |
| 每工具一次 | 20/20有MCP回执；12正常，8拒绝/不可用。变体/审包/评分/ACK/检查点走保护路径；trace无运行中审阅，旧结束Trial不具备提交预检状态，公开分布unknown。不能称20个功能全部正向通过；tool-calls.json |
| 官方试构建 | built，退出0，提交14→14；hidden/preview.json |
| 沙箱与Job预检 | 首次验证脚本漏算历史7200秒累计预算，SANDBOX_BUDGET在预约/远端创建前拒绝。只修私有验证授权，保守再记一次预算；同一隐藏期间补验实际创建、同镜像bash探测、echo退出0，image_checked=true，0新增Job。初次删除回执deleting，随后只读对账deleted；sandbox/supplementary-result.json与final-reconciliation.json。时限适配无真实Job耗时，保留warn |
| CLI与客户端 | Codex0.161.0、bohr2.7.8、兼容1.1.0、dflow1.8.133、SDK0.15.0通过。脚本误写main.js导致官方版本检查失败；同一隐藏期间按实际设置index.js补查0.1.40；保留两份结果 |
| 全部账号 | 配置4个Agent，原2个/auth/me=200；新2个没有凭据，未发认证请求、HTTP=null。操作者另查200。不能称5个本人Agent齐备或全部认证通过 |
| 最后审计 | 初脚本误用提交存储路径作Run产物路径，404；修正为实际归档trials路径，另一次短暂隐藏下仅只读审计通过。历史Run与12,739,087字节归档ZIP均HTTP200。首轮脚本仍保留为不通过，不把补验冒称首轮完整通过 |
| 路径与数据 | 活动配置/指定活动DB列/提示词索引开发绝对路径0，内容拒绝0，禁用文件0，技能副本差异0；48Run/14提交/163Job/4邮箱及经验/秘密SHA前后相同；audit.json |
| 原生全文 | 两角色开发路径/施工约定/全局AGENTS路径均0；80个外部技能名逐词仍仅PI resume1、执行者worktree1，位置均session_meta:base_instructions。严格字面零命中不通过 |

实际全文检索由 `.venv/bin/python .runtime/validate-audit.py` 执行，代码见 `scripts/cs18_validation/validate-audit.py`。开发路径使用 `re.escape('/home/wmywb/CyberScientist') + r'(?![A-Za-z0-9_.-])'`，避免把合法的CyberScientist-comp/归档兄弟目录当开发路径；技能名使用 `r'(?<![\w:-])' + re.escape(name) + r'(?![\w:-])'`。前8帧与全文分别记录，原文不改。原生SHA分别a6f49420deba1b40f41eef38d4557c09c85c6e9be5bbfec9c72523bf5f12daef、fbd94820adf776bb855d162e184de1e45e30014d62f03d249261adc5cb79f6ab。

全局Codex配置最终SHA仍与迁移前一致；比赛23技能目录字节一致，系统桥字节与fallback-8一致。经验技术迁移累计76派生修订，原文与审批保留；隐藏前后经验文件完全一致，未导入8条候选。可选A5未实施：保留原生cwd元数据和实际运行能力事实，不声称去掉所有比赛绝对路径/项目ID。

本轮预算保守计沙箱10/20（含已证明创建前拒绝）、Job2/20、镜像请求3/3、提交1/6、注册2/2；本卡只新增一个实际验证箱，已deleted。开发目录原名已恢复，开发后端继续禁用；比赛后端留待验收。完整迁移验收仍不通过，后续只需针对明确缺口处理，不重放unknown操作。
