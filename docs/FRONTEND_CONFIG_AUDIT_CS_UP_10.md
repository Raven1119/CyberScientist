# 前端配置持久化清单 CS-UP-10

W3a修复前：PUT以默认设置为底，其他页面只发部分字段时会清除已有值；深层provider_sessions也会丢掉兄弟字段。修复后，以当前修订深合并；冲突409不写入，GET瞬态_status不落盘，密钥只在独立后端入口保存。完整价格JSON与host映射显式替换，删除条目、价格时段和空表不会复活；部分字段更新仍保留其他值。

| 页面或卡片 | 配置字段 | 持久化与验证 |
|---|---|---|
| 连接与设置 / 模式 | app.mode；mailbox.platform | settings；刷新与新后端实例回归 |
| PI | brain.executable；runtime/provider/model_id/reasoning_effort/auth_mode固定Astra/xhigh/native | 设置后端严格校验；旧配置投影 |
| 求解者 | executor.runtime/provider/model_id/reasoning_effort/executable | settings命名空间往返 |
| 审查者 / 复盘 | reviewer、post_review各自provider/model_id/effort/executable | 独立保存，不覆盖其他角色 |
| 求解者条目 | solver_roster[].id/name/runtime/provider/model_id/effort/note | 列表替换，完整条目往返 |
| 自动收割 | harvest.score_threshold/experiments_done_at_leader/deadline_check_hours | 非默认值保存；其他页保存不丢失 |
| 模型价格 | model_pricing；模型Profile pricing | settings；无虚构账单 |
| Prime排障 | prime.executable/llm_profile_id | 只改项目配置 |
| 模型Profile | llm_profiles[].id/label/protocol/base_url/model_id/secret_ref | 列表保存；密钥值不入设置 |
| Playground | playground.base_url/token_secret_ref | 设置引用；独立密钥写入不回显 |
| Bohrium | bohrium.executable/project_id/access_key_secret_ref/wenyon_executable/wenyon_home | 项目设置；不改全局CLI |
| 并行运行 | run_defaults.max_active_runs；resources.provider_sessions各提供方、max_concurrent_jobs/sandboxes | 深层部分写保留兄弟字段 |
| 停滞与等待 | run_defaults.stall_seconds/max_brain_wait_seconds/brain_review_timeout_seconds/rate_limit_max_seconds | 整数校验与往返 |
| 静默监督 | shadow.max_reviews/min_interval_seconds；Run创建时enabled | 全局设置与独立Run快照 |
| 常驻技能 | skills.always_on | 页面保存和独立always_on写入都保留其他设置 |
| 邮箱与提交 | 收割邮箱、实验邮箱、停用状态、绑定平台 | 独立mailboxes账本；平台不匹配红色提示 |
| 评分轮询 | polling.disabled_challenges | 独立轮询开关写入，不重置连接设置 |
| 经验库 | Markdown/frontmatter；全局审批；修订恢复 | 独立版本和审批账本，不混入trace |
| 比赛轮次 | 模板、逐题模型/授权、priority、paused | 独立eval_runs/eval_results冻结记录 |
| 研究工作台 | 题目模型、技能绑定、授权、续跑、变体预测/叙述 | 各自实际后端入口，不用演示假成功 |
| 环境目录 / 共享区 | 目录条目、验证器与共享版本 | 独立只读展示；后台追加版本 |
| 评测 | suite/repeats/label；报告版本 | 独立评测记录和实际报告入口 |
| 显示偏好 | theme/motion/focus | 浏览器本地存储，与后端配置分开 |
| W3后续入口 | 自检、11功能开关、限速后备、分诊JSON | 后续对应小项实现并补充浏览器走查 |

自动化：tests/test_settings_persistence_cs10.py覆盖19设置命名空间保存→GET刷新→关闭SQLite/新后端应用→其他字段保存，以及深层兄弟字段和旧修订409；连同现有设置/PI/连接共38项通过。前端73项及构建通过，邮箱绑定匹配/不匹配均有测试。

Chromium真实浏览器使用.package-checks/cs-up-10/ui/独立演示数据，未创建科研Run、注册平台账号、发起模型或提交；设置、评测、邮箱、经验、比赛页面截图留该忽略目录。实际后端重启和独立技能写入的持久化结果见本机browser.json。后续新入口在W3全部完成后统一再走查。
