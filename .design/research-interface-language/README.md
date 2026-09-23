# Research Interface Language · 1.0.0

以最终的 **V9 源码动效版 + 冷石墨夜间色调**为固定基准。原 HTML 按字节保留，没有重新设计、替换动画或调整颜色。

## 直接开始

解压后双击 **`START.html`**。它提供完整演示、起步页、截图、安装命令和 Agent 提示词入口。完整演示不需要联网或安装依赖；观测场需要浏览器启用 WebGL/WebGL2。

## 安装到项目（推荐）

在解压目录打开终端，只把下面的项目路径改成自己的路径：

```sh
python install.py --project "D:/Projects/MyApp"
```

需要 **Python 3.9+**。macOS/Linux 使用 `python3` 也可以。没有 Python 时见下方“手动方式”。

这条命令为 Codex 安装 `.agents/skills/research-interface-language/`，并在项目 `AGENTS.md` 的专用区块写入引用，保留原有内容。该项目级通用技能目录也在 Kimi Code 的检索范围内。存在有效 `AGENTS.override.md` 时，Codex 接入口写到该覆盖文件中。

其他 Agent 可指定：

```sh
python install.py --project "D:/Projects/MyApp" --agent kimi
python install.py --project "D:/Projects/MyApp" --agent claude
```

分别使用 `.kimi/skills/` + `AGENTS.md`、`.claude/skills/` + `CLAUDE.md`。不要为同一 Agent 同时装多个同名全局／项目副本。路径依据与官方文档见 `references/AGENT_SETUP.md`。

安装只放入设计资料与引用，**不会改动项目业务代码、依赖、Git 配置或全局规则**。重复执行相同安装不会追加重复段落；不同内容的旧 Skill 默认拒绝覆盖。确实需要升级时添加 `--replace`，旧 Skill 和旧指令文件会备份到 `.design-language-backups/`。

安装后在项目内开启新 Agent 会话，粘贴：

> 使用 research-interface-language。先读取本项目中的 SKILL.md 并打开 reference.html，保留 V9 动效和冷石墨夜间基线。审计现有前端后，用这套设计语言完成本次页面任务，按项目业务安排布局，不复制演示任务与假数据。完成后验证日夜、窄屏、键盘和动效开关。

## 多项目全局使用

```sh
python install.py --global
```

默认安装到 `~/.agents/skills/research-interface-language/`，不修改全局 `AGENTS.md`。在每个项目明确要求使用该 Skill 即可。其他 Agent 用 `--global --agent kimi` 或 `--global --agent claude`。只在本机运行的 Agent 可读到本机全局目录；远程／云环境请用项目安装并把资料提供到远端。

## 手动方式（零脚本）

将解压后的整个 `research-interface-language` 文件夹放入项目 `.agents/skills/`。在项目指令文件粘贴 `templates/AGENTS.frontend.md` 的内容；已有 `AGENTS.override.md` 时放到当前有效文件。Claude 使用 `.claude/skills/` 和 `templates/CLAUDE.frontend.md`。随后开始新会话。

## 包里有什么

| 入口 | 用途 |
|---|---|
| `SKILL.md` | Agent 的短入口与工作流程 |
| `assets/reference.html` | 最新完整交互演示，原样保存 |
| `assets/tokens.css` / `tokens.json` | 带命名空间的颜色、字体、尺寸及动效参数 |
| `assets/primitives.css` | 自有基础控件样式，不覆盖项目全局样式 |
| `examples/starter.html` | 可直接打开的最小起步页：主题、书写和本地草稿 |
| `assets/motion-map.json` | 15 项动效的用途、上游链接、代码位置和真实方法签名 |
| `references/` | 视觉规则、动效规则、移植依赖、代码定位与验收 |
| `assets/screenshots/` | 从同一份 HTML 截取的日夜／窄屏参考 |
| `install.py` / `verify.py` | 安全安装与标准库完整性校验 |
| `tests/` / `VALIDATION.md` | 安装器测试、可选浏览器测试和本次实测记录 |
| `licenses/` | 原始许可证、改动说明与打包范围 |

第三方动效保留在完整演示应用中，并提供源码定位；没有把受限组件另行包装成一个可分发组件库。`starter.html` 使用自有外壳，不预载第三方动效。实际应用迁移方式见 `references/IMPLEMENTATION.md`。

## 校验

```sh
python verify.py
python -m unittest discover -s tests -p "test_*.py"
```

第一条核对文件 SHA-256、基准、tokens 与动效索引；第二条测试安装器的副本、备份、重复执行和路径处理。浏览器动态测试为可选项，环境要求在 `tests/browser_smoke.py` 文件头。实际已运行的项目见 `VALIDATION.md`。

## 更新设计语言

修改自己的项目组件，不要让单个项目未经确认地改写共享基线。确认共享修改后再更新参考 HTML、tokens、动效索引、截图及 VERSION，并重新生成 `manifest.json`。本版清单固定，不会自动追踪或下载上游 main。
