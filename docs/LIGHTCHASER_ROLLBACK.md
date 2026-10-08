# Lightchaser 比赛中回退：只换代码，保留当前账本

比赛中使用最新实际验证的标签，保留当前 `.cyberscientist/`、`workspace/` 和 `experience/`。恢复比赛前旧数据库会丢失 Run、Attempt、评分、额度及远程任务关联；旧数据库仅用于离线取证或当前账本损坏后的专项恢复，不能作为版本回退的常规步骤。

标签起点：fallback-0=`5940418`，fallback-1=`ec5e24b`，fallback-2=`20069d7`；CS-UP-14 的 lightchaser-fallback-5 是当前CLI回退目标；fallback-4及以前使用原接口，只能显式选择submission_transport=api时作为兼容回退；fallback-3存在收割缺陷，只能作历史读取。标签不代表比赛资格、unknown 已解决或真实整轮彩排已通过。

代码已封存、当前经验可兼容目标时，在同一Linux目录执行：

```bash
.venv/bin/cyberscientist ops redeploy --commit lightchaser-fallback-5 --port 8765
```

命令等待can_shutdown=true、确认Linux进程身份后停止，核实目标代码，启动健康检查，执行resume只读对账、自检和digest；任一步失败即停止，保留关机屏障、账本和日志，不强杀、不自动重发unknown。日志在.package-checks/redeploy/。目标会改变experience文件时拒绝切换，需含当前经验的兼容提交。旧后端无PID接口时按OPS_CLI的一次迁移步骤安全停止，不能猜进程。

保持当前.cyberscientist/、workspace/和experience/，不覆盖SQLite、settings、密钥或原生认证。切标签可能进入detached HEAD，开发时git switch main。普通serve会在对账后恢复明确关机意图；因此回退前须在禁止派发的一致性副本验证，不要先启动当前账本再决定授权。

CS-UP-13在6ad9479的完整账本副本实际执行全部步骤，停机126.686秒，总维护142.334秒，preflight warn，无科研Run启动。副本显式设置resume_on_startup=0、auto_submission=false、auto_harvest=false；不是生产科研恢复彩排。原后台未停止，旧unknown未重发。

## CS-UP-12 兼容实测与边界

在独立 worktree 载入原始 fallback-2（完整 commit `20069d7b8eda03f1056d9649c84258c0cf4bd133`），独立端口 8872，打开本卡 ADD-only 迁移后主账本的一致性副本。生产后端未启动，生产数据库未恢复旧版本。旧代码完整 lifespan 启动、只读远程对账及当前健康/轮次/Run/提交/收割接口实测记录见 [修复证据](CS_UP_12_FIX_EVIDENCE.md)。维护验证显式禁止科研模型入口、研究派发、自动收割和资源删除；未恢复科研 Run。这证明账本读取和对账兼容，不等同于完整比赛恢复彩排。

fallback-2 没有 CS-UP-12 的用户提示词、独立赛道时钟及赛末收割规则，旧 `run_clock.remaining` 仍只按 `max_run_minutes`。新赛道无上限授权在该旧版本可能立即到期；因此不能直接恢复 CS-UP-12 新赛道 Run。比赛中的新功能应回退到 fallback-5 或更新的兼容版本；fallback-2 仅作为历史数据读取/诊断选项，只在一致性副本及禁止科研入口/派发/删除的维护守卫下启动；普通serve会自动恢复，不能用于这个诊断步骤。不能因“旧代码能读账本”声称所有新功能也兼容。

原始备份仍保存在 `.package-checks/cs-up-08/`、`.package-checks/cs-up-09/`、`.package-checks/cs-up-12/`，供离线取证。保留原后端密钥存储和原生认证，不复制或打印密钥，不改全局 CLI 配置，不删除已有 Bohrium 资源。

CS-UP-14边界：fallback-5真实单题CLI调用仍unknown，没有确认harbor_worker/正式轨迹分/accept或真实收割；公开科学契约代理100/low与实际封存包轨迹0/review不能替代这些硬项。只换代码仍须保留未知提交预约及原封存字节；切换api不是unknown重发许可。原始完整原生会话转换3350步，manifest所选56行的证据缺口见CS_UP_14_EVIDENCE.md。
