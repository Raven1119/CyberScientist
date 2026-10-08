---
name: cyberscientist-job-spec
description: Prepare a bounded Bohrium v4 Job specification, inputs and entry declaration, and interpret native receipts without replaying unknown operations.
audience: executor
---

# Bohrium Job 规格

本地秒级计算遵循 运行规则：由执行器记录命令、输出、耗时和来源；PI只读审阅。依赖验证、较重科研计算、统计和科学作图在授权 Bohrium Job 或沙箱执行。环境目录是起点：先读镜像版本和最近真实冒烟事实，再用关键 import、设备检查和最小实际操作做远端冒烟；目录存在不等于验证器或科研结论通过。

通过本 Run 的 `research_job` / 受控 `bohr job` 准备规格。v4 使用原生 CLI 的 Job submit/describe/download；区分平台 jobId 与 bohrJobId，按原回执指定的 native ID 查询。HTTP接受不等于启动、Finished不等于结果正确，下载和文件哈希分别核验。项目、机器、最长时间、数量、费用及GPU授权由网关核验；无限比赛仍不能越过赛道结束时间。

- `result_path` 只允许 `/personal`、`/share` 或这两者的子目录；不能用 `/data` 作为结果盘。结果文件还须列在 `backward_files`，日志使用 `log_file`。
- 规格和命令不能残留未替换的占位符，例如 `{{ENTRY}}`、`${IMAGE}`、`<PROJECT_ID>`；填写真实已授权的值，密钥不能放进规格或命令。
- `input_directory` 只放入口、必要源码和输入，路径相对该目录；目录内文件在远端工作目录根展开，不会自动多一层 `input/`。先列文件、计算SHA并确认入口已打包；不要把整个工作树、缓存、凭据打包。脚本可用 `bash work.sh` 或 `python3 work.py`；直接 `./work.sh` 时保留可执行权限（`chmod +x` 后检查权限），压缩/传输也核对 mode。
- `python3 -I -c '...'` 中 `-I` 是隔离选项、`-c` 后是内联代码，不是入口文件。若代码使用打包模块，明确声明真实 `preflight.entry` 源文件用于依赖预检；不要声明 `-I`。`python3 -m package.module` 同样声明对应的打包源文件；解释器选项不能当文件名。
- GPU 机型从本平台实时机器目录选，例如目录已观察的 `c4_m15_1 * NVIDIA T4`；先核对本轮独立GPU授权和价格/资源事实，运行后用 `nvidia-smi` 和框架 `cuda.is_available()` 确认。CUDA wheel须与当前驱动兼容，不能从机型名称推断驱动版本。
- 交互调依赖、快速定位入口或 Job 平台故障时，可在已有独立沙箱授权内改用沙箱；不是免费替代，也不扩权。未知 Job 按原操作身份对账：控制器证明未接受时可按现行自动重交规则处理；D-31允许超过10分钟仍无法对账时在原授权内换新 operation_id，保留旧费用估算和后台对账，后来找到时正常登记、必要时停止。禁止同一操作盲重放，不能推广成“unknown绝不重发”或“不确定就停”。

大文件优先对象存储通道。Run绑定沙箱的 `/bohr-workspace/` 文件传输由网关使用原生 `--ti --session-id`；结果留文件并通过受控下载取回。必要时分块写入：每块独立稳定操作ID、序号、字节数和SHA，组装后核验整文件SHA；未知写入先对账，不能盲目重发。不要把大对象或密钥内联进提示词。
