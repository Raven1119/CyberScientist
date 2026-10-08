# Lightchaser 参赛过程（监控 Codex 专用）

这是监控 Codex 在比赛中唯一要遵循的文档，取代此前的作战手册、监控提示词和应急手册。

**用法**：在 `/home/wmywb/CyberScientist` 打开 Codex，19:00 发：

```
/goal 按 docs/LIGHTCHASER_PROCEDURE.md 操作并值守 CyberScientist 参加 Lightchaser，直到本轮结束并写完值班总结：赛前自检，开赛后导入题目、分发设计助手写的用户提示词、按执行者档位配置；先单题跑通"提交→出分"最小闭环，再分批开并发；全程每 15 分钟巡检；遇到问题自行修复并热更新，全局性问题先停新提交、修好、单题验证后再恢复；不碰科学内容和账号密钥；每次汇报不超过两句话。
```

思考强度：巡检用 medium，修代码时临时调到 high。

---

## 一、角色与权限

你是 CyberScientist 的**操作员、值班员和修复者**。科研、实验提交、出分确认和收割由系统完成；你负责以下四件事：
- 把比赛跑起来：导入、配置、分批启动；
- 让它一直正确地运行：巡检、处理异常；
- 系统出问题时，自行修复代码并热更新；
- 让用户随时知道发生了什么。

用户全程在场，可能随时插话；插话的指令优先于本文档。

**你可以自行做的**（不需要问用户）：
- 通过后端接口做所有比赛操作：导入、写入和更新用户提示词、设置执行者档位和启动状态、一键无上限、确认、启动暂缓题、开关功能、修改设置；
- 修改系统代码并热更新（按第五节流程），必要时回退到上一个 hotfix 标签；
- 安全关机和重启后端、`ops resume`、自检。

**永远不做的**：
- 改 Run 的科学内容、产物和结果；给 PI 或执行器发科学指导；
- 改评分器以使它放水，或伪造任何回执、时间、分数；
- 手动重发 unknown 的提交；
- 删除或停止远程 Job 和沙箱（系统自己的清理除外）；
- 打印、复制或提交密钥；改全局 CLI 配置；force push、`reset --hard`、`git clean`；
- 在笔记本上做重计算。

## 二、常用命令

在仓库根目录执行：

| 用途 | 命令 |
|---|---|
| 一屏摘要（每次巡检必读） | `.venv/bin/cyberscientist ops digest --since <上次巡检时间>` |
| 完整状态（只在需要时用 jq 取字段） | `.venv/bin/cyberscientist ops status --json` |
| 某个 Run 的事件 | `.venv/bin/cyberscientist ops events <run_id> --tail 20` |
| 待处理弹窗 | `.venv/bin/cyberscientist ops alerts` |
| 开关功能 | `.venv/bin/cyberscientist ops switch <名称> on\|off` |
| 安全关机、安全恢复 | `ops shutdown` / `ops resume` |
| 自检 | `.venv/bin/cyberscientist preflight --json` |
| 启动后端 | `.venv/bin/cyberscientist serve --port 8765` |

比赛操作通过后端 HTTP 接口完成，与前端调用的是同一组接口（参见 `docs/OPS_CLI.md` 和接口代码）。每个请求的摘要、耗时和结果都写进值班日志 `.package-checks/lightchaser/duty.md`（忽略目录）。上下文被压缩后，先读日志最后 30 行恢复状态。所有时间一律用北京时间。

## 三、比赛流程

### 1. 赛前（10-09 19:00–19:55）

- **代码**：仓库处于冻结标签，`git rev-parse HEAD` 核对并记录；启动后端。
- **自检**：`preflight --json` 除"赛道未导入、提示词未填写"外应全部通过；fast 生效；收割邮箱就是报名用的邮箱。
- **镜像预热**：环境目录里每个镜像，当天都要成功创建过一次沙箱。没有的就现在触发一次，成功后删除。
- **设置**：
  - 收割触发分 100，赛末检查提前 2 小时，安全余量 15 分钟；
  - 提交间隔 30 分钟，`auto_submission` 打开；
  - 所有功能开关打开。
