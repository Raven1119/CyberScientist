# CS-UP-04：固定版本轨迹转换对照

本实验只读取已封存的 63 条本人历史原生轨迹；完整转换文件、原始哈希索引和补丁后的 CLI 副本留在本机忽略目录 `.package-checks/cs-up-04/`。脚本 `checks/build_trace_conversion_variants.py` 执行前验证公开 scorer commit `81c434907e7b0a2feccc79236f6601f7abbc1d84`、源码 SHA-256 `afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46` 和本机 Playground CLI 0.1.33 的 `dist/index.js` SHA-256 `d231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03`。公开源码附带 MIT 许可证，允许保留许可文本再分发。转换使用隔离空 HOME 和阻断 Node 网络入口的 preload，没有模型或平台请求。

固定的修复只调整 `parseTraceSteps` 中 OpenCode 优先级：有 Codex `thread.started` 与 `item.*` 签名，而 OpenCode 信号只有通用顶层 `error` 时，继续交给后面的 Codex 分支。全局安装的 CLI 不修改；其精确副本位于本机忽略目录。补丁仅改 1 行，unified diff 的变更行数为 2：

```diff
--- a/dist/index.js
+++ b/dist/index.js
@@ -1069,7 +1069,7 @@
     const normalized = normalizeArmSteps(rows);
     if (normalized.length >= Math.max(1, Math.floor(rows.length * 0.8)))
         return normalized;
-    if (opencodeEventLike(rows))
+    if (opencodeEventLike(rows) && !(codexEventLike(rows) && rows.every((row) => !["step_start", "step_finish", "text", "tool_use"].includes(stringValue(row.type) || ""))))
         return convertOpenCodeEvents(rows, source);
     if (claudeCodeEventLike(rows))
         return convertClaudeCodeEvents(rows, source);
```

运行命令：

```bash
mkdir -p .package-checks/cs-up-04
touch .package-checks/cs-up-04/.ignored-evidence
PATH="$HOME/.local/bin:$PATH" .venv/bin/python checks/build_trace_conversion_variants.py \
  --diagnostics .package-checks/agentmaster-grader-diagnostics-20260928/diagnostics.jsonl \
  --agentmaster ../AgentMaster \
  --upstream .package-checks/trace-score-source-20260928/upstream \
  --cli /home/wmywb/.local/lib/node_modules/@paper2arm/playground-cli/dist/index.js \
  --out .package-checks/cs-up-04
```

| 转换输入 | 成功样本 | 总事件数 | 成对工具调用数 | error 事件数 |
|---|---:|---:|---:|---:|
| V-native，原生事件清点 | 63 | 4034 | 1419 | 5 |
| V-CLI，官方原版转换 | 63 | 3230 | 1384 | 22 |
| V-CLI-fix，单行修复 | 63 | 3317 | 1419 | 18 |

逐条的事件数、成对工具调用、error 数与 SHA-256 见本机 `conversions.jsonl`，63 条无缺失。V-native 这里仅清点原生数据，直接喂给 v6 解析器的表现由 W2 另列，不计一致率。

按转换后除时间戳外的内容比较，**只有 S10、S30** 发生实质变化。S10 是 78 条原生事件、25 对工具调用；原版变为 4 条 error、0 对，修复版为 65 条事件、25 对。S30 对应先前报告的 E008：43 条原生事件、10 对工具调用；原版只剩 1 条 error，修复版为 27 条事件、10 对。修复后的 Codex 转换并未把顶层传输 error 保留为 ARM error 行；原生文件仍在本机，不能把修复版描述成无损转换。

同一份轨迹两次独立调用 CLI 时，缺少原始时间戳的行可能由 CLI 填入当前时间，使两个原始输出 SHA 不同，即使事件类型和内容相同。第二次运行中 S59 仅有这种时间戳差异；脚本同时记录原始 SHA 和排除时间戳后的语义 SHA，后续一致性统计按实际两组输出运行，不把单纯哈希差异算作检查项变化。样本键 S01–S63 与真实提交标识的映射只在忽略目录。
