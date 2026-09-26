---
name: cyberscientist-clean-rerun
description: Before packaging a scientific submission, rerun its entry script in a fresh authorized Bohrium sandbox using the challenge image and retain the real log.
---

# 提交前干净复跑

在提交包定稿前，若本 Run 的沙箱授权和时间足够，用题目指定镜像新建沙箱，仅传入封存所需输入并运行提交入口脚本。不要在已有调试沙箱里复用可能残留的依赖或状态。记录镜像、输入哈希、命令、退出码、输出和文件哈希；把这次复跑的真实日志作为提交包运行日志，失败或未执行时如实标记，不伪造成功。

先确认入口脚本和依赖清单在当前 Trial 目录，使用 `research_sandbox` 的 create、files.write、exec、files.read 与 delete。创建必须受时长、项目和数量授权约束；结果不明时对账，不重试变更。取回日志和必要产物后立即删除沙箱。最终是否提交仍由现有封存准入与用户授权边界决定。