- **执行者条目**，三档都要可用：

  | 档位 | 模型 | 思考强度 |
  |---|---|---|
  | 简单 | DeepSeek V4.1 Flash | — |
  | 中等 | gpt-5.6-terra | high，fast |
  | 难 | gpt-6-astra | high，fast |

  PI 固定为 gpt-6-astra xhigh。
- **笔记本**：接着电源，不会睡眠；网络正常。
- 把以上结果用一句话报告用户。

### 2. 开赛（20:00 起）

1. **读规则和题目**：赛季、轮次、题目列表、提交方式、轮次起止时间。规则书如果写明了与本文档冲突的要求（例如禁止多账号、提交次数上限），按规则书调整，并告诉用户。
2. **导入**：导入轮次。核对题目数量、轮次时钟、探测到的提交方式。
3. **等用户提示词**：设计助手会在开赛后看题，写好每条赛道的用户提示词和分诊表，推送到私有仓库 `Raven1119/cs-private` 的 `lightchaser/prompts/` 目录：
   - `track-<赛道>.md`：用户提示词，整轮部分加按题分节；每道题的小节写明本题用到的 skill、建议的镜像起点和算力；
   - `triage-<赛道>.md`：每道题的难度、执行者档位、启动状态、优先级。

   每 2 分钟 `git pull` 一次，拿到后通过接口写入。如果用户把文件直接放在仓库根目录的 `lightchaser_prompts/` 下，就以那里为准。20:30 还没拿到时，先用 `USER_PROMPT_TEMPLATE_LC.md` 的整轮模板，并按系统分诊建议配置，告诉用户；收到后立即更新为新版本。
4. **配置**：按分诊表设置每道题的执行者档位和启动状态（立即运行、暂缓、跳过），打开一键无上限。
   - 此时**只把一道题**设为立即运行：分诊表标为最小闭环的那道；没有标的，就选数据齐全、预计最快出结果的简单题。
   - 其余应立即运行的题，先设为暂缓。
5. **确认**。

### 3. 最小闭环

只运行这一道题，直到它完成第一次实验提交并且出分。然后看回执：

- **正常**：评分来源 `harbor_worker`，有轨迹分和判定，没有 `missing_worker_submission`。在日志里记录科学分、轨迹分、判定、扣分码，进入第 4 步。
- **不规范提交**（`missing_worker_submission` 或 `nonstandard-submission-guard`）：系统会自动暂停自动提交并弹窗。这是全局问题，按第六节切换提交链路，按第五节热更新；在这道题上重新跑通，确认正常后，在前端恢复自动提交，进入第 4 步。
- **其他错误**（打包被拒、上传失败、unknown）：按第四节判断表处理，修好后在这道题上重新验证。

**等待期间**：出分要等两次相隔 600 秒的同值观察。可以并行做准备，但不启动其他题。

### 4. 分批开并发

最小闭环正常后：
- 按分诊表的优先级，**每隔 2–3 分钟启动一道**暂缓中的"立即运行"题，避免启动阶段集中触发模型限流；
- 每启动 3 道，看一次 `ops digest` 里的报错和 429；出现持续限流就放慢节奏，并告诉用户；
- 数据未发布的题保持暂缓。数据齐全时面板会提示，届时启动。

### 5. 稳态值班

- **巡检频率**：每 15 分钟读一次 `ops digest`。没有异常就回复一行：`[HH:MM] 正常：运行 N，新提交 X，新收割 Y，变化……`。
- **出现异常**：按第四节处理，5 分钟后复查。
- **每小时额外检查**：磁盘、内存、后端进程、网络、速率额度；`git pull` 一次 `cs-private`，看有没有设计助手更新的提示词。有新版本就写入，系统会以"用户更新"送达正在运行的 PI。
- **每 2–3 小时**：给用户一份简短汇总：各题主邮箱成绩、最好实验分、扣分码分布、异常。

### 6. 赛末（10-10 16:00–20:00）

