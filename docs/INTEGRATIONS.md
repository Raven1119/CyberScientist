# 外部集成与核查边界

核查日期：2026-09-17。来源索引见 REFERENCES。下面区分官方文档中已确认的能力与仍需现场验证的细节。

## Prime Agent

官方仓库提供 `prime-agent --mode rpc`，stdin/stdout 为 JSONL；命令包括 prompt、steer、abort、get_state 等。[S1] 后端以独立进程接入，保持 stderr 和协议 stdout 分离，严格按 LF 分帧，保留请求 ID 与异步事件的区别。

**先完成零模型调用的 get_state 探针**，再在用户允许额度的前提下做一次真实工具往返：让 Prime 通过 IPython 写入并读回一段测试文本。该测试验证工具执行/结果回传，不进行科研计算。再验证 steer、取消和会话恢复；未验证能力显示 unsupported/unverified。

自定义模型使用上游 `models.json`，已确认支持 `openai-completions`、`openai-responses`、`anthropic-messages` 等 API 类型，密钥可以引用环境变量。[S2] 本系统协议枚举经 ProfileCompiler 映射为上游名称。不要重复实现 token/tool-call 协议，也不要截断上游 reasoning/tool 结构。

生成项目隔离的运行时配置，并核实当前版本如何指定其目录。上游默认配置在用户目录；**本包没有确认每个版本的隔离目录环境变量或命令参数**。施工必须查源码/`--help` 并做“两 Profile 不串配置”测试，不能杜撰 `--config`，不能覆盖用户 `~/.prime`。

默认不启用 `/refine` 自动改写运行环境，也不自动导入全部个人 skills。允许的项目技能固定版本；新增候选经过测试用于下一 Trial。必要的 Python skill 应按照上游的真实导入与发现机制封装，不把普通 SKILL.md 直接当 Python 包。

## Codex 大脑

使用 `codex app-server` 的 stdio 接口。已确认连接初始化后可建立/恢复 thread、启动 turn、流式读取事件；已确认可以从实际 CLI 生成对应版本的 JSON Schema。[S3]

最小序列是 initialize → initialized → thread/start 或 thread/resume → turn/start → 读取终态。以实际 CLI 生成的 schema 校验适配器，不把网站示例中的模型 ID写为默认值。处理中如出现审批请求，必须响应或展示待批准，不能放任会话挂死。

原生登录优先；自定义供应商仅编译为该版本支持的项目隔离配置。连接设置同时显示“CLI 已安装”“身份可用”“所选模型已实测”三个事实。[S4] 不复制登录凭据到 workspace，不擅自打开危险的全权限模式。确认自定义配置没有破坏原生认证后才启用。

大脑最终消息解析为本系统 Decision；保留原始终态消息。未经支持性探针，不假设所有 schema 输出/interrupt/steer 参数跨版本通用。

## Kimi Code 大脑

使用 `kimi --wire`，Wire 提供基于 JSON-RPC 的双向 stdio 通信，包含 prompt、cancel、event 和需要客户端响应的 request。[S5] 对实际协议版本握手协商；不要把网站当前版本号锁成永久常量。

后端要处理 ApprovalRequest / QuestionRequest 等受支持的请求。显示给用户的审批用结构化描述；读取本 Run 文件等已授权动作可按有限策略批准，不使用无边界自动同意。未知请求类型返回明确不支持，不能静默丢掉。

Kimi 和 Codex 最终都输出同一 Decision，但原生消息、会话 ID 和恢复方法由各自适配器处理。Kimi 的可配置供应商、模型名称和认证配置以安装版本的文档/探针为准。[S8] 不承诺直接使用任意 OpenAI 兼容地址。

## Playground：题目与比赛提交

公开入口提示代理使用 `GET /api/docs`；检索到的官方索引展示了 challenge detail/content、Attempt 读取及“创建 Attempt → 上传 bundle”的两步路径。[S6] **本次未取得 `/api/docs` 与完整 Agent API 正文，未实际认证，未验证创建/上传字段、资格或评分契约。**

施工时从用户配置的 origin 获取官方文档，保存脱敏的协议摘要与日期，再实现并测试。建议验证的已公布路径如下，前缀由 `base_url=https://play.bohrium.com/api` 提供：

| 动作 | 官方索引展示的相对路径 | 本次状态 |
|---|---|---|
| API 文档 | `/docs` | 入口已发现；正文不可用 |
| 题目与内容 | `/challenges/{id}`、`/challenges/{id}/content` | 索引已发现；报文未实测 |
| 题目尝试列表/单次尝试 | `/challenges/{id}/attempts`、`/attempts/{id}` | 索引已发现；字段未实测 |
| 创建尝试 | `POST /challenges/{id}/attempts` | 索引已发现；认证/载荷待核实 |
| 上传结果包 | `POST /attempts/{id}/bundle` | 两步模式已发现；载荷/触发评分语义待核实 |

历史工作流使用过 `PLAYGROUND_USER_TOKEN`，可作为本系统 SecretRef 的环境变量约定；这不证明当前 API 的认证 header 或适用赛季。创建字段、文件名、zip 布局、大小限制、评分器名称、评分权重、正式截止时间、是否需要 Trace、允许尝试次数与自动化规则全部读取实际题目/平台说明，禁止硬编码历史值。

官方存在 ARM bundle 说明入口，但本次未读取正文。[S10] 首版先实现 bundle 允许清单/hash/脱敏与预览；具体比赛包结构只能在契约核实后启用。不能把任意 zip 上传成功当合格提交。

评分器状态只能从明确的公开文档、题目元数据、自己有权读取的 Attempt 反馈与平台公告判断。没有已证实的全局 health API；不能创造 `/grader/health` 或做试探性高频提交。“接口可达”“配置存在”“队列等待”“评分已完成”“评分可计入比赛”分别显示。

题面与元数据冲突时记录双方原文及时间，置 contract_status=conflict，阻止正式提交。允许继续不依赖冲突项的离线工程工作或用户明确授权的探索。不要把上一场赛季或旧评分器套到当前题目。

## Bohrium 科学计算

使用官方 bohr CLI 及 dptech-corp/bohrium-skills 中相关任务/文件/项目说明。已核实官方 skill 集合包含 Job、文件、项目等能力，使用 Bohrium AccessKey 认证。[S7]

本系统自己的配置字段为 `access_key_secret_ref` 与 `project_id`。当前 CLI 究竟读取 `BOHR_ACCESS_KEY` 还是 `ACCESS_KEY`、支持哪些 host override，施工必须从 `bohr --help` 和安装版本确认后按需注入，禁止把历史变量全部塞入所有进程。

先进行版本/帮助和只读项目访问验证，不自动安装大型科学环境。第一个真实科学环境 smoke Job 需用户授权资源、时限和额度；远程验证依赖安装、命令执行、输出取回和结果来源，再开展题目计算。

JobSpec 由用户允许的项目、镜像、机型、资源、时限、脚本和输入清单组成。提交、查询、取消、取回映射到当前 CLI 的实际参数。bohr 未安装或认证失败时绝不回退本地科学计算。

## 必须落地的验证记录

写入 `docs/INTEGRATION_STATUS.md`（施工时创建），每种连接记录实际版本/commit、探针命令、日期、脱敏响应位置、已证实能力、未知项和复现方法。外部文档可以变动，必须将实测版本保存在运行 manifest。

没有凭据时允许使用**显式手写测试 fixture**来开发状态机；这种 fixture 必须标记 synthetic，不能放进“真实协议回归录制”目录。获得一次授权真实响应后再追加真实脱敏 fixture，校验适配器的假设。
