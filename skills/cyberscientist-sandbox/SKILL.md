---
name: cyberscientist-sandbox
description: Use the Run-scoped Bohrium sandbox for authorized interactive scientific checks, debugging, and evaluation inside a chosen image.
---

# 沙箱使用

开局把交付契约、验证器和环境准备同时排上。先从环境登记簿和最新 environment 经验读配方，执行一个能覆盖关键依赖的远端冒烟测试。成功后以执行操作 ID 调用 `research_environment` 的 `record_smoke`，附可以直接复用的安装命令、依赖版本与冒烟命令；后端核验自己的真实回执。该记录证明当前环境可运行，持久镜像仍需另行授权构建/验证。遇到环境问题先套用已有配方。

用 `research_sandbox` 或本 Run 的 `bohr sandbox` 代理搭环境和调依赖；确认可行后优先用受控 Job 做批量计算，也可在授权内选择适合当前证据的沙箱实验。沙箱和 Job 均消耗各自的本轮授权；创建前查看剩余分钟、当前沙箱数量和预期费用。没有沙箱授权时报告缺项。

创建须提供稳定 `operation_id`、正数 `timeout` 秒。网关强制项目 ID，限制本轮剩余时长和累计沙箱分钟。创建结果 `unknown` 时调用 `reconcile` 按原 request ID 查询，不重发创建。MCP 的 `exec` 和 `files.write` 也须各用稳定的 `operation_id`，以防回执丢失后重复执行。执行命令给出不超过沙箱剩余存活时间的 timeout；执行回执和事件可供审阅与轨迹使用。文件读写仅能指向当前 Trial 或题目工作目录；运行结果要保存到本地受控工作目录，再在检查点引用。

指定题目镜像时用 `image` 与合适的 `cpu` 配置；不要假定默认镜像有科研依赖。GPU 需要本轮单独授权。无后续用途时 `delete` 并检查账本状态；有授权复用价值时保留环境并记录剩余额度；删除结果未知时报告，不重复发删除。挂载用户存储、Wenyon、继承认证及无限期实例不在当前网关支持范围内。
