# 注意力审计 2026-10-09

范围：模型实际输入与工具输出；读取权限不等于已经进入上下文。数据取自唯一真实冒烟Run及比赛发布文件；所有未调用角色明确用模板还原，不能当成真实原生证据。正文内容只列问题，不在本卡改技能或经验。

## 取值与送达分支

| 设置 | 实际值 | 决定的输入 |
|---|---|---|
| evidence_mode | "competition" | controller使用比赛生命周期与原生轨迹封存 |
| progressive_context | true | compact将经验/环境正文降为索引，保留题面和能力 |
| local_calculation | false | 关闭科研本地计算入口 |
| science_compute | "sandbox_first" | 本题常驻沙箱/同镜像Job通路 |
| clean_run_policy | "when_not_accepted" | clean_runs.offer发起建议条件 |
| initial_method_approval | true | 方法提案完整后关闭计算门等待批准 |
| science_first_flow | true | 真实科学回执优先；本地诊断不硬拦提交 |
| reviewer | true | 仅PI显式request_package_review时调用 |
| scorer_audit | true | 只读审查模板含评分器审计 |
| deepseek_fallback | true | 供应商故障回退配置；本轮未授权额外模型，不主动调用 |

PI默认Astra xhigh/fast，执行者Terra(gpt-6.1-sol) high/fast。post_review默认provider=deepseek、model=deepseek-flash；它不是PI默认，但属于备用维护配置，本轮不结束Run、不授权复盘，因此只列模板不调用。

## 实际原生输入完整清单

唯一 Run `run_f9a4404816`，探索和干净复跑各一个真实 Trial。下表覆盖采样时原生记录全部 session_meta、world_state、turn_context、消息和工具调用/返回；不重复 event_msg 日志，也不将加密推理当作可见输入。字节数是该帧 payload 的紧凑 UTF-8 JSON 字节数，不是 token 数；调用和助手历史是在后续回合中可见的内容。全部原始帧留在私有本机，不进 Git。

| 角色 | 原生线程 | 原生字节 | 前八帧角色标记 | 开发绝对路径命中 | 全局AGENTS命中 | 比赛外技能命中 |
|---|---|---:|---|---:|---:|---|
| PI | `01a11fab-c781-7703-8403-e410413e6736` | 1489613 | True | 0 | 0 | {"checkpoint": 26, "resume": 24} |
| 探索执行者 | `01a11fab-dde5-7202-ae1d-9a9c7324f310` | 1361666 | True | 0 | 0 | {"brainstorm": 4, "checkpoint": 15, "distill": 4, "orchestrate": 4, "reflect": 4, "resume": 11, "wrap-up": 4} |
| 干净复跑执行者 | `01a11fe5-9115-7963-8200-888a697597f4` | 824091 | True | 0 | 0 | {"checkpoint": 11, "resume": 1} |

