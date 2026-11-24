"""Deterministic assertion/evidence plumbing over original synthetic fixtures."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from apps.baseline.runner import load_cases
from core.multimodal.fixtures import generate_fixtures

Verifier = Callable[[bytes, dict[str, Any]], dict[str, Any]]

TEMPLATES: dict[str, dict[str, str]] = {
    "What color is the square? Answer with one lowercase color word.": {
        "kind": "color",
        "shape": "square",
    },
    "What color is the circle? Answer with one lowercase color word.": {
        "kind": "color",
        "shape": "circle",
    },
    "How many green squares are shown? Answer with one digit.": {
        "kind": "count",
        "color": "green",
        "shape": "square",
    },
    "How many blue circles are shown? Answer with one digit.": {
        "kind": "count",
        "color": "blue",
        "shape": "circle",
    },
    (
        "Is the red square to the left or right of the blue circle? "
        "Answer left or right."
    ): {
        "kind": "relation",
        "subject_color": "red",
        "subject_shape": "square",
        "object_color": "blue",
        "object_shape": "circle",
    },
    "Which bar is tallest? Answer with one lowercase color word.": {"kind": "tallest"},
}


def claim_for(question: str, candidate: str) -> dict[str, Any]:
    """Route only an exact supported question; metadata never selects a claim."""
    if not isinstance(question, str) or question not in TEMPLATES:
        raise ValueError("unsupported question grammar")
    if not isinstance(candidate, str) or not candidate or len(candidate) > 32:
        raise ValueError("invalid candidate")
    return dict(TEMPLATES[question], answer=candidate)


def wrong_candidate(claim: dict[str, Any]) -> str:
    """Create an explicitly synthetic counterexample, not a model-generated answer."""
    candidate = claim["answer"]
    if claim["kind"] in {"color", "tallest"}:
        return "blue" if candidate == "red" else "red"
    if claim["kind"] == "count":
        if (
            not isinstance(candidate, str)
            or not candidate.isascii()
            or not candidate.isdigit()
        ):
            raise ValueError("count candidate requires ASCII digits")
        return str(int(candidate) + 1)
    if claim["kind"] == "relation" and candidate in {"left", "right"}:
        return "right" if candidate == "left" else "left"
    raise ValueError("unsupported candidate for synthetic counterexample")


def _verify() -> Verifier:
    module = import_module("core.verification.claims")
    return cast(Verifier, module.verify_claim)


def _result(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {
        "expected",
        "claimed",
        "status",
        "reason",
        "evidence",
    }:
        raise ValueError("invalid verifier result fields")
    if not isinstance(document["status"], str) or document["status"] not in {
        "verified",
        "contradicted",
        "abstained",
    }:
        raise ValueError("invalid verifier status")
    # Only completed JSON-safe data is retained, never arbitrary Python objects.
    detached: dict[str, Any] = json.loads(json.dumps(document, allow_nan=False))
    if len(json.dumps(detached).encode("utf-8")) > 64 * 1024:
        raise ValueError("verifier evidence exceeds 64 KiB")
    return detached


def run_demo(
    output_dir: str | Path, *, verifier: Verifier | None = None
) -> dict[str, Any]:
    """Generate fixtures and verify twelve explicit synthetic answer assertions.

    No model, OCR, cloud endpoint or language reasoning inference is invoked.
    Fixture answers supply candidate inputs only, never verifier evidence.
    """
    output = Path(output_dir)
    output.mkdir(mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    manifest = generate_fixtures(output / "fixtures")
    cases, manifest_hash = load_cases(manifest)
    injected = verifier is not None
    load_error: Exception | None = None
    if verifier is None:
        try:
            verifier = _verify()
        except Exception as exc:
            load_error = exc
    counts = {"verified": 0, "contradicted": 0, "abstained": 0, "error": 0}
    assertions = 0
    results_path = output / "results.jsonl"
    with results_path.open("x", encoding="utf-8") as stream:
        os.chmod(results_path, 0o600)
        for case in cases:
            candidates: list[tuple[str, str | None]] = [
                ("fixture_candidate", case.expected_answer)
            ]
            try:
                original = claim_for(case.question, case.expected_answer)
                candidates.append(
                    ("deliberately_wrong_candidate", wrong_candidate(original))
                )
                routing_error = None
            except ValueError as exc:
                candidates.append(("deliberately_wrong_candidate", None))
                routing_error = exc
            for source, candidate in candidates:
                row: dict[str, Any] = {
                    "id": case.identifier,
                    "image_sha256": case.image_sha256,
                    "question": case.question,
                    "candidate_source": source,
                    "candidate": candidate,
                    "claim": None,
                    "status": "error",
                    "expected": None,
                    "claimed": candidate,
                    "reason": None,
                    "evidence": None,
                    "error": None,
                }
                try:
                    if routing_error is not None:
                        raise routing_error
                    assert candidate is not None
                    claim = claim_for(case.question, candidate)
                    row["claim"] = claim
                    if load_error is not None:
                        raise load_error
                    assert verifier is not None
                    result = _result(verifier(case.image_bytes, claim))
                    row.update(result)
                except Exception as exc:
                    row["error"] = {
                        "type": type(exc).__name__,
                        "message": str(exc)[:1024],
                    }
                counts[row["status"]] += 1
                assertions += 1
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
    summary: dict[str, Any] = {
        "schema_version": 1,
        "kind": "synthetic-pixel-verification-demo",
        "candidate_source": "fixture-derived synthetic assertions, not model outputs",
        "verifier_mode": "injected" if injected else "deterministic-pixel-verifier",
        "cases": len(cases),
        "assertions": assertions,
        "counts": counts,
        "manifest_sha256": manifest_hash,
        "results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "model_inference_executed": False,
        "benchmark_result": False,
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        os.chmod(output / "summary.json", 0o600)
        json.dump(summary, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return summary
