"""Paired exact-answer accounting and seeded descriptive bootstrap intervals."""

from __future__ import annotations

import platform
import random
from pathlib import Path
from typing import Any

from .metrics import _load

STATUSES = ("correct", "incorrect", "abstained")
MAX_DRAWS = 2_000_000


def _status(reference: dict[str, Any], prediction: dict[str, Any]) -> str:
    if prediction["answer"] is None:
        return "abstained"
    return "correct" if prediction["answer"] == reference["answer"] else "incorrect"


def _summary(counts: dict[str, int], total: int) -> dict[str, Any]:
    answered = total - counts["abstained"]
    return {
        "total": total,
        "answered": answered,
        "abstained": counts["abstained"],
        "correct": counts["correct"],
        "coverage": answered / total,
        "accuracy_all": counts["correct"] / total,
    }


def compare_predictions(
    references: str | Path,
    before: str | Path,
    after: str | Path,
    *,
    seed: int,
    replicates: int = 1000,
) -> dict[str, Any]:
    """Resample whole task pairs; abstentions count as not correct.

    The empirical percentile interval is descriptive under task-resampling
    assumptions, not a causal or significance claim. Inputs/host are trusted and
    frozen. Python implementation/version and RNG algorithm are recorded because
    seeded randrange behavior is not promised identical across Python versions.
    """
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an unsigned 32-bit integer")
    if type(replicates) is not int or not 100 <= replicates <= 5000:
        raise ValueError("replicates must be an integer from 100 to 5000")
    refs, reference_hash = _load(references, prediction=False)
    first, before_hash = _load(before, prediction=True)
    second, after_hash = _load(after, prediction=True)
    if refs.keys() != first.keys() or refs.keys() != second.keys():
        raise ValueError("all reference and prediction IDs must match exactly")
    total = len(refs)
    if total * replicates > MAX_DRAWS:
        raise ValueError("paired bootstrap exceeds 2000000 task draws")
    transitions = {status: dict.fromkeys(STATUSES, 0) for status in STATUSES}
    first_counts = dict.fromkeys(STATUSES, 0)
    second_counts = dict.fromkeys(STATUSES, 0)
    deltas = []
    for identifier in sorted(refs):
        left = _status(refs[identifier], first[identifier])
        right = _status(refs[identifier], second[identifier])
        transitions[left][right] += 1
        first_counts[left] += 1
        second_counts[right] += 1
        deltas.append(int(right == "correct") - int(left == "correct"))
    rng = random.Random(seed)
    means = [
        sum(deltas[rng.randrange(total)] for _ in range(total)) / total
        for _ in range(replicates)
    ]
    means.sort()
    lower_index = (replicates - 1) * 25 // 1000
    upper_index = (replicates - 1) * 975 // 1000
    return {
        "schema_version": 1,
        "method": "paired-exact-bootstrap-v1",
        "model_execution_verified": False,
        "reference_sha256": reference_hash,
        "before_prediction_sha256": before_hash,
        "after_prediction_sha256": after_hash,
        "total": total,
        "before": _summary(first_counts, total),
        "after": _summary(second_counts, total),
        "transitions": transitions,
        "accuracy_all_delta": sum(deltas) / total,
        "bootstrap": {
            "method": "paired-task-empirical-percentile-v1",
            "seed": seed,
            "replicates": replicates,
            "task_draws": total * replicates,
            "level": 0.95,
            "lower_index": lower_index,
            "upper_index": upper_index,
            "lower": means[lower_index],
            "upper": means[upper_index],
            "task_order": "sorted-reference-id",
            "rng": "random.Random.randrange",
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        },
    }
