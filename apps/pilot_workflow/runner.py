"""Compose bounded local stages while retaining source failures."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from apps.baseline.runner import Adapter, run_pilot
from apps.evidence_report.renderer import _publish
from apps.pilot_report.renderer import build_report
from apps.pilot_verification.runner import verify_pilot
from apps.source_audit.runner import audit_source
from core.multimodal.fixtures import generate_fixtures


def run_workflow(
    output: str | Path,
    *,
    live: bool = False,
    allow_download: bool = False,
    device: str = "cpu",
    max_new_tokens: int = 64,
    adapter: Adapter | None = None,
) -> dict[str, Any]:
    """Run original synthetic cases in a new private directory, dry-run by default.

    Live/injected source failures are retained and yield complete-with-failures.
    Infrastructure errors raise and can leave a partial newly-created directory;
    existing outputs are never overwritten. Inputs/host directories are trusted.
    No runtime installation, GPU allocation, training or paid fallback is performed.
    """
    if type(live) is not bool or type(allow_download) is not bool:
        raise ValueError("workflow flags must be booleans")
    if device not in ("cpu", "cuda") or not isinstance(device, str):
        raise ValueError("device must be cpu or cuda")
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 128:
        raise ValueError("token limit must be an integer from 1 to 128")
    if not live and (allow_download or device != "cpu" or adapter is not None):
        raise ValueError("model options require explicit live mode")
    if adapter is not None and allow_download:
        raise ValueError("injected adapters cannot request model downloads")
    root = Path(output)
    root.mkdir(mode=0o700, exist_ok=False)
    os.chmod(root, 0o700)
    manifest = generate_fixtures(root / "fixtures")
    source = run_pilot(
        manifest,
        root / "source",
        adapter=adapter,
        dry_run=not live,
        allow_download=allow_download,
        device=device,
        max_new_tokens=max_new_tokens,
    )
    verified = verify_pilot(root / "source", manifest, root / "verification")
    rendered = build_report(root / "source", manifest, root / "report.html")
    if rendered != verified:
        raise ValueError("frozen source changed between verification and reporting")
    audited = audit_source(root / "source")
    if audited["status"] != "matches":
        raise ValueError("observed source files changed during workflow")
    _publish(
        root / "source-audit.json",
        (json.dumps(audited, sort_keys=True, indent=2) + "\n").encode(),
    )
    summary = {
        "schema_version": 1,
        "kind": "local-synthetic-pilot-workflow",
        "mode": "live-requested" if live else "dry-run",
        "source_adapter_mode": source["adapter_mode"],
        "status": "complete-with-source-failures" if source["failed"] else "complete",
        "cases": source["cases"],
        "source_counts": {
            key: source[key] for key in ("answered", "failed", "not_executed")
        },
        "verification_counts": verified["counts"],
        "model_execution_verified": False,
        "manifest_sha256": verified["manifest_sha256"],
        "source_results_sha256": verified["source_results_sha256"],
        "verification_results_sha256": verified["results_sha256"],
        "observed_source_inventory_sha256": audited["current_inventory_sha256"],
        "artifacts": {
            "source": "source",
            "manifest": "fixtures/manifest.jsonl",
            "verification": "verification",
            "report": "report.html",
            "source_audit": "source-audit.json",
        },
    }
    _publish(
        root / "workflow.json",
        (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode(),
    )
    return summary
