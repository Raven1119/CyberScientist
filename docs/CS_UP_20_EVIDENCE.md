# CS-UP-20 验证证据

本报告按 W0–W11 记录真实实现和验证；RH-02 的科学结果、平台回执与算力另记，不用本地测试证明远端成功。

## W0：开工与决定

- 已实现：D-85–D-88 及本卡/RH-02 授权分界已写入 DECISIONS。
- 已实际验证：`git status --short` 无跟踪文件改动，保留全部用户未跟踪材料；开发 HEAD `eaf1891f6c3792534f7c1b31ac7f0057c52ab4e4`；候选版 2 标签存在。
- 已实际验证：读比赛 `.runtime/version.json`，运行 `.venv/bin/cyberscientist ops digest --target comp --since 2026-10-09T09:00:00Z`，loaded/checkout 都是 `4ef48d74d2f3c3f174527423477a18baf79a9410`，matches=true；提交 unknown 数量为 0。
- 尚未验证：W1–W11 与 RH-02。
- 阻塞项：历史 `trial9-clean-replay-create` 沙箱仍 unknown，不重放创建；不属于本卡新建额度。

后续逐项追加命令、原始私有证据位置及边界。
