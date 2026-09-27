---
title: abc 本地评分的沙箱链路与失败对账边界
scope: challenge
challenge_id: local_a619cdef
status: active
evidence_status: hypothesis
kind: failure
audience: both
applicability: 本题通过产品网关创建 Bohrium 沙箱并运行 local_score 时适用；网关路径契约、沙箱接口、评分器版本或账本对账能力变化后须重新核验。经验不增加沙箱创建、Job
  或提交授权。
evidence_refs:
- checkpoint:cp_14d4060324
- checkpoint:cp_1aefb34604
- checkpoint:cp_3914d2e025
- checkpoint:cp_3a050349b7
- checkpoint:cp_861b5bb05a
- checkpoint:cp_9f235bcb90
- checkpoint:cp_f1bb350bcf
- checkpoint:cp_fd8a89b7ae
- event:run_06316b6fa6:163
id: exp_6bdc973e0c
tags: []
---
既往 Trial 的沙箱创建先后遇到 INVALID_ARGUMENTS 和网关 INVALID_PATH；后者不能证明远端已检验 cpu、镜像和超时参数，失败操作须按原 operation_id 对账，不以新标识重试未知操作。本次修复后验收中，执行器检查点报告结果包预检 admitted；唯一一次以 cpu=2c4g、声明镜像、timeout=600 创建的沙箱进入 active；一次 research_local_score 返回最终 local_scores 行 ls_cc04d41aabb1，science_score=20.0、confidence=medium。评分后一次删除，随后只读 describe 返回 RESOURCE_NOT_FOUND，账本为 deleted、active_or_unknown=0，累计占用约 1.91 分钟。此结果支持本次调用链可完成，不能单独证明具体修复的因果作用，也不能把题面本地 20.0 分当作平台 ARM 正式评分。以上新事实来自执行器检查点；原始回执有保存路径和哈希，本次大脑未独立读取其内容。
