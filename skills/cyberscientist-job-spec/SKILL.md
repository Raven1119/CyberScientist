---
name: cyberscientist-job-spec
description: Prepare a bounded Bohrium Job specification, inputs and entry declaration for long or large computations, and interpret native receipts without replaying unknown operations.
audience: executor
---

# Bohrium Job 规格

**计算放置**：先在本题沙箱调试和冒烟；长时间、大规模的计算才用 Job，镜像与沙箱相同。Job 提交前系统会自动预检（脚本语法、命令和路径是否在镜像中、是否需要网络、backward_files、时限、ABACUS 可动原子等），不过就直接返回原因，不消耗 Job。

通过本 Run 的 `research_job` 或受控 `bohr job` 准备规格。HTTP 接受不等于已启动，Finished 不等于结果正确，下载和文件哈希要分别核验。项目、机器、最长时间、数量、费用及 GPU 授权由网关核验，任何 Job 都不能越过赛道结束时间。

- `result_path` 只允许 `/personal`、`/share` 或它们的子目录，不能用 `/data` 作结果盘。结果文件还须列在 `backward_files` 中，日志用 `log_file`。
- 规格和命令里不能残留未替换的占位符（如 `{{ENTRY}}`、`${IMAGE}`、`<PROJECT_ID>`）；填写真实已授权的值，密钥不能放进规格或命令。
- `input_directory` 只放入口、必要源码和输入，路径相对该目录；目录内文件在远端工作目录根展开，不会多出一层 `input/`。先列出文件、计算 SHA，确认入口已打包；不要把整个工作树、缓存或凭据打包。脚本可以用 `bash work.sh` 或 `python3 work.py`；直接 `./work.sh` 时要保留可执行权限。
- `python3 -I -c '...'` 里 `-I` 是隔离选项，`-c` 后是内联代码，不是入口文件。代码用到打包模块时，声明真实的 `preflight.entry` 源文件用于依赖预检。
- 设定时限：有冒烟耗时时，时限至少是冒烟耗时乘以合理系数；没有冒烟时先做冒烟。
- GPU 机型从平台实时机器目录选；先核对本轮 GPU 授权，运行后用 `nvidia-smi` 和框架的 `cuda.is_available()` 确认。
- **状态未知**：按原操作 ID 对账，不用同一 ID 盲目重放。超过 10 分钟仍无法确认时，可在授权内换新 operation_id 重新提交，旧操作继续在后台对账，找到后正常登记，必要时停止。

大文件优先走对象存储通道；必要时分块写入，每块有独立的稳定操作 ID、序号、字节数和 SHA，组装后核验整个文件的 SHA。

**模板**：附件 `attachments/abacus/` 里有 ABACUS 的 SCF 和 cell-relax 模板（含运行前的输入检查和运行后的收敛检查），用于 ABACUS 计算时可直接改用。
