# CyberScientist 运维命令

在仓库根目录使用 `.venv/bin/cyberscientist ops …`。命令连接本机配置端口的后端；每条命令可带 `--port 8765`。后端未启动或响应不能判定时退出码2；安全关机/恢复未确认退出码1；成功退出码0。输出JSON经过已登记密钥及常见令牌脱敏，仍只在本机保管研究事件。

| 命令 | 用途 |
| --- | --- |
| `ops status --json` | 全局屏障、赛道时钟/提示词版本/赛末窗口、各Run正式最好/主邮箱/实验成绩、原生会话fast确认、提供方用量及429等待、代码版本 |
| `ops digest [--since <ISO时间>]` | 约60行以内的直接账本摘要，优先活动Run，错误去重计数、unknown ID、倒计时和速率状态；纯文本 |
| `ops events <run_id> --tail 20` | 最近1–1000条公开事件，按原seq升序输出 |
| `ops alerts` | 未确认提醒与待用户审批的全局经验版本；不会自动知悉或批准 |
| `ops switch <name> on` / `off` | 切换对应的新动作，保留历史、冻结包及已接受工作 |
| `ops shutdown` | 请求安全暂停，等待原生收尾，建立屏障并一致性备份SQLite；只有can_shutdown=true才可关机 |
| `ops resume` | 先只读对账远程Job、沙箱和提交，再恢复安全关机明确标记的Run |

开关名称：`auto_harvest`、`reviewer`、`scorer_audit`、`strategy_cards`、`deepseek_fallback`、`protocol_drift`、`await_score`、`shared_area`、`environment_catalog`、`system_triage`、`local_calculation`。也可在连接与设置页面保存开关。关闭自动收割不会关闭用户手动收割；失败/unknown提交不会自动重发。

低频监控先读 `ops digest`，保存其首行UTC时间，下次用 `ops digest --since 2026-10-06T15:00:00+00:00` 增量读取；仅对需要关注的Run再读events或status。digest直接查询小投影，不调用完整status/pending，不返回配置快照；分数无变化的轮询不算更新，状态/分数/提示词/赛道改变才计入。全局代码、屏障及速率快照始终作为上下文显示；历史记录超过行预算时明确报告省略数量。`stuck.suspected`只表示running期间超过配置静默时长，没有证明科学计算停滞；结合实际事件、远程任务与恢复信息判断。`platform_best`属于该Run，`topic_best_current_platform`是当前平台同题所有Run确认分，不应混为一项。缺少成绩返回null，不能改成0。`code.loaded`是后端载入代码，checkout是当前磁盘；不一致说明进程需安全重启。tags属于载入commit，读取失败以tags_status=unknown标记。

shutdown不会停止或删除远程Job/沙箱，远程可能继续计费。先检查其回执、未关闭原生句柄和can_shutdown，保留backup路径。resume不重发Job创建、不删除沙箱；发生对账异常或原生关闭未知不会清除已有屏障。仅clock_version=1且resume_on_startup=1的明确关机恢复意图可自动恢复，用户手动暂停和旧时钟Run不恢复。并发新关机优先于之前的恢复请求。重复或丢响应的resume共用一个后台对账任务，不重复启动；unknown先查看status；若已解除限流，可再次resume，只重试持久的关机恢复意图。恢复科学会话仍消耗原Run授权，未获得明确运行授权时只做查询。

会话fast字段来自原生thread握手回执，未观察的历史会话保持unknown，不从配置推断已生效。会话观察写库失败只报通用警告，不关闭已握手的原生进程。`provider_rates.native_throttle`包括原生willRetry的waiting/recovered事实，provider-wide可用性仍未知。

赛前可用前端自检或 `POST /api/v1/preflight`：只读认证/模型目录/公开工具，不开科研Run或提交。tracks逐项显示调度时钟、协议确认及证据、用户提示词、无上限状态和收割邮箱匹配；旧轮次资料不足为warn，不能当作已就绪。

## 安全重部署（CS-UP-13）

`cyberscientist ops redeploy --commit <hash或标签> --port 8765` 先验证目标与干净的跟踪文件，再安全关机等待can_shutdown，核对Linux PID/启动时间/cwd后SIGTERM，确认退出、切换代码、启动并核对目标commit，然后resume只读对账、自检、digest。任一步失败退出1并保留当前状态；不强杀、不自动回退、不跨失败继续。自检warn可完成并明确输出，fail停止；外部unknown不能被当成通过。每步回执和停机时间写入本机.package-checks/redeploy/。

只换代码保留SQLite、秘密存储、workspace和经验账本。目标会改变experience跟踪文件时拒绝回退，需使用包含当前经验的兼容提交。无目标参数表示当前HEAD。旧后端未提供PID时需先安全关机，再人工识别Linux进程完成一次迁移；不能猜PID。不同commit切换为detached HEAD，后续开发应回到main。

自检显示自动提交状态、新lc经验有效修订、执行器技能和每个镜像创建成功时间。创建时间不代表缓存寿命。设置页可持久保存auto_submission、judge_replica_hint、间隔策略；自动提交恢复需专用恢复按钮清除数据库屏障。
