"""Render revalidated saved answers without running a model or external content."""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from typing import Any

from apps.evidence_report.renderer import MAX_REPORT, _publish
from apps.pilot_verification.runner import verify_pilot


def _escape(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=True, sort_keys=True))


def build_report(
    run_dir: str | Path, manifest: str | Path, output: str | Path
) -> dict[str, Any]:
    """Recompute results from frozen trusted inputs; publish one no-clobber HTML file.

    This exports raw answers and task IDs; review their contents before sharing.
    Source failure messages, source paths and reference labels are not exported.
    """
    target = Path(output)
    if target.exists() or target.is_symlink():
        raise FileExistsError("report output already exists")
    with tempfile.TemporaryDirectory(prefix=".pilot-report-", dir=target.parent) as tmp:
        verified = Path(tmp) / "verified"
        summary = verify_pilot(run_dir, manifest, verified)
        rows = [
            json.loads(line)
            for line in (verified / "results.jsonl").read_text().splitlines()
        ]
    cards = []
    for row in rows:
        cards.append(
            "<article><h2>Task " + _escape(row["id"]) + "</h2>"
            "<dl><dt>Status</dt><dd>" + _escape(row["status"]) + "</dd>"
            "<dt>Saved answer</dt><dd><pre>"
            + _escape(row["raw_answer"])
            + "</pre></dd>"
            "<dt>Normalized answer</dt><dd>"
            + _escape(row["normalized_answer"])
            + "</dd>"
            "<dt>Pixel-derived expected value</dt><dd>"
            + _escape(row["expected"])
            + "</dd>"
            "<dt>Reason</dt><dd>" + _escape(row["reason"]) + "</dd>"
            "<dt>Source error stage/type</dt><dd>"
            + _escape(row["source_error"])
            + "</dd>"
            "<dt>Image SHA256</dt><dd>" + _escape(row["image_sha256"]) + "</dd>"
            "<dt>Pixel evidence</dt><dd><pre>"
            + _escape(row["evidence"])
            + "</pre></dd>"
            "</dl></article>"
        )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>Saved pilot verification</title><style>"
        "body{font:16px system-ui;max-width:980px;margin:2rem auto;padding:0 1rem;"
        "color:#172235;background:#f5f7fb}article{background:white;padding:1rem;"
        "margin:1rem 0;border:1px solid #ccd5e2;border-radius:8px}"
        "dt{font-weight:650;margin-top:.7rem}dd{margin:.2rem 0;overflow-wrap:anywhere}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}h1{line-height:1.2}</style>"
        "<h1>Saved pilot verification</h1>"
        "<p>Offline pixel checks of supported synthetic-image claims. "
        "This report performs no model inference and does not establish model accuracy "
        "or authenticate the source runtime. Unsupported answers abstain.</p>"
        "<p>Source adapter declaration: "
        + _escape(summary["source_declared_adapter_mode"])
        + ". Source run kind: "
        + _escape(summary["source_run_kind"])
        + ".</p>"
        "<h2>Complete task accounting</h2><pre>" + _escape(summary["counts"]) + "</pre>"
        "<p>Normalization: "
        + _escape(summary["normalization"])
        + "</p>"
        + "".join(cards)
        + "<h2>Reproduction digests</h2><pre>"
        + _escape(
            {
                k: summary[k]
                for k in ("manifest_sha256", "source_results_sha256", "results_sha256")
            }
        )
        + "</pre></html>"
    ).encode("utf-8")
    if len(document) > MAX_REPORT:
        raise ValueError("report exceeds 4 MiB")
    _publish(target, document)
    return summary
