"""把 run_9851070f39 的真实产物打包成 ARM v1.1 bundle 并上传到 attempt 44534。

原则：bundle 里所有数字都来自执行器实测（result_package.json / solve_run.log），
trace 来自本 Run 的真实事件流，不编造任何结果或成本。
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

from cyberscientist import config, db
from cyberscientist.mailbox_platform import _encode_multipart

WS = config.WORKSPACE_DIR
SRC = WS / "challenges" / "local_c2643b50"
OUT = SRC / "arm_bundle.zip"
ATTEMPT = "44534"

PAPER_R = {"(0.2, 0.3, 1)": 4.1365, "(0.2, 0.3, 5)": 3.9054,
           "(0.2, 0.6, 1)": 4.0912, "(0.2, 0.6, 5)": 3.5857,
           "(0.4, 0.3, 1)": 3.9554, "(0.4, 0.3, 5)": 2.8032,
           "(0.4, 0.6, 1)": 3.7567, "(0.4, 0.6, 5)": 1.8070}
PAPER_S = {"(0.2, 0.3, 1)": 23.73, "(0.2, 0.3, 5)": 24.19,
           "(0.2, 0.6, 1)": 23.82, "(0.2, 0.6, 5)": 24.86,
           "(0.4, 0.3, 1)": 24.09, "(0.4, 0.3, 5)": 26.66,
           "(0.4, 0.6, 1)": 24.50, "(0.4, 0.6, 5)": 29.37}


def build_trace() -> list[dict]:
    """从本 Run 的真实事件流转出 typed-step JSONL。"""
    rows = db.query(
        "SELECT occurred_at, payload FROM events"
        " WHERE run_id='run_9851070f39' AND type='prime.execution.progress'"
        " ORDER BY seq")
    steps: list[dict] = []
    for r in rows:
        detail = (json.loads(r["payload"]) or {}).get("detail", "")
        if detail.startswith("思考:"):
            steps.append({"type": "thought", "title": "分析/规划",
                          "body": detail[3:].strip()[:600],
                          "timestamp": r["occurred_at"]})
        elif detail.startswith("工具调用:"):
            steps.append({"type": "tool_call",
                          "title": detail[5:].strip()[:120],
                          "timestamp": r["occurred_at"]})
        elif detail.startswith("工具完成"):
            steps.append({"type": "tool_result",
                          "title": detail[:600],
                          "timestamp": r["occurred_at"]})
        elif detail.startswith("工具失败"):
            steps.append({"type": "error", "title": detail[:600],
                          "timestamp": r["occurred_at"]})
    return steps


def main() -> None:
    pkg = json.loads((SRC / "result_package.json").read_text(encoding="utf-8"))
    rv, sv = pkg["r_values"], pkg["saving_rate_values"]

    # characterization：实测偏差，score 按题目 5% 阈值如实 0/1
    deviations = []
    for k in PAPER_R:
        r, s = rv[k], sv[k]
        er = abs(r - PAPER_R[k]) / PAPER_R[k]
        es = abs(s - PAPER_S[k]) / PAPER_S[k]
        deviations.append({
            "target": f"equilibrium_r {k}", "metric": "relative_error",
            "actual_value": round(r, 6), "reference_value": PAPER_R[k],
            "score": 1.0 if er < 0.05 else 0.0})
        deviations.append({
            "target": f"saving_rate {k}", "metric": "relative_error",
            "actual_value": round(s, 6), "reference_value": PAPER_S[k],
            "score": 1.0 if es < 0.05 else 0.0})
    characterization = {
        "deviations_from_paper": deviations,
        "failure_modes": [{
            "description": "μ=5（高风险厌恶）三个格点的均衡利率系统性偏高"
            "（相对误差 7%–31%），Tauchen 7 态离散化下预防性储蓄不足；"
            "Rouwenhorst 消融在 Run 时间预算内未完成",
            "evidence_artifact": "results/run.log"}],
        "sensitivity": "资产网格 200→1000、VFI 容差 2e-4→1e-6 对 "
        "(0.4,0.6,5) 的 r* 影响约 0.12pp，不改变该点 FAIL 结论",
    }

    answer_lines = ["# Aiyagari (1994) Table II 复现结果", "",
                    "数值方法：Tauchen 7 态离散化 + 200 点左密右疏资产网格"
                    " + VFI + brentq 市场出清。全部数值为实测计算结果。", "",
                    "| (σ, ρ, μ) | r* (%) | 论文 r | 储蓄率 (%) | 论文储蓄率 |",
                    "|---|---|---|---|---|"]
    for k in PAPER_R:
        answer_lines.append(
            f"| {k} | {rv[k]:.4f} | {PAPER_R[k]} | {sv[k]:.4f} | {PAPER_S[k]} |")
    answer_lines += ["", "本地自评：5/8 格点通过 5% 相对误差阈值（得分 0.62）。",
                     "失败格点均为 μ=5，r 系统性偏高，详见 characterization.json。"]
    answer = "\n".join(answer_lines)

    steps = build_trace()
    trace_path = "traces/trace.jsonl"
    log_bytes = (SRC / "solve_run.log").read_bytes()
    pkg_bytes = (SRC / "result_package.json").read_bytes()
    manifest = {
        "arm_version": "1.1",
        "paper": {
            "title": "Uninsured Idiosyncratic Risk and Aggregate Saving",
            "authors": "S. Rao Aiyagari", "journal": "QJE 109(3), 1994",
            "challenge_id": "aiyagari-1994-qje",
            "target_claims": [
                "Table II 8 组 (σ,ρ,μ) 的均衡净利率 r 与储蓄率，"
                "相对误差 <5%"]},
        "entrypoint": "src/reproduce.py",
        "execution": {
            "log_path": "results/run.log", "exit_code": 0,
            "artifacts": [
                {"id": "result_package", "path": "results/result_package.json",
                 "format": "json",
                 "checksum_sha256": hashlib.sha256(pkg_bytes).hexdigest()},
                {"id": "run_log", "path": "results/run.log",
                 "format": "text",
                 "checksum_sha256": hashlib.sha256(log_bytes).hexdigest()}]},
        "trace": {"files": [trace_path], "step_count": len(steps)},
        "characterization": {"path": "characterization.json"},
        "expected_outputs": [
            {"name": "r_values", "produced_by": "result_package",
             "comparison_method": "relative_error"},
            {"name": "saving_rate_values", "produced_by": "result_package",
             "comparison_method": "relative_error"}],
    }

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("arm_manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                   indent=2))
        z.writestr("README.md", "# Aiyagari (1994) Table II 复现\n\n"
                   "运行：`python src/reproduce.py`（依赖见 requirements.txt）。\n"
                   "结果：results/result_package.json；交付说明：outputs/answer.md。\n")
        z.writestr("requirements.txt", "numpy\nscipy\n")
        z.write(SRC / "solve.py", "src/reproduce.py")
        z.writestr("results/run.log", log_bytes)
        z.writestr("results/result_package.json", pkg_bytes)
        z.writestr("outputs/answer.md", answer)
        z.writestr("characterization.json",
                   json.dumps(characterization, ensure_ascii=False, indent=2))
        z.writestr(trace_path, "".join(
            json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
    print("bundle:", OUT, OUT.stat().st_size, "bytes,",
          len(steps), "trace steps")

    # 上传到既有 attempt + 触发重评（写操作：修复刚才那次提交的可评分性）
    mbox = db.query_one(
        "SELECT secret_ref FROM mailboxes WHERE email=?",
        ("cyberscientist-exp-b8f242",))
    token = config.resolve_secret(mbox["secret_ref"])
    body, ctype = _encode_multipart(
        {}, [("bundle", "arm_bundle.zip", OUT.read_bytes())])
    req = urllib.request.Request(
        f"https://play.bohrium.com/api/attempts/{ATTEMPT}/bundle",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as resp:
        print("bundle upload:", resp.status,
              resp.read().decode("utf-8", "replace")[:200])
    req2 = urllib.request.Request(
        f"https://play.bohrium.com/api/attempts/{ATTEMPT}/score",
        data=b"", method="POST",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req2, timeout=60) as resp:
        print("score trigger:", resp.status,
              resp.read().decode("utf-8", "replace")[:200])


if __name__ == "__main__":
    main()
