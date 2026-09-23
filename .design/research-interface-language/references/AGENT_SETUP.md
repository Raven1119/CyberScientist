# Agent 接入路径与来源

核对日期：2026-09-19。以下为官方文档的目录约定；安装器只在本机复制文件，不调用 Agent API 或修改权限。

| 选项 | 项目 Skill | 用户级 Skill | 项目引用文件 |
|---|---|---|---|
| codex（默认） | `.agents/skills/research-interface-language` | `~/.agents/skills/research-interface-language` | `AGENTS.md`；存在有效覆盖时 `AGENTS.override.md` |
| kimi | `.kimi/skills/research-interface-language` | `~/.kimi/skills/research-interface-language` | `AGENTS.md` |
| claude | `.claude/skills/research-interface-language` | `~/.claude/skills/research-interface-language` | `CLAUDE.md` |

Kimi 项目级也会检索 `.agents/skills`，所以默认项目安装可共用。这里提供 kimi 专用选项避免用户级通用目录选择的差异。

按需读取参考资料，SKILL.md 不应该包含全部代码。Codex 自动识别不保证每个泛化提示词都调用；需要固定风格时显式要求使用该 Skill。项目目录更深处的覆盖指令仍可能影响结果；安装器不修改所有子目录。

本机全局安装不会自动传到云会话。云端任务用项目安装并使目录出现在远端工作区。每个 Agent 尽量保持一个同名技能来源，避免不同副本互相遮盖。

手动显式入口：Codex `$research-interface-language`；Kimi `/skill:research-interface-language`；Claude `/research-interface-language`。也可以直接要求读取项目内的 SKILL.md。

## 官方来源

- Codex Skills（原 URL 会重定向至官方 Learn）：https://developers.openai.com/codex/skills/
- Codex AGENTS.md：https://developers.openai.com/codex/guides/agents-md/
- Claude Skills：https://code.claude.com/docs/en/skills
- Kimi Skills 官方源码文档：https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/customization/skills.md

以上为本次打包时的核对记录，不作为未来版本永久不变的保证。