| 角色 | 原生文件:行 / 轮 | 帧种类 | 字节数 | 内容摘要 | 判定 | 建议 |
|---|---|---|---:|---|---|---|
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:1` / 0 | `session_meta//` | 22398 | 供应商基础指令、动态工具定义、元数据 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` / 0 | `response_item/message/developer` | 30574 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:4` / 0 | `response_item/message/developer` | 2778 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:5` / 0 | `response_item/message/developer` | 584 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:6` / 0 | `response_item/message/user` | 856 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:7` / 0 | `world_state//` | 16180 | 供应商运行时工作区状态 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:8` / 1 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:9` / 1 | `response_item/message/user` | 35536 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:14` / 1 | `response_item/message/assistant` | 425 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:15` / 1 | `response_item/custom_tool_call/` | 471 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:17` / 1 | `response_item/custom_tool_call_output/` | 409 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:26` / 1 | `response_item/message/assistant` | 9364 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:32` / 2 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:33` / 2 | `response_item/message/user` | 33914 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:36` / 2 | `response_item/message/assistant` | 502 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:37` / 2 | `response_item/custom_tool_call/` | 465 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:39` / 2 | `response_item/custom_tool_call_output/` | 1417 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:43` / 2 | `response_item/custom_tool_call/` | 375 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:45` / 2 | `response_item/custom_tool_call_output/` | 5365 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:49` / 2 | `response_item/custom_tool_call/` | 857 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:54` / 2 | `response_item/custom_tool_call_output/` | 1314 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:58` / 2 | `response_item/custom_tool_call/` | 831 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:63` / 2 | `response_item/custom_tool_call_output/` | 7747 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:67` / 2 | `response_item/custom_tool_call/` | 691 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:72` / 2 | `response_item/custom_tool_call_output/` | 6080 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:74` / 2 | `response_item/custom_tool_call/` | 934 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:79` / 2 | `response_item/custom_tool_call_output/` | 2922 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:84` / 2 | `response_item/message/assistant` | 658 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:85` / 2 | `response_item/custom_tool_call/` | 872 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:89` / 2 | `response_item/custom_tool_call_output/` | 7484 | 真实工具返回（包括ls/cat/research_*内容） | 内容待设计复核 | 旧规则:先过门 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:93` / 2 | `response_item/custom_tool_call/` | 394 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:96` / 2 | `response_item/custom_tool_call_output/` | 21477 | 真实工具返回（包括ls/cat/research_*内容） | 内容待设计复核 | 旧规则:30 分钟 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:100` / 2 | `response_item/custom_tool_call/` | 654 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:106` / 2 | `response_item/custom_tool_call_output/` | 32449 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:115` / 2 | `response_item/message/assistant` | 13020 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:121` / 3 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:122` / 3 | `response_item/message/user` | 38850 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:128` / 3 | `response_item/message/assistant` | 3397 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:134` / 4 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:135` / 4 | `response_item/message/user` | 41972 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:140` / 4 | `response_item/message/assistant` | 430 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:141` / 4 | `response_item/custom_tool_call/` | 759 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:148` / 4 | `response_item/custom_tool_call_output/` | 8912 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:152` / 4 | `response_item/custom_tool_call/` | 737 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:160` / 4 | `response_item/custom_tool_call_output/` | 61208 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:164` / 4 | `response_item/custom_tool_call/` | 631 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:168` / 4 | `response_item/custom_tool_call_output/` | 4882 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:172` / 4 | `response_item/custom_tool_call/` | 600 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:177` / 4 | `response_item/custom_tool_call_output/` | 26339 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:182` / 4 | `response_item/message/assistant` | 2122 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:189` / 4 | `response_item/message/developer` | 8675 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:190` / 4 | `world_state//` | 8375 | 供应商运行时工作区状态 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:191` / 5 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:192` / 5 | `response_item/message/user` | 39797 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:197` / 5 | `response_item/message/assistant` | 1407 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:203` / 6 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:204` / 6 | `response_item/message/user` | 42417 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:209` / 6 | `response_item/message/assistant` | 534 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:210` / 6 | `response_item/custom_tool_call/` | 656 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:214` / 6 | `response_item/custom_tool_call_output/` | 3606 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:216` / 6 | `response_item/custom_tool_call/` | 432 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:219` / 6 | `response_item/custom_tool_call_output/` | 2024 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:228` / 6 | `response_item/message/assistant` | 10688 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:234` / 7 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:235` / 7 | `response_item/message/user` | 39914 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:240` / 7 | `response_item/message/assistant` | 476 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:241` / 7 | `response_item/custom_tool_call/` | 830 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:249` / 7 | `response_item/custom_tool_call_output/` | 9462 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:253` / 7 | `response_item/custom_tool_call/` | 905 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:259` / 7 | `response_item/custom_tool_call_output/` | 17321 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:263` / 7 | `response_item/custom_tool_call/` | 599 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:268` / 7 | `response_item/custom_tool_call_output/` | 19555 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:273` / 7 | `response_item/message/assistant` | 2070 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:280` / 8 | `turn_context//` | 889 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:281` / 8 | `response_item/message/user` | 37716 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| PI | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:286` / 8 | `response_item/message/assistant` | 1315 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:1` / 0 | `session_meta//` | 22801 | 供应商基础指令、动态工具定义、元数据 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` / 0 | `response_item/message/developer` | 20252 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:4` / 0 | `response_item/message/developer` | 2778 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:5` / 0 | `response_item/message/developer` | 584 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:6` / 0 | `response_item/message/user` | 2171 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:7` / 0 | `world_state//` | 17495 | 供应商运行时工作区状态 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:8` / 1 | `turn_context//` | 4679 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:9` / 1 | `response_item/message/user` | 33154 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:12` / 1 | `response_item/message/assistant` | 591 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:13` / 1 | `response_item/custom_tool_call/` | 880 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:17` / 1 | `response_item/custom_tool_call_output/` | 10591 | 真实工具返回（包括ls/cat/research_*内容） | 内容待设计复核 | 旧规则:先过门 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:19` / 1 | `response_item/custom_tool_call/` | 944 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:25` / 1 | `response_item/custom_tool_call_output/` | 47632 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:29` / 1 | `response_item/custom_tool_call/` | 1343 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:36` / 1 | `response_item/custom_tool_call_output/` | 48191 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:41` / 1 | `response_item/message/assistant` | 645 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:42` / 1 | `response_item/custom_tool_call/` | 822 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:46` / 1 | `response_item/custom_tool_call_output/` | 6037 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:50` / 1 | `response_item/custom_tool_call/` | 1579 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:54` / 1 | `response_item/custom_tool_call_output/` | 40367 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:58` / 1 | `response_item/custom_tool_call/` | 4306 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:62` / 1 | `response_item/custom_tool_call_output/` | 4388 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:67` / 1 | `response_item/message/assistant` | 623 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:68` / 1 | `response_item/custom_tool_call/` | 4575 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:73` / 1 | `response_item/custom_tool_call_output/` | 7796 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:77` / 1 | `response_item/custom_tool_call/` | 2808 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:86` / 1 | `response_item/custom_tool_call_output/` | 1384 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:90` / 1 | `response_item/function_call/` | 355 | 模型产生的工具调用，保留后续上下文；wait | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:93` / 1 | `response_item/function_call_output/` | 10276 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:97` / 1 | `response_item/function_call/` | 355 | 模型产生的工具调用，保留后续上下文；wait | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:101` / 1 | `response_item/function_call_output/` | 3865 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:105` / 1 | `response_item/custom_tool_call/` | 1071 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:109` / 1 | `response_item/custom_tool_call_output/` | 38818 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:114` / 1 | `response_item/message/assistant` | 666 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:115` / 1 | `response_item/custom_tool_call/` | 1461 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:119` / 1 | `response_item/custom_tool_call_output/` | 7787 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:123` / 1 | `response_item/custom_tool_call/` | 553 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:126` / 1 | `response_item/custom_tool_call_output/` | 11867 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:130` / 1 | `response_item/custom_tool_call/` | 1125 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:135` / 1 | `response_item/custom_tool_call_output/` | 3131 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:139` / 1 | `response_item/custom_tool_call/` | 6962 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:144` / 1 | `response_item/custom_tool_call_output/` | 19579 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:148` / 1 | `response_item/custom_tool_call/` | 2377 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:151` / 1 | `response_item/custom_tool_call_output/` | 722 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 探索执行者 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:154` / 1 | `response_item/message/assistant` | 1224 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:1` / 0 | `session_meta//` | 22849 | 供应商基础指令、动态工具定义、元数据 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` / 0 | `response_item/message/developer` | 20276 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:4` / 0 | `response_item/message/developer` | 2778 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:5` / 0 | `response_item/message/developer` | 584 | 角色、系统工具和比赛技能索引 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:6` / 0 | `response_item/message/user` | 2339 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:7` / 0 | `world_state//` | 17663 | 供应商运行时工作区状态 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:8` / 1 | `turn_context//` | 4967 | 原生模型/思考强度/cwd/服务档位上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:9` / 1 | `response_item/message/user` | 53850 | 本题首条任务/每轮ReviewPacket/系统回执 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:12` / 1 | `response_item/message/assistant` | 550 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:13` / 1 | `response_item/custom_tool_call/` | 970 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:17` / 1 | `response_item/custom_tool_call_output/` | 11973 | 真实工具返回（包括ls/cat/research_*内容） | 内容待设计复核 | 旧规则:先过门 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:19` / 1 | `response_item/custom_tool_call/` | 986 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:25` / 1 | `response_item/custom_tool_call_output/` | 36652 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:29` / 1 | `response_item/custom_tool_call/` | 1039 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:33` / 1 | `response_item/custom_tool_call_output/` | 47461 | 真实工具返回（包括ls/cat/research_*内容） | 内容待设计复核 | 旧规则:先过门 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:38` / 1 | `response_item/message/assistant` | 652 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:39` / 1 | `response_item/custom_tool_call/` | 1286 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:43` / 1 | `response_item/custom_tool_call_output/` | 2750 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:47` / 1 | `response_item/custom_tool_call/` | 1279 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:53` / 1 | `response_item/custom_tool_call_output/` | 41651 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:57` / 1 | `response_item/custom_tool_call/` | 10487 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:60` / 1 | `response_item/custom_tool_call_output/` | 1248 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:65` / 1 | `response_item/message/assistant` | 573 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:66` / 1 | `response_item/custom_tool_call/` | 943 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:70` / 1 | `response_item/custom_tool_call_output/` | 2430 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:72` / 1 | `response_item/custom_tool_call/` | 1373 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:76` / 1 | `response_item/custom_tool_call_output/` | 9474 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:80` / 1 | `response_item/custom_tool_call/` | 1397 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:84` / 1 | `response_item/custom_tool_call_output/` | 3369 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:89` / 1 | `response_item/message/assistant` | 688 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:90` / 1 | `response_item/custom_tool_call/` | 909 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:94` / 1 | `response_item/custom_tool_call_output/` | 2143 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:98` / 1 | `response_item/custom_tool_call/` | 2529 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:103` / 1 | `response_item/custom_tool_call_output/` | 2560 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:107` / 1 | `response_item/custom_tool_call/` | 1708 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:112` / 1 | `response_item/custom_tool_call_output/` | 5369 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:117` / 1 | `response_item/custom_tool_call/` | 1621 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:123` / 1 | `response_item/custom_tool_call_output/` | 1072 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:128` / 1 | `response_item/message/assistant` | 728 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:129` / 1 | `response_item/custom_tool_call/` | 10183 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:133` / 1 | `response_item/custom_tool_call_output/` | 11937 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:138` / 1 | `response_item/message/assistant` | 629 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:139` / 1 | `response_item/custom_tool_call/` | 2562 | 模型产生的工具调用，保留后续上下文；exec | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:142` / 1 | `response_item/custom_tool_call_output/` | 722 | 真实工具返回（包括ls/cat/research_*内容） | 保留 | 无指定关键词命中；保留本题必要数据 |
| 干净复跑执行者 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:145` / 1 | `response_item/message/assistant` | 695 | 上轮模型答复，进入后续上下文 | 保留 | 无指定关键词命中；保留本题必要数据 |

只读审查者本轮没有调用。仅使用 `package_reviews.review` 的常驻 instructions、packet 与 output_contract 进行静态还原；不伪造原生会话。供应商基础指令中的 resume/worktree 是既有接受例外，不能据此认定读取旧 Run。

## 模板来源与送达边界

| 角色 | 内容 | 来源 | 文件字节数 | 判定 | 建议 |
|---|---|---|---:|---|---|
| PI | 角色、信任顺序、方法审批、大改、提交、四段干净复跑 | `prompts/roles/pi.md` | 4744 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| 探索/干净 | 真实实现、检查点、ack、题面契约与结果包 | `prompts/roles/executor.md` | 3113 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| PI | 每轮协议/Decision，存在角色文件已常驻的通用重复 | `prompts/collaboration/brain.md` | 5764 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| 探索 | 协作与ack规则，常驻角色外的每轮通用重复 | `prompts/collaboration/executor.md` | 6280 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| PI | compact：能力/经验/环境索引及按需读入口 | `src/cyberscientist/progressive_context.py` | 6577 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| 探索 | start_trial和prime_spec：题面/批准方法/环境/交付路径 | `src/cyberscientist/controller.py` | 298706 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| 干净 | 完整首条消息、四段、环境/技能索引、固定完成判据 | `src/cyberscientist/clean_runs.py` | 3080 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |
| 只读审查 | 专用审查任务与JSON输出契约 | `src/cyberscientist/package_reviews.py` | 17204 | 保留（重复项只列） | 运行时文件；字节数是整文件，不冒充整文件均送达 |

## 六项本方技能全文核对

逐字读取比赛目录六个SKILL.md；名称/字节数与原文摘录如下。旧规则摘录是库内发现；只有原生工具回执真的读到才算实际污染。

| 技能 | 字节数 | 判定 | 建议 |
|---|---:|---|---|
| cyberscientist-clean-rerun | 1707 | 过时/无意义编号（有摘录） | 只列，不改正文 |
| cyberscientist-job-spec | 3367 | 过时/无意义编号（有摘录） | 只列，不改正文 |
| cyberscientist-local-scorer | 6988 | 保留；方法须服从本题与新角色 | 只列，不改正文 |
| cyberscientist-sandbox | 2473 | 保留；方法须服从本题与新角色 | 只列，不改正文 |
| cyberscientist-submission-gate | 2792 | 过时/无意义编号（有摘录） | 只列，不改正文 |
| cyberscientist-trace-writing | 3616 | 过时/无意义编号（有摘录） | 只列，不改正文 |

- `skills/cyberscientist-clean-rerun/SKILL.md:18` 原文摘录：“现（写文件的命令或编辑工具，代码内容出现在轨迹中）。内容可以与探索阶段的最终版相同，但不能只把旧文件拷进来直接运行：这会被判"产物先于轨迹存在"（N17）或"重放已有解答"（N16 蒸馏）。”

- `skills/cyberscientist-job-spec/SKILL.md:18` 原文摘录：“在已有独立沙箱授权内改用沙箱；不是免费替代，也不扩权。未知 Job 按原操作身份对账：控制器证明未接受时可按现行自动重交规则处理；D-31允许超过10分钟仍无法对账时在原授权内换新 operation_id，保留旧费用估算和后台对账，后来找到时正常登记、必要时停止。禁止同一操作盲重放，不能推广成“unknown绝不重发”或“不确定就停”。”

- `skills/cyberscientist-submission-gate/SKILL.md:32` 原文摘录：“- 同一账号同一题，两次提交间隔至少 30 分钟（≤2 分钟触发突发惩罚的概率是 54%，30 分钟以上约 5%）；每题每账号尽量不超过 3–4 次。系统也会强制执行。”

- `skills/cyberscientist-submission-gate/SKILL.md:33` 原文摘录：“- 一个账号在多道题上的提交要错开，不要在 30 分钟内集中提交 5 次以上。”

- `skills/cyberscientist-trace-writing/SKILL.md:8` 原文摘录：“# 轨迹：先过门，再谈分数”

- `skills/cyberscientist-trace-writing/SKILL.md:15` 原文摘录：“   - 否则触发 N17：产物先于轨迹存在，accept 率 0；”

重点：submission-gate的30分钟节奏与新science-first行为并存；trace-writing标题“先过门，再谈分数”及无条件独立交叉验证与新角色“题目要求时才做交叉验证”冲突。job-spec含D-31内部编号；sandbox偏向Job批量计算与sandbox_first主路径需统一说明。clean-rerun要求每次新沙箱，系统clean线程与常驻本题沙箱不是同一隔离维度。以上正文保留给设计助手。

## 所有active经验逐条读取

读取122条active修订；此前开局基线122条/415494正文UTF-8字节。global与本题条目才由active_experiences过滤后形成索引，其他题条目没有因为本审计而送入模型。每行字节数为完整正文，修订哈希可复核；经验原文未修改。

| ID | scope | 正文字节数 | 来源 | 判定/建议 |
|---|---|---:|---|---|
| csup08_artifact_paths | global | 1090 | `experience/global/csup08_artifact_paths.md` | 全局仅索引，正文按题需要读取 |
| csup08_large_transfers | global | 1107 | `experience/global/csup08_large_transfers.md` | 全局仅索引，正文按题需要读取 |
| csup08_lean_environment | global | 2468 | `experience/global/csup08_lean_environment.md` | 全局仅索引，正文按题需要读取 |
| csup08_mirror_recovery | global | 1155 | `experience/global/csup08_mirror_recovery.md` | 全局仅索引，正文按题需要读取 |
| csup08_verified_local_grade | global | 1047 | `experience/global/csup08_verified_local_grade.md` | 全局仅索引，正文按题需要读取 |
| csx1_atom | global | 1193 | `experience/global/csx1_atom.md` | 全局仅索引，正文按题需要读取 |
| csx1_decide | global | 1430 | `experience/global/csx1_decide.md` | 全局仅索引，正文按题需要读取 |
| csx1_delivery | global | 1074 | `experience/global/csx1_delivery.md` | 全局仅索引，正文按题需要读取 |
| csx1_handoff | global | 1428 | `experience/global/csx1_handoff.md` | 全局仅索引，正文按题需要读取 |
| csx1_inverse | global | 1204 | `experience/global/csx1_inverse.md` | 全局仅索引，正文按题需要读取 |
| csx1_learn | global | 1347 | `experience/global/csx1_learn.md` | 全局仅索引，正文按题需要读取 |
| csx1_literature | global | 1038 | `experience/global/csx1_literature.md` | 全局仅索引，正文按题需要读取 |
| csx1_ml | global | 1131 | `experience/global/csx1_ml.md` | 全局仅索引，正文按题需要读取 |
| csx1_noise | global | 990 | `experience/global/csx1_noise.md` | 全局仅索引，正文按题需要读取 |
| csx1_numeric | global | 1248 | `experience/global/csx1_numeric.md` | 全局仅索引，正文按题需要读取 |
| csx1_reopen | global | 990 | `experience/global/csx1_reopen.md` | 全局仅索引，正文按题需要读取 |
| csx1_resource | global | 1147 | `experience/global/csx1_resource.md` | 全局仅索引，正文按题需要读取 |
| env_05c5d9e0e816a77587d8ba96 | global | 1503 | `experience/global/env_05c5d9e0e816a77587d8ba96.md` | 全局仅索引，正文按题需要读取 |
| env_27f12b667d8354cbe0a599d3 | global | 2301 | `experience/global/env_27f12b667d8354cbe0a599d3.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_4ba6c98d6c4a8f371c4d32eb | global | 6078 | `experience/global/env_4ba6c98d6c4a8f371c4d32eb.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_54ebc8461c6b9e818bcfb036 | global | 368 | `experience/global/env_54ebc8461c6b9e818bcfb036.md` | 全局仅索引，正文按题需要读取 |
| env_5f90993ab43387dac00828d0 | global | 1336 | `experience/global/env_5f90993ab43387dac00828d0.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_6603056db4bc204561d53b7b | global | 1541 | `experience/global/env_6603056db4bc204561d53b7b.md` | 全局仅索引，正文按题需要读取 |
| env_675705e5e89f6d481d62f019 | global | 5669 | `experience/global/env_675705e5e89f6d481d62f019.md` | 全局仅索引，正文按题需要读取 |
| env_72713113cbe9f65a8a9bdc4f | global | 135 | `experience/global/env_72713113cbe9f65a8a9bdc4f.md` | 全局仅索引，正文按题需要读取 |
| env_7c556087b62b76e7ebeed6eb | global | 138 | `experience/global/env_7c556087b62b76e7ebeed6eb.md` | 全局仅索引，正文按题需要读取 |
| env_805bed2952e1fba5f5c2618b | global | 6078 | `experience/global/env_805bed2952e1fba5f5c2618b.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_881caab7c7ea204219fdd5d2 | global | 2685 | `experience/global/env_881caab7c7ea204219fdd5d2.md` | 全局仅索引，正文按题需要读取 |
| env_9cf7026357c72efb8d64a97a | global | 1807 | `experience/global/env_9cf7026357c72efb8d64a97a.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_a06e53028328001387129c59 | global | 2421 | `experience/global/env_a06e53028328001387129c59.md` | 全局仅索引，正文按题需要读取 |
| env_b0c2134fb033ab0ed8763d53 | global | 3264 | `experience/global/env_b0c2134fb033ab0ed8763d53.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_b6ae19119697105d26e82a7f | global | 3446 | `experience/global/env_b6ae19119697105d26e82a7f.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| env_ea3a46cc65bdd02a9c1ad13b | global | 2839 | `experience/global/env_ea3a46cc65bdd02a9c1ad13b.md` | 全局仅索引，正文按题需要读取 |
| exp_16229f64f3 | challenge | 1937 | `experience/challenges/local_d8ff052e/exp_16229f64f3.md` | 保留原文；其他题不进入当前上下文 |
| exp_171f93edd6 | challenge | 4389 | `experience/challenges/local_2f7b3f2f7896/exp_171f93edd6.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| exp_218584b1fd | challenge | 537 | `experience/challenges/local_d7774e59/exp_218584b1fd.md` | 保留原文；其他题不进入当前上下文 |
| exp_32c5fb5a78 | challenge | 919 | `experience/challenges/local_d8ff052e/exp_32c5fb5a78.md` | 保留原文；其他题不进入当前上下文 |
| exp_408ecd977c | challenge | 5192 | `experience/challenges/local_8dc2884edcee/exp_408ecd977c.md` | 保留原文；其他题不进入当前上下文 |
| exp_4de2beaa32 | challenge | 703 | `experience/challenges/local_d7774e59/exp_4de2beaa32.md` | 保留原文；其他题不进入当前上下文 |
| exp_6bdc973e0c | challenge | 930 | `experience/challenges/local_a619cdef/exp_6bdc973e0c.md` | 保留原文；其他题不进入当前上下文 |
| exp_74ed157080 | challenge | 4481 | `experience/challenges/local_289e485d/exp_74ed157080.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| exp_755347d4e9 | challenge | 5333 | `experience/challenges/local_8dc2884edcee/exp_755347d4e9.md` | 保留原文；其他题不进入当前上下文 |
| exp_7736ba8a07 | challenge | 758 | `experience/challenges/local_d8ff052e/exp_7736ba8a07.md` | 保留原文；其他题不进入当前上下文 |
| exp_7ff9beeb97 | challenge | 2706 | `experience/challenges/local_56b7e4716ad2/exp_7ff9beeb97.md` | 保留原文；其他题不进入当前上下文 |
| exp_9531e2839c | challenge | 655 | `experience/challenges/local_289e485d/exp_9531e2839c.md` | 保留原文；其他题不进入当前上下文 |
| exp_a8640e677f | challenge | 3543 | `experience/challenges/local_a619cdef/exp_a8640e677f.md` | 保留原文；其他题不进入当前上下文 |
| exp_aebf07c31d | challenge | 574 | `experience/challenges/local_14c116ff/_arm_v1_1_generic_controller.md` | 保留原文；其他题不进入当前上下文 |
| exp_b04be443be | challenge | 6514 | `experience/challenges/local_36cd497cbd73/exp_b04be443be.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| exp_baa8258170 | challenge | 985 | `experience/challenges/local_d8ff052e/exp_baa8258170.md` | 保留原文；其他题不进入当前上下文 |
| exp_c06f411fe8 | challenge | 1735 | `experience/challenges/local_d8ff052e/exp_c06f411fe8.md` | 保留原文；其他题不进入当前上下文 |
| exp_c3b1eee74c | challenge | 560 | `experience/challenges/local_d7774e59/exp_c3b1eee74c.md` | 保留原文；其他题不进入当前上下文 |
| exp_c64038b549 | challenge | 1141 | `experience/challenges/local_d8ff052e/exp_c64038b549.md` | 保留原文；其他题不进入当前上下文 |
| exp_cf1e4b8dda | challenge | 4689 | `experience/challenges/local_289e485d/exp_cf1e4b8dda.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| exp_cs_up03_scoring_contract_20260927 | global | 1117 | `experience/global/exp_cs_up03_scoring_contract_20260927.md` | 全局仅索引，正文按题需要读取 |
| exp_cs_up03r_pair_before_fit_20260927 | global | 938 | `experience/global/exp_cs_up03r_pair_before_fit_20260927.md` | 全局仅索引，正文按题需要读取 |
| exp_e79c4ecdfe | challenge | 1423 | `experience/challenges/local_d8ff052e/exp_e79c4ecdfe.md` | 保留原文；其他题不进入当前上下文 |
| exp_ed7bcda49e | challenge | 1232 | `experience/challenges/local_d8ff052e/exp_ed7bcda49e.md` | 保留原文；其他题不进入当前上下文 |
| exp_f3169d22d5 | challenge | 3629 | `experience/challenges/local_2f7b3f2f7896/exp_f3169d22d5.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| exp_ffc1669988 | challenge | 1793 | `experience/challenges/local_d8ff052e/exp_ffc1669988.md` | 保留原文；其他题不进入当前上下文 |
| lc_causal_outputs | global | 776 | `experience/global/lc_causal_outputs.md` | 全局仅索引，正文按题需要读取 |
| lc_judge_visibility | global | 785 | `experience/global/lc_judge_visibility.md` | 全局仅索引，正文按题需要读取 |
| lc_materials_env | global | 931 | `experience/global/lc_materials_env.md` | 全局仅索引，正文按题需要读取 |
| lc_paired_evidence | global | 1129 | `experience/global/lc_paired_evidence.md` | 全局仅索引，正文按题需要读取 |
| lc_requested_method | global | 760 | `experience/global/lc_requested_method.md` | 全局仅索引，正文按题需要读取 |
| lc_resubmit_policy | global | 842 | `experience/global/lc_resubmit_policy.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| lc_rhythm | global | 992 | `experience/global/lc_rhythm.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| lc_submission_spacing | global | 891 | `experience/global/lc_submission_spacing.md` | 全局仅索引，正文按题需要读取；有历史/编号/规则摘录待设计核对 |
| lc_trace_gate | global | 977 | `experience/global/lc_trace_gate.md` | 全局仅索引，正文按题需要读取 |
| lc_visible_creation | global | 1371 | `experience/global/lc_visible_creation.md` | 全局仅索引，正文按题需要读取 |
| strategy_run_19080bf816 | challenge | 8669 | `experience/challenges/local_8dc2884edcee/strategy_run_19080bf816.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| strategy_run_45c53e60f1 | challenge | 9913 | `experience/challenges/local_289e485d/strategy_run_45c53e60f1.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| strategy_run_472994b1fd | challenge | 8687 | `experience/challenges/local_56b7e4716ad2/strategy_run_472994b1fd.md` | 保留原文；其他题不进入当前上下文 |
| strategy_run_8a21b7d249 | challenge | 11318 | `experience/challenges/local_22be5bccf043/strategy_run_8a21b7d249.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| strategy_run_c937c8e414 | challenge | 4090 | `experience/challenges/local_2f7b3f2f7896/strategy_run_c937c8e414.md` | 保留原文；其他题不进入当前上下文 |
| strategy_run_d4d0a11a67 | challenge | 10114 | `experience/challenges/local_36cd497cbd73/strategy_run_d4d0a11a67.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| strategy_run_defca520c0 | challenge | 10640 | `experience/challenges/local_f232ee5f51b7/strategy_run_defca520c0.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_04dc15406d | challenge | 3611 | `experience/challenges/local_22be5bccf043/trial_note_trial_04dc15406d.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_0509384ddb | challenge | 6112 | `experience/challenges/local_8dc2884edcee/trial_note_trial_0509384ddb.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_07fd16717a | challenge | 4939 | `experience/challenges/local_8dc2884edcee/trial_note_trial_07fd16717a.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_16de6c6899 | challenge | 7341 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_16de6c6899.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_1f39ce86e3 | challenge | 5612 | `experience/challenges/local_8dc2884edcee/trial_note_trial_1f39ce86e3.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_22b5417a36 | challenge | 5796 | `experience/challenges/local_289e485d/trial_note_trial_22b5417a36.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_2fd4728de8 | challenge | 6498 | `experience/challenges/local_56b7e4716ad2/trial_note_trial_2fd4728de8.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_4fd0ad721a | challenge | 5864 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_4fd0ad721a.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_500acecf83 | challenge | 4875 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_500acecf83.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_52829c4213 | challenge | 2881 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_52829c4213.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_556df04fa9 | challenge | 1798 | `experience/challenges/local_22be5bccf043/trial_note_trial_556df04fa9.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_5ec704fb32 | challenge | 2961 | `experience/challenges/local_289e485d/trial_note_trial_5ec704fb32.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_677dd52cf0 | challenge | 4063 | `experience/challenges/local_36cd497cbd73/trial_note_trial_677dd52cf0.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_68a3dfe1bf | challenge | 4793 | `experience/challenges/local_8dc2884edcee/trial_note_trial_68a3dfe1bf.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_6d593e0e0a | challenge | 3812 | `experience/challenges/local_22be5bccf043/trial_note_trial_6d593e0e0a.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_6eff28d9b3 | challenge | 5928 | `experience/challenges/local_8dc2884edcee/trial_note_trial_6eff28d9b3.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_6ffb24ab6f | challenge | 3330 | `experience/challenges/local_f232ee5f51b7/trial_note_trial_6ffb24ab6f.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_76144b0ae8 | challenge | 5083 | `experience/challenges/local_289e485d/trial_note_trial_76144b0ae8.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_7b9d8288af | challenge | 6027 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_7b9d8288af.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_83ce99f78a | challenge | 5399 | `experience/challenges/local_8dc2884edcee/trial_note_trial_83ce99f78a.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_9d1cf617b0 | challenge | 2434 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_9d1cf617b0.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_9e32bb7013 | challenge | 6451 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_9e32bb7013.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_9fe3f3f666 | challenge | 4983 | `experience/challenges/local_56b7e4716ad2/trial_note_trial_9fe3f3f666.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_a0113f5bca | challenge | 6201 | `experience/challenges/local_289e485d/trial_note_trial_a0113f5bca.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_a3beca33f0 | challenge | 6350 | `experience/challenges/local_8dc2884edcee/trial_note_trial_a3beca33f0.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_b1d99891c1 | challenge | 6312 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_b1d99891c1.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_b7b389fc49 | challenge | 5615 | `experience/challenges/local_8dc2884edcee/trial_note_trial_b7b389fc49.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_bd96dc7b2f | challenge | 6230 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_bd96dc7b2f.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_bf84db6691 | challenge | 2426 | `experience/challenges/local_36cd497cbd73/trial_note_trial_bf84db6691.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_c35a356537 | challenge | 4270 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_c35a356537.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_c3b56969cd | challenge | 2715 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_c3b56969cd.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_c84288a926 | challenge | 2549 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_c84288a926.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_d3a2c271d2 | challenge | 6395 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_d3a2c271d2.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_d3b3199fca | challenge | 3571 | `experience/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a/trial_note_trial_d3b3199fca.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_d47a6c6116 | challenge | 4589 | `experience/challenges/local_2f7b3f2f7896/trial_note_trial_d47a6c6116.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_dc1f282d19 | challenge | 6358 | `experience/challenges/local_8dc2884edcee/trial_note_trial_dc1f282d19.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_de05641608 | challenge | 4590 | `experience/challenges/local_22be5bccf043/trial_note_trial_de05641608.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_e08cbaba7b | challenge | 3676 | `experience/challenges/local_f232ee5f51b7/trial_note_trial_e08cbaba7b.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_e6bee2613a | challenge | 6649 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_e6bee2613a.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_ea0ccdc679 | challenge | 4777 | `experience/challenges/local_56b7e4716ad2/trial_note_trial_ea0ccdc679.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_f080a7eb9d | challenge | 6953 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f080a7eb9d.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_f2c2b57402 | challenge | 3538 | `experience/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a/trial_note_trial_f2c2b57402.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_f5c0f4f8fc | challenge | 6362 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f5c0f4f8fc.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |
| trial_note_trial_f81fa8781e | challenge | 5966 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f81fa8781e.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_fa74f28639 | challenge | 2733 | `experience/challenges/flowforge-paired-block-boundary-projection-v10-fe06025a/trial_note_trial_fa74f28639.md` | 保留原文；其他题不进入当前上下文 |
| trial_note_trial_fec5d66df7 | challenge | 2084 | `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_fec5d66df7.md` | 保留原文；其他题不进入当前上下文；有历史/编号/规则摘录待设计核对 |

### 有冲突关键词的原文位置

- `env_27f12b667d8354cbe0a599d3` `experience/global/env_27f12b667d8354cbe0a599d3.md` body_md:4 原文摘录：“3a3db97", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest", "observed_command": "mkdir -p /app/outputs /app/evidence && OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/c”。待设计助手核对；本卡不改。
- `env_4ba6c98d6c4a8f371c4d32eb` `experience/global/env_4ba6c98d6c4a8f371c4d32eb.md` body_md:4 原文摘录：“ 0, "id": 207489, "image": "registry.dp.tech/dptech/dp/native/prod-10385/114/lobster-loop-base@sha256:92d177e819641ad828771ce58cc2a54251e51d36c90e6fcf916fad49c33c5af0", "is_starred": false, "max_warmup_replicas": 1, "memor”。待设计助手核对；本卡不改。
- `env_5f90993ab43387dac00828d0` `experience/global/env_5f90993ab43387dac00828d0.md` body_md:4 原文摘录：“d5c4df8", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest", "observed_command": "/opt/csenv/bin/python -c \"import sys,numpy,scipy,sklearn; from sklearn.linear_model i”。待设计助手核对；本卡不改。
- `env_805bed2952e1fba5f5c2618b` `experience/global/env_805bed2952e1fba5f5c2618b.md` body_md:4 原文摘录：“7d3f8d9", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest", "observed_command": "cd /app\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/csenv/bin/python - <<'PY'\nimpo”。待设计助手核对；本卡不改。
- `env_9cf7026357c72efb8d64a97a` `experience/global/env_9cf7026357c72efb8d64a97a.md` body_md:4 原文摘录：“5b175c1", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest", "observed_command": "mkdir -p /bohr-workspace/trial && tar -xzf /bohr-workspace/input_v1.tar.gz -C /bohr-wo”。待设计助手核对；本卡不改。
- `env_b0c2134fb033ab0ed8763d53` `experience/global/env_b0c2134fb033ab0ed8763d53.md` body_md:4 原文摘录：“1339261", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest", "observed_command": "set -x; cd /root/cnv-data && sha256sum *.cnn evaluation_cases.tsv task_data_manifest.j”。待设计助手核对；本卡不改。
- `env_b6ae19119697105d26e82a7f` `experience/global/env_b6ae19119697105d26e82a7f.md` body_md:4 原文摘录：“3ca0e85", "image_address": "registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-torch-cuda-pypi-1791299290:latest", "observed_command": "mkdir -p /bohr-workspace/trial9 && nvidia-smi && /opt/csenv/bin/python -c \"i”。待设计助手核对；本卡不改。
- `exp_171f93edd6` `experience/challenges/local_2f7b3f2f7896/exp_171f93edd6.md` body_md:4 原文摘录：“回执；不为等待不可得的内部原因停止所有工作，也不重复相同修复、相同unknown操作或把原包盲目重投。状态不明Job的后续操作仍按D-31处理，不能推广为绝不重发。”。待设计助手核对；本卡不改。
- `exp_171f93edd6` `experience/challenges/local_2f7b3f2f7896/exp_171f93edd6.md` body_md:10 原文摘录：“，不能把节省时间、诊断成功或更高分当成已实现结果。没有证据支持仅靠这一修复可突破0分，能够获得更高分的具体改动仍unknown。对D-24–D-61的逐项核对见summary；特别保留D-28/policy-31/D-33的继续推进与有条件新操作路径，遵循D-38现有ARM格式，不新增D-42收割审批，不把D-49普通环境复现误当题目镜像复跑。conflicts为空是待验证的文本分析结论。”。待设计助手核对；本卡不改。
- `exp_74ed157080` `experience/challenges/local_289e485d/exp_74ed157080.md` body_md:5 原文摘录：“为完整交付证据；若既无文件证据也无操作终态，保持unknown，选择其他未试过的已授权路径。对超过10分钟仍无法对账的Job，应按D-31允许新操作ID继续推进，并保留原费用估算及后台对账；这不等于重复原unknown请求，也不是本次上传已经验证了Job恢复机制。”。待设计助手核对；本卡不改。
- `exp_74ed157080` `experience/challenges/local_289e485d/exp_74ed157080.md` body_md:14 原文摘录：“逐条设计核对（模型分析，待验证）：D-24给恢复方法而非系统代办；D-25保留历史包及其来源；D-26不修改适配器或运行内核；D-27哈希匹配不等于正式评分；D-28unknown留证并换已授权路径；D-29不扩展提交权限；D-30环境保存以后续D-52为准；D-31明确保留10分钟未决Job的新操作ID路径，不重复同一unknown请求；”。待设计助手核对；本卡不改。
- `exp_b04be443be` `experience/challenges/local_36cd497cbd73/exp_b04be443be.md` body_md:11 原文摘录：“未知状态保留并寻找授权内替代路径，不要求反复核查到确定才继续；policy-29：不区分评测专用能力；policy-30：按后来的D-52，不保存运行中环境新版本；policy-31：不重复同一unknown操作，Job在10分钟仍无法对账时可按规则换新ID，该阈值不泛化到其他工具；policy-32：不冒认固定评分器Job得分；policy-33：不以unknown要求暂停等用户；policy-34：使用原始可见验证器而不修改；po”。待设计助手核对；本卡不改。
- `exp_cf1e4b8dda` `experience/challenges/local_289e485d/exp_cf1e4b8dda.md` body_md:14 原文摘录：“逐条设计核对（模型分析，待验证）：D-24由执行器选择等价实验实现；D-25区分历史与新增数组、重复不算独立；D-26不改冻结内核及评分器；D-27不把数值复核当正式评分；D-28不明符号留证并继续可区分实验；D-29不扩大提交授权；D-30环境保存以D-52为准；D-31不限制符合条件的新操作ID；D-32没有确认的Job分数；D-33不”。待设计助手核对；本卡不改。
- `exp_f3169d22d5` `experience/challenges/local_2f7b3f2f7896/exp_f3169d22d5.md` body_md:9 原文摘录：“n未证实实际存在上述数值错误，指导后四件数值产物未变，因此不能宣称这项做法会把已观察的0分提高。可实现的分数增益unknown。对D-24–D-61的逐项核对见summary；尤其不把内部核验提升为D-27/D-32正式分，不违反D-28/D-33要求的继续推进，不改写D-31的换新操作规则。conflicts为空仅表示本次文本分析未发现冲突，不代表符合性已经验证。”。待设计助手核对；本卡不改。
- `lc_resubmit_policy` `experience/global/lc_resubmit_policy.md` body_md:9 原文摘录：“4. 与上一次提交间隔 30 分钟以上再交。”。待设计助手核对；本卡不改。
- `lc_rhythm` `experience/global/lc_rhythm.md` body_md:9 原文摘录：“- **收尾**：最后 3 小时只做低风险的改进，给出分确认和收割留足时间。”。待设计助手核对；本卡不改。
- `lc_submission_spacing` `experience/global/lc_submission_spacing.md` body_md:7 原文摘录：“| 间隔 | ≤2 分钟 | 2–5 分钟 | 5–10 分钟 | 10–30 分钟 | 30 分钟以上 |”。待设计助手核对；本卡不改。
- `lc_submission_spacing` `experience/global/lc_submission_spacing.md` body_md:11 原文摘录：“前 60 分钟内已有 3 次提交时，触发率为 27%；第 4 次以后的提交风险明显上升。账号在 30 分钟内跨题提交 5 次以上，也会被判突发。”。待设计助手核对；本卡不改。
- `lc_submission_spacing` `experience/global/lc_submission_spacing.md` body_md:14 原文摘录：“- 同一账号同一题，两次提交之间至少间隔 30 分钟；每题每个账号尽量不超过 3–4 次。”。待设计助手核对；本卡不改。
- `strategy_run_19080bf816` `experience/challenges/local_8dc2884edcee/strategy_run_19080bf816.md` body_md:15 原文摘录：“Job 评分；policy-33 允许继续已授权未试路线；policy-34 不隐藏或修改评分器；policy-35 重分析遵守 Bohrium-first，并结合 policy-49、policy-50；policy-36 榜首缺失保留 unknown；policy-37 保留 PI 指导归属；policy-38 不改变 ARM 格式；policy-39 模型安排以后续 policy-51、policy-59、policy-60 为准；policy-”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `strategy_run_45c53e60f1` `experience/challenges/local_289e485d/strategy_run_45c53e60f1.md` body_md:19 原文摘录：“逐条设计核对（模型分析，待验证）：D-24保留执行器方法选择；D-25历史包保留、同分支不算独立；D-26不修改运行内核或评分器；D-27内检不登记正式分；D-28保留失败并换研究路线；D-29不改变提交授权；D-30按D-52处理环境保存；D-31不提出unknown绝不新发规则；D-32无已确认Job评分；D-33局部止损不停止其他已授”。待设计助手核对；本卡不改。
- `strategy_run_8a21b7d249` `experience/challenges/local_22be5bccf043/strategy_run_8a21b7d249.md` body_md:16 原文摘录：“充正式分；policy-28：分区不确定时继续其他已授权验证；policy-29：不另设评测能力限制；policy-30：按后来的D-52，不提议保存新环境版本；policy-31：不将stop_unknown变成永久禁止新操作，超10分钟仍无法对账时按授权与现行规则处理，且不重复原unknown操作；policy-32：没有评分回执则分数unknown；policy-33：不因缺少一种分区工具而暂停全部工作；policy-34：不编”。待设计助手核对；本卡不改。
- `strategy_run_d4d0a11a67` `experience/challenges/local_36cd497cbd73/strategy_run_d4d0a11a67.md` body_md:16 原文摘录：“-28：记录不明事实并转向有证据支持的可行工作；policy-29：不另设评测能力限制，保留经验来源；policy-30：按后来的D-52，不建议运行中另存环境版本；policy-31：不禁止授权内的新操作，Job无法对账的10分钟规则保留，不重复同一unknown操作；policy-32：未获固定评分器Job回执，不登记正式本地分；policy-33：不以评分unknown要求等待用户；policy-34：保留公开验证器可见性；po”。待设计助手核对；本卡不改。
- `strategy_run_defca520c0` `experience/challenges/local_f232ee5f51b7/strategy_run_defca520c0.md` body_md:21 原文摘录：“逐项设计核对（模型分析，待验证）：D-24保留执行器自主选择；D-25注明验证集复用不独立；D-26不提议修改运行后端；D-27代理MAE不登记正式分；D-28不以缺评分证据阻止可行科学推进；D-29不设评测专用路径；D-30按后续D-52处理环境保存；D-31不提出unknown永久禁新操作ID，10分钟仍无法对账时按该决定处理，且不重复”。待设计助手核对；本卡不改。
- `strategy_run_defca520c0` `experience/challenges/local_f232ee5f51b7/strategy_run_defca520c0.md` body_md:55 原文摘录：“首个 Trial 以 30 分钟为首个证据检查点、45 分钟为交接上限，争取在启动后 30–60 分钟进入实验提交审阅；不承诺尚未核实的评分时延。验收包括实际数据清单与分组审计、starter/简单基线及至少一个残差候选的可比预测、双向和往返逐项指标、独立指标复核、真实远程运行回执，以及带哈希的 solution.py、runne”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_04dc15406d` `experience/challenges/local_22be5bccf043/trial_note_trial_04dc15406d.md` body_md:4 原文摘录：“经控制器授权、预算和去重检查触发；未知状态先对账。剩余时间优先首个实验及评分反馈，不突破全 Run 两次实验、同账号同题至少间隔 30 分钟的限制。主邮箱仅由监控按既有授权与开关处理，不绕过 auto_harvest=false。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_16de6c6899` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_16de6c6899.md` body_md:7 原文摘录：“约 41.3 MiB，但全空间稠密 Gaussian 算符不可作为实现路线。首轮最多使用 1 个 CPU Bohrium Job、30 分钟墙钟，不使用 GPU sandbox，遵守总计 5 Job、180 分钟授权。先做小规模已知输入的符号与一致性检查，再对已独立核验的 Q1 测量前向、梯度时间及峰值内存，据此限定少量初始化与迭代；Q2–Q4 本轮不做大规模优化。若真实端点尚不可用，仍完成不依赖端点的解析恒等式和小规模回放检查，并准确”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_16de6c6899` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_16de6c6899.md` body_md:19 原文摘录：“441a611163fb7aacedba7ff4cfe118200f9b25a4c1c7；唯一名称cs-run_a654e422fd-6d6a76f8ca15370b；项目88474/c4_m8_cpu/10GB/30分钟/无重调度。最终对账仍无已确认Job ID，账本unknown且预留1、active_or_unknown1（见job_handover_status.json）。实际运行起止/耗时/费用unknown，30分钟是”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_2fd4728de8` `experience/challenges/local_56b7e4716ad2/trial_note_trial_2fd4728de8.md` body_md:7 原文摘录：“的规定训练；不挑选最好种子或提前迭代结果。修复公共求解器时补做float64前向、梯度、Adam更新对照及lambda=1回归。先30分钟交接机制证据，最迟60分钟交接候选结果或明确反证，再据剩余时间决定扩展。计算、批量分析均走已授权Bohrium；同时对账AC终态与unknown沙箱请求，不盲目重放创建操作。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_4fd0ad721a` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_4fd0ad721a.md` body_md:5 原文摘录：“采用接口实际支持的精确查询或完整分页。确认身份后只取回已有状态、日志和产物，保留原 Trial 归属。查询范围不足时记录准确缺口；30分钟仅为请求上限，实际终止须另有证据。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_4fd0ad721a` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_4fd0ad721a.md` body_md:19 原文摘录：“7aacedba7ff4cfe118200f9b25a4c1c7、unique job_name cs-run_a654e422fd-6d6a76f8ca15370b。账本platform_job_id=null/statusunknown/reserved1/active_or_unknown1；当前对账回执evidence/job_reconcile.json，历史自有事件235和309各只覆盖三页、partial/matche”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_500acecf83` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_500acecf83.md` body_md:4 原文摘录：“Lean 声明不证明本题依赖就绪。资源试算：Trial 总墙钟最多 45 分钟，最多一个 c8_m32_cpu Job、运行最多 30 分钟；确需环境准备时，最多一个 2c4g CPU sandbox、生命周期最多 15 分钟。按已读报价事件 run_8eeef876cb#380/#379，分别约 0.32 元和 0.04 元，预留估算上限 0.50 元；报价估算不是账单，未定价费用保持 unknown。为最终评分和修正至少保留 30 ”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_52829c4213` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_52829c4213.md` body_md:4 原文摘录：“ 目标：先复核 Q1 诊断产物，再固定一条已核查的 SWAP 序列与同一前向模型；在至多一个新增 CPU Bohrium Job、30 分钟和 2 GiB 内，以预先记录的随机种子及等额评估预算，对照旧最佳点继续优化和从不同有效 Gaussian 块初值或受控酉扰动出发的多起点优化，检验旧结果是否为可逃离的优化停滞。保持本地评估，不提交平台。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_677dd52cf0` `experience/challenges/local_36cd497cbd73/trial_note_trial_677dd52cf0.md` body_md:4 原文摘录：“-sci-py-v1环境。首轮限45分钟作为复盘边界，10分钟内报告资源物化、环境冒烟和文献坐标获取状态；先用4c8g CPU沙箱30分钟作资源试算，必要时有界续期。CEG路线20分钟仍无可验证几何时，转KEG解析候选保底并保留CEG诊断。单个环境或下载渠道失败先换已授权路线；资源读取缺项不阻止独立生成与验证。保留实际命令、输出、耗时、执行来源、候选和最终产物哈希，不修改评分器。达到完整验收即请求既有提交审阅，不直接提交正式Attem”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_6d593e0e0a` `experience/challenges/local_22be5bccf043/trial_note_trial_6d593e0e0a.md` body_md:4 原文摘录：“idance.kind=submit 经现有检查触发；未知回执先对账。全部额度与时间按整个 Run 累计：实验最多两次、至少间隔 30 分钟，主邮箱最多一次且仅由监控在确认实验评分后按规则触发。当前剩余约 26 分钟，优先完成首个实验的审阅和反馈，不为第二次提交突破期限或间隔。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_6d593e0e0a` `experience/challenges/local_22be5bccf043/trial_note_trial_6d593e0e0a.md` body_md:25 原文摘录：“若审阅给出 guidance.kind=submit，由控制器按全 Run 实验额度/30 分钟间隔/去重门禁决定唯一首个实验；若 unknown 先对账。上传、Attempt、worker、科学分、轨迹分、正式分与旧题资格逐项记录；现均非已知。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_6ffb24ab6f` `experience/challenges/local_f232ee5f51b7/trial_note_trial_6ffb24ab6f.md` body_md:4 原文摘录：“析走已授权Bohrium CPU沙箱或Job，复用cs12-sci-py-v1并做本Run冒烟；通道失败先对账再切换，不保存环境。30分钟交接证据，45分钟停止扩搜；按控制器剩余时间保留最后90分钟用于收割。具备实质改进或已证实的交付修复后请求requested/shadow提交审阅，实验提交和主邮箱收割均走现有授权、预算与去重流程。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_7b9d8288af` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_7b9d8288af.md` body_md:7 原文摘录：“是账单，未知费用不计零。科学计算在 Bohrium Job 中完成；不使用 GPU、不平台提交、不写经验库，继续保留最终评分至少 30 分钟余量。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_9d1cf617b0` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_9d1cf617b0.md` body_md:4 原文摘录：“l 目标：先复核上一 Trial 取回的 Q1 输入、日志与独立重放数值；若一致，在至多一个新增 CPU Bohrium Job、30 分钟和 2 GiB 内，固定前向模型与总优化预算，对照原 SWAP 序列继续优化和若干替代相邻 SWAP 序列，检验序列选择是否限制端点保真度。不提交平台。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_9d1cf617b0` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_9d1cf617b0.md` body_md:11 原文摘录：“equence_compare_v1）已 Finished、exitCode=0、结果取回；c2_m2_cpu 2 GiB，平台 30 分钟上限，脚本 467.742425 秒、峰值 RSS 96084 KiB。搜索前独立重放上一 Trial：初始 F=1.9068863713718166e-05，最佳 F=0.734998617147374，输入/日志/结果哈希吻合。原序列 [0,1,2] 与三个替代序列 [4,5,6]、[9,10,”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_9e32bb7013` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_9e32bb7013.md` body_md:4 原文摘录：“andbox约0.021元、15分钟Job约0.160元，估算预留上限0.50元，非账单。当前约剩65分钟，最终评分和修正至少保留30分钟。wheel未准备完整前不创建计算Job；准备失败即交接具体失败阶段。来源准入单独处理：保留公开父归档及真实清单，若现有受控接口支持完整资源关联则使用它，避免假设缺失的Q1子集接口可用；缺入口保持unknown，不改内核、评分器或来源标记。原未知操作继续独立对账并保留预留，已失败Job及历史输入不改”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_9fe3f3f666` `experience/challenges/local_56b7e4716ad2/trial_note_trial_9fe3f3f666.md` body_md:4 原文摘录：“务在交接时保留可恢复checkpoint和任务句柄。固定输入下核验朴素与批量实现的前向值、梯度及一次Adam更新后再采用加速版本。30分钟汇报首次进展，最迟60分钟交接真实结果、参考误差、资源估算和剩余配置；约90分钟收割窗口前停止引入新的大范围方法变更。当前不执行任何比赛提交，不以评分器缺失阻塞计算。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_b1d99891c1` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_b1d99891c1.md` body_md:7 原文摘录：“Bohrium Job 中完成，不修改运行时内核、供应商适配器或评分器，不使用 GPU、不平台提交、不写经验库。保留最终评分至少 30 分钟余量，取得足够判断的结果后即可交接。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_bd96dc7b2f` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_bd96dc7b2f.md` body_md:4 原文摘录：“缺失则如实记录，不修改内核、评分器或来源标记来解除 PROXY_EVIDENCE。零平台提交、零经验写入，最终评分与修正至少保留 30 分钟。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_bf84db6691` `experience/challenges/local_36cd497cbd73/trial_note_trial_bf84db6691.md` body_md:4 原文摘录：“最小修复并验证；需要重放时在授权Bohrium CPU环境对实际封存包执行。暂不开展H2密度搜索。10分钟报告诊断入口与关键发现，30分钟作为复盘边界；通道失败先换另一已授权路线。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_c35a356537` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_c35a356537.md` body_md:15 原文摘录：“11163fb7aacedba7ff4cfe118200f9b25a4c1c7、job_name=cs-run_a654e422fd-6d6a76f8ca15370b、input及1份预留完整保留；上次受控账本观测reserved_jobs=1、active_or_unknown=1。本次没有新的Job查询、reconcile、submit、sandbox或本地科学计算，未把旧观测伪装为新远端确认。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_c84288a926` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_c84288a926.md` body_md:4 原文摘录：“钟。本轮仅检验恢复假设R：已有回执、原始响应及受控只读查询可能补齐任务身份或可回收结果。Trial总墙钟最多8分钟，并在Run剩余30分钟前交接；不创建新Job或沙箱，不重发任何未知提交，不修改冻结输入或运行时内核。优先检查已有未解析响应和任务关联线索，分别对账两个unknown操作；没有新线索即提前交接，不重复空轮询。发现具名Job后取回真实日志及已有产物，核对代码、输入和执行阶段；已有计算遵守原任务生命周期，不延长或重启。若取回H”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_d3a2c271d2` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_d3a2c271d2.md` body_md:4 原文摘录：“量资源传输。资源边界：本 Trial 墙钟最多 45 分钟，新 Job 优先采用此前可请求的 c8_m16_cpu、生命周期最多 30 分钟；按已读 0.64 元/小时报价约预留 0.32 元，预留估算上限 0.50 元，原任务费用未知继续保留。最终评分和修正至少保留 30 分钟。Run 仍有约 142 分钟和 19 个 Job 额度，没有证据要求此时结束研究。零平台提交、零经验写入。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_d3a2c271d2` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_d3a2c271d2.md` body_md:23 原文摘录：“资源：本轮仅一个新 c8_m16_cpu Job，最多30分钟、输入58630 bytes，不新建sandbox、不续建任务。API报告native_amount=0.02/currency=null/spend_seconds=131，非确认账单；原生describe先前cost=1/spendTime=78的单位语义不明，保留冲突。旧 operation ”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_d47a6c6116` `experience/challenges/local_2f7b3f2f7896/trial_note_trial_d47a6c6116.md` body_md:4 原文摘录：“k_package实施；契约、验证器、CPU环境并行准备，采用cs12-sci-py-v1实测冒烟。先进行2 CPU/8 GiB、30分钟资源试算并报告实际结果，争取60分钟内准备好首个实验提交审阅包。保留全部命令、输出、耗时、来源和哈希；遇环境失败切换已授权路线，不改变固定科学方法。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_de05641608` `experience/challenges/local_22be5bccf043/trial_note_trial_de05641608.md` body_md:7 原文摘录：“算通道受阻，先对账再换已授权 Job 或沙箱路线。提交额度按整个 Run 累计，不因新 Trial 重置：实验最多两次且至少间隔 30 分钟；主邮箱仅由监控在确认实验评分后按规则触发。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_e08cbaba7b` `experience/challenges/local_f232ee5f51b7/trial_note_trial_e08cbaba7b.md` body_md:4 原文摘录：“固定 validation 由独立评估进程持有；所有候选共用分组划分，辅助实验池暂不引入监督训练。首选一个 2c4g 沙箱，先以 30 分钟资源试算：按 2026-10-03 观察报价 0.16 CNY/小时约 0.08 CNY，属于估算而非账单；若换 c4_m4_cpu Job，按 2026-10-01 报价同样 30 分钟约 0.16 CNY。实际配额、可用性及费用另记，不使用 GPU，不保存环境。30 分钟交接阶段证据，45 分钟”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_e6bee2613a` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_e6bee2613a.md` body_md:7 原文摘录：“中完成。按包内报价新增资源估算上限约 0.24 元，预留 1 元，原预约单独保留；估算不是账单，未知费用不计零。保持最终评分至少 30 分钟余量，不使用 GPU、不平台提交、不写经验库。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_e6bee2613a` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_e6bee2613a.md` body_md:20 原文摘录：“m16_cpu/max_run_time30/10GB/单节点无重调度，原input没有改动，20项冻结文件hash全部重核匹配。30分钟配置不能证明生命周期或已停，实际费用unknown。最后运行事实16:45:33Z：剩余9384秒、jobs19、sandboxes600分钟、原预算预约0.32/1个预约、余额49.68元（非账单）；本Trial新Job0/sandbox0，仍留出超过30分钟最终评分余量。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_ea0ccdc679` `experience/challenges/local_56b7e4716ad2/trial_note_trial_ea0ccdc679.md` body_md:8 原文摘录：“30分钟内交接首批机制证据，最迟60分钟交接候选或明确反证，再据实际剩余时间决定扩展。训练、批量分析和科学作图走已授权Bohrium；秒级本地小算须保留命令、输出、耗时、产物哈希及local来源供PI审阅。继续有界对账AC账本终态和无ID沙箱请求，不能把执行器声明或未计费用当作已确认终态或零费用。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_f080a7eb9d` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f080a7eb9d.md` body_md:8 原文摘录：“源上限：本 Trial 总墙钟不超过 40 分钟，至多一个 c8_m32_cpu Bohrium CPU Job、生命周期不超过 30 分钟；确需准备环境时至多一个 2c4g CPU sandbox、不超过 10 分钟。按已读报价估算 0.64×30/60+0.16×10/60≈0.347 元，预留 1 元并通过现有预算检查；这是估算，不是账单，未知费用不计零。所有科学计算在 Bohrium Job 完成，不使用 GPU、不作平台提交、”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_f080a7eb9d` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f080a7eb9d.md` body_md:19 原文摘录：“ist为空；受控默认上限内存16GB/磁盘10GB，保守缩小为唯一c8_m16_cpu/10GB/单节点/max_run_time30分钟、不重调度。operation_id=trial_f080a7eb9d-q1-cpu-v2创建超时unknown/platform_job_id=null，多次受控reconcile及bohr job list收到只读远程列表仍无唯一匹配。缺席不证明未创建，未重提。创建预留2026-10-03T16”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_f5c0f4f8fc` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_f5c0f4f8fc.md` body_md:7 原文摘录：“ 0.373 元，预留 1 元并保留已有预约；这不是账单，未知费用不计零。所有科学验证和优化在 Job 中完成，保持最终评分至少 30 分钟余量；不使用 GPU、不平台提交、不写经验库。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。
- `trial_note_trial_fec5d66df7` `experience/challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/trial_note_trial_fec5d66df7.md` body_md:4 原文摘录：“1 有 C(12,6)=924 个复振幅，单个稠密扇区算子约 13.7 MB；仅使用至多 1 个 CPU Bohrium Job、30 分钟和 2 GiB 内存，公开数据登记包为 24,137,739 字节。产出资源核对记录、可复现的 Q1 前向计算、合法电路 JSON、初始与最佳保真度及实际耗时；不提交平台。”。历史题内事实，不把30分钟资源期限误判为提交间隔；保持题内隔离。

## 新目录、缺失与重复

- 新Run创建前workspace/runs为空；本Run新建brain_view为空（后续fact文件放在facts，不放PI cwd）。探索cwd只属于本Run，开始时有系统生成bin/bohr和facts索引文件，属于必要工具/事实，未放旧Trial产物。干净线程cwd为新Trial目录；其开局首个工具实际pwd和列目录没有旧Trial文件。
- role_prompts读取失败/空立即拒绝；原生新建/续用/干净路径均同一spec。比赛端仅允许已确认developerInstructions协议的Codex。
- PI角色例子自带LiSi参考参数，属于用户授权角色原文；与本题无关的例子可能占注意力，只列给设计助手。
- 每轮通用操作文字与常驻角色重复，按卡要求不删；clean-run必需信息不依赖PI goal/success_check。
- 原有技能文字包含D-31等编号，中文相邻编号可能未被旧发布扫描器词边界识别；不把发布扫描通过等同于所有正文内容已由设计助手更新。
- 本轮无只读审查者真实模型输入，不能满足该角色的实际原生验证；保留模板来源与输出契约作为替代，避免超出只授权PI/执行者的模型范围。

两个真实Trial已完成；下述必需项表与全帧清单是实际输入核对。

## 冒烟新增 active 修订的全文读取与停用

停用前逐字读取全部126条 active 正文，427640 UTF-8字节；在前述122条之外新增以下4条。3条同题策略/过程仅更改状态为retired，正文未改，历史修订保留；环境事实仍保留。第一次PUT返回的是写入回执而非详情，读回代码发生KeyError；没有盲重发，随后GET确认已停用第一条，再顺序停用其余两条。

| ID | scope | 字节数 | 来源 | 判定 / 建议 |
|---|---|---:|---|---|
| strategy_run_f9a4404816 | challenge | 3565 | `experience/challenges/local_4a948751/strategy_run_f9a4404816.md` | 本次题内冒烟数据，已停用 |
| env_d9c46d4be59bb60bd34b7baa | global | 2239 | `experience/global/env_d9c46d4be59bb60bd34b7baa.md` | 真实环境事实，保留 |
| trial_note_trial_8a3d91e3ca | challenge | 3729 | `experience/challenges/local_4a948751/trial_note_trial_8a3d91e3ca.md` | 本次题内冒烟数据，已停用 |
| trial_note_trial_6778aa2515 | challenge | 2501 | `experience/challenges/local_4a948751/trial_note_trial_6778aa2515.md` | 本次题内冒烟数据，已停用 |

## 逐角色必需输入核对

下表用实际开发者/用户消息或真实工具返回定位；助手自述不用于证明首条消息送达。合并项的更细来源见全帧表，缺少真实角色调用仍明确记录。

| 角色 | 必需内容 | 实际位置 | 对应帧字节数 | 判定 / 建议 |
|---|---|---|---:|---|
| PI | 角色/信任顺序 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 能力索引 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 技能索引 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 题面/资源 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 用户提示 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:9` | 35536 | 已送达，保留 |
| PI | 审批/方法大改 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 提交/四段交接 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| PI | 科学分提前回执 | `rollout-2026-10-09T15-58-33-01a11fab-c781-7703-8403-e410413e6736.jsonl:3` | 30574 | 已送达，保留 |
| 探索执行者 | 角色 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 探索执行者 | 题面/契约 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 探索执行者 | PI简报/批准方法 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:9` | 33154 | 已送达，保留 |
| 探索执行者 | 能力/环境/经验/技能索引 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 探索执行者 | 本题沙箱 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 探索执行者 | 交付路径/包名 | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 探索执行者 | 完成/检查点/ack | `rollout-2026-10-09T15-58-39-01a11fab-dde5-7202-ae1d-9a9c7324f310.jsonl:3` | 20252 | 已送达，保留 |
| 干净复跑执行者 | 角色 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` | 20276 | 已送达，保留 |
| 干净复跑执行者 | 题面 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` | 20276 | 已送达，保留 |
| 干净复跑执行者 | 四段 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` | 20276 | 已送达，保留 |
| 干净复跑执行者 | 能力/环境/技能索引 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` | 20276 | 已送达，保留 |
| 干净复跑执行者 | 交付目录/包名 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:3` | 20276 | 已送达，保留 |
| 干净复跑执行者 | 固定完成判据 | `rollout-2026-10-09T17-01-41-01a11fe5-9115-7963-8200-888a697597f4.jsonl:9` | 53850 | 已送达，保留 |
| 只读审查者 | 审查任务与输出JSON契约 | `package_reviews.py:101` / SCHEMA | 1073 / 1039 | 仅静态：基本任务562字节、评分器审计511字节，输出契约1039字节；本轮未调用 |

