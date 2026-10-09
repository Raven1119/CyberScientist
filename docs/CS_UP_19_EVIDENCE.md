# CS-UP-19 验收证据

本卡由用户重新授权执行。真实提交0、镜像构建0；真实模型调用仅W2冒烟。未完成项持续列在STATUS，不以模拟测试替代真实闭环。

## W1 当前比赛快照

- 私有仓库：https://github.com/Raven1119/CyberScientist-comp，GitHub查询isPrivate=true。
- main快照提交：f5f9b571b44694fbc19d541fdf9dafd2bf82cecb；远端refs/heads/main与本地HEAD一致。
- 发布版本：1285f164b878cd5ba7839554762680314de59d43。264个发布文件逐项复核清单SHA，另导出版本、发布清单、脱敏设置、脱敏Codex配置、23个启用技能清单、两层目录名称/大小，共271文件。
- 完整导出清单：[export-manifest.json](https://github.com/Raven1119/CyberScientist-comp/blob/f5f9b571b44694fbc19d541fdf9dafd2bf82cecb/snapshot/export-manifest.json)。
- 现有已知秘密扫描与ASP、API token、Bearer凭据、AccessKey值、长base64/JWT、私钥块扫描：271文件、0命中。初次扫描将代码中的函数名判为AccessKey值；修正为凭据值模式后重扫，未修改清单文件字节。位置记录留在本机私有证据，不输出匹配值。
- 导出目录/home/wmywb/CyberScientist-comp-export，与比赛目录分离；比赛目录没有.git。未导出auth.json、秘密库、数据库、运行工作区、原生记录、虚拟环境、日志、备份或历史归档。两层目录树只包含名称、类型和大小。
- 命令：tools/export_comp_snapshot.py --root /home/wmywb/CyberScientist-comp --output /home/wmywb/CyberScientist-comp-export；GitHub建私库、推送main、repo view、ls-remote。
- 安全回归：tests/test_comp_snapshot_cs19.py，3 passed in 1.17s；覆盖原始字节、凭据排除/脱敏、违规清单、清单字节失配、扫描不回显。

## 未完成验收

W2–W8继续执行；W2第5步依赖W4/W5接线。

## W6 机械修复与发布目录依赖

已实现：迁移后ops默认比赛端、显式dev核对进程身份；PI能力索引三个计算入口明确由执行者调用；比赛专用Node放在`.runtime/bin/node`（不进Git），启动脚本及发布启动均优先此目录。官方CLI取同一Node，避免隔离HOME后丢失可执行文件。专项61 passed / 18.37秒，日志为私有`w6-tests.log`。

| 目录 | 处理 | 实际读取依据 |
|---|---|---|
| src/cyberscientist | 保留 | Python应用、原生协议适配器及运行时工具桥import |
| prompts/roles、prompts/collaboration | 保留 | role_prompts、kimi及controller会话开发者指令 |
| skills | 保留 | skills索引及read、Job模板附件；原生CODEX_HOME技能同步 |
| environments | 保留 | environment_catalog、compute与环境预检读取 |
| contracts | 保留 | challenge_import、输出契约与提交暂存校验 |
| vendor/playground_contracts | 保留 | 官方协议/评分器快照，public research及drift检查 |
| templates | 保留 | 官方提交模板及数据格式验证 |
| tools/playground-cli/0.1.40 | 保留 | 固定官方CLI；integrity、package元数据与dist读取 |
| apps/web/dist | 保留 | API静态前端读取；每次从指定commit构建 |
| pyproject.toml、uv.lock、启动脚本、示例配置 | 保留 | 独立环境锁定、迁移/发布和冷启动 |
| evals | 移出 | 开发评估目录；比赛端显式拒绝开发评估目录入口 |
| challenges | 移出 | 仓库旧题参考数据；当前题从workspace/challenges读取，旧历史记录另行归档 |
| docs、tests、开发工具、旧brain/prime | 不发布 | 不属于比赛运行时 |
| experience、workspace、设置/数据库、HOME、CODEX_HOME凭据 | 运行时数据 | 不属于发布所有权，发布不覆盖、不导出内容 |

发布同时清理上一版清单拥有、这一版已移除的目录，备份放`.runtime/previous`；回归确认新题工作数据保持。每次成功ops release后自动扫描并更新私有比赛快照，扫描失败或推送失败如实报告`release_completed`，不冒充快照成功。

凭据独立性：本次账户ID、刷新令牌哈希比较均为“相同”，只保存比较结果，不保存值或指纹。用户需自行执行：

```bash
CODEX_HOME=~/CyberScientist-comp/.runtime/codex codex login
```

尚未验证：用户自行登录后两侧最小会话；不以原有共享登录冒充独立性。移出目录后的实际冷启动和隐藏依赖测试随后执行。

## W7 巡检与输入门禁

比赛数据库寿命观察读回`effective_ceiling_seconds=604800`。没有记录或值无效时不返回3600；比赛启动记录自检失败并持久化前端告警，显式检查同样失败。已有记录未修改。

maintain_due忙锁即跳过，独立周期任务与提交/存活链分开；真实线程关机仍受resource_coordinator管理。测试使用另线程持Run锁以及让巡检等待的应用lifespan，确认一秒内返回/提交推进，不用提示词替代结构隔离。cell-relax缺force_thr_ev或stress_thr，在check_inputs运行前明确列缺项；force_thr不替代。65 passed / 34.11秒，真实云Job未重复执行。

pg-*只读报告：[REPORT.md](https://github.com/Raven1119/cs-private/blob/e8238ab/reviews/pg_skills/REPORT.md)，32项逐目录调查、两项指定SHA仅相同/不同、七项逐字全文；8文件密钥扫描零命中，未启用任何pg技能。
