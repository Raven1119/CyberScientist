# 外部集成探针记录
探针日期：2026-09-17 13:58 UTC。本文件只记录实际执行的命令与结果，不编造接口。
## Codex 大脑
- 可执行文件：`C:\Users\wmywb/.codex/.sandbox-bin/codex.exe`
- `✅ codex --version` → codex-cli 0.154.0-alpha.6.2（）
- `✅ codex app-server (initialize handshake)` → 0.154.0-alpha.6.2（app-server 握手成功（initialize），未发起模型调用； codexHome=C:\Users\wmywb\.codex）
- initialize 原始返回（脱敏原样记录）: `{"initialize_result": {"userAgent": "cyberscientist/0.154.0-alpha.6.2 (Windows 10.0.26200; x86_64) dumb (cyberscientist; 0.1.0)", "codexHome": "C:\\Users\\wmywb\\.codex", "platformFamily": "windows", "platformOs": "windows"}}`
- 已证实：app-server stdio 启动 + initialize/initialized 握手（零模型调用）。
- 未证实：thread/start、turn/start 的字段形状与终态事件（需一次授权的模型往返）；
  turn/interrupt、thread/resume、审批请求处理。能力标记保持保守。

## Prime Agent
- 安装：否（None）
- 版本：未在 PATH 或常见安装位置发现
- RPC 协议（`prime-agent --mode rpc`，JSONL stdin/stdout）按官方仓库文档实现适配壳，未经真实探针核实；可执行文件缺失时不启动真实会话。

## bohr（Bohrium CLI）
- 安装：否（None）
- 版本：未在 PATH 或常见安装位置发现
- Bohrium 科学计算在阶段 2 接入；bohr 缺失时绝不回退本地科学计算。

## Kimi Code 大脑
- 安装：否（None）
- 版本：未在 PATH 或常见安装位置发现
- 未发现可独立调用的 `kimi --wire` 可执行文件 → 适配器保持“未接入”边界，不退化为普通聊天 API。
