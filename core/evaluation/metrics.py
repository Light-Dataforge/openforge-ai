"""Evaluate categorical answers; confidence means probability of exact correctness.

This evaluator establishes accounting, not semantic or visual verification.
Inputs are bounded local JSONL files. No models, tools, or network calls execute.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from core.local_files import read_regular

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10000


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _text(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _load(
    path: str | Path, *, prediction: bool
) -> tuple[dict[str, dict[str, Any]], str]:
    raw = read_regular(path, MAX_BYTES)
    rows: dict[str, dict[str, Any]] = {}
    lines = raw.decode("utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    if not 1 <= len(lines) <= MAX_RECORDS:
        raise ValueError("input requires 1 to 10000 records")
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except (ValueError, RecursionError) as exc:
            raise ValueError(f"invalid JSON at line {number}") from exc
        fields = {"id", "answer", "confidence"} if prediction else {"id", "answer"}
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError(f"invalid fields at line {number}")
        if not _text(row["id"]) or row["id"] in rows:
            raise ValueError(f"invalid or duplicate ID at line {number}")
        answer = row["answer"]
        if not (prediction and answer is None) and not _text(answer):
            raise ValueError(f"invalid answer at line {number}")
        if prediction:
            confidence = row["confidence"]
            if answer is None:
                if confidence is not None:
                    raise ValueError("abstentions require null confidence")
            elif (
                type(confidence) not in (int, float)
                or not 0 <= confidence <= 1
                or not math.isfinite(confidence)
            ):
                raise ValueError("confidence must be finite and between 0 and 1")
        rows[row["id"]] = row
    return rows, hashlib.sha256(raw).hexdigest()


def evaluate(references: str | Path, predictions: str | Path) -> dict[str, Any]:
    """Return deterministic metrics; every reference must have a prediction row.

    Answer matching is exact and case-sensitive, with no Unicode normalization.
    Missing predictions fail validation rather than silently inflating accuracy.
    Abstentions use a null answer and null confidence. Brier score is conditional
    on answered records and must always be interpreted alongside coverage.
    """
    refs, ref_hash = _load(references, prediction=False)
    preds, pred_hash = _load(predictions, prediction=True)
    if refs.keys() != preds.keys():
        raise ValueError("reference and prediction IDs must match exactly")
    answered = correct = 0
    squared_errors = []
    for identifier in sorted(refs):
        pred = preds[identifier]
        if pred["answer"] is None:
            continue
        answered += 1
        success = int(pred["answer"] == refs[identifier]["answer"])
        correct += success
        squared_errors.append((pred["confidence"] - success) ** 2)
    total = len(refs)
    return {
        "schema_version": 1,
        "method": "exact-string-v1",
        "reference_sha256": ref_hash,
        "prediction_sha256": pred_hash,
        "total": total,
        "answered": answered,
        "abstained": total - answered,
        "correct": correct,
        "coverage": answered / total,
        "accuracy_all": correct / total,
        "accuracy_answered": correct / answered if answered else None,
        "brier_answered": math.fsum(squared_errors) / answered if answered else None,
    }
