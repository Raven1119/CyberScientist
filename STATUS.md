# 当前状态（2026-09-26）

## 已实现

- CS-EV-01a：非 ZIP 提交也执行同一代理证据门；放弃待处理 Trial 意图后在 running 阶段唤醒大脑；预算等待中保留用户显式审阅并在帧中标明门禁；日志锚点按协议快照的完整修剪行长度判定。Job 账本增加结果取回状态，受控下载/日志操作按实际文件及 SHA-256 留痕，研究帧、轨迹文本和前端远程任务列表显示该状态。
- CS-EV-01 已接入数据物化登记/独立授权/冻结输入校验、ARM 事件轨迹封存与提交准入、bundle 上传回执闸、Run 生命周期 v2、Job 依赖与镜像事实预检、交付状态保留及大脑审阅指标；前端展示数据、六项信号、预算等待、用户目标状态和交付标签。新增迁移只加表/列，旧 Run 保留 v1 语义。
- Wenyon 下载可单独选择项目隔离的 bohr 2.7.8 与 Wenyon 1.36.0 扩展，HOME/XDG 会话目录均隔离；现有 Job 客户端保留 bohr 1.1.0。未安装扩展的回执归类为 `WENYON_CLI_UNAVAILABLE`。已识别 v1 公开清单按原文字节哈希、声明文件哈希/大小和总字节数核对，匹配才标 `verified`。测试进程对沙箱 socketpair 唤醒限制做条件兼容，回环监听不可用时明确跳过对应 CLI 测试。

- Linux 工作台已接入 Kimi、Codex 和 Prime 的可选大脑/执行器路径，提供运行控制、技能、经验、提交和可审计的事件记录。
- Bohrium 计算由后端网关准入和对账；创建结果不明时保留占位，不盲目重试。
- 前端已连接真实后端，提供运行监督、设置、经验管理与操作界面。
- TBMA 运行后的准入、恢复、审阅和经验整理改动已纳入本次代码更新；含账户和实际任务标识的运行记录保留在本机忽略目录。
- CS-SB-01 新 Run 稀疏研究大脑已实现：开放研究回答、按需只读轨迹、研究级唤醒、自然边界全文投递与 ACK；前端显示回答、交付和读取。旧 Run 保留原协议。详见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。
- CS-SB-01 稀疏输入与唤醒修复：可选短研究摘要独立存储；新 Run 普通检查点不唤醒 shadow，Job/Trial 研究级重复状态按 ID 去重。详见 `docs/SPARSE_BRAIN_INPUT_WAKE_FIX_2026-09-24.md`。

## 已实际验证

