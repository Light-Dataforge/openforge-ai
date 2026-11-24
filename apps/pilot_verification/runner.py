"""Revalidate source artifacts and conservatively verify supported saved answers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from apps.baseline.runner import _bounded_regular, load_cases
from apps.verification_demo.runner import claim_for
from core.verification.claims import verify_claim

MAX_RUN_BYTES = 65536
MAX_RESULTS_BYTES = 2 * 1024 * 1024
ROW_FIELDS = {
    "id",
    "image",
    "image_sha256",
    "question",
    "reference_answer",
    "answer",
    "latency_ns",
    "error",
    "status",
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
    except RecursionError as exc:
        raise ValueError("source JSON nesting is too deep") from exc


def _text(value: Any, maximum: int) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def verify_pilot(
    run_dir: str | Path, manifest: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    """No model execution or confidence estimation; sources must be frozen local files.

    The source run format and hashes are checked, not the authenticity of its
    declared runtime. Computation completes before a new output directory is made.
    Publication is not a multi-file transaction; interruptions can leave a partial
    newly-created directory. Existing output directories are never overwritten.
    """
    root = Path(run_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("source run must be a trusted real directory")
    info = _json(_bounded_regular(root / "run.json", MAX_RUN_BYTES))
    if (
        not isinstance(info, dict)
        or type(info.get("schema_version")) is not int
        or info["schema_version"] != 1
    ):
        raise ValueError("unsupported pilot run schema")
    if (
        info.get("kind") not in ("pilot", "dry-run")
        or info.get("model_execution_verified") is not False
        or info.get("adapter_mode") not in ("injected", "local-smolvlm")
    ):
        raise ValueError("unsupported pilot run declaration")
    cases, manifest_hash = load_cases(manifest)
    if (
        type(info.get("cases")) is not int
        or info["cases"] != len(cases)
        or info.get("manifest_sha256") != manifest_hash
    ):
        raise ValueError("pilot manifest mismatch")
    raw = _bounded_regular(root / "results.jsonl", MAX_RESULTS_BYTES)
    source_hash = hashlib.sha256(raw).hexdigest()
    if info.get("results_sha256") != source_hash:
        raise ValueError("pilot results hash mismatch")
    lines = raw.decode("utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) != len(cases):
        raise ValueError("pilot results must account for exactly every task")
    rows = [_json(line.encode("utf-8")) for line in lines]
    by_id = {case.identifier: case for case in cases}
    source_counts = dict.fromkeys(("answered", "failed", "not_executed"), 0)
    seen: set[str] = set()
    validated = []
    load_failures = 0
    expected_calls = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise ValueError("invalid pilot result fields")
        identifier, status = row["id"], row["status"]
        if (
            not isinstance(identifier, str)
            or identifier not in by_id
            or identifier in seen
        ):
            raise ValueError("invalid, extra or duplicate task ID")
        if not isinstance(status, str) or status not in source_counts:
            raise ValueError("unknown source task status")
        seen.add(identifier)
        case = by_id[identifier]
        if (
            row["image"],
            row["image_sha256"],
            row["question"],
            row["reference_answer"],
        ) != (case.image, case.image_sha256, case.question, case.expected_answer):
            raise ValueError("source task differs from frozen manifest")
        latency = row["latency_ns"]
        if latency is not None and (
            type(latency) is not int or not 0 <= latency <= 2**63 - 1
        ):
            raise ValueError("invalid source duration")
        if status == "answered":
            if (
                not _text(row["answer"], 16384)
                or row["error"] is not None
                or latency is None
            ):
                raise ValueError(
                    "answered source task requires answer/duration without error"
                )
        elif status == "failed":
            error = row["error"]
            if (
                row["answer"] is not None
                or not isinstance(error, dict)
                or set(error) != {"stage", "type", "message"}
            ):
                raise ValueError("invalid failed source task")
            if (
                error["stage"] not in ("model_load", "answer")
                or not _text(error["type"], 128)
                or not isinstance(error["message"], str)
                or len(error["message"]) > 1024
            ):
                raise ValueError("invalid source failure details")
            if (latency is None) != (error["stage"] == "model_load"):
                raise ValueError("source failure stage/duration mismatch")
        elif (
            row["answer"] is not None or row["error"] is not None or latency is not None
        ):
            raise ValueError("unexecuted task cannot contain execution data")
        if status == "answered" or (
            status == "failed" and row["error"]["stage"] == "answer"
        ):
            expected_calls += 1
        if status == "failed" and row["error"]["stage"] == "model_load":
            load_failures += 1
        source_counts[status] += 1
        validated.append((case, row))
    for field, amount in source_counts.items():
        if type(info.get(field)) is not int or info[field] != amount:
            raise ValueError("source counts differ from task records")
    expected_load = info["kind"] == "pilot" and info["adapter_mode"] == "local-smolvlm"
    if (
        type(info.get("answer_calls")) is not int
        or info["answer_calls"] != expected_calls
        or type(info.get("model_load_attempted")) is not bool
        or info["model_load_attempted"] != expected_load
    ):
        raise ValueError("source call/load accounting is inconsistent")
    if load_failures and (not expected_load or load_failures != len(cases)):
        raise ValueError("source model-load failure accounting is inconsistent")
    expected_status = (
        "dry-run-complete"
        if info["kind"] == "dry-run"
        else ("complete-with-failures" if source_counts["failed"] else "complete")
    )
    if (
        info.get("status") != expected_status
        or (info["kind"] == "dry-run" and source_counts["not_executed"] != len(cases))
        or (info["kind"] == "pilot" and source_counts["not_executed"])
    ):
        raise ValueError("source run lifecycle is inconsistent")
    counts = dict.fromkeys(
        ("verified", "contradicted", "abstained", "failed", "not_executed"), 0
    )
    output_rows = []
    for case, row in sorted(validated, key=lambda pair: pair[0].identifier):
        result: dict[str, Any] = {
            "id": case.identifier,
            "question": case.question,
            "image_sha256": case.image_sha256,
            "raw_answer": row["answer"],
            "normalized_answer": None,
            "status": row["status"],
            "expected": None,
            "reason": None,
            "evidence": None,
            "source_error": None,
        }
        if row["status"] == "failed":
            result["source_error"] = {
                key: row["error"][key] for key in ("stage", "type")
            }
            result["reason"] = "source_task_failed"
        elif row["status"] == "not_executed":
            result["reason"] = "source_task_not_executed"
        else:
            normalized = row["answer"].strip().lower()
            result["normalized_answer"] = normalized
            try:
                claim = claim_for(case.question, normalized)
                checked = verify_claim(case.image_bytes, claim)
            except ValueError:
                result.update(
                    status="abstained", reason="unsupported_answer_or_question"
                )
            else:
                for key in ("status", "expected", "reason", "evidence"):
                    result[key] = checked[key]
        counts[result["status"]] += 1
        output_rows.append(result)
    encoded = "".join(
        json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in output_rows
    ).encode("utf-8")
    if len(encoded) > MAX_RESULTS_BYTES:
        raise ValueError("verification output exceeds 2 MiB")
    summary = {
        "schema_version": 1,
        "kind": "offline-pilot-pixel-verification",
        "cases": len(cases),
        "counts": counts,
        "source_run_kind": info["kind"],
        "source_declared_adapter_mode": info["adapter_mode"],
        "source_execution_verified": False,
        "performs_model_inference": False,
        "normalization": "strip-and-lower-v1; no narrative or punctuation extraction",
        "source_results_sha256": source_hash,
        "manifest_sha256": manifest_hash,
        "results_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    destination = Path(output_dir)
    destination.mkdir(mode=0o700, exist_ok=False)
    os.chmod(destination, 0o700)
    for name, payload in [
        ("results.jsonl", encoded),
        (
            "summary.json",
            (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode(),
        ),
    ]:
        fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    return summary
