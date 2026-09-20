# CyberScientist 协作施工包

**交付类型：施工文档、静态代码审计和可检查的协议样例。这里没有宣称已实现新后端。**

将包内目录合并到当前 CyberScientist 根目录，从 [单次任务卡](../../START_KIMI_SHADOW.md) 开始。包中不包含替换版根 AGENTS.md，也不覆盖旧应用文件。

| 文件 | 用途 |
|---|---|
| [SPEC.md](SPEC.md) | 目标、静默语义、调度、UI 和经验边界 |
| [CONTRACTS.md](CONTRACTS.md) | 唤醒工具、观察帧、决定、投递和恢复 |
| [CODE_AUDIT.md](CODE_AUDIT.md) | 固定版本的实际代码发现及接入位置 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 一次施工必须通过的行为测试与交付证据 |
| [contract.schema.json](contract.schema.json)、[examples.json](examples.json) | 可写入消息的约束和合成样例 |
| [大脑片段](../../prompts/collaboration/brain.md)、[执行器片段](../../prompts/collaboration/executor.md) | 接入实际提示词构建器，不能只放文件不加载 |

设计文件与实际代码不一致时，以本次用户目标、可靠性约束和核实后的最小实现为准；源码中的旧默认行为不自动成为正确规格。适配器字段以本机 CLI 版本和真实协议探针为准。

包内验证：在仓库根目录运行 `python checks/validate_collaboration_pack.py`（需要 `jsonschema`）。它只验证文档链接、Schema、样例与少量协议反例，不测试 CyberScientist 应用。
