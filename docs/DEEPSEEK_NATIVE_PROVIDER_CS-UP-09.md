# CS-UP-09 W5：原生 DeepSeek 与角色配置

四角色（PI、求解者、审查者、复盘）分别保存提供方、原生运行时、模型和推理强度。DeepSeek 使用 Codex，模型 `deepseek-flash`，强度 low/high/max；原生线程必须回读确认模型、强度及 DeepSeek 提供方，禁止静默切换。复盘新默认 DeepSeek/high，审查者 Codex `gpt-6.1-sol/high`。已有显式设置保留。

后端优先读取 `DEEPSEEK_API_KEY` 环境变量，其次只读仓库根目录已忽略的 `.env`。项目 DATA_DIR 下独立 `codex-deepseek/` 只写公开 TOML 和模型目录；使用 `env_key`，认证值只进原生进程环境，不进入线程配置、工具 shell allowlist、提示词或保存文件。公开配置使用原子替换，用户全局配置和认证未修改。统一脱敏覆盖原生错误、stderr、研究简报、经验、数据与远端回执等持久化边界。

连接页提供有界的一次真实工具探针，授权后才能启动；成功需要完成的原生读取工具回执及内容一致，接受线程或 HTTP 成功不够。Prime 工具探针协议尚未核实，会在任何模型调用前明确返回 unavailable，不能错误改用 Kimi。

求解者条目带唯一 ID、名称和 PI 备注。整轮、逐题及追加 Run 可选择条目；确认时冻结规范化条目，追加默认沿用已冻结配置，后续修改条目不改变旧 Run。手动编辑模型会清除条目选择。分诊获得完整条目清单，可推荐已有具体 ID。

用量按实际原生 session 的单调累计计数记账，同一 session 多次通知不重复加总；缺 session、缺累计值、回退计数和未观察角色保持 unknown。价格来自配置，保留币种、来源、观察日期和时段；时段/缓存未知显示上下界，未报价模型及实际账单不填零。独立提供方会话和 429 退避覆盖普通研究、分诊、探针与维护，不重发未知维护调用。

实际验证（2026-10-05，隔离数据库与工作区）：Linux Codex 0.159.3 + `deepseek-flash/high` 完成一轮只读随机文件工具探针，工具状态 completed、exit=0、内容一致。累计 input=24564、cached input=12160、output=123；这些是原生用量观察，非最终账单。后续零 turn 原生线程回读确认 provider=deepseek、model=deepseek-flash、effort=high。未创建科研 Run、Job、沙箱或 Attempt。原始回执和身份只在本机忽略目录；W8 将另验实际求解者研究闭环。

依据：[DeepSeek Codex 集成](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)、[DeepSeek 价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Codex 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。官方集成示例的全局目录／文件 bearer token 写法被用户授权边界替换为项目独立目录和 env_key；公开模型目录只包含必要元数据与本项目自己的简短指令。
