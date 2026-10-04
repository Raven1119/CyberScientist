---
id: csup08_large_transfers
title: 大输入传输：优先已有对象或数据集，逐次核验完整哈希
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
audience: both
tags:
- 上传
- 数据集
- 传输
- 环境
applicability: 大文件、工具链与科学包转运
evidence_refs:
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
---
先看 operating_facts 的按输入大小分档结果。大输入优先复用已有数据集挂载或题目资源物化，减少重复上传；当前卡只授权公开软件新建环境，不能把题目答案或密钥装进环境。

没有可复用数据集时，可把公开依赖文件随受控 Job 输入冻结上传，再由系统下载；沙箱 files.write 用于明确、可核验的输入。任何通道收到 unknown 后不重复原操作，先只读核对长度、SHA256 和目标状态；有余量时换新 ID／通道。

转运完成的判据是完整长度与 SHA256 一致，前缀到达不是上传成功。若必须分块，保存明确序号、每块哈希、完整文件哈希；只在远程授权环境组装后核对。v3 科学 ZIP 曾只到达 1,228,800 字节；Lean 首轮四个 64MiB 块没传完，不能把它们称为环境就绪。不要承诺某条网络通道恒定可靠。

证据引用：
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:docs/EVAL_V1_RUN_AUDIT.md#sha256=75680ecce33100bb0145288d5a50b244cdabb5809d8cac96133e07dac20df7c4