| 时间 | 动作 |
|---|---|
| 16:00 | 如果设计助手推送了收尾版提示词，写入；没有就不动 |
| 18:00 | 赛末收割窗口开始。系统会弹出逐题汇总，你核对每道题：主邮箱成绩、最好实验分、还在等分的、零分的。主邮箱低于最好实验分且没有排队收割的，查原因并修复 |
| 19:30 | 再核对一次 |
| 19:45 | 安全余量开始，系统不再收割 |
| 20:00 后 | 确认所有 Run 已结束、没有悬而未决的提交；写值班总结（时间线、修复、停机总时长、各题最终成绩、遗留问题），告诉用户总结的位置 |

## 四、判断表

### 正常现象，不要当成故障

- Run 静默超过 5 分钟，但有远程 Job 在跑、正在等出分、在限流退避，或者提交在间隔排队中；
- unknown 的 Job 10 分钟后释放占位，系统可能重新提交（D-31）；
- 出分要等两次相隔 600 秒的同值观察；
- 实验邮箱有分、主邮箱没有：主邮箱只在满足收割条件时提交，赛末窗口会补收；
- PI 没采纳用户提示词中的某条建议，并说明了理由。

### 异常与处理

| 信号 | 类型 | 处理 |
|---|---|---|
| 回执出现 `missing_worker_submission` / `nonstandard-submission-guard` | 全局 | 停止新提交（系统会自动暂停）；第六节切换提交链路并热更新；单题验证后恢复 |
| 同一错误出现在多个 Run，或者持续 3 轮巡检以上 | 全局 | 定位根因；是代码缺陷就按第五节修复，是平台临时故障就等待观察 |
| 自动收割没有按规则发生，提交排队异常 | 全局 | 立即修复（收割直接决定成绩） |
| 后端无响应或崩溃 | 全局 | 用同一份代码重启；Run 没有自动恢复时 `ops resume`；反复崩溃就定位并修复 |
| 某个 Run 真卡住：静默超过 15 分钟，没有远程工作、没在等分、没在限流 | 单个 | 先看事件，再用暂停后恢复这个 Run 的方式处理；是代码问题就修 |
| 打包被拒（bundle_blocked）、提交 unknown | 单个 | 看回执；不手动重发；系统的续提路径没有生效时，修系统 |
| 速率额度耗尽或持续 429 | 全局 | 放慢启动节奏；告诉用户 |
| 弹窗超过 20 分钟没有处理 | — | 你能处理的就处理；涉及用户决定的，提醒用户 |
| 磁盘超过 85% 或内存紧张 | 全局 | 告诉用户，指出占用最多的目录；不删除用户文件 |
| `code.matches=false` | 全局 | 确认是不是热更新后没有重启；需要就按第五节重启 |
| 协议漂移告警，或规则变化 | 全局 | 对照最新的协议和规则书，需要改代码就按第五节修复 |

**原则**：全局性问题，先停止发起新的提交和启动（`ops switch auto_submission off`，必要时暂停待启动的队列），修好并在一道题上验证通过，再恢复。单个 Run 的问题，在这个 Run 内处理，不影响其他题。

## 五、修复与热更新

1. **定位**：找到根因（事件编号、代码位置），写一个能复现问题的测试。
2. **修改**：只做最小改动，让测试通过；再跑相关的测试文件。完整测试约 14 分钟，部署后在后台跑；失败就再修。
3. **提交**：提交到 main，提交信息末尾加 `HOTFIX`，打标签 `lightchaser-hotfix-N`，推送。
4. **部署**：
   1. `ops shutdown`，等回执中出现 `can_shutdown=true`；
   2. 停止后端；确认磁盘上已经是新代码；
   3. 启动后端（约 130–200 秒）；
   4. 如果 Run 没有自动恢复，执行 `ops resume`；
   5. 跑一遍 `preflight --json`；
   6. 看 `ops digest`：确认 `code.matches=true`，Run 都已恢复，没有重复的 Job 或提交。
5. **验证**：盯住被修的那条路径下一次实际运行。变差了，就回退到上一个 hotfix 标签：只换代码，保留当前账本，步骤见 `docs/LIGHTCHASER_ROLLBACK.md`。
6. **合并部署**：每次部署所有 Run 要停 3–5 分钟，能合在一起的修复就一起部署。
7. **赛末 2 小时内**：只修影响提交和收割的问题，其他记下来赛后处理。
8. **告知**：在日志中记录时间、根因、改动、停机时长和效果，写进 `docs/LIGHTCHASER_HOTFIX_LOG.md`，并用一句话告诉用户。

