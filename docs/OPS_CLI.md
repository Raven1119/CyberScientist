# CyberScientist 运维命令

在仓库根目录使用 `.venv/bin/cyberscientist ops …`。命令连接本机配置端口的后端；每条命令可带 `--port 8765`。后端未启动或响应不能判定时退出码2；安全关机/恢复未确认退出码1；成功退出码0。输出JSON经过已登记密钥及常见令牌脱敏，仍只在本机保管研究事件。

| 命令 | 用途 |
| --- | --- |
| `ops status --json` | 全局屏障、各Run阶段/本地正式最好/该Run确认平台最好、静默提醒、待处理弹窗/经验、最近错误、速率及代码版本 |
| `ops events <run_id> --tail 20` | 最近1–1000条公开事件，按原seq升序输出 |
| `ops alerts` | 未确认提醒与待用户审批的全局经验版本；不会自动知悉或批准 |
| `ops switch <name> on` / `off` | 切换对应的新动作，保留历史、冻结包及已接受工作 |
| `ops shutdown` | 请求安全暂停，等待原生收尾，建立屏障并一致性备份SQLite；只有can_shutdown=true才可关机 |
| `ops resume` | 先只读对账远程Job、沙箱和提交，再恢复安全关机明确标记的Run |

开关名称：`auto_harvest`、`reviewer`、`scorer_audit`、`strategy_cards`、`deepseek_fallback`、`protocol_drift`、`await_score`、`shared_area`、`environment_catalog`、`system_triage`、`local_calculation`。也可在连接与设置页面保存开关。关闭自动收割不会关闭用户手动收割；失败/unknown提交不会自动重发。

监控时先读status，再读需要关注的Run事件与alerts。`stuck.suspected`只表示running期间超过配置静默时长，没有证明科学计算停滞；结合实际事件、远程任务与恢复信息判断。`platform_best`属于该Run，`topic_best_current_platform`是当前平台同题所有Run确认分，不应混为一项。缺少成绩返回null，不能改成0。`code.loaded`是后端载入代码，checkout是当前磁盘；不一致说明进程需安全重启。tags属于载入commit，读取失败以tags_status=unknown标记。

shutdown不会停止或删除远程Job/沙箱，远程可能继续计费。先检查其回执、未关闭原生句柄和can_shutdown，保留backup路径。resume不重发Job创建、不删除沙箱；发生对账异常或原生关闭未知不会清除已有屏障。仅clock_version=1且resume_on_startup=1的明确关机恢复意图可自动恢复，用户手动暂停和旧时钟Run不恢复。并发新关机优先于之前的恢复请求。重复或丢响应的resume共用一个后台对账任务，不重复启动；unknown先查看status；若已解除限流，可再次resume，只重试持久的关机恢复意图。恢复科学会话仍消耗原Run授权，未获得明确运行授权时只做查询。
