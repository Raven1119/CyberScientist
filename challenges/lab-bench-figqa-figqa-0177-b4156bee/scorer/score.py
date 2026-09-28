"""Scientific score for the canonical FigQA-0177 answer-file interface.

Ground truth comes from Future-House/LAB-Bench, not historical score labels.
The benchmark's semantic answer is M10. B is specific to this challenge's
frozen option order. Unobserved malformed-input behavior is left unverified.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

CHALLENGE_ID = "lab-bench-figqa-figqa-0177-b4156bee"
PUBLIC_INSTANCE_ID = "ae9125e5-ce14-46f9-9ff7-d7bda1e101e1"
CORRECT_OPTION = "B"


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
    match = re.fullmatch(r"\[ANSWER\]([A-E])\[/ANSWER\]", answer)
    if not match:
        raise Unverified("noncanonical answer parsing is not historically validated")
    option = match.group(1)
    return {"score": 100 if option == CORRECT_OPTION else 0,
            "components": {"option": option, "correct_option": CORRECT_OPTION,
                           "semantic_target": "M10", "format": "canonical",
                           "answer_sha256": hashlib.sha256(raw).hexdigest()},
            "confidence": "medium",
            "notes": "Reconstructs canonical scientific scoring from the public LAB-Bench answer and exact-match rule. "
                     "Option B is challenge-specific. Does not predict trace or display score, packaging acceptance, "
                     "or the hidden parser's behavior on malformed answers.",
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