## 实际内容污染与字面搜索的区分

- 三个原生会话中开发目录绝对路径和全局AGENTS内容/路径均0；原生技能索引限于比赛启用的23项。表内比赛外名称是全文字面命中，不能一概解释为技能加载。`checkpoint`是普通检查点用语，`resume`来自供应商基础指令。
- 探索执行者实际读取`contracts/arm_protocol.json`，其旧安装副作用说明列出checkpoint、resume、reflect、distill、orchestrate、sync-and-plan、wrap-up、brainstorm。实际输入位置为探索原生第54行工具返回；这段与题目契约占位流程无关，判为污染/过时资料，建议设计助手裁剪合同正文。并非从全局原生技能扫描加载，正文在本卡保留。
- 执行者通过工具读到trace-writing的轨迹门优先与无条件交叉验证规则，属于实际过时指令；新角色的science-first与题目要求优先常驻，但重复旧规则仍占上下文。clean线程读取clean-rerun/sandbox/trace-writing，逐项冲突交设计助手。
- 干净线程首个pwd/rg返回正确新Trial路径且未列出文件；供应商随后生成空的只读.agents/.aws/.codex/.git防护目录。第25行ls只列本Run顶层bin/brain_view/facts/research_brief/trials名，不读取探索源码或科学产物。读取权限不属于本审计结论。
- 供应商工具函数声明与实时机器目录会占较多字节，实际工具返回已逐帧计数；运行时能力索引不能用一页模板字节数代替真实读取量。

