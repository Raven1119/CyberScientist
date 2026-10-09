# CS-UP-19 验收证据

本卡由用户重新授权执行。真实提交0、镜像构建0；真实模型调用仅W2冒烟。未完成项持续列在STATUS，不以模拟测试替代真实闭环。

## W1 当前比赛快照

- 私有仓库：https://github.com/Raven1119/CyberScientist-comp，GitHub查询isPrivate=true。
- main快照提交：f5f9b571b44694fbc19d541fdf9dafd2bf82cecb；远端refs/heads/main与本地HEAD一致。
- 发布版本：1285f164b878cd5ba7839554762680314de59d43。264个发布文件逐项复核清单SHA，另导出版本、发布清单、脱敏设置、脱敏Codex配置、23个启用技能清单、两层目录名称/大小，共271文件。
- 完整导出清单：[export-manifest.json](https://github.com/Raven1119/CyberScientist-comp/blob/f5f9b571b44694fbc19d541fdf9dafd2bf82cecb/snapshot/export-manifest.json)。
- 现有已知秘密扫描与ASP、API token、Bearer凭据、AccessKey值、长base64/JWT、私钥块扫描：271文件、0命中。初次扫描将代码中的函数名判为AccessKey值；修正为凭据值模式后重扫，未修改清单文件字节。位置记录留在本机私有证据，不输出匹配值。
- 导出目录/home/wmywb/CyberScientist-comp-export，与比赛目录分离；比赛目录没有.git。未导出auth.json、秘密库、数据库、运行工作区、原生记录、虚拟环境、日志、备份或历史归档。两层目录树只包含名称、类型和大小。
- 命令：tools/export_comp_snapshot.py --root /home/wmywb/CyberScientist-comp --output /home/wmywb/CyberScientist-comp-export；GitHub建私库、推送main、repo view、ls-remote。
- 安全回归：tests/test_comp_snapshot_cs19.py，3 passed in 1.17s；覆盖原始字节、凭据排除/脱敏、违规清单、清单字节失配、扫描不回显。

## W2 唯一真实冒烟

题目 `find-an-exactly-verifiable-counterexample-to-edge-7141d3ed`（weighted random forest），S4第1轮、closed、结束于2026-08-01。开始前本方导入记录0、Run0，与排练候选分开；本次唯一 Run `run_f9a4404816`、题目 `local_4a948751`。只验证契约占位通路，没有检验科学答案、计算不等式或运行评分器。

| 步骤 | 实际结果与证据 |
|---|---|
| 1 冷启动 | 比赛目录start-runtime.sh，首轮隔离HOME缺Node失败；补比赛Node后冷启动及自检0fail，74.11秒包含启动等待。最新版还增加工具宿主检查，避免RPC握手通过掩盖工具缺失 |
| 2 PI/批准 | 默认Astra xhigh、Terra high fast，原生握手priority；15:58:27启动，16:07:12研究简报和方法提案事件93/95，门关闭。Playwright真实Chromium按aria-label批准初始方法，真实POST200、2.19秒，之后门开放。SSE导致networkidle首次超时、历史告警弹窗阻挡的处理与100条旧告警未被确认均留有记录 |
| 3 探索 | trial_8a3d91e3ca，16:14:58创建至16:22:25 trial_complete，447.12秒。执行者现场写脚本，Bohrium沙箱真实短命令、生成submission.json、独立契约检查、result_package.zip；两项检查只确认placeholder，未声称反例 |
| 4 探索试构建 | ops submit --dry-run真实status=built，submission_created=false；科学输出仅outputs/submission.json；源包SHA47cf078789366fa2a5711ae0a7b12cad975ad197f4f93cf8c832628fc2feb1af，官方包SHA13380e037339212ba0bb564df63127385770fd5962109ee35bea6abb01d0dd0d |
| 5 干净复跑 | trial_6778aa2515，17:01:43创建至17:07:57 trial_complete，373.53秒。PI四段交接，新原生线程01a11fe5-9115-7963-8200-888a697597f4，不续用探索线程；cwd为新Trial目录，首个pwd/文件列表无旧Trial产物。新沙箱现场脚本重新生成同一契约占位文件，结果包和ops试构建均实际成功 |
| 6 同版本发布/续用 | ops release 667fa68重新发布同一版本，status=completed，17:12:08事件575读回原PI线程01a11fab-c781-7703-8403-e410413e6736，17:12:23事件577读回新执行者线程01a11fe5-9115-7963-8200-888a697597f4，模型/强度/priority仍匹配；快照7113d64fcf3b96e0811124757b8008cc2398111d，253文件扫描0 |
| 7 数据隔离 | Run实际paused、resume_on_startup=0；策略strategy_run_f9a4404816和两个trial_note通过经验API停用为retired，active_revision_id=null，正文未改、历史保留；有效经验索引不再选入这三条 |

时间为北京时间；私有原始证据放本机`.package-checks/cs-up-19`及比赛`.runtime/validation/cs-up-19`。首次PI工具调用因codex-code-mode-host缺失失败；暂停同一Run后，从与比赛Codex二进制SHA匹配的官方0.161.0 wheel迁移宿主及资源（非凭据），续用原线程恢复。首次ops试构建遗漏系统封存而失败，已机械修复为与提交相同的真实原生绑定；题面fenced `/app/submission.json`解析和根输出暂存也已补齐，不要求执行者伪造轨迹。

封包核对：实际额外官方CLI试构建包`w2-clean-official-built.zip`（仅私有本机）SHA为`d02e0715c9a359a9c11101fc23b545d76efde53e00dcbc2f282426f74c5fdaaf`。原生818491字节、SHA`a82bd403d7a03dbaec27e4cb3077793ccd3894a52a61a16739f3c5518b1f62dd`，首帧ID为新执行者。`native_trace/native.jsonl`逐字相等；`raw_messages.jsonl`仅多官方CLI的session_start首行，后面逐字相等，`traces/raw_messages.jsonl`与其相同。逐成员搜索旧探索ID和PI ID均0。科学文件SHA`543a4b3ba02e40c230203eb9a27356a094c44af621b0fa5ce18d12ec49dbcf27`与源输出相同。第一次核对误以为官方包只存一份原生副本而断言失败；实际三条路径均是同一新线程，没有旧轨迹混入。不同试构建的包SHA因CLI时间戳而不同，科学字节和原生字节逐项核对。

本卡新Run1、Trial2、沙箱2（均已deleted）、Job0、镜像0、真实提交0；数据库提交仍14、Job仍163、邮箱仍5。PI原生仅Astra、执行者仅Terra，没有只读审查/复盘模型调用；原生内部模型调用与费用计量仍unknown，不能把turn额度配置当作已完整计量。

## W4/W5 角色、交接和目录

附录角色文件逐字复制，加载到developerInstructions；三种真实原生前八帧分别出现roles/pi v1、roles/executor v1、roles/executor v1。缺失/空文件后端自检和新Run都失败，旧静默返回已删除。比赛端拒绝尚未确认该指令协议的非Codex提供商；开发端其他供应商协议保留。旧brain/prime归档到开发docs/archive，不发布；两个仍使用的collaboration文件保留。

fresh线程新Trial目录先于开会话创建为空，供应商之后创建只读.guard目录，不放旧Trial文件。首条消息附完整Run/Trial/交付目录/包名/真实原生绑定说明、环境和技能索引及固定trial_complete判据；四段同等校验并按流程/参数/验证/故障顺序拼装，不用PI goal/success_check。线程ID和cwd在同事务保存，重启或新建失败也不丢恢复位置。参数规则采用卡内原句，方法参数允许、探索科学结果数值禁止。

## W6 机械修复与发布目录依赖

已实现：迁移后ops默认比赛端、显式dev核对进程身份；PI能力索引三个计算入口明确由执行者调用；比赛专用Node放在`.runtime/bin/node`（不进Git），启动脚本及发布启动均优先此目录。官方CLI取同一Node，避免隔离HOME后丢失可执行文件。专项61 passed / 18.37秒，日志为私有`w6-tests.log`。

| 目录 | 处理 | 实际读取依据 |
|---|---|---|
| src/cyberscientist | 保留 | Python应用、原生协议适配器及运行时工具桥import |
| prompts/roles、prompts/collaboration | 保留 | role_prompts、kimi及controller会话开发者指令 |
| skills | 保留 | skills索引及read、Job模板附件；原生CODEX_HOME技能同步 |
| environments | 保留 | environment_catalog、compute与环境预检读取 |
| contracts | 保留 | decision.schema、collaboration.schema、experience-policy和mailboxes读取arm_protocol |
| vendor/playground_contracts | 保留 | 官方协议/评分器快照，public research及drift检查 |
| templates/lightchaser-user-prompt.md | 保留 | competition.py实际读取赛道用户提示；未被运行代码读取的experience.md/trial.md移出，缓存验证后裁剪 |
| tools/playground-cli/0.1.40 | 保留 | 固定官方CLI；integrity、package元数据与dist读取 |
| apps/web/dist | 保留 | API静态前端读取；每次从指定commit构建 |
| pyproject.toml、uv.lock、启动脚本、示例配置 | 保留 | 独立环境锁定、迁移/发布和冷启动 |
| evals | 移出 | 开发评估目录；比赛端显式拒绝开发评估目录入口 |
| challenges | 移出 | 仓库旧题参考数据；当前题从workspace/challenges读取，旧历史记录另行归档 |
| docs、tests、开发工具、旧brain/prime | 不发布 | 不属于比赛运行时 |
| experience、workspace、设置/数据库、HOME、CODEX_HOME凭据 | 运行时数据 | 不属于发布所有权，发布不覆盖、不导出内容 |

发布同时清理上一版清单拥有、这一版已移除的目录，备份放`.runtime/previous`；回归确认新题工作数据保持。每次成功ops release后自动扫描并更新私有比赛快照，扫描失败或推送失败如实报告`release_completed`，不冒充快照成功。

凭据独立性：本次账户ID、刷新令牌哈希比较均为“相同”，只保存比较结果，不保存值或指纹。用户需自行执行：

```bash
CODEX_HOME=~/CyberScientist-comp/.runtime/codex codex login
```

尚未验证：用户自行登录后两侧最小会话；不以原有共享登录冒充独立性。隐藏开发目录后的复验在最终测试结束后执行，避免把正在跑测试的源路径移走。

## W7 巡检与输入门禁

比赛数据库寿命观察读回`effective_ceiling_seconds=604800`。没有记录或值无效时不返回3600；比赛启动记录自检失败并持久化前端告警，显式检查同样失败。已有记录未修改。

maintain_due忙锁即跳过，独立周期任务与提交/存活链分开；真实线程关机仍受resource_coordinator管理。测试使用另线程持Run锁以及让巡检等待的应用lifespan，确认一秒内返回/提交推进，不用提示词替代结构隔离。cell-relax缺force_thr_ev或stress_thr，在check_inputs运行前明确列缺项；force_thr不替代。65 passed / 34.11秒，真实云Job未重复执行。

pg-*只读报告：[REPORT.md](https://github.com/Raven1119/cs-private/blob/e8238ab/reviews/pg_skills/REPORT.md)，32项逐目录调查、两项指定SHA仅相同/不同、七项逐字全文；8文件密钥扫描零命中，未启用任何pg技能。
