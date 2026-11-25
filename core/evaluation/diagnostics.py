"""Descriptive exact-answer confidence diagnostics; not calibration proof."""

from __future__ import annotations

import math
from bisect import bisect_right
from itertools import groupby
from pathlib import Path
from typing import Any

from .metrics import _load


def diagnose(
    references: str | Path, predictions: str | Path, *, bins: int = 10
) -> dict[str, Any]:
    """Describe answered records; coverage always uses every reference as denominator.

    Confidence means probability of exact string correctness. Whole confidence-tie
    groups enter the selective curve together. No interpolation or AUC is computed.
    Inputs and host directories must be trusted and frozen between file reads.
    """
    if type(bins) is not int or not 2 <= bins <= 50:
        raise ValueError("bins must be an integer from 2 to 50")
    refs, reference_hash = _load(references, prediction=False)
    preds, prediction_hash = _load(predictions, prediction=True)
    if refs.keys() != preds.keys():
        raise ValueError("reference and prediction IDs must match exactly")
    answered: list[tuple[float, int]] = []
    for identifier in sorted(refs):
        pred = preds[identifier]
        if pred["answer"] is not None:
            answered.append(
                (
                    float(pred["confidence"]),
                    int(pred["answer"] == refs[identifier]["answer"]),
                )
            )
    edges = [index / bins for index in range(bins + 1)]
    members: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for confidence, correct in answered:
        index = min(bisect_right(edges, confidence) - 1, bins - 1)
        members[index].append((confidence, correct))
    calibration = []
    weighted_gaps = []
    for index, rows in enumerate(members):
        count = len(rows)
        mean_confidence = math.fsum(row[0] for row in rows) / count if count else None
        accuracy = sum(row[1] for row in rows) / count if count else None
        gap = (
            abs(mean_confidence - accuracy)
            if mean_confidence is not None and accuracy is not None
            else None
        )
        if gap is not None:
            weighted_gaps.append(count * gap)
        calibration.append(
            {
                "lower": edges[index],
                "upper": edges[index + 1],
                "upper_inclusive": index == bins - 1,
                "count": count,
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "gap": gap,
            }
        )
    total = len(refs)
    retained = correct_count = 0
    curve = []
    for threshold, group in groupby(
        sorted(answered, key=lambda row: row[0], reverse=True), key=lambda row: row[0]
    ):
        rows = list(group)
        retained += len(rows)
        correct_count += sum(row[1] for row in rows)
        curve.append(
            {
                "threshold": threshold,
                "retained": retained,
                "correct": correct_count,
                "coverage": retained / total,
                "risk": (retained - correct_count) / retained,
            }
        )
    return {
        "schema_version": 1,
        "method": "exact-confidence-diagnostics-v1",
        "model_execution_verified": False,
        "reference_sha256": reference_hash,
        "prediction_sha256": prediction_hash,
        "total": total,
        "answered": len(answered),
        "abstained": total - len(answered),
        "coverage": len(answered) / total,
        "bin_count": bins,
        "bins": calibration,
        "ece_answered": math.fsum(weighted_gaps) / len(answered) if answered else None,
        "risk_coverage": curve,
    }
