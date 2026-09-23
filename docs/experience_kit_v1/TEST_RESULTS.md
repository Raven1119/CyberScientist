# 本包验证记录

## 已实际验证

Python 3.13.5 / Linux。运行 `python tools/run_checks.py`：**18 tests，全部通过**。完整日志与环境见压缩包 `checks/importer_tests.log`、`checks/TEST_RESULTS.json`。

测试使用与审计基线 Git blob 完全一致的 `experiences.py`，其依赖为隔离 SQLite/config/db 夹具；不是完整应用环境。

| 范围 | 实际检查 |
|---|---|
| 内容与完整性 | 12 条种子、7 个组合、合法 frontmatter、来源/边界、每组合最多5条且正文总字符低于6000 |
| 初始导入 | ID文件名不碰撞，原版读取模块能读回全部条目，文件/正文/hash/修订一致 |
| 治理 | 全局 candidate+hypothesis；绑定题目 active+hypothesis；不伪装前端审批 |
| 重复与修改 | 重复导入无新增修订；用户编辑保留；真实题目ID绑定；无效ID拒绝 |
| 写入安全 | Dry-run不写仓库，工作区锁占用时拒绝，源码变化/新head表拒绝旧表写入 |
| 恢复 | 初次文件写入前中断保留pending并可重试；孤儿历史不盲目重建 |
| 撤回与保护 | 仅退役本次新建且未修改条目，保留历史与后续用户修改；不改源码/settings/secrets |

另重跑原审计探针：经验11、链路6、提交3，**20个预期缺陷均重新观察到**。这表明旧缺陷可在指定夹具中复现，不能称为20项产品回归通过。原包证据完整保留在 `reference/audit_46bba5d/`；本轮重跑日志单独保存。

## 未执行

未在用户真实工作区安装，未运行整仓 pytest、前端构建/浏览器、Windows锁、Codex/Kimi/Prime、模型往返、Bohrium Job或比赛提交。未应用21项修复，未测得经验的科研收益。

## 在接收环境复验

先 `check-package`，再在仓库现有Python环境执行 `python <pack>/tools/run_checks.py`。应用导入后按receipt运行 `verify`。真正的经验采用与增益应由后续的运行时接入和等预算实验检验，不由导入器自评。
