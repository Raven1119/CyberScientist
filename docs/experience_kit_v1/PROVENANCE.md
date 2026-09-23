# 来源与证据等级

基线：`46bba5d0bc24a03ec1be889384442e6dbe36ced2`；本轮通过 GitHub 读取 main 确认未变。

<a id="design-prior"></a>
## design-prior

本包 12 条条目均为**设计先验（hypothesis）**。来源中的事实可以是实际代码或历史运行记录，但从事实提出的可迁移协作策略尚需在使用中检验。没有捏造支持次数、成功率、因果收益、运行 ID 或比赛评分。

| 来源 | 可支持内容 | 不能据此推断 |
|---|---|---|
| 同包 AUDIT.md 与隔离复现证据 | 指定基线上的程序症状、对持续学习的风险 | 修复已经上线；所有环境均复现；策略能提升胜率 |
| 仓库 `checks/build_arm_bundle.py` | Aiyagari 复现打包时记录的误差及未完成消融 | 尚未完成的替代离散化已经成功 |
| 仓库 `STATUS.md` | 历史工具来源、状态传递与资源阻塞记录 | 用户当前账户仍无配额；当前赛题契约未变 |
| 仓库 `prompts/collaboration/executor.md`、`collab.py` | 当前协作角色及接口约定 | 工具返回、ACK 就等于研究完成 |
| 用户先前的原子构型修复描述 | 曾报告精度、分支切割与符号约定相关问题 | 旧题数值阈值、符号修复可以通用于新材料 |
| 其余方法型条目 | 本包提出的条件化协作与诊断流程 | 已在某科研基准、比赛任务或用户工作区实测有效 |

固定代码入口：

- https://github.com/Raven1119/CyberScientist/tree/46bba5d0bc24a03ec1be889384442e6dbe36ced2
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/checks/build_arm_bundle.py
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/STATUS.md
- https://github.com/Raven1119/CyberScientist/blob/46bba5d0bc24a03ec1be889384442e6dbe36ced2/prompts/collaboration/executor.md

`source_type`、`seed_pack`、`seed_id`、`derived_from` 是旧版解析器允许保留的附加元数据；旧版控制器更新可能丢失它们（B06），所以关键证据等级及边界也写入正文。不存在运行结果时继续保持 hypothesis。
