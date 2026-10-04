# Lightchaser 本地版本回退

已推送标签：`lightchaser-fallback-0` 指向 `5940418`，`lightchaser-fallback-1` 指向 CS-UP-08 最终版本 `ec5e24b`。比赛应选择最后实际通过彩排的版本；标签存在不表示 CS-UP-09 的真实提交/收割验收已经通过。

先在前端点击“安全关机”，或在当前 Linux 项目运行 `.venv/bin/cyberscientist shutdown`。只在回执 `can_shutdown=true` 后停止后端进程。远程 Job/沙箱仍可能运行和计费；本地回退不取消资源、不撤销 Attempt，也不证明未知操作未执行。

在 `/home/wmywb/CyberScientist` 中检查和另存当前改动、数据库与版本。保留未跟踪经验和任务卡，不使用 reset --hard、clean 或 force push。

```bash
git status --short
git rev-parse HEAD
git show --no-patch --oneline lightchaser-fallback-1
```

以下 Python 在停止后端后，用 SQLite 的备份接口保存当前账本；不复制密钥。

```bash
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

跟踪改动已另存且工作区允许切换后，选择标签，不改 main 远程引用：

```bash
git switch --detach lightchaser-fallback-1
```

需要保留当前代码目录时，改用一个尚不存在的目录创建 worktree：`git worktree add --detach ../CyberScientist-fallback-1 lightchaser-fallback-1`。新 worktree 的软件和数据默认隔离，不能直接把原目录的可执行入口当作该 worktree 的入口。

CS-UP-08 迁移前备份在 `.package-checks/cs-up-08/pre-migration-20261004T131841Z.db`；CS-UP-09 开工前备份在 `.package-checks/cs-up-09/pre09-20261004T154033Z.sqlite`，其 SHA-256 为 `f7a7d17237b2b9b3714ed6e5b3ac12061a4b8589c43ffa6f75df5bd9dd82d189`。后者是生产账本的一致性副本；三题验证的隔离数据库另在 `.package-checks/lightchaser-validation/state/final-08.sqlite`。生产与隔离验证数据不能混用。

选择匹配标签的备份，先核对哈希，再恢复到停止中的生产数据库。以下示例只适用 fallback-1 与09开工前备份；08之前的标签应选择08迁移前备份。

```bash
.venv/bin/python - <<'PY'
import hashlib, sqlite3
from pathlib import Path
root = Path('/home/wmywb/CyberScientist')
backup = root / '.package-checks/cs-up-09/pre09-20261004T154033Z.sqlite'
assert hashlib.sha256(backup.read_bytes()).hexdigest() == 'f7a7d17237b2b9b3714ed6e5b3ac12061a4b8589c43ffa6f75df5bd9dd82d189'
with sqlite3.connect('file:' + str(backup) + '?mode=ro', uri=True) as source, sqlite3.connect(root / '.cyberscientist/cyberscientist.db') as target:
    source.backup(target)
    target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
PY
```

保留原后端凭据存储和原生认证，不复制或打印密钥，不改全局 CLI 配置。启动时先看 Job/Attempt 对账结果与 unknown，再决定恢复；旧账本仍可能关联实际存在的远端任务。返回开发分支用 `git switch main`；回退步骤本身没有替用户执行数据库恢复或启动历史 Run。