- CS-EV-01a 最终回归：`.venv/bin/pytest -q` 为 355 passed、1 skipped（回环监听受沙箱限制的既有跳过）；`tests/test_ev_upgrade.py tests/test_compute_gateway.py` 定向测试 86 passed；`npm --prefix apps/web test -- --run` 为 12 passed；`npm --prefix apps/web run build`、`.venv/bin/python -m compileall -q src tests` 和 `git diff --check` 均通过。前端测试和构建使用项目 Linux Node 22 路径。
- CS-EV-01a 迁移前 SQLite 在线备份保存在本机忽略目录 `.package-checks/upgrade-20260926T154308Z/`，随后在本机数据库执行 `db.init_db()`，实际只追加 `compute_jobs.retrieval_status` 一列。获授权的 D1 单次只读旧 USCT Finished Job 下载探针保存在 `.package-checks/job-retrieval-probe-20260926T154546Z/`：bohr 1.1.0 进程退出码 0，后端回执 `ok=false`，输出文件 0 个；脱敏输出明确显示当前沙箱在 DNS 查询时因 socket 权限拒绝，请求未到平台。探针未创建 Job、Run 或 Attempt，也未重试。
- 提交前将依赖真实 Wenyon 文件/回执的测试改为运行时生成合成样本，并把 8 个未跟踪的真实实验文件移入本机忽略目录 `.package-checks/cs-ev-01-real-fixtures-unpublished/` 后重跑：`.venv/bin/pytest -q` 为 337 passed、1 skipped；前端 `npm --prefix apps/web test -- --run` 为 11 passed，`npm --prefix apps/web run build` 成功。测试和构建未再次访问账号服务或创建 Job/Attempt。
- 真实 Linux connected Run 已从同源前端启动并于 2026-09-26 07:53:46 UTC 结束，目标状态 `partial`；Codex 大脑和执行器 inspect 版本 0.155.1，随后完成 6 次大脑审阅和首个 Trial 的原生模型往返。开局 v2 Decision 因解析器只认 v1 而暂停；修复后恢复**同一 Run**，没有创建替代 Run。完整回归验证 337 passed、1 skipped。
- 本 Run 的官方 Wenyon 公开数据经受控 API 物化为 `verified`；2 个文件共 1148 字节，逐文件哈希及公开清单原文字节哈希通过。缺失本地模块的预检在预留 Job 前返回 `MISSING_LOCAL_MODULE`。
- 唯一获授权的 PR-4 Job 由普通 `compute.submit` 网关创建，平台创建回执成功；账本中的数据引用指向本轮已验证的物化记录，冻结输入包含官方文件、物化清单及探针。配置为 `c2_m2_cpu`、2 核/2 GB、10 GB 磁盘、最长 5 分钟、无 GPU/重调度。远端列表观察到 `Finished`，不将此状态冒充进程退出码或结果成功。本 Run 有 193 条事件、1 个 Job、0 个 Attempt、0 条镜像事实；前端返回 HTTP 200。原始标识、回执、检查点和结果包仅在本机忽略目录 `.package-checks/real-acceptance-20260926T073421Z/` 与 `workspace/runs/`；可提交的结果概述见 `docs/CS_EV_01_REAL_RUN_ACCEPTANCE_2026-09-26.md`。
- PR-3 在用户新增授权下，于项目隔离 HOME 原生登录一次；Wenyon 本地 `auth whoami` 随后通过。只下载一次登记的公开数据集，CLI 回执退出码 0、2 文件、1148 字节、无失败文件。第四季本机题目快照的 `public_manifest_sha256` 与下载的 `public-manifest.json` 原文字节 SHA-256 一致，清单内资源文件哈希/大小和题目登记总字节数也一致。完整回执与真实下载文件留在本机忽略目录 `.package-checks/wenyon-pr3-login-authorized-20260926/` 和 `.package-checks/wenyon-pr3-download-after-login-20260926/`；不提交真实数据 fixture。该 PR-3 探针当时无新 Run、模型调用、Job 或 Attempt。
- PR-3 后曾用真实公开文件作离线回归，验证有效清单、登记哈希错误和资源文件被改写；当时 `.venv/bin/python -m pytest -q` 为 336 passed、1 skipped，前端测试 11 passed，构建、`compileall`、`git diff --check` 均通过。为避免提交实验文件，可提交的测试现改为运行时生成合成 v1 清单；真实授权探针的结果仍由本机审计目录保留。
- 本轮只读 PR-1：`GET /api/protocol` 返回 200、21194 字节，SHA-256 `7042a86210915ad516521b052be3c62278c28696716909ca43cb08ea375c8cf4`；PR-2：本机 SQLite 的 USCT bundle/score 两条回执已脱敏冻结，确认 `bundleStatus=needs_review`、`validation.trace_admission.admitted=false`、`violations[].rule=trace_admission_blocked`。PR-3 已按单次授权执行固定 `bohr wenyon dataset download`，本机 CLI 报 `unknown command "wenyon"`，无文件下载。
- 迁移前源码、工作树补丁与 SQLite 备份已保存在本机忽略目录 `.package-checks/upgrade-20260925T161211Z/`；该目录未纳入公开 fixture。
- CS-EV-01 初次实施时，`.venv/bin/python -m pytest -q tests/test_ev_upgrade.py` 为 35 passed；测试进程定时唤醒包装下，EV/计算/提交相关测试 69 passed，Python 全套 `pytest -q -k 'not test_cli_sigterm_exits_with_sse_client_still_connected'` 为 330 passed、1 deselected。原始 `.venv/bin/python -m pytest -q` 当时在 90 秒后超时，仅输出 4 个通过点；直接组合运行 EV/提交相关三组测试在 30 秒后于 42 个通过点处仍未退出，手动中断。两者都未记为通过。
- 本次修复后，项目本机数据目录的 bohr 2.7.8 npm 归档 integrity、二进制哈希以及 Wenyon 1.36.0 manifest 哈希均核对通过；隔离 HOME 下 `extension list` 返回 `status=ok`，`wenyon dataset download --help` 返回 0，后端 `_native` 入口同样成功且回执不含密钥。`.venv/bin/python -m pytest -q` 不再需要包装：332 passed、1 skipped（沙箱禁用回环监听）。`apps/web` 的 `npm test -- --run` 为 11 passed，`npm run build` 成功；没有新增模型调用、Job 或 Attempt。
- 新授权的 PR-3 单次重试已执行：bohr 2.7.8/Wenyon 1.36.0 返回退出码 3、服务 `401 Not authenticated`，没有数据文件。回执与空文件清单在本机忽略目录 `.package-checks/wenyon-pr3-authorized-20260926/`。离线 `bohr auth status` 只确认环境中存在 AccessKey；离线 `wenyon auth whoami` 返回 `not logged in (no state)`。这不能证明 AccessKey 有效或账号拥有该数据集权限。
- 当时针对专用 CLI、扩展缺失和 401 分类的 Python 定向测试为 3 passed；前端测试 11 passed，构建与 `git diff --check` 通过。当前提交的 401 测试使用合成回执，不携带真实实验回执。
- 本轮 Linux `apps/web` 执行 `npm test -- --run`：11 passed；`npm run build` 成功。`compileall` 与 `git diff --check` 通过。上述新增科研流程测试均使用临时数据库、fake CLI/平台，未发起真实模型、Job 或 Attempt。

