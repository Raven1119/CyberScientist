# 2026-09-22 · 经验包安装与 B01–B21 修复交付

依据根目录 `CyberScientist_AGENT_INSTALL.md`、`CyberScientist_BUG_FIXES.md`；基线为 `46bba5d0bc24a03ec1be889384442e6dbe36ced2`。开发、迁移、测试均在 Linux / WSL2，保留已有代码和原经验文件。本记录中的平台与代理回归使用明确的模拟边界，不代表真实科研成绩或原生 CLI 已完成 Linux 往返。

## 内容安装

- ZIP 安全解压至 `.incoming/CyberScientist_Experience_Kit_v1/`，加入 Git 忽略；未执行 reference 的其他仓库脚本。
- 原版存储仍在时，先检查包与预览，再持工作区锁安装：global candidate **12**、challenge active **0**。数据库没有真实题目，因此没有创建虚构题目或绑定题型组合。
- 首次收据：`.cyberscientist/experience_imports/20260921T181439_1939b96f/receipt.json`。`verify` 返回 `verified=true, checked=12, failures=[]`。
- 在改动存储代码前重复安装：`create=0, unchanged=12`，无重复修订。收据中的 preserve_existing 为空；仓库原有 `experience/challenges/local_14c116ff/_arm_v1_1_generic_controller.md` 独立保留，`git diff --exit-code -- <该路径>` 通过。
- 导入文件全部为 hypothesis；没有批准全局候选。库中仍只有这 12 条新候选和 1 条原文件。

## 修复与验证对应

| 批次 / 问题 | 已实现 | 回归位置 |
|---|---|---|
| A · B01 | 不可变 ID 文件名、独占创建、拒绝碰撞 | `test_experience_integrity.py` 四类标题碰撞 |
| A · B02 | 独立 revision_id、父操作指针、operation_id 去重；回滚保留独立历史 | rollback/redo 回归及 `test_experiences.py` |
| A · B03 | 外部字节登记；单次读取的正文和哈希一致；pending 写入对账；非法草稿不抹已批准内容 | 外部编辑、写文件后故障、旧库迁移回归 |
| A · B04 | 禁止原位变更 scope/challenge；模型目标和激活操作核对当前题 | 归属回归与 controller 边界审查 |
| A · B05 | ID/题目路径校验、拒绝符号链接与越界 | 路径参数化与外部 symlink 回归 |
| A · B06 | 审批不改证据等级；模型更新保留扩展字段，新结论默认 hypothesis | 审批/提议回归 |
| A · B07 | 必填字符串、枚举、列表元素、可 JSON 表示的元数据校验 | 非法 metadata 参数化回归 |
| A · B08 | 新建状态保护；请求序号和选择身份核对；刷新不重置编辑 | ExperiencePage DOM 测试 |
| A · B20 | head/active 分离；审批必须带所见 revision_id；草稿更新不换运行时批准版 | 服务层、HTTP 409、旧 active 可读回归 |
| B · B13 | 检查点与原 review/guidance 收据同事务；重试按当前门禁回答 | `test_control_integrity.py` |
| B · B14 | Run 固定 runtime/mode；启动、恢复、模型审阅检查授权；预算仍可调整 | 配置切换与既有控制器回归 |
| B · B15 | 授权截止限制队列等待；pausing 请求原生取消，确认终态才 paused；迟到判断不能发起动作 | 无事件截止、accepted/终态、暂停迟到回归 |
| B · B16 | 同事务核对请求指纹、Run 限额、邮箱限额并预占；unknown 保留额度 | `test_submission_integrity.py` 真实线程并发 |
| B · B17 | 冻结发送字节与 hash；创建/上传/提交阶段先记发送再记回执；Attempt ID 即时持久化 | 三阶段丢回执、原 ID 重试、文件变动回归 |
| B · B18 | 最外层清理覆盖部分会话启动；等待泵/worker 退出；撤销能力令牌；原生适配器及 stdio 幂等清理 | 启动失败、JSON-RPC 子进程退出回归 |
| B · B19 | 注册/提交/收割转线程；秘密与配置写入串行；批量注册逐条持久化 | 部分成功与慢注册期间 health 响应回归 |
| B · B21 | 两个指导通道共享当前 Trial/phase/gate/epoch 检查；未知发送不盲重试 | 旧 Trial 两通道参数化回归 |
| C · B09 | 起止清单仅 availability_only；presented/adopted/result_linked 事件；采用投影可重建；结果只连接采用后的同 Trial 提交 | `test_learning_integrity.py` |
| C · B10 | 统一读取 active revision，题内优先/目标词排序、字符预算；Trial 和指导冻结；两侧提示保留等级与适用性 | 字符预算、冻结版本、hypothesis/contradicted 回归 |
| C · B11 | 分页读到固定上界；覆盖游标使用真实 processed_through_seq；检查点只投影上界前事件 | 千条积压尾部错误可见、未来事件排除 |
| C · B12 | 评分 delta 和已知评分携带原提交/Trial/hash/最终性；更正追加事件；仅运行中唤醒队列 | 幂等轮询、更正、取消后迟到分数回归 |

