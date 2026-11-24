"""Revalidate both source runs before comparing identical frozen tasks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from apps.evidence_report.renderer import _publish
from apps.pilot_verification.runner import MAX_RESULTS_BYTES, verify_pilot

STATUSES = ("verified", "contradicted", "abstained", "failed", "not_executed")


def compare_pilots(
    before: str | Path, after: str | Path, manifest: str | Path, output: str | Path
) -> dict[str, Any]:
    """Compare software outcomes, not model accuracy or statistical significance.

    Inputs and directories must be trusted and frozen. Raw answers, reference
    labels, source paths and error messages are excluded from the published JSON.
    """
    target = Path(output)
    if target.exists() or target.is_symlink():
        raise FileExistsError("comparison output already exists")
    with tempfile.TemporaryDirectory(
        prefix=".pilot-compare-", dir=target.parent
    ) as tmp:
        summaries = []
        results = []
        for index, source in enumerate((before, after)):
            directory = Path(tmp) / str(index)
            summaries.append(verify_pilot(source, manifest, directory))
            results.append(
                [
                    json.loads(line)
                    for line in (directory / "results.jsonl").read_text().splitlines()
                ]
            )
    if summaries[0]["manifest_sha256"] != summaries[1]["manifest_sha256"]:
        raise ValueError("manifest changed between source checks")
    first = {row["id"]: row for row in results[0]}
    second = {row["id"]: row for row in results[1]}
    if set(first) != set(second):
        raise ValueError("source task sets differ")
    transitions = {a: dict.fromkeys(STATUSES, 0) for a in STATUSES}
    pairs = []
    for identifier in sorted(first):
        left, right = first[identifier], second[identifier]
        if (left["image_sha256"], left["question"]) != (
            right["image_sha256"],
            right["question"],
        ):
            raise ValueError("source task image or question changed")
        transitions[left["status"]][right["status"]] += 1
        pairs.append(
            {
                "id": identifier,
                "image_sha256": left["image_sha256"],
                "before_status": left["status"],
                "after_status": right["status"],
                "normalized_answer_changed": left["normalized_answer"]
                != right["normalized_answer"],
                "reason_changed": left["reason"] != right["reason"],
            }
        )
    report = {
        "schema_version": 1,
        "kind": "paired-offline-pilot-comparison",
        "cases": len(pairs),
        "manifest_sha256": summaries[0]["manifest_sha256"],
        "before": {
            key: summaries[0][key]
            for key in (
                "source_declared_adapter_mode",
                "source_run_kind",
                "source_results_sha256",
                "counts",
            )
        },
        "after": {
            key: summaries[1][key]
            for key in (
                "source_declared_adapter_mode",
                "source_run_kind",
                "source_results_sha256",
                "counts",
            )
        },
        "source_execution_verified": False,
        "performs_model_inference": False,
        "transitions": transitions,
        "pairs": pairs,
    }
    payload = (
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    if len(payload) > MAX_RESULTS_BYTES:
        raise ValueError("comparison report exceeds 2 MiB")
    _publish(target, payload)
    return report
