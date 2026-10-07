# CS-UP-13 修复证据

阶段 1 按 W0–W8 施工，真实回执与 fake 分开记录。原始数据只在忽略目录。
尚未完成的验收不会标为通过。阶段 2 另见 CS_UP_14_EVIDENCE。

## W0

D-63–D-72 原文已加入 §5。开局 main 比 origin/main 落后 13 个 S4 文档/分析提交；rebase 的 STATUS 冲突已停止，原 W0 提交保留在 archive/cs-up-13-w0-before-sync，在最新 origin 上重新应用内容。使用已有 Windows gh 凭据 helper 单次调用推送，未保存凭据、未强推。

## W1

- 无上限收割统一调用 `run_limits.track_unlimited`，不会扩大历史独立 Run 的有限授权。红测试两种收割均失败；修复后覆盖一键确认→授权零计数→实验分确认→阈值/窗口收割。`w1-green-final.log` 82 passed；新增的一键完整链路等 `w1-integration.log` 10 passed。
- 两份彩排真实公开事件输入 5,600,974 / 2,446,981 字符，旧整段脱敏分别在 875,323 / 948,762 位置无法解析；字符串字段递归脱敏后 JSON roundtrip 均通过。`w1-real-redaction.json`。超长、转义引号测试已通过；历史 failed 维护记录未改写，不声称真实模型复盘成功。
- 三个环境文件与账本差异只有过期降级状态和固定待复核说明。新增受控登记只接受已登记 system_environment 旧修订的精确过期转换；文件正文或其他字段变化仍拒绝。三个文件字节保持不变，新修订为 candidate，不进入有效经验。`w1-environment-recovery.json`，原文件与 diff 已保留。写入来源的具体进程身份 unknown；不能用这些已过期观察当新鲜能力。
- 封包拦截真实平台拒绝的 `handoff.status=complete`，给出省略可选字段或诚实交接状态的提示；characterization 指针须存在且为 JSON 对象。公开 schema 的 complete 仍被允许，本次 GET 刷新后依然如此，DECISIONS 保留这一协议差异。现有预提交 public schema 验证继续保留；未编造 `modality` 必填字段。
- 沙箱创建超过 600 秒、请求 ID 404 且完整列表证明不存在时，添加列 unknown_slot_released 释放并发占位；对外显示 unknown_released，原 status unknown 和费用预约保留。总数不完整、字段不足、已有远端 ID 均不释放，不重发。仅新增列，未重建 CHECK 表。合成协议测试通过；旧真实 unknown 的列表证据不足时仍须保留 unknown。
- 叙述变体沿用真实引用事件时间或明确事后注释写作时间；任意耗时/token 字段仍被拒绝，未发现改写时间戳的路径。既有叙述和变体回归通过。
- 六 Run 全量投影的缺结果调用数依次 1/0/3/0/0/0，无缺调用、无重复配对。缺失的原事件只有 inProgress/exec_started，也没有对应完成回执；无法诚实补齐，保留 N08 风险（替代：下一轮干净复跑保留完整原生会话）。`w1-pairing-before.json`。两个未提交 Run 没有封存包，严格“六个封存包”验收无法满足，将在 W4 以四个真实包和六 Run 投影分别核验。

证据根：`.package-checks/cs-up-13/`；只提交实现、测试和脱敏汇总。
