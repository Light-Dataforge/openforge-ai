"""Bounded, script-free local HTML reports; never model or benchmark results."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from apps.baseline.runner import load_cases
from apps.verification_demo.runner import claim_for
from core.verification.claims import verify_claim

MAX_RESULTS = 2 * 1024 * 1024
MAX_REPORT = 4 * 1024 * 1024
STATUSES = ("verified", "contradicted", "abstained", "error")
ROW_FIELDS = {
    "candidate",
    "candidate_source",
    "claim",
    "claimed",
    "error",
    "evidence",
    "expected",
    "id",
    "image_sha256",
    "question",
    "reason",
    "status",
}


def _read(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("report input must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
    finally:
        os.close(fd)
    if len(raw) > limit:
        raise ValueError("report input exceeds its byte limit")
    return raw


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
        raise ValueError("JSON nesting is too deep") from exc


def _publish(path: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".evidence-report-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def build_report(run_dir: str | Path, output: str | Path) -> dict[str, Any]:
    """Recompute every non-error claim against its bytes before exporting.

    Inputs and parent directories must be trusted and frozen. Atomic final-name
    publication refuses overwrite; interruption can leave private staging files.
    A post-link sync error can leave a complete valid report, never a partial one.
    """
    root = Path(run_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("run directory must be a trusted real directory")
    destination = Path(output)
    if destination.parent.resolve() == root.resolve() and destination.name in {
        "summary.json",
        "results.jsonl",
    }:
        raise ValueError("report output overlaps an input")
    summary = _json(_read(root / "summary.json", 32768))
    if (
        not isinstance(summary, dict)
        or summary.get("kind") != "synthetic-pixel-verification-demo"
        or summary.get("model_inference_executed") is not False
        or summary.get("benchmark_result") is not False
    ):
        raise ValueError("only synthetic pixel-demo summaries are supported")
    if type(summary.get("schema_version")) is not int or summary["schema_version"] != 1:
        raise ValueError("unsupported summary schema")
    declared_counts = summary.get("counts")
    if (
        not isinstance(declared_counts, dict)
        or set(declared_counts) != set(STATUSES)
        or any(
            type(value) is not int or value < 0 for value in declared_counts.values()
        )
    ):
        raise ValueError("invalid declared status counts")

    raw = _read(root / "results.jsonl", MAX_RESULTS)
    results_hash = hashlib.sha256(raw).hexdigest()
    if summary.get("results_sha256") != results_hash:
        raise ValueError("result hash differs from summary")
    cases, manifest_hash = load_cases(root / "fixtures" / "manifest.jsonl")
    if summary.get("manifest_sha256") != manifest_hash or summary.get("cases") != len(
        cases
    ):
        raise ValueError("fixture manifest differs from summary")
    if sum(len(case.image_bytes) for case in cases) > MAX_RESULTS:
        raise ValueError("embedded images exceed report budget")
    by_id = {case.identifier: case for case in cases}
    lines = raw.decode("utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    rows = [_json(line.encode("utf-8")) for line in lines]
    if not 1 <= len(rows) <= 40 or summary.get("assertions") != len(rows):
        raise ValueError("invalid assertion count")
    counts = dict.fromkeys(STATUSES, 0)
    seen: set[tuple[str, str]] = set()
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in by_id}
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise ValueError("invalid assertion record fields")
        identifier, source, status = row["id"], row["candidate_source"], row["status"]
        if (
            not isinstance(identifier, str)
            or identifier not in by_id
            or source not in ("fixture_candidate", "deliberately_wrong_candidate")
            or not isinstance(status, str)
            or status not in STATUSES
        ):
            raise ValueError("invalid assertion identity or status")
        key = (identifier, source)
        if key in seen:
            raise ValueError("duplicate assertion")
        seen.add(key)
        case = by_id[identifier]
        if row["image_sha256"] != case.image_sha256 or row["question"] != case.question:
            raise ValueError("assertion source does not match frozen fixture")
        if status != "error":
            if (
                row["error"] is not None
                or not isinstance(row["claim"], dict)
                or row["claim"] != claim_for(case.question, row["candidate"])
            ):
                raise ValueError("inconsistent assertion")
            verified = verify_claim(case.image_bytes, row["claim"])
            if any(row[field] != value for field, value in verified.items()):
                raise ValueError("assertion does not match recomputed pixel evidence")
        elif not isinstance(row["error"], dict):
            raise ValueError("error record requires details")
        counts[status] += 1
        grouped[identifier].append(row)
    if (
        any(len(group) != 2 for group in grouped.values())
        or summary.get("counts") != counts
    ):
        raise ValueError("incomplete or inconsistent accounting")
    escape = html.escape
    cards = []
    for case in cases:
        image = base64.b64encode(case.image_bytes).decode("ascii")
        assertions = []
        for row in grouped[case.identifier]:
            evidence = escape(json.dumps(row["evidence"], sort_keys=True, indent=2))
            assertions.append(
                f'<section><span class="badge {row["status"]}">{escape(row["status"])}</span><p>Claim: <strong>{escape(str(row["candidate"]))}</strong> · Pixel result: <strong>{escape(str(row["expected"]))}</strong></p><details><summary>Inspect pixel evidence</summary><pre>{evidence}</pre></details></section>'  # noqa: E501
            )
        cards.append(
            f'<article><img alt="Synthetic geometric test scene" src="data:image/png;base64,{image}"><h2>{escape(case.question)}</h2>{"".join(assertions)}<details><summary>Image SHA-256</summary><code>{case.image_sha256}</code></details></article>'  # noqa: E501
        )
    style = """body{margin:0;background:#f4f6f8;color:#18242c;font:16px system-ui,sans-serif}header{background:#143b43;color:white;padding:32px}main{padding:24px;max-width:1200px;margin:auto}.metrics{display:flex;gap:24px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}article{background:white;padding:20px;border:1px solid #dce3e7;border-radius:12px}img{width:256px;max-width:100%;image-rendering:pixelated}h2{font-size:18px}section{border-top:1px solid #ddd;padding:14px 0}.badge{padding:4px 9px;border-radius:6px;font-weight:700}.verified{background:#d4eddf}.contradicted{background:#ffe0db}.abstained{background:#fff0c2}.error{background:#eee}pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}details{margin:10px 0}footer{padding:24px;font-size:13px}"""  # noqa: E501
    metrics = "".join(
        f"<p><strong>{counts[key]}</strong> {key}</p>" for key in STATUSES
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><title>OpenForge pixel evidence</title><style>{style}</style></head><body><header><h1>Pixel verification evidence</h1><p>Original synthetic scenes · deterministic geometry · no model inference</p><div class="metrics">{metrics}</div></header><main><p>Every non-error decision below was recomputed from the image bytes before export. These are conformance examples, not benchmark results or general image understanding.</p><div class="grid">{"".join(cards)}</div></main><footer>Results SHA-256: <code>{results_hash}</code><p>Offline, read-only report. No scripts, network requests, model calls or calibrated confidence.</p></footer></body></html>"""  # noqa: E501
    payload = document.encode("utf-8")
    if len(payload) > MAX_REPORT:
        raise ValueError("HTML report exceeds 4 MiB")
    _publish(destination, payload)
    return {
        "schema_version": 1,
        "cases": len(cases),
        "assertions": len(rows),
        "counts": counts,
        "source_results_sha256": results_hash,
        "report_sha256": hashlib.sha256(payload).hexdigest(),
        "model_inference_executed": False,
    }