附补充原文冲突：

- `skills/cyberscientist-trace-writing/SKILL.md:22` 原文：“6. **独立验证**：至少一次单独运行的交叉检查，打印"一致/不一致"和差值。”。无条件交叉验证或偏Job的旧规则，建议与常驻角色和sandbox_first统一，正文未改。

- `skills/cyberscientist-submission-gate/SKILL.md:16` 原文：“5. 有一次独立验证的输出。”。无条件交叉验证或偏Job的旧规则，建议与常驻角色和sandbox_first统一，正文未改。

- `skills/cyberscientist-clean-rerun/SKILL.md:19` 原文：“3. 依次运行，打印关键中间值和最终数值；做一次独立验证，打印结论。”。无条件交叉验证或偏Job的旧规则，建议与常驻角色和sandbox_first统一，正文未改。

- `skills/cyberscientist-sandbox/SKILL.md:10` 原文：“用 `research_sandbox` 或本 Run 的 `bohr sandbox` 代理搭环境和调依赖；确认可行后优先用受控 Job 做批量计算，也可在授权内选择适合当前证据的沙箱实验。沙箱和 Job 均消耗各自的本轮授权；创建前查看剩余分钟、当前沙箱数量和预期费用。没有沙箱授权时报告缺项。”。无条件交叉验证或偏Job的旧规则，建议与常驻角色和sandbox_first统一，正文未改。
