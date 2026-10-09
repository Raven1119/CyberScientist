---
name: cyberscientist-submission-gate
description: PI checklist before issuing kind=submit — science validity, output contract, required method, evidence in the executor session — and what the system handles automatically.
metadata:
  audience: both
---

# 提交前检查（PI 用）

提交由你用 kind=submit 的指导发起。系统负责打包（官方 CLI，加上执行者的原生会话）、账号轮换、上传和取回回执。你只需确认以下几点。

## 科学
1. 结果在科学上成立：物理或逻辑检查通过，收敛或稳定性有证据；题目要求时才需要第二种方法交叉验证。
2. 最终结果来自题目要求的方法；替代方法只用于探索或对照。
3. 这是当前真实的最佳版本，不是为试探评分器只改了一个参数。

## 交付
4. 题面输出契约中的每个文件都在结果包里，文件名、路径、格式、字段与契约一致。
5. 交付文件中的数值与执行者会话里最后一次生成时打印的一致。

## 证据（执行者会话就是提交轨迹）
6. 题目特定代码在会话中可见地写出再运行；每个交付文件都有生成它的可见命令；关键数字已打印。
7. 会话中没有凭据，没有编造的工具结果或时间。

任何一项不满足，先让执行者补上。轨迹不必追求完美，稳过 accept（轨迹分 ≥70）即可，写法见 cyberscientist-trace-writing。

## 系统会处理的
- 提交前的结构预检、密钥扫描、官方 CLI 试构建；
- 同题连续提交自动换账号；提交不限次数，但每次都应有实质变化；
- 平台明确拒收（达到上限、包未通过校验）时换账号或报错；状态未知时先对账，不盲目重发；
- 科学分先到，轨迹分和判定稍后；“人工复核中”的提交不影响继续迭代。

## 回执之后
- 科学分高且 accept：继续改进科学，或结束本题。
- 科学分高但没有 accept：按干净复跑策略发起，交接写法见角色说明。
- 回执出现 missing_worker_submission 或 nonstandard-submission-guard：这是提交链路问题，由系统和监控处理，不要改科学内容。
