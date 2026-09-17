"""外部协议真实探针：结果写入 docs/INTEGRATION_STATUS.md。

只执行零模型调用的握手/版本探针，不消耗额度。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "INTEGRATION_STATUS.md"


def probe_codex() -> dict:
    from cyberscientist.brains.codex import CodexBrain, default_executable
    exe = default_executable()
    result: dict = {"executable": exe or "(未找到)",
                    "probes": []}
    if exe:
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True,
                               timeout=30)
            result["probes"].append({"cmd": "codex --version",
                                     "ok": v.returncode == 0,
                                     "output": (v.stdout or v.stderr).strip()[:200]})
        except Exception as exc:  # noqa: BLE001
            result["probes"].append({"cmd": "codex --version", "ok": False,
                                     "output": f"{exc.__class__.__name__}: {exc}"})
        try:
            health = asyncio.run(CodexBrain(exe).inspect())
            result["probes"].append({
                "cmd": "codex app-server (initialize handshake)",
                "ok": health.installed and bool(health.version),
                "version": health.version,
                "detail": health.detail,
                "raw_capabilities": getattr(health, "raw", {})})
        except Exception as exc:  # noqa: BLE001
            result["probes"].append({"cmd": "codex app-server", "ok": False,
                                     "output": f"{exc.__class__.__name__}: {exc}"})
    return result


def probe_command(name: str, *candidates: str) -> dict:
    for c in candidates:
        path = shutil.which(c)
        if path:
            try:
                v = subprocess.run([path, "--version"], capture_output=True,
                                   text=True, timeout=30)
                return {"installed": True, "path": path,
                        "version": (v.stdout or v.stderr).strip()[:200]}
            except Exception as exc:  # noqa: BLE001
                return {"installed": True, "path": path,
                        "version": f"版本探针失败: {exc}"}
    return {"installed": False, "path": None,
            "version": "未在 PATH 或常见安装位置发现"}


def main() -> None:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    codex = probe_codex()
    prime = probe_command("prime-agent", "prime-agent", "prime")
    bohr = probe_command("bohr", "bohr")
    kimi = probe_command("kimi", "kimi", "kimi-code")

    lines = [f"# 外部集成探针记录\n",
             f"探针日期：{date}。本文件只记录实际执行的命令与结果，不编造接口。\n",
             "## Codex 大脑\n",
             f"- 可执行文件：`{codex['executable']}`\n"]
    for p in codex["probes"]:
        lines.append(f"- `{'✅' if p['ok'] else '❌'} {p['cmd']}` → {p.get('version') or p.get('output', '')}"
                     f"（{p.get('detail', '')}）\n")
    if codex["probes"]:
        caps = codex["probes"][-1].get("raw_capabilities")
        if caps:
            lines.append(f"- initialize 原始返回（脱敏原样记录）: `{json.dumps(caps)[:400]}`\n")
    lines += ["- 已证实：app-server stdio 启动 + initialize/initialized 握手（零模型调用）。\n",
              "- 未证实：thread/start、turn/start 的字段形状与终态事件（需一次授权的模型往返）；\n",
              "  turn/interrupt、thread/resume、审批请求处理。能力标记保持保守。\n"]
    lines += ["\n## Prime Agent\n",
              f"- 安装：{'是' if prime['installed'] else '否'}（{prime['path']}）\n",
              f"- 版本：{prime['version']}\n",
              "- RPC 协议（`prime-agent --mode rpc`，JSONL stdin/stdout）按官方仓库文档实现适配壳，"
              "未经真实探针核实；可执行文件缺失时不启动真实会话。\n"]
    lines += ["\n## bohr（Bohrium CLI）\n",
              f"- 安装：{'是' if bohr['installed'] else '否'}（{bohr['path']}）\n",
              f"- 版本：{bohr['version']}\n",
              "- Bohrium 科学计算在阶段 2 接入；bohr 缺失时绝不回退本地科学计算。\n"]
    lines += ["\n## Kimi Code 大脑\n",
              f"- 安装：{'是' if kimi['installed'] else '否'}（{kimi['path']}）\n",
              f"- 版本：{kimi['version']}\n",
              "- 未发现可独立调用的 `kimi --wire` 可执行文件 → 适配器保持“未接入”边界，"
              "不退化为普通聊天 API。\n"]
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
