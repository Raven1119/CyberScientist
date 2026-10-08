---
name: cyberscientist-local-scorer
description: Build and calibrate a challenge-specific local science scorer against an explicit rubric and confirmed platform feedback.
metadata:
  audience: both
---

# 本地科学评分器

从题面、公开评分协议和已确认的提交回执提取可复刻的计分条件。将可直接验证的条件写成确定性检查；隐藏参考值或不可观测门槛保持未知，给出低置信度或分数区间，不用一次反馈推断通用规则。不得通过构造提交索取隐藏答案或测试数据。

先核对每条样本在提交时的轮次、评分策略、原始科学文件和分项回执。只有同一评分方式下可配对的输入与科学分，才用于推断字段、门槛或容差；仅有总分时记录“不可复刻”。主办方告知的 30–70 轨迹因子规则是外部规则，不是从历史分数推断的。CS-UP-03R 的 71 条历史实时分项记录没有可取回科学包或轨迹；10 条完整展示分与告知规则冲突，另一个分段计算虽能在样本内解释它们，平台未确认其适用性，见 `docs/SCORER_REVERSE_ENGINEERING.md`。不要把这些分数当作产物评分器的验收样本。

用 `scorer.json` 声明 Python 入口、题目镜像、人工版本和契约版本。入口接收从封存ARM包提取的科学输入ZIP：轨迹成员已剔除，manifest的trace指针已移除。只输出一个JSON对象：`score`（0–100）、`components`、`confidence`、`notes`、`scorer_version`；最后一项使用运行时提供的`CS_SCORER_VERSION`。科学计算、依赖验证和科学评分在授权 Bohrium Job 或沙箱完成；本机仅准备代码、文件与应用诊断。正式评分继续通过下述可信登记通道，不能把本地自报值当系统评分。

题目已有 `challenges/<challenge_id>/scorer/` 或 `workspace/challenges/<challenge_id>/scorer/` 时保持只读，科研 Run 不得改写。若工具明确返回 `SCORER_MISSING`，在**当前 Trial 目录内**创建独立草稿（如 `scorer-draft/`），按公开题面构建检查，不读取隐藏答案、不自行提高权重；缺失规则保持 unknown/低置信度。调用 `research_local_score(action="initialize", trial_id="当前Trial", operation_id="稳定ID", source_directory="草稿绝对路径")`。后端只校验并冻结这一次草稿，不在本机执行；记录源路径和全部文件哈希。成功后题目评分器不可替换或再次初始化，即使删除也不能重建。需要修正现有评分器时报告问题，不能在 Run 中自改。初始化的候选评分器没有官方评分权威；系统验证执行回执不意味着验证其科学标尺。随后用 `prepare_job/register_job` 或 `prepare/register` 执行评分并登记。

提交前对当前产物做本地评分，把评分器版本、封存包哈希和分项写入账本；建议在实验提交时写下可证伪的分数变化预测，缺失则记录 unknown。平台分数只有在 `confirmed` 后才作为校准目标。对齐同一封存包哈希，分别看科学分、轨迹分和展示分；分数或回执修订时更新校准状态，不悄悄覆盖旧预测。将不一致归因于具体尚未复刻的规则，而非伪造更高本地分。

子项候选只有经 `research_local_score` 评分并登记后，才进入本 Run 的正式候选记录；独立实验日志中的自报数值不会自动登记。评分器的 `components` 中，嵌套子项用 `score`、`points` 或 `*_score` 表示分数，其余字段为诊断。系统按 Run、评分器哈希和完整科学输入哈希复用评分；finish 会比较实际最终包与已登记的子项最佳成绩。退步作为可见事实交给 PI 判断；可选择修复，也可在 finish 中可选记录 `finish_confirmation` 的 token 和 reason_md 后如实收尾。系统不替换产物，确认不增加权限。

已有评分器的科研 Run 保持评分器只读。需要自行准备环境或系统评分失败时，用 `research_local_score(action=prepare)` 固定当前候选与评分输入；按返回的 transfers 在本 Trial 的受控沙箱中传输文件，自行准备依赖，再通过 `research_sandbox(action=exec)` 执行返回的完整 command。以同一次 exec 的 operation_id 作为 `execution_operation_id` 调用 `research_local_score(action=register)`；也可用 `prepare_job` 固定输入后在已授权 Job 执行完整 command，再用 `register_job` 对账。后端核对自己的回执后才登记正式分，来源为 `executor_verified`。有声明环境时，用 environment_paths 指定实际工具链、公共库和固定项目所在路径；身份和项目哈希在评分执行中核对。环境准备、评分器 ZIP、科学 ZIP 或公开数据有误时，按返回的事实修复后明确选择下一操作。

提交或最终评分被拒绝时，继续当前 Run 并处理系统修复反馈。先通过 `research_operating_facts` 查看剩余时间、额度、价格和环境事实，自行安排环境准备与最终评分。远端状态 unknown 的原操作保持原 ID 并只读对账；反馈本身不新增授权，不自动重发。

## 通用评分骨架（S4 60 题归纳）

S4 各题的科学评分都可以拆成五步。建本地评分器时按这个顺序搭，题面没说清的部分标为 unknown，不要猜：

1. **门槛**（每题平均约 5 条）：文件存在、格式和列名、数量约束（如"恰好 t 个"）、数值有限、物理约束（如酉性容差、粒子数）、唯一性等。任一不满足时，该项或整题记 0，并在 `components` 中写明哪条门槛失败。
2. **指标**：按题面逐项计算（误差、保真度、能量、覆盖率等）。
3. **映射**：把指标变成分数。S4 中出现的映射类型及题数：
   - 容差内满分、容差外 0 或递减（65）；
   - 二值对错（51）；
   - 部分分（35）；
   - 线性截断（25），如 `25 × clip((F−0.80)/0.19, 0, 1)`；
   - 分档（6）；
   - 大模型评审（4）；
   - 排名（3）。

   参数一律逐字取自题面。
4. **汇总**：按题面权重加总。题面没给权重时，写明假设并降低置信度。
5. **重放**：60 题中 24 题明确要求在容器中重放。本地用干净环境运行入口脚本，确认输出能重新生成。

隐藏参考数据无法取得时，用公开部分、解析极限或自洽性检查给出分数区间，`confidence` 设低。不得试图获取隐藏答案。
