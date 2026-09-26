# CS-EV-01 真实运行与 PR-4 Job 验收（2026-09-26）

结论：**部分通过**。Linux connected Run 完成一次 Codex 大脑与执行器的真实往返、官方 Wenyon 数据物化、冻结输入、唯一 CPU Job 创建与远端列表对账；结果下载失败，因此不能确认远端脚本、数据读取或镜像事实探针成功。Run 由大脑按 `partial` 裁决结束，没有比赛 Attempt。

## 授权与执行范围

- 本轮授权最长 20 分钟、至多 1 个 Job、同时至多 1 个，Job 资源上限为 2 CPU、2 GB 内存、10 GB 磁盘、无 GPU；Job 自身 `max_run_time=5` 分钟，禁止重调度，`max_submissions=0`。
- 题目的一份 Wenyon v1 公开数据在本 Run 内下载并核验。平台清单所列 2 个文件共 1148 字节；原始 `public-manifest.json` 的 SHA-256、清单成员哈希和大小、题目登记总字节数一致。物化状态为 `verified`，哈希语义为 `manifest_sha256`。
- 缺失本地 Python 模块的预检在 Job 预留前以 `MISSING_LOCAL_MODULE` 拒绝。真实机器目录没有模板中的 `c1_m1_cpu`，据目录改用最小可用的 `c2_m2_cpu`。
- 唯一 Job 经受控 `compute.submit` 路径创建；输入清单和计算账本都包含本轮已验证数据的物化引用。远端创建回执含 Job ID，后续列表对账观察到 `Finished`。账本统计为 1 个 Job、0 个 Attempt、0 条镜像事实；Run 有 193 条规范化事件和 6 次大脑审阅。

## 发现的问题与证据边界

开局大脑实际给出结构合法的 v2 Decision，解析器却只接受 v1，导致 Run 暂停。修复后对原始最终消息的提取与结构校验通过，使用原 Run 的 recovery 控制继续，没有另建 Run。新增 fenced v2 Decision 回归测试。

远端列表的 `Finished` 只证明列表状态。旧 bohr 1.1.0 的 `job describe`、`job download` 和 Job 组下载均返回 `json: cannot unmarshal object into Go struct field RespErr.error of type string`；这些命令的进程退出码为 0，但网关如实标记 `ok=false`。`job log -o` 未取得文件；隔离的新版 bohr 2.7.8 对该旧协议 Job 返回 `RESOURCE_NOT_FOUND`。没有取得 `facts.json` 或 `data-proof.json`，故远端进程退出码、镜像依赖/API、实际文件读取及其哈希都保持 **unknown**。未重投 Job，也未用准备但未执行的脚本冒充结果。

执行器交付的检查点和结果包明确记为部分验收；大脑据此结束目标。完整 Run/Trial/Job 标识、冻结输入哈希、原始回执、迁移前 SQLite 备份与交付包仅在本机被 Git 忽略的 `.package-checks/real-acceptance-20260926T073421Z/` 和 `workspace/runs/` 中保留，供后续审计。此文档只发布结论与验证范围，不包含实验文件或凭据。

提交前离线回归命令 `.venv/bin/pytest -q` 和前端测试、构建的最终结果记于 `STATUS.md`；这些测试不访问 Bohrium。真实下载文件和回执未进入可提交测试 fixture，可提交的 Wenyon v1 测试在运行时生成合成清单。
