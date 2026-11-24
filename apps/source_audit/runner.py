"""Strict receipt checks and observed-byte comparison, without execution claims."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from apps.baseline.runner import _bounded_regular
from apps.pilot_verification.runner import _json
from core.evaluation.provenance import MAX_SOURCE_BYTES, SOURCE_FILES, capture_source


def validate_inventory(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {"schema_version", "kind", "execution_verified", "files", "inventory_sha256"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["kind"] != "observed-source-inventory"
        or value["execution_verified"] is not False
        or not isinstance(value["files"], list)
        or len(value["files"]) != len(SOURCE_FILES)
    ):
        raise ValueError("invalid source inventory schema")
    for name, row in zip(SOURCE_FILES, value["files"], strict=True):
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "bytes", "sha256"}
            or row["path"] != name
            or type(row["bytes"]) is not int
            or not 0 <= row["bytes"] <= MAX_SOURCE_BYTES
            or not isinstance(row["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        ):
            raise ValueError("invalid source file declaration")
    encoded = json.dumps(value["files"], sort_keys=True, separators=(",", ":")).encode()
    if value["inventory_sha256"] != hashlib.sha256(encoded).hexdigest():
        raise ValueError("source inventory digest mismatch")
    return value


def audit_source(
    run_dir: str | Path, *, source_root: Path | None = None
) -> dict[str, Any]:
    """Check receipt structure and compare declared hashes with current observations.

    This does not validate run results, manifests, model weights or execution.
    """
    root = Path(run_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("run source must be a trusted real directory")
    info = _json(_bounded_regular(root / "run.json", 65536))
    if (
        not isinstance(info, dict)
        or type(info.get("schema_version")) is not int
        or info["schema_version"] != 1
    ):
        raise ValueError("unsupported run metadata schema")
    if "source_inventory" not in info:
        return {
            "schema_version": 1,
            "status": "unavailable",
            "execution_verified": False,
            "reason": "source_inventory_not_recorded",
            "changed_files": [],
        }
    recorded = validate_inventory(info["source_inventory"])
    current = capture_source(source_root)
    changed = [
        left["path"]
        for left, right in zip(recorded["files"], current["files"], strict=True)
        if left != right
    ]
    return {
        "schema_version": 1,
        "kind": "observed-source-comparison",
        "status": "different" if changed else "matches",
        "execution_verified": False,
        "recorded_inventory_sha256": recorded["inventory_sha256"],
        "current_inventory_sha256": current["inventory_sha256"],
        "changed_files": changed,
    }
