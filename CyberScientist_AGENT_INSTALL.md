# 给接入 Agent 的说明

## 1. 目标与明确边界

将本包的实际经验文件登记到 CyberScientist 的 Markdown + SQLite 经验库；保留现有内容与修订。默认完成：12 条全局候选，以及已存在非 Demo 题目的题内冷启动组合。题内副本允许使用但全部保持 hypothesis。

本任务不授权模型调用、科学计算、账号注册、比赛提交、覆盖全局提示词或偷偷审批全局候选。不要执行 `reference` 中带历史平台副作用的其他仓库脚本。本包只附三个隔离复现脚本，它们也不需要平台凭据。

Bug 处理按 `docs/BUG_FIXES.md` 进行。本包没有将未实现的持续学习功能包装成已经运行的模块。只接入内容库时，到导入验收即结束；用户另行要求实施修复/运行时升级时，再使用同包中的规格与测试断言。不要把任务无限拆分。

## 2. 解压到哪里

目标仓库根目录记作 `<repo>`，必须同时有 `pyproject.toml` 和 `src/cyberscientist/{config,db,experiences}.py`。先从当前工作目录/用户明确指定的路径定位，不猜测用户电脑盘符。

压缩包固定包含一级目录 `CyberScientist_Experience_Kit_v1/`。解压到：

```text
<repo>/.incoming/CyberScientist_Experience_Kit_v1/
```

真正的接入位置由导入器建立：

```text
<repo>/experience/global/csx1_*.md
<repo>/experience/challenges/<真实本地题目ID>/csx1_*_c<题目哈希>.md
<repo>/docs/experience_kit_v1/*.md
<repo>/.cyberscientist/experience_imports/<时间戳>/receipt.json
```

**不要直接覆盖解压到 `experience/`**：旧版外部文件不自动登记修订，单纯复制会留下正文/版本错配。根目录说明、修复文档和模板也不能混入 `experience/global/*.md`。

Windows PowerShell（只替换 zip 与仓库路径；不要把尖括号作为真实路径）：

```powershell
$repo = (Resolve-Path "C:\实际路径\CyberScientist").Path
$zip = (Resolve-Path "C:\实际路径\CyberScientist_Experience_Kit_v1.zip").Path
$incoming = Join-Path $repo ".incoming"
Expand-Archive -LiteralPath $zip -DestinationPath $incoming
$pack = Join-Path $incoming "CyberScientist_Experience_Kit_v1"
Set-Location $repo
uv run python "$pack/tools/experience_pack.py" check-package
uv run python "$pack/tools/experience_pack.py" inspect --repo "$repo"
uv run python "$pack/tools/experience_pack.py" install --repo "$repo" --bind-existing
```

Linux/macOS：

```bash
REPO="/实际路径/CyberScientist"
ZIP="/实际路径/CyberScientist_Experience_Kit_v1.zip"
mkdir -p "$REPO/.incoming"
unzip -n "$ZIP" -d "$REPO/.incoming"
PACK="$REPO/.incoming/CyberScientist_Experience_Kit_v1"
cd "$REPO"
uv run python "$PACK/tools/experience_pack.py" check-package
uv run python "$PACK/tools/experience_pack.py" inspect --repo "$REPO"
uv run python "$PACK/tools/experience_pack.py" install --repo "$REPO" --bind-existing
```

同名 staging 已存在时先校验，不盲目 `-Force` 覆盖。`check-package` 和 `inspect` 不修改数据库；省略 `--apply` 的安装/绑定只预览。安装器依赖 PyYAML，优先使用仓库现有的 `uv run` 环境，不改全局 Python。

## 3. 接入与验证

先检查预览中的题目、profile 与 preserve_existing；`auto` 仅按明确标题/slug 词匹配，不知道题型就用 core。不要把自动匹配当作题面或数据可用性的验证。无题目时只能得到全局候选；先通过原产品导入真实题目，再 bind，不创建虚构题目。

应用写入必须取得与产品相同的工作区文件锁。若后端仍在运行，脚本会拒绝。先确认无正在执行或等待远程任务的科研 Run，再按项目正常方式停止后端；**不要为了导入杀掉用户科研任务**。只停止浏览器并不等于停止后端。

```text
uv run python "<pack>/tools/experience_pack.py" install --repo "<repo>" --bind-existing --apply
```

导入器先备份数据库（包含已提交 WAL 内容）及 experience 目录，再登记每条新修订并写 ID 文件；不读取或打包 `secrets.json`。生成 `receipt_path` 后执行：

```text
uv run python "<pack>/tools/experience_pack.py" verify --repo "<repo>" --receipt "<receipt_path>"
```

必须得到 `verified=true`。对 `preserve_existing` 的条目另行说明：它们有用户版本，未覆盖，不能把它们计为新导入成功。然后重复同一安装命令，确认已有条目为 unchanged / preserve_existing，且没有重复修订。

按仓库原方式启动后端，检查经验页可看到候选、题内副本、hypothesis 标签与修订。无需发起真实科研 Run 验证显示；内容被列出不代表已被模型采用。旧版 B08 会影响手动新建，导入无需点击新建按钮。

精确绑定单题：

```text
uv run python "<pack>/tools/experience_pack.py" bind --repo "<repo>" --challenge "<数据库中的本地ID>" --profile numerical_reproduction
uv run python "<pack>/tools/experience_pack.py" bind --repo "<repo>" --challenge "<数据库中的本地ID>" --profile numerical_reproduction --apply
```

在 B06/B20 修复前，不批量批准本包全局候选；旧审批路径会改写证据等级且不绑定版本。题内副本不依赖该审批路径。

可用 profile：`core`、`numerical_reproduction`、`inverse_problem`、`atomistic_simulation`、`ml_finetuning`、`resource_blocked`、`literature_start`。默认 `auto`。给同一题增加第二个 profile 会保留先前绑定，不自动退役；避免一次堆入所有组合。是否改变实际检索预算由后续 B10 修复统一处理。

## 4. 异常、版本变化与撤回

存储源码变化或存在 `experience_heads` 时，旧表导入器拒绝写入。此时根据 `docs/INTEGRATION.md` 使用新版原生创建接口，或由 agent 先适配导入器并在临时副本验证；**不要强行跳过版本检查直接写旧表**。

导入中断：保留 receipt、备份和 applied=0 记录。若仅缺文件且 pending 记录与本包字节完全一致，重复安装可完成它；已存在不完整/不同字节时停止自动恢复，不覆盖，按 B03 的对账流程处理。不要删除历史来“让检查通过”。

撤回本次新建且未被后续修改的条目：

```text
uv run python "<pack>/tools/experience_pack.py" retire --repo "<repo>" --receipt "<首次安装receipt>"
uv run python "<pack>/tools/experience_pack.py" retire --repo "<repo>" --receipt "<首次安装receipt>" --apply
```

退役新增修订并保留旧历史；已被用户修改/审批/删除的条目跳过。不要拿“重复安装”的收据撤回首次导入，也不要在产生新 Run 后整库恢复旧备份。新文件异常只针对本次导入对账，避免抹掉其他后续写入。

## 5. 向用户报告完成

只报告：仓库/基线、实际新增 global candidate 与 challenge active 的数量、采用的题型组合、收据路径、完整性及读回验证、保留的冲突/旧版限制。没有做的真实调用与 bug 修复明确写未执行，不拿历史测试数量充当本次结果。
