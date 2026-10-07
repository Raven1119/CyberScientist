# CS-RH-01 值班日志摘要

这是可发布摘要。完整逐请求日志、回执、备份及诊断仅在本机忽略目录 `.package-checks/cs-rh-01-20261007/`；不包含邮箱、凭据或完整提交包。结论见 [REHEARSAL_1_REPORT.md](REHEARSAL_1_REPORT.md)。所有时间为 2026-10-07 UTC+8。

| 阶段 | 已执行操作、返回摘要 | 耗时/结果证据 |
| --- | --- | --- |
| 开局 | 只读电源/工具/Git检查，保存 before.sqlite/settings；启动 Linux 后端 | 20:46:26→20:48:36，约130s；AC不睡眠，DC180s，未改系统。 |
| 自检 | POST /preflight，CLI preflight --json | 初次HTTP200，33.236s；R1 CLI exit0，镜像预热新鲜度warn。 |
| 设置 | GET/PUT /settings；fast开启、Astra xhigh、Sol high、DeepSeek roster、收割100/1.5h/15min | 初次参数名错误422无副作用，base_revision纠正后200。 |
| 导入 | POST /rounds/import，S4第4/5轮；协议探针及 transport核对 | 52.883s / 55.164s，均10题；默认ARM流程，不导入活跃题。 |
| 题目核验 | 20次只读 GET，记录开放状态/批准状态及原始赛末 | 全部open/approved；后续真实提交另证可提交性。 |
| 提示词/分诊 | PUT /prompt、POST /triage、采纳建议及逐项选择 | A客户端60.059s超时，后台10/10完成，未重发；B196.440s HTTP200。B无easy，TSA按hard保留。 |
| 确认 | 后端确认一键无上限模板，两赛道各2立即/1暂缓/7跳过 | T0=20:59:12.387。授权含unlimited=1/max_submissions=0；确认后不改。 |
| R1 | preflight、ops digest/status，读取原生session.configuration/rate | 21:29:13开始、21:29:51结束；54行，原生额度12%。 |
| 暂缓 | POST 两条 deferred item/start | 21:44:14接口成功，约21:44:20创建Run。 |
| 更新/R2 | PUT A prompt v2；PUT features/reviewer false，25s后true，再25s观察 | 21:59:13→22:00:05；已有review继续，新review恢复后可见。A三PI收到“用户更新”，B不串送。 |
| R3 | 日志写“请求同意”（已预先同意）；POST safe-shutdown，can_shutdown=true，SIGTERM，启动，POST ops/resume，preflight/digest | shutdown HTTP200耗时0.605s；服务停机197.040s，启动196.038s，完整恢复核验209.695s。自动恢复已完成，显式resume为ready/no-op。 |
| 用户时间调整 | 用户要求上一步完成后进入下一步，原时间表改为顺序推进 | 22:54:37登记timing_override；之后的clock PUT均保留原start，并独立记录旧/新end。 |
| R4 | 计数/事件/弹窗快照，SIGKILL精确匹配后端PID，同版本启动，不手动恢复Run | 22:54:39→22:57:07；启动132.029s，恢复观测147.390s；计数无回退、无重复创建、弹窗保留。 |
| R5-A | PUT A clock使窗口active，30s后GET round/alerts/计数 | 22:57:58完成；汇总alert_d64d5a0fdfde，B仍before_window，收割0。 |
| R5-B | A核对完成后PUT B clock进入窗口，同样观察 | 22:59:14完成；汇总alert_6488576c835d，收割0；诊断unlimited guard，未绕过授权。 |
| R6-A | PUT A clock到当时+20s；截止后等controller并GET round/digest | 23:00:04三个Run finished，23:00:34核对complete，B仍运行。 |
| R6-B | A核对完成后PUT B clock到当时+20s；同样观察 | 23:01:21–22三个Run finished，23:01:52核对complete；六笔提交均confirmed。 |
| 恢复 | GET current settings，PUT deadline_check_hours=2/margin15，GET再确认 | 23:02:41，revision16；未恢复整份旧设置覆盖本轮连接/roster。 |
| 诊断 | 只读审计收割guard、经验登记不一致、JSON脱敏复盘失败、unknown和未取回Job | 第2/3级修复均未执行；无手动科学操作、无手工提交/收割。 |
| 交付 | 两赛道结束后git pull --rebase，整理报告与此日志 | 同步9f5395c，仅两个文档纳入本次提交；不认证、不打标签。 |

59 次自动增量 digest 轮询为15–54行；弹窗逐条读取并保留，不批准/驳回候选，不重发unknown。初始49条历史提醒、10条经验待审批均保留；最终快照74条提醒包括历史数据，不是74个新增故障。

TSA-seq与CNVkit分别在21:44:57/21:46:17完成首交；Packing/XAS初次bundle拒收后由系统自行续提成功；监控未触发续提。6次实际提交均确认通用ARM 0分，两个未提交Run保持unknown。低分provisional曾被误判为字段缺失，后经源码与确认事件撤回：600s稳定确认属于正常机制。

R6严格“结束后零新动作”未满足：科研Run已终止，但独立整理/复盘模型调用仍启动。23:07:43快照六次整理done、四个复盘running、两个复盘failed；不等待维护并不意味着维护已完成。Deep BSDE和Packing的失败已只读复现为整段JSON脱敏后语法损坏，未重跑或修复。

速率取同一周窗口的新鲜观测1%→12%→37%→49%→53%；最初38%旧缓存排除。监控goal累计token计数508994（23:02:54），原生额度无法分会话归因，保留unknown。后台继续维护可能继续增加用量，报告数值是标明时间的快照。

未修改用户全局CLI配置或系统睡眠设置；既有文件保留，监控未删除远程资源，系统自行清理的沙箱仍有账本记录。未执行应用回归测试；交付检查仅针对两个文档的证据一致性、差异与脱敏。
