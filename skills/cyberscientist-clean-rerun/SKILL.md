---
name: cyberscientist-clean-rerun
description: Before packaging, redo the final solution in a fresh authorized sandbox with the code visibly re-created in this trajectory, run it, verify it, and write the submitted outputs from visible commands.
metadata:
  audience: executor
---

# 提交前干净复跑

**目的有两个**：
- 证明在干净环境中能复现；
- 产生一条证据完整、能过轨迹门的求解轨迹。

S4 的数据显示，展示分 ≥90 的轨迹，会话时长中位约 40 分钟、约 80 步：在干净环境中，可见地写出代码、运行、打印、验证、写出产物。

**做法**：
1. 用题目指定的镜像（或环境目录中已验证的起点）新建沙箱，只传入官方题目资产和必要的公开数据。
2. **在本轨迹中重新写出**求解脚本和题目特定的实现（写文件的命令或编辑工具，代码内容出现在轨迹中）。内容可以与探索阶段的最终版相同，但不能只把旧文件拷进来直接运行：这会被判"产物先于轨迹存在"（N17）或"重放已有解答"（N16 蒸馏）。
3. 依次运行，打印关键中间值和最终数值；做一次独立验证，打印结论。
4. 用可见命令写出所有提交文件，路径与包内一致，并回显关键内容。
5. 记录镜像、输入哈希、命令、退出码、输出和文件哈希，作为提交包的运行日志。失败或未执行时如实标记。
6. 使用 `research_sandbox` 的 create、files.write、exec、files.read、delete。创建受时长、项目和数量授权约束；结果不明时对账，不重试变更。无后续用途时释放沙箱。

最终是否提交，由封存准入和 PI 决定。
