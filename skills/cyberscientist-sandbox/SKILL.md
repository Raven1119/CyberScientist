---
name: cyberscientist-sandbox
description: Use the Run-scoped Bohrium sandbox for short interactive scientific checks, debugging, and evaluation inside a chosen image.
---

# 沙箱使用

用 `research_sandbox` 或本 Run 的 `bohr sandbox` 代理进行短时探索、脚本调试和题目镜像内的快速评测。长时间、可批处理或需稳定产物的计算使用受控 Job。沙箱和 Job 均消耗各自的本轮授权；创建前查看剩余分钟、当前沙箱数量和预期费用。没有沙箱授权时报告缺项。

创建须提供稳定 `operation_id`、正数 `timeout` 秒。网关强制项目 ID，限制本轮剩余时长和累计沙箱分钟。创建结果 `unknown` 时调用 `reconcile` 按原 request ID 查询，不重发创建。MCP 的 `exec` 和 `files.write` 也须各用稳定的 `operation_id`，以防回执丢失后重复执行。执行命令给出不超过沙箱剩余存活时间的 timeout；执行回执和事件可供审阅与轨迹使用。文件读写仅能指向当前 Trial 或题目工作目录；运行结果要保存到本地受控工作目录，再在检查点引用。

指定题目镜像时用 `image` 与合适的 `cpu` 配置；不要假定默认镜像有科研依赖。GPU 需要本轮单独授权。用完立即 `delete`，检查账本状态；删除结果未知时报告，不重复发删除。挂载用户存储、Wenyon、继承认证及无限期实例不在当前网关支持范围内。
