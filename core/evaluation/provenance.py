"""Bounded observed source inventories, never execution or model attestation."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

SOURCE_FILES = (
    "apps/baseline/runner.py",
    "core/model_adapters/smolvlm.py",
    "core/multimodal/fixtures.py",
    "requirements-vlm.txt",
)
MAX_SOURCE_BYTES = 256 * 1024


def capture_source(root: Path | None = None) -> dict[str, Any]:
    """Hash four frozen local files; no git, network or optional model imports.

    Observed bytes may differ from code already loaded by the interpreter. This
    inventories neither dependencies nor weights and cannot authenticate execution.
    The source root and directory ancestors must be trusted and stable.
    """
    source = Path(__file__).resolve().parents[2] if root is None else root
    files = []
    for name in SOURCE_FILES:
        descriptor = os.open(source / name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("source inventory requires regular files")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("source inventory file exceeds 256 KiB")
        files.append(
            {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        )
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "kind": "observed-source-inventory",
        "execution_verified": False,
        "files": files,
        "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
    }