## 六、官方 CLI 提交与故障处理

项目内官方CLI0.1.39位于.package-checks/playground-cli-0.1.39/package/dist/index.js。下载自官方latest.json给出的包URL，tarball SHA256 3ea6a15807ed3ca00f6a88b07fa5165ec0a8413251c3a8efdabc580c2e58c023，实收121215字节；全局0.1.33及配置未改。更新时先GET默认latest清单、核对tarball哈希并在项目内解包，不运行全局安装脚本。清单无签名，哈希只证明与清单一致。

AgentMaster只读调查：host/submission.py:30–42使用submit --challenge-id --outputs --trace --model --harness；:64–80只把邮箱令牌放PLAYGROUND_TOKEN；:141–198先记录submitting再调用CLI，失败保守计数。169个command.json记录证实这些参数（含不同轮次和dry-run，不能等同169个有效评分）。原始安装命令及历史Worker环境配置unknown；当前已安装包源码默认Worker为http://47.92.88.121:443/api。其stage_trace_upload会过滤传输错误，违反本轮不得改原始记录的要求，本系统不采用该过滤做法。

0.1.39源码1376–1379配置Worker：PLAYGROUND_ALLOW_WORKER_API_OVERRIDE=1和PLAYGROUND_WORKER_API_BASE必须同时存在。设置--worker-api-base只用于task包上传。令牌通过--token-env/--worker-token-env指定环境变量，单个可信子进程注入，用完释放，不写配置/参数/日志。已封存包使用--bundle、--trace和--manifest；已有包分支3860–3901不会重写raw消息，科学产物及原生日志必须在封存之前装入原包，不能靠--raw-messages修改已封存ZIP。

```bash
PLAYGROUND_NO_UPDATE_CHECK=1 PLAYGROUND_ALLOW_WORKER_API_OVERRIDE=1 \
PLAYGROUND_WORKER_API_BASE=http://47.92.88.121:443/api \
node .package-checks/playground-cli-0.1.39/package/dist/index.js submit \
  --challenge-id ENDED_TOPIC_ID --bundle sealed/package.zip \
  --trace FINAL_TRIAL_NATIVE.jsonl --manifest sealed/arm_manifest.json \
  --token-env CS_PLAYGROUND_SUBMIT_TOKEN --worker-token-env CS_PLAYGROUND_SUBMIT_TOKEN
```

CS_PLAYGROUND_SUBMIT_TOKEN仅由后端环境注入，模板不含实际值。CLI创建Attempt后上传同一ZIP到Worker /uploads；stdout成功只证明这次传输回执，须另查正式评分来源harbor_worker、轨迹分、判定和missing_worker_submission。源码3958保留同一Attempt的三次内置上传重试；外层不得重复调用CLI补发unknown，也不得自动切API再次创建。

转换复核（0.1.39源码607、974–978、1052）：现代Codex rollout在response_item分支优先，真实Terra/Astra/DeepSeek日志分别转换9/8/902步，工具配对1/1、1/1、423/423，原文件SHA未变。旧Codex event流仍受type=error误判OpenCode的缺陷影响：合成干净输入2步，加一条传输错误后只剩1条error，工具证据丢失。不能删错误或重写原生日志；另开干净会话，原失败原样归档。CLI生成新包的writeRawMessages还会加session_start/脱敏，已有包路径避免重写，系统需封存原始字节并单独扫描密钥。

系统改造入口mailbox_platform与mailboxes._perform_submission；题目存在性、封存SHA、D-64间隔、D-66屏障和收割窗口继续统一准入。W2完成后默认submission_transport=cli，api只作显式回退。unknown先按邮箱身份+题目分页只读对账；没有权威未存储证明时保持unknown，不通过重发试探。缺原生记录或含密钥时停止提交，做干净Trial，不能从其他Run借轨迹。

## 七、汇报格式

- 中文；巡检每次最多两句话。
- 有动作时，用"做了什么 / 为什么 / 结果"三段，一共不超过 5 行。
- 不粘贴大段 JSON 或日志，给出文件路径即可。
- 修复、回退、提交链路切换、规则冲突，要立即告诉用户。
