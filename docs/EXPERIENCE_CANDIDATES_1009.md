# 比赛经验候选（未导入，等待设计助手审阅）

扫描开发STATUS、决定、各卡证据/复盘/审计及本轮私有摘要，逐项与当前experience Markdown核对。来源清单和SHA只保存在私有cs18-candidate-scan.json；本文件只给教训与定位，不复制原生记录、回执或密钥。此时比赛兄弟目录尚未创建。

| 教训（一句话） | 适用范围 | 依据和位置 | 建议形式 |
|---|---|---|---|
| pybader计算成功与输出格式兼容要分别验证，当前已验证组合应使用默认pickle，dat格式会触发已删除的pandas接口。 | pybader0.3.12及当前材料镜像 | docs/CS_UP_17_EVIDENCE.md「W4 模板与组合镜像」；私有materials-smoke-poll.json及首次失败日志 | 工具链速查附件；正文由设计助手定稿，不泛化为所有版本dat均不可用 |
| GPU镜像的dp命令可用不代表CPU沙箱里的LAMMPS可用，应按实际硬件分别检查插件加载和子进程退出码。 | DeePMD/LAMMPS镜像 | docs/CS_UP_17_EVIDENCE.md「W5 工具链与离线文件」CPU失败/4090成功；deepmd-lammps-smoke.json | 工具链技能；现有目录已写CPU限制，避免再加重复通用资源经验 |
| 预训练模型的“最新可用”要落实为官方可下载权重及SHA，空的新版本仓库不能作为可用新版。 | DPA公开预训练材料权重 | docs/CS_UP_17_EVIDENCE.md「W5」来源/限制；assets.json；私有DPA元数据摘要 | 工具链技能；列实际可用版本与路径，不声称文件存在证明推理兼容 |
| ABACUS验收须检查最后一次SCF及其后的结束标记，旧的成功行不能掩盖后来失败或截断。 | ABACUS SCF/弛豫 | docs/CS_UP_17_EVIDENCE.md「W4」；tests/test_abacus_templates_cs17.py的截断/后续失败用例 | 已由附件检查程序强制，无需另写通用经验 |
| 不同ABACUS与dpdata版本的能量/应力标题需兼容视图，原日志必须保留且记录哈希。 | 当前固定材料工具链 | docs/CS_UP_17_EVIDENCE.md「W4」；两个案例check_results.py；原日志SHA | 已由模板代码强制；工具链技能注明版本边界 |
| 官方CLI实际发送ZIP的哈希必须现场核验，试构建ZIP可能仅因官方UTC元数据而不同。 | 官方提交CLI0.1.40 | docs/CS_UP_15_EVIDENCE.md实际发送包/预览包哈希与Worker核对段；私有lisi-api-result.json | 已由提交路径绑定真实发送包强制，无需重复经验 |
| 注册的pending账号在POST前就应持久化随机凭据，账号创建成功不保证稍后仍可恢复登录。 | 账号注册/认领 | docs/CS_UP_15_EVIDENCE.md「W2两新Agent」及凭据缺失说明；tests/test_accounts_cs15.py | 已由注册代码强制；保留现有两账号缺口，不用新注册或Regenerate掩盖 |
| 系统注入技能清单与原生会话自动加载是两条入口，比赛外技能可能绕过应用扫描进入轨迹。 | Codex原生运行时 | STATUS.md本轮隔离审计；私有native-first-frames-baseline.json，两角色均见比赛外原生技能 | 由隔离代码和发布/原生帧验收强制，无需用提示词约束替代结构 |

去重：提交受理/评分/科学结论分层已有csx1_delivery；资源unknown和失败条件已有csx1_resource/csx1_reopen；大文件传输和镜像恢复已有对应全局条目，不再写同义候选。科学优先流程已改变固定本地评分前置策略，现有csup08_verified_local_grade等相关正文需设计助手同步审阅；本轮不自行改写策略。

仅待审，不导入、不启用。设计助手定稿后通过比赛目录经验接口导入；经验运行时修订不随ops release覆盖。上述“已由代码强制”项供审阅删减，不要再作为运行提示重复注入。
