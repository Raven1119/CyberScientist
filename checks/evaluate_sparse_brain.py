"""Offline sparse-brain evaluation entrypoint; never invokes a model or Job.

Optionally pass a JSON response file shaped as {case_id: ResearchAnswer}.
The program checks completeness and prints the questions for human evidence
review. It deliberately does not reward dissent or trace reads by quantity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sparse_brain_independence.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, help="saved model outputs (offline JSON)")
    args = parser.parse_args()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == 3 and cases[0]["facts"] == cases[1]["facts"]
    answers = json.loads(args.answers.read_text(encoding="utf-8")) if args.answers else {}
    if args.answers and set(answers) != {case["id"] for case in cases}:
        parser.error("answer file must contain exactly the fixture case IDs")
    for case in cases:
        answer = answers.get(case["id"])
        if answer is not None and (not isinstance(answer, dict) or
                                   not isinstance(answer.get("answer_md"), str) or
                                   not answer["answer_md"].strip()):
            parser.error(f"{case['id']}: answer_md is required")
        print(json.dumps({"id": case["id"], "facts": case["facts"],
                          "question": case["question"], "options": case["options"],
                          "review_focus": case["review_focus"],
                          "answer_md": answer.get("answer_md") if answer else None},
                         ensure_ascii=False))
    print(f"Offline fixture ready: {len(cases)} cases; "
          f"{len(answers)} saved answers; no model calls")


if __name__ == "__main__":
    main()
