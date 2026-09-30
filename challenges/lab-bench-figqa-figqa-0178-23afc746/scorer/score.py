"""Canonical scientific answer for the fixed FigQA-0178 option order.

The public LAB-Bench instance 1dcc341b-c11c-4d2b-b4e0-b331d98ca6b7 names
P7C3-A20. In this platform challenge it is option F. Malformed-input
behavior of the platform's hidden wrapper remains unverified.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

CHALLENGE_ID = "lab-bench-figqa-figqa-0178-23afc746"
PUBLIC_INSTANCE_ID = "1dcc341b-c11c-4d2b-b4e0-b331d98ca6b7"
CORRECT_OPTION = "F"


class Unverified(ValueError):
    pass


def evaluate(package: Path, version: str) -> dict:
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) > 5000 or len(names) != len(set(names)):
            raise Unverified("ambiguous archive")
        if any(n.startswith("/") or "\\" in n or ".." in PurePosixPath(n).parts for n in names):
            raise Unverified("unsafe archive paths")
        paths = [n for n in names if n == "outputs/answer.txt" or n.endswith("/outputs/answer.txt")]
        if len(paths) != 1:
            raise Unverified("exactly one outputs/answer.txt is required")
        if archive.getinfo(paths[0]).file_size > 100_000:
            raise Unverified("answer file exceeds evaluator limit")
        raw = archive.read(paths[0])
    try:
        answer = raw.decode("utf-8-sig").strip()
    except UnicodeError as exc:
        raise Unverified("answer is not UTF-8") from exc
    match = re.fullmatch(r"\[ANSWER\]([A-F])\[/ANSWER\]", answer)
    if not match:
        raise Unverified("noncanonical answer parsing is not historically validated")
    option = match.group(1)
    return {"score": 100 if option == CORRECT_OPTION else 0,
            "components": {"option": option, "correct_option": CORRECT_OPTION,
                           "semantic_target": "P7C3-A20", "format": "canonical",
                           "answer_sha256": hashlib.sha256(raw).hexdigest()},
            "confidence": "medium",
            "notes": "Canonical scientific answer from public LAB-Bench and this challenge's fixed option order. "
                     "Four F-answer historical receipts have science score 100. Other options and malformed "
                     "inputs have not been calibrated to the platform wrapper. No trace or display prediction.",
            "scorer_version": version}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: score.py science_package.zip")
    try:
        result = evaluate(Path(sys.argv[1]), os.environ["CS_SCORER_VERSION"])
    except (Unverified, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "unverified", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
