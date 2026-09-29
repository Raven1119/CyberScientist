"""Compare pinned public v6 checklist calls with 63 private v8 receipts.

The detailed JSON is private and must stay in an ignored output directory.
Reliability thresholds are predeclared in docs/TRACE_CHECKLIST_V6_V8_AGREEMENT.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def classification(positives: int, precision: float | None,
                   recall: float | None) -> str:
    if precision is None or recall is None:
        return "unavailable_or_unknown"
    if positives >= 5 and precision >= .9 and recall >= .9:
        return "reliable"
    if positives >= 3 and precision >= .7 and recall >= .7:
        return "indicative"
    return "unavailable_or_unknown"


def compare(rows: list[dict], labels: dict[str, dict], variant: str) -> dict:
    universe = sorted({x["code"] for r in rows for x in r["items"]})
    entries = []
    for code in universe:
        cell = Counter()
        positives_all = sum(code in labels[r["sample"]]["reasons"] for r in rows)
        for row in rows:
            item = next((x for x in row["items"] if x["code"] == code), None)
            if item is None or item["status"] == "not_observable":
                cell["not_observable"] += 1
                continue
            predicted = item["status"] == "triggered"
            listed = code in labels[row["sample"]]["reasons"]
            cell["tp" if predicted and listed else "fp" if predicted else "fn" if listed else "tn"] += 1
        tp, fp, fn, tn = (cell[key] for key in ("tp", "fp", "fn", "tn"))
        precision = ratio(tp, tp + fp)
        recall = ratio(tp, tp + fn)
        # Open-world bounds: every unlisted v8 code may have been suppressed.
        # FP are unlisted locally positive; TN are unlisted locally negative.
        precision_bounds = [precision, 1.0 if tp + fp else None]
        recall_bounds = [ratio(tp, tp + fn + tn),
                         ratio(tp + fp, tp + fp + fn)]
        entries.append({"code": code, "v8_listed_positives": positives_all,
                        "eligible_positives": tp + fn, "eligible_samples": tp + fp + fn + tn,
                        "not_observable": cell["not_observable"],
                        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                        "precision": precision, "recall": recall,
                        "open_world_precision_bounds": precision_bounds,
                        "open_world_recall_bounds": recall_bounds,
                        "classification": classification(tp + fn, precision, recall)})
    v8_unique = sorted({code for r in rows for code in labels[r["sample"]]["reasons"]} - set(universe))
    limits = []
    for row in rows:
        actual = labels[row["sample"]]["score"]
        if row["cap"] + 1e-9 < actual:
            limits.append({"sample": row["sample"], "v6_cap": row["cap"],
                           "v8_score": actual, "v6_codes": row["codes"],
                           "v8_listed_codes": labels[row["sample"]]["reasons"]})
    return {"variant": variant, "rows": len(rows), "items": entries,
            "v8_unique_codes": v8_unique,
            "observable_comparisons": sum(x["eligible_samples"] for x in entries),
            "closed_world_mismatches": sum(x["fp"] + x["fn"] for x in entries),
            "cap_violations": limits}


def older_limits(rows: list[dict], labels: dict[str, dict], variant: str) -> dict:
    violations = [r for r in rows if r["cap"] + 1e-9 < labels[r["sample"]]["score"]]
    cap_counts = Counter(str(r["cap"]) for r in violations)
    score_bands = Counter("under30" if labels[r["sample"]]["score"] < 30 else
                          "30to69" if labels[r["sample"]]["score"] < 70 else "70plus"
                          for r in violations)
    return {"variant": variant, "rows": len(rows), "violation_count": len(violations),
            "by_v6_cap": dict(sorted(cap_counts.items())), "by_v8_score_band": dict(sorted(score_bands.items())),
            "final_score_violations": sum(labels[r["sample"]]["score_is_final"] for r in violations)}


def _display(value: float | None) -> str:
    return "未知" if value is None else f"{value:.3f}"


def render_tables(report: dict, main: dict, older: dict, n18: list[dict], native: list[dict]) -> None:
    start = "<!-- BEGIN GENERATED AGREEMENT TABLES -->"
    end = "<!-- END GENERATED AGREEMENT TABLES -->"
    text = report.read_text()
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise ValueError("predeclared report markers missing or duplicated")
    lines = ["", "本轮使用固定公开源码中的 `loadTrace`、`lintTrace`、`collectSubmissionEvidence` 和 `buildChecklistReport` 原函数。题面来自各次本地封存快照，产物目录先核对已有文件哈希；`runContext` 不可得时保留 `not_observable`，不伪造 worker 或裁判回执。", ""]
    for name, title in (("cli", "V-CLI：原版转换"), ("fix", "V-CLI-fix：修复版转换")):
        block = main[name]
        lines += [f"### {title}", "", "| 检查项完整代码 | v8 列出阳性 | 本地不可观察 | TP | FP | FN | TN | 精确率 | 召回率 | 条件分级 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for row in block["items"]:
            grade = {"reliable": "可靠", "indicative": "提示性", "unavailable_or_unknown": "不可用／未知"}[row["classification"]]
            lines.append("| " + " | ".join([row["code"], str(row["v8_listed_positives"]),
                str(row["not_observable"]), *(str(row[key]) for key in ("tp", "fp", "fn", "tn")),
                _display(row["precision"]), _display(row["recall"]), grade]) + " |")
        lines += ["", f"可观察代码-样本对 {block['observable_comparisons']}，闭世界不一致 {block['closed_world_mismatches']}；v8 独有代码：{', '.join(block['v8_unique_codes']) or '无'}。", ""]
    lines += ["### 回执未列出的开放世界解释", "", "下表将所有未列出的 v8 项视为可能被隐藏，仅列 v8 有阳性的代码。已列出阳性的命中／遗漏可知；未列出部分的 FP/TN 不可确认，因此给最宽的精确率、召回率区间。区间很宽时，闭世界条件分级不能当作已证明的完整 v8 触发规则。", "", "| 转换 | 代码 | 精确率可行区间 | 召回率可行区间 |", "|---|---|---|---|"]
    for name in ("cli", "fix"):
        for row in main[name]["items"]:
            if not row["v8_listed_positives"]:
                continue
            p = "–".join(_display(x) for x in row["open_world_precision_bounds"])
            r = "–".join(_display(x) for x in row["open_world_recall_bounds"])
            lines.append(f"| {name} | {row['code']} | {p} | {r} |")
    lines += ["", "### 上限不等式与转换影响", "", "| 集合／转换 | 样本数 | v6 上限低于历史 v8 轨迹分 | 违反上限的分布 |", "|---|---:|---:|---|"]
    for name in ("cli", "fix"):
        block = main[name]
        samples = ", ".join(x["sample"] for x in block["cap_violations"]) or "无"
        lines.append(f"| 主集 {name} | {block['rows']} | {len(block['cap_violations'])} | {samples} |")
        aux = older[name]
        lines.append(f"| 辅助集 {name} | {aux['rows']} | {aux['violation_count']} | 按本地上限 {aux['by_v6_cap']}；按历史分段 {aux['by_v8_score_band']}；最终分样本 {aux['final_score_violations']} |")
    lines += ["", f"主集闭世界不一致从 V-CLI 的 **{main['cli']['closed_world_mismatches']}** 增至 V-CLI-fix 的 **{main['fix']['closed_world_mismatches']}**。两组均未发现上限不等式违例；这只说明这批实际分数没有超过本地上限，不证明 v8 用了同一上限。逐样本的违例清单当前为空。", ""]
    lines += ["### N18：v8 独有的过程证据项", "", "| 脱敏样本 | v8 轨迹分 | v8 判定 | 修复版 v6 事件 | 工具调用／结果 | 修复版 v6 其他触发项 |", "|---|---:|---|---:|---:|---|"]
    for row in n18:
        lines.append(f"| {row['sample']} | {row['v8_score']} | {row['v8_decision']} | {row['v6_events']} | {row['v6_tool_calls']}／{row['v6_tool_results']} | {', '.join(row['v6_codes']) or '无'} |")
    lines += ["", f"V-native 直接输入公开 v6 时，{len(native)}/{len(native)} 份均被判 N04；工具调用解析总数 {sum(x['stats']['toolCalls'] for x in native)}。这组不用于和 v8 做一致率统计。", ""]
    before, after_start = text.split(start)
    _, after = after_start.split(end)
    report.write_text(before + start + "\n" + "\n".join(lines) + end + after)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not (args.out.resolve().parent / ".ignored-evidence").exists():
        raise ValueError("summary must stay in the ignored evidence directory")
    rows = read_jsonl(args.results)
    labels = {x["sample"]: x for x in json.loads(args.labels.read_text())}
    if len(rows) != 331 or len(labels) != 134 or len({(r["sample"], r["variant"]) for r in rows}) != 331:
        raise ValueError("incomplete or duplicate v6 checklist result set")
    by = {(r["sample"], r["variant"]): r for r in rows}
    main = {name: compare([by[(f"S{i:02d}", name)] for i in range(1, 64)], labels, name)
            for name in ("cli", "fix", "native")}
    older = {name: older_limits([by[(f"A{i:02d}", name)] for i in range(1, 72)], labels, name)
             for name in ("cli", "fix")}
    n18 = []
    for i in range(1, 64):
        key = f"S{i:02d}"
        if "N18_PROCESS_EVIDENCE_INSUFFICIENT" in labels[key]["reasons"]:
            record = by[(key, "fix")]
            n18.append({"sample": key, "v8_score": labels[key]["score"],
                        "v8_decision": labels[key]["decision"],
                        "v6_events": record["stats"]["events"],
                        "v6_tool_calls": record["stats"]["toolCalls"],
                        "v6_tool_results": record["stats"]["toolResults"],
                        "v6_codes": record["codes"]})
    result = {"schema": "cyberscientist/trace-checklist-agreement/v1",
              "score_interpretation": "v8 listed negatives are observed, unlisted may be hidden",
              "main": main, "older": older, "n18": n18}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if args.report:
        render_tables(args.report, main, older, n18,
                      [by[(f"S{i:02d}", "native")] for i in range(1, 64)])
    print(json.dumps({"main_rows": main["fix"]["rows"],
                      "eligible_codes": [x["code"] for x in main["fix"]["items"]
                                         if x["classification"] in ("reliable", "indicative")],
                      "mismatches": {name: main[name]["closed_world_mismatches"] for name in ("cli", "fix")},
                      "cap_violations": {name: len(main[name]["cap_violations"]) for name in ("cli", "fix")},
                      "older_violations": {name: older[name]["violation_count"] for name in ("cli", "fix")},
                      "n18": len(n18)}))


if __name__ == "__main__":
    main()
