# 经验目录与加载组合

全部种子为设计先验，默认全局 candidate。题内绑定不提升证据等级。

| ID | 策略 |
|---|---|
| `csx1_decide` | 用能够区分解释的实验推进研究 |
| `csx1_handoff` | 大脑与执行器按决策需要交接证据 |
| `csx1_learn` | 从实际采用与结果更新经验 |
| `csx1_numeric` | 数值复现先定位误差结构再提高计算精度 |
| `csx1_inverse` | 反问题同时检查数据拟合与重建可信度 |
| `csx1_atom` | 原子模拟先通过构型与约定检查 |
| `csx1_ml` | 模型优化保持可比评估与数据边界 |
| `csx1_resource` | 资源阻塞按可验证状态分类 |
| `csx1_delivery` | 交付物、提交回执与科研结论分别验收 |
| `csx1_noise` | 指标改善先排除随机性与口径变化 |
| `csx1_reopen` | 负经验保留失败条件与重新尝试条件 |
| `csx1_literature` | 将文献方法转成可检验的题内候选 |

## 组合

| profile | 包含 ID |
|---|---|
| `core` | `csx1_decide`, `csx1_handoff`, `csx1_learn` |
| `numerical_reproduction` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_numeric`, `csx1_noise` |
| `inverse_problem` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_inverse`, `csx1_noise` |
| `atomistic_simulation` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_atom`, `csx1_delivery` |
| `ml_finetuning` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_ml`, `csx1_resource` |
| `resource_blocked` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_resource`, `csx1_reopen` |
| `literature_start` | `csx1_decide`, `csx1_handoff`, `csx1_learn`, `csx1_literature`, `csx1_delivery` |

只把与当前题匹配的组合建立为题内副本；其余保留候选目录。不得用“内容完整”作为每轮注入全部条目的理由。
auto 仅识别 Aiyagari、FWI/muon、LAMMPS/位错/DPA4、LoRA/fine-tuning 等明确名称；多类同时命中或无命中时回退 core。
