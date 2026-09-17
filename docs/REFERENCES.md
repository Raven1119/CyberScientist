# 官方来源与证据边界

核查日期：**2026-09-17**。文档中的架构、UI、内部 schema 是本项目设计；标记 `[Sx]` 的内容关联下表外部事实。源码 main 和在线文档可变，施工需另行固定实际版本。

| 编号 | 官方来源 | 本次确认内容与限制 |
|---|---|---|
| S1 | [Prime RPC](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/rpc.md) | 已读取官方 RPC 文档，确认 stdio JSONL 与基础控制命令、steer 排队语义；未运行 CLI |
| S2 | [Prime custom models](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/models.md) | 已读取配置文档，确认 API 类型、自定义模型与密钥引用；未验证用户具体供应商 |
| S3 | [Codex App Server](https://developers.openai.com/codex/app-server) | 官方页面本次转至 learn.chatgpt.com；确认 stdio、初始化、线程/回合和按 CLI 生成 schema；未启动进程 |
| S4 | [Codex configuration](https://developers.openai.com/codex/config-reference) | 官方配置入口已读取；用户原生认证与自定义配置隔离仍需现场探针 |
| S5 | [Kimi Wire](https://moonshotai.github.io/kimi-cli/en/customization/wire-mode.html) | 已读取官方双向协议说明与 prompt/cancel/event/request；不锁定在线展示的协议版本 |
| S6 | [Playground 首页](https://play.bohrium.com/) / [提交技能入口](https://play.bohrium.com/skill/submit-attempt) | 公开搜索索引给出 `/api/docs`、challenge/attempt 路径和两步提交模式；页面动态内容及完整 API 正文未成功取得 |
| S7 | [Bohrium skills](https://github.com/dptech-corp/bohrium-skills) / [Job skill](https://github.com/dptech-corp/bohrium-skills/blob/main/zh/bohrium-job/SKILL.md) | 已读官方仓库与 Job 文档入口；确认算力管理与 AccessKey 体系，未用用户凭据验证 CLI |
| S8 | [Kimi configuration files](https://moonshotai.github.io/kimi-cli/en/configuration/config-files.html) | 已读取官方配置入口；具体 provider 能力以安装版本为准 |
| S9 | [Prime usage](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/usage.md) | 官方使用说明描述持久 Python 控制环境；不作为崩溃后 kernel 内存可恢复的证据 |
| S10 | [ARM bundle 文档入口](https://play.bohrium.com/docs/arm-bundles) | 搜索确认入口存在；动态正文未取得，不据此编造 bundle 格式 |

## 本次不能宣称已经核实

比赛赛季和精确规则、剩余资格/尝试次数、截止时间、评分器契约、用户配额、实际模型访问权限、两步提交的报文字段、Prime 项目隔离配置参数、各 CLI 安装版本与提交 SHA。

设计依赖上述事实的部分使用 `unknown / unverified / needs_authorization`，在实际环境核查前不开放相关正式写操作。源页面存在不等于用户账户可访问；HTTP 200 不等于 grader 健康。

## 本次工程包验证与接口验证不同

本包可以验证文件完整性、JSON/YAML 结构和前端原型行为。没有对真实 Codex/Kimi/Prime 模型调用、Bohrium 算力或 Playground 提交进行测试；后续 STATUS 不得混淆这些层次。
