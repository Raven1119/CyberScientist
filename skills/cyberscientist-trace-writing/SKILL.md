---
name: cyberscientist-trace-writing
description: How to leave judge-visible evidence while solving, since the executor's native session is submitted as the trace — visible code creation, causal outputs, paired calls, printed key numbers.
metadata:
  audience: both
---

# 留证据的写法

你的原生会话会原样作为提交轨迹。轨迹分 ≥70 时判 accept，展示分等于科学分；低于 70 按比例打折；被 block 为 0。目标是稳过 70：证据在求解过程中自然留下，不追求满分，也不为轨迹另做表演。

下面括号里的 N 编号是平台回执中的扣分码。

## 求解时
1. **可见地写代码**：题目特定的脚本、推导和实现，用写文件命令或编辑工具在会话中写出（内容可见），再运行。不运行会话之外已有的完整脚本，不拿旧 Trial 或其他 Run 的成品交差。（N17：产物先于轨迹存在；N16：重放已有解答。）
2. **产物有来路**：每个交付文件都由一条可见命令生成，路径与包内一致，写完立刻打印关键内容。（N11：产物没有因果支撑，最常见的扣分。）
3. **用题目要求的方法**得出最终结果。（N14）
4. **调用都有结果**：失败也留下输出，并在下一步说明怎么处理。（N08、N09）
5. **打印关键数字**：中间值、收敛过程、误差、最终值。
6. **按 PI 的验证要求做检查**，打印结论和差值。

## 写给评审看
- 评审对每个事件只看开头一段，看不到图片。每段输出先打印结论和关键数字（如 `RESULT x=… err=… PASS`），长日志写进文件，只打印摘要；图片的结论用文字和数字写出来。
- 一个事件只做一件事；不重复粘贴同样的内容。（N12）
- 时间、耗时都是真实记录，不改写。（N15）

## 不要做
- 不自己编写轨迹文件、叙述文件或 ARM 清单；提交轨迹就是本会话。
- 不删改、不伪造任何记录。
