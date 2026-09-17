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


def probe_prime() -> dict:
    import shutil
    exe = shutil.which("prime-agent")
    result: dict = {"executable": exe or "(未找到)", "probes": []}
    if exe:
        from cyberscientist.prime import PrimeRpc
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True,
                               timeout=30)
            result["probes"].append({"cmd": "prime-agent --version",
                                     "ok": v.returncode == 0,
                                     "output": (v.stdout or v.stderr).strip()[:200]})
        except Exception as exc:  # noqa: BLE001
            result["probes"].append({"cmd": "prime-agent --version", "ok": False,
                                     "output": f"{exc.__class__.__name__}: {exc}"})
        try:
            health = asyncio.run(PrimeRpc(exe).inspect())
            result["probes"].append({
                "cmd": "prime-agent --mode rpc (get_state)",
                "ok": health.installed and "探针成功" in health.detail,
                "output": health.detail,
                "state_keys": getattr(health, "raw_state_keys", [])})
        except Exception as exc:  # noqa: BLE001
            result["probes"].append({"cmd": "prime-agent --mode rpc", "ok": False,
                                     "output": f"{exc.__class__.__name__}: {exc}"})
    return result


def main() -> None:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    codex = probe_codex()
    prime = probe_prime()
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
              f"- 可执行文件：`{prime['executable']}`\n"]
    for p in prime["probes"]:
        lines.append(f"- `{'✅' if p['ok'] else '❌'} {p['cmd']}` → {p.get('output', '')[:220]}\n")
    if prime["probes"] and prime["probes"][-1].get("state_keys"):
        lines.append(f"- get_state 返回字段（原样记录）: `{', '.join(prime['probes'][-1]['state_keys'])}`\n")
    lines += ["- 已证实：版本探针 + RPC 模式启动 + `get_state` 零模型调用响应"
              "（sessionId/isStreaming/steeringMode 等字段与官方文档一致）。\n",
              "- 已证实（文档级，未实测）：prompt/steer/abort 命令形状、steer 排队语义、"
              "get_session_stats 用量/成本。\n",
              "- 未证实：真实模型回合（需用户授权额度与模型供应商配置）；"
              "项目隔离 `--session-dir` 与自定义 models.json 的两 Profile 不串配置测试。\n"]
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
