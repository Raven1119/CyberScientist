# 经验运行时接入规格

## 1. 本包导入后已经得到什么

旧版可读的 Markdown、与其完全一致的初始 SQLite 修订、题内可试用组合、全局候选和安装审计信息。原版存储的读取兼容性通过隔离夹具验证，完整产品/原生 CLI/比赛端点未在本包验证。

导入没有实现：统一上下文选择、跨角色冻结投影、结构化实际采用、因果收益评估、自动处理迟到评分或修复 B01–B21。以下是这些能力的可施工规格；细化设计见 EXPERIENCE_PLAN.md。

## 2. 一个完整切片：经验在下一轮被可信复用

沿用当前大脑与执行器。修复存储版本和控制正确性后，只新增 `experience_context.py`，复用现有事件、指导、检查点与审阅 worker。

| 接口/位置 | 输入 | 输出与关键约束 |
|---|---|---|
| `experiences.py` 的版本读写 | id、expected_revision、操作者、内容或回滚目标 | 明确 revision_id/content_hash/head/active；不凭创建时间猜当前版 |
| `experience_context.select_for` | challenge_id、当前目标、角色、预算 | 候选可为空；保持适用条件和证据等级；一个选择来源 |
| `experience_context.freeze` | 选择结果、run/trial/frame 引用 | 最终交付文本与哈希；本轮编辑不改变包 |
| controller 的 Trial 启动和指导 | 同一冻结包、角色投影 | 执行器获得固定正文/路径；大脑获得判断视图；不读可变目录冒充快照 |
| `Decision` / `Guidance` 的可选 experience_refs | id + revision_id + 使用理由 | 仅声明采用，不直接计科学收益 |
| checkpoint 可选 experience_uses | use_id、采用/质疑、行动与结果引用 | 本 Run/Trial 绑定；引用已冻结版本；没有证据就 reported/unknown |
| `observation.py` | 真实已处理事件区间、提交/评分记录 | 结构化新结果、确切覆盖游标、保留原始证据定位 |
| 已有 curation 审阅 | 尚未整理的采用结果和反例 | 新建/修订/不变；不把整轮 MAX(score) 分配给每条经验 |

新增两张表：`experience_heads`（head_revision_id/active_revision_id）和 `experience_uses`（presented/adopted 与 result_refs）；修订操作用独立 ID，内容 hash 可以重复。用途与变化写现有 append-only events，不创建另一套学习事件总线。

使用事件的最小形状（仅示例，需在对应 schema/MCP/API/前端同时接入）：

```json
{
  "experience_id": "exp_example",
  "revision_id": "rev_example",
  "disposition": "adopted",
  "reason_md": "用于决定先做哪一个可区分解释的实验",
  "action_refs": ["checkpoint:actual-checkpoint-id"],
  "result_refs": [],
  "attribution": "reported_not_causal"
}
```

这些 example ID 不是实际证据，不能原样写入生产。判断采用与指导采纳的 ACK 分开，查阅次数不自动变成使用收益。

## 3. 必须同时改通的真实路径

`controller._lifecycle_packet`、`observation._selected_experiences`、Trial task_text 使用同一冻结渲染入口；保留总字符预算，避免全局条目固定排在前面。处理不了自由文本适用性时交给现有模型判断，不加硬编码科研裁判。

`_apply_experience_proposal` 更新已有条目时保留扩展元数据，检查当前题归属及期望版本；题内可自动 active+hypothesis，全局编辑只更新草稿，旧批准版继续可用。`ExperiencePage` 区分草稿/生效版并按用户实际看到的 revision 审批。

`_experience_usage` 的历史内容改名 availability_only；不得回填 adopted。`poll_scores` 带具体 submission、Trial、产物 hash/最终性进入帧。新的经验不能关联到它产生以前的成绩。

大脑可以在当前审阅中整理新证据；暂停/终止/额度尽后只保留待处理引用，下次授权再消费。一次整理可以没有新条目；失败事实和被否决版本保留。

## 4. 三个验收阶段

| 阶段 | 完整验收 |
|---|---|
| A 可信保存和运行 | B01/B02/B03/B06/B20 修订与审批；B13–B19 控制/提交闭环；旧数据先备份，错误历史保持未知 |
| B 一次可信复用 | 第一轮产生题内经验，第二轮采用固定 revision，结果回联；编辑/回滚不会改变已冻结输入；B09–B12 覆盖反馈链 |
| C 连续改进 | 相同模型/工具/总预算下比较无经验、固定先验、先验+在线更新；测试任务与提炼材料按时间隔离 |

验收必须包括一次反例使经验缩小范围，以及“本轮没有新经验”。所有消耗计入比较；先证明闭环，再考虑 embedding/效用排序或图结构。不要新增第三个常驻 agent、权重训练或分布式存储。

源码更新后，重新以当前代码建立 source fingerprint。旧版离线导入器不得向新 head/active 架构直接写旧表。新版原生导入应满足同样的状态策略、ID 命名、来源保留和幂等断言。
