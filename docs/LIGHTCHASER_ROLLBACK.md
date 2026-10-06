# Lightchaser 比赛中回退：只换代码，保留当前账本

比赛中使用最新实际验证的标签，保留当前 `.cyberscientist/`、`workspace/` 和 `experience/`。恢复比赛前旧数据库会丢失 Run、Attempt、评分、额度及远程任务关联；旧数据库仅用于离线取证或当前账本损坏后的专项恢复，不能作为版本回退的常规步骤。

标签起点：fallback-0=`5940418`，fallback-1=`ec5e24b`，fallback-2=`20069d7`；CS-UP-12 完整验收后的 fallback-3 是新赛道功能的回退起点。标签不代表比赛资格、unknown 已解决或真实整轮彩排已通过。

1. 在当前 Linux 后端执行 `.venv/bin/cyberscientist ops shutdown`，等待 `can_shutdown=true`。若原生关闭或远程操作 unknown，保留屏障和句柄，先读 events/status；没有确认前不能强杀再恢复。远程 Job/沙箱可能继续运行和计费。
2. 停止后端，记录 HEAD、工作区及当前一致性备份。保留未跟踪任务卡、经验和产物；另存跟踪改动，确保切换代码不会覆盖它们。
3. 在同一仓库目录切到已验证标签，保留当前数据和凭据。无需恢复任何旧 SQLite、settings 或 workspace。
4. **普通 `serve` 会在启动对账后自动恢复明确的安全关机意图，并非只读启动。** 启动生产账本前，先用一致性副本和禁止派发的维护守卫核查所选代码的加载commit、账本记录与对账；本卡的副本验证记录见下文。确认兼容、原生关闭和恢复授权后，再启动当前账本，这一步同时允许科研恢复。不能先普通启动再决定是否恢复。
5. 启动实际先对账再恢复 `clock_version=1 && resume_on_startup=1` 的意图，手动暂停和历史时钟Run不自动恢复。unknown保持unknown，禁止靠重发创建/提交推断恢复成功。`ops resume`用于核查后重试仍持久的恢复意图；不是普通启动的必经人工闸门。

安全停止后保存当前账本，不复制密钥：

```bash
git status --short
git rev-parse HEAD
.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
root = Path('/home/wmywb/CyberScientist')
archive = root / '.package-checks' / 'rollback'
archive.mkdir(parents=True, exist_ok=True)
backup = archive / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite')
with sqlite3.connect('file:' + str(root / '.cyberscientist/cyberscientist.db') + '?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
    source.backup(target)
print(backup)
PY
```

跟踪改动已安全另存且工作区允许切换后，在相同目录操作；不改远程 main，不 force push：

```bash
git show --no-patch --oneline lightchaser-fallback-3
git switch --detach lightchaser-fallback-3
# 已在禁止派发的一致性副本上核查兼容，并明确允许立即恢复后才执行
.venv/bin/cyberscientist serve
# 另一个终端核查实际自动恢复结果
.venv/bin/cyberscientist ops status --json
# 对账无异常、恢复意图仍待处理时，可显式重试
.venv/bin/cyberscientist ops resume
```

切回开发代码使用 `git switch main`。本步骤保留当前 `.cyberscientist/cyberscientist.db`，不执行旧备份覆盖。独立 worktree 默认数据路径不同，不能把新 worktree 空账本当作当前账本。

## CS-UP-12 兼容实测与边界

在独立 worktree 载入原始 fallback-2（完整 commit `20069d7b8eda03f1056d9649c84258c0cf4bd133`），独立端口 8872，打开本卡 ADD-only 迁移后主账本的一致性副本。生产后端未启动，生产数据库未恢复旧版本。旧代码完整 lifespan 启动、只读远程对账及当前健康/轮次/Run/提交/收割接口实测记录见 [修复证据](CS_UP_12_FIX_EVIDENCE.md)。维护验证显式禁止科研模型入口、研究派发、自动收割和资源删除；未恢复科研 Run。这证明账本读取和对账兼容，不等同于完整比赛恢复彩排。

fallback-2 没有 CS-UP-12 的用户提示词、独立赛道时钟及赛末收割规则，旧 `run_clock.remaining` 仍只按 `max_run_minutes`。新赛道无上限授权在该旧版本可能立即到期；因此不能直接恢复 CS-UP-12 新赛道 Run。比赛中的新功能应回退到已验收的 fallback-3 或更新的兼容版本；fallback-2 仅作为历史数据读取/诊断选项，只在一致性副本及禁止科研入口/派发/删除的维护守卫下启动；普通serve会自动恢复，不能用于这个诊断步骤。不能因“旧代码能读账本”声称所有新功能也兼容。

原始备份仍保存在 `.package-checks/cs-up-08/`、`.package-checks/cs-up-09/`、`.package-checks/cs-up-12/`，供离线取证。保留原后端密钥存储和原生认证，不复制或打印密钥，不改全局 CLI 配置，不删除已有 Bohrium 资源。