主代理分别检查了三个批次的变更边界。A 审查补充了单次读取一致性、首次迁移保留旧批准内容、全局保存不能绕过审批；B 补充了冻结发送字节、到期提交拒绝、Linux 已退出进程的幂等清理；C 补充了收尾整理读取采用结果、两类指导共用冻结入口以及无评分增量时保留已知评分。未使用子代理。

## 本次实际命令与结果

```bash
/tmp/cyberscientist-dev-tools/bin/uv sync --locked --cache-dir /tmp/cyberscientist-uv-cache
# 项目 .venv 创建并按 uv.lock 安装成功
cd apps/web
PATH="/home/wmywb/.local/bin:$PATH" npm ci --cache /tmp/cyberscientist-npm-cache --no-audit --no-fund
# 随后增加固定版本 Vitest/jsdom/Testing Library 开发依赖，已写 package-lock.json
PATH="/home/wmywb/.local/bin:$PATH" npm test
# 3 passed
PATH="/home/wmywb/.local/bin:$PATH" npm run build
# tsc + vite build 成功
cd ../..
.venv/bin/python -m pytest -q
# 184 passed in 33.06s
.venv/bin/python -m pytest tests/test_learning_integrity.py -q
# 最后补充 curation 采用结果投影后：6 passed in 1.63s
.venv/bin/python -m compileall -q src/cyberscientist
git diff --check
# 均成功
```

最初沙箱中的测试在 asyncio 默认线程池退出时挂起。最小 `asyncio.run(asyncio.to_thread(lambda: 1))` 同样在沙箱内超时，限制外成功；以上完整应用回归在允许本机线程/子进程通信的环境执行。没有把超时的测试记为通过。

实际库迁移预览为 12 条旧修订；应用后 13 条、13 个文件条目、pending/file errors 均为空。增加的第 13 条是原仓库文件的首次外部内容登记，不是新增经验或虚构历史。再次应用保持 13 条。迁移后旧导入收据再次验证 `verified=true`。

本机临时 Uvicorn 使用真实工作区与构建产物读回：根页面 HTTP 200、经验 API HTTP 200、12 个 candidate/hypothesis、12 个正文与修订匹配、0 个真实题目、0 个 Run。进程已正常停止；结果保存在本地 `checks/results/experience-kit-smoke.json`。DOM 测试不等同于完整浏览器人工验收。

## 迁移与回滚边界

执行入口为 `checks/migrate_experience_v3.py`，不带参数只读预览；`--apply` 使用产品同一工作区锁，存在未结束 Run 则拒绝。旧库第一次启动也自动迁移，DDL 前通过 SQLite backup 保存包含 WAL 的数据库，并复制 experience；不会复制 secrets。

本次迁移备份：`.cyberscientist/migrations/experience-v3-45ed142e7c5842048babb9a037bceb1f/`。导入前备份与首次安装收据另外保留。新结构去掉 `(experience_id, revision_hash)` 唯一约束，保留旧 revision ID；新增 heads、审批记录、冻结包与采用投影，以及提交阶段/指纹字段。不会将旧可用清单变为 adopted，也不会补造遗失的编辑/回滚历史。

仅在停止后端、无后续业务写入且核对备份范围后，才可同时恢复该备份数据库、experience 与匹配旧代码。有新的 Run/审批/编辑/提交后禁止整库回退；应使用原生版本操作，保留新历史。单独切回旧代码不受支持。旧包导入器的 source fingerprint/experience_heads 拒写保护保持不变，后续绑定或退役须走新原生接口，不可强行跳过检查。

## 尚未验证与外部限制

- 未运行付费模型、Bohrium Job、真实账号注册或比赛 Attempt；未声称这些修复已经过真实平台验收。
- 有 Attempt ID 的 unknown 只通过已有 score 端点查询；final 评分可确认原 Attempt 的结果。未有最终证据时继续保留 unknown/预占。创建响应丢失且没有 ID，平台无已核实的客户端引用查询/幂等契约，必须保留 unknown 等待对账，不能自动新建重提。
- Linux 的 Kimi/Codex 原生模型往返未验证；Codex 执行器协作 MCP 桥仍是此前已知未完成项，不能把后端单元测试当成该能力验证。
- 此次完成的是可信记录与复用链；经验改善科研成绩、因果贡献、等预算连续改进实验未验证，也没有为验证这些结论追加模型授权。