- 本次 Linux 项目虚拟环境执行 `.venv/bin/python -m pytest -q tests/test_collaboration.py -k 'not test_t13b_submit_guidance_failure_marks_failed and not test_t13_submit_guidance_auto_submits_without_executor'`：55 passed、2 deselected；其中 fake runtime + HTTP MCP + outbox 闭环证明零读取第三路线、可选读取、全文交付和 ACK。
- 本次在测试进程临时增加事件循环定时唤醒、未改产品代码或断言后，Python 全套除本机回环监听用例外 283 passed、1 deselected；回环 CLI 关闭用例单独获准本机监听后 1 passed。确切入口与局限见 `docs/SPARSE_BRAIN_UPGRADE_RESULT.md`。
- 本次执行 `.venv/bin/python checks/evaluate_sparse_brain.py`：3 个离线样例加载，0 次真实模型调用。
- 本次 `apps/web` 执行 `npm test -- --run`：10 passed；`npm run build` 成功。
- 代码与资源提交前已核查大文件、归档、数据库和已知密钥；本次公开提交不包含实际运行状态文件。
- 本轮测试进程定时唤醒包装下，协作及 Kimi/Codex 相关回归 95 passed；排除 CLI 关闭测试的 Python 回归 285 passed。默认协作测试曾以 120 秒超时退出，未记为通过。

## 尚未验证

- D1 的单次探针受沙箱网络权限阻断，未能验证平台对旧 USCT Job 的下载接口；因此 PR-4 是否为单例故障、bohr 1.1.0 是否仍能取回历史结果，均未判定。新取回状态在本轮仅经 fake CLI 和本机文件验证，尚无新生产 Job 的真实结果回执。
- PR-3 的这个 v1 样本已下载并核对，且本轮经真实 Run 物化与 Job 输入冻结；其他 Wenyon 清单格式及不同数据集的哈希语义未验证。已验证 Job 输入清单和引用，不等于验证远端实际读取。真实平台对封存包的准入结论、镜像事实和科学结果仍未验证。

- 本次已执行 Linux 原生模型往返及一个 Bohrium Job；没有比赛提交。远端 Job 的实际退出码、运行环境和产物仍未知。
- 经验改动对科研结果的因果效果尚未证明。
- CS-SB-01 的真实 Kimi/Codex 双会话往返、模型独立判断效果和原生内建工具完全禁用能力尚未验证；本轮按要求未启动真实模型或科研。
- CS-SB-01 当轮未重跑 CLI 关闭测试，也未验证未经包装的完整 pytest；该轮未修改 UI，故未重跑前端测试与构建。本轮 CS-EV-01 的前端测试与构建结果见上方。

## 阻塞项

- 下一次真实科研 Run 前，应在允许网络访问的环境中另行核实 Job 结果取回协议或客户端版本；本次唯一获授权的探针已消耗，不能把当前沙箱的 DNS/socket 拒绝记作平台或客户端协议故障。
- PR-4 唯一 Job 的旧 bohr 1.1.0 `job describe`、`job download` 及 `job_group download` 均报 `json: cannot unmarshal object into Go struct field RespErr.error of type string`，即使进程退出码为 0 也不能视作成功；`job log -o` 未取到文件。隔离的新版 bohr 2.7.8 查询同一旧协议 Job 返回 `RESOURCE_NOT_FOUND`。因此 `facts.json`、`data-proof.json` 未取得，`image_facts` 未登记；本轮上限 1 Job，不重投。
- 本次登录及其后的单次下载授权已使用；任何额外账号数据访问仍需新授权。本沙箱禁止回环监听，故 CLI SIGTERM/SSE 测试在此环境明确跳过；此前在允许回环监听的环境曾单独通过，当前代码没有在该环境重跑。
