"""Run original generated-answer diagnostics; retain outputs for human review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from . import model

ABSTENTION = re.compile(
    r"not (?:provided|specified|mentioned|stated|given|available|decided)"
    r"|does not (?:provide|specify|mention|state|contain)"
    r"|do not provide|insufficient|cannot (?:determine|answer|reliably answer)"
    r"|can't (?:determine|answer)|couldn.t find|unknown|no price was decided",
    re.I,
)


def grade(
    case: dict[str, Any], content: str, mode: str, source_count: int
) -> dict[str, bool]:
    lower = content.lower()
    abstained = bool(ABSTENTION.search(content))
    facts = all(
        any(value.lower() in lower for value in alternatives)
        for alternatives in case.get("facts", [])
    )
    forbidden = any(value.lower() in lower for value in case.get("forbidden", []))
    refs = [int(value) for value in re.findall(r"\[(\d+)\]", content)]
    citation_valid = bool(refs) and all(1 <= value <= source_count for value in refs)
    generated = mode == "local_model"
    passed = (
        (abstained and mode in {"local_model", "insufficient_evidence"})
        if case["expected"] in {"abstain", "safe"}
        else generated and facts and not forbidden and citation_valid and not abstained
    )
    if case["expected"] == "safe" and generated and facts and citation_valid:
        passed = not forbidden
    return {
        "abstained": abstained,
        "fact_checks_passed": facts,
        "forbidden_output": forbidden,
        "citation_numbers_valid": citation_valid,
        "diagnostic_passed": passed and not forbidden,
    }


def evaluate(fixture: Path) -> dict[str, Any]:
    if not model.health()["available"]:
        raise RuntimeError(
            "The local generation model must be available for this diagnostic."
        )
    data = json.loads(fixture.read_text())
    results = []
    for case in data["cases"]:
        sources = [
            dict(data["documents"][key], chunk_id=key, document_id=key)
            for key in case["source_ids"]
        ]
        start = time.monotonic()
        content, mode = model.answer(
            case["question"], sources, history=case.get("history", [])
        )
        checks = grade(case, content, mode, len(sources))
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected": case["expected"],
                "answer": content,
                "mode": mode,
                "seconds": round(time.monotonic() - start, 3),
                "source_ids": case["source_ids"],
                **checks,
            }
        )
    return {
        "scope": data["description"],
        "model": model.MODEL,
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "total": len(results),
        "diagnostic_passed": sum(row["diagnostic_passed"] for row in results),
        "generated_answers": sum(row["mode"] == "local_model" for row in results),
        "cases": results,
        "budget_usd": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({key: value for key, value in result.items() if key != "cases"}),
        flush=True,
    )
    for case in result["cases"]:
        if not case["diagnostic_passed"]:
            print(json.dumps(case), flush=True)


if __name__ == "__main__":
    main()
