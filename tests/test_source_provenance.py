import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from core.evaluation.provenance import SOURCE_FILES, capture_source
from core.multimodal.fixtures import generate_fixtures


class SourceInventoryTests(unittest.TestCase):
    def test_real_inventory_is_deterministic_and_independently_hashable(self):
        first = capture_source()
        self.assertEqual(first, capture_source())
        self.assertFalse(first["execution_verified"])
        encoded = json.dumps(
            first["files"], sort_keys=True, separators=(",", ":")
        ).encode()
        self.assertEqual(first["inventory_sha256"], hashlib.sha256(encoded).hexdigest())
        for row in first["files"]:
            raw = Path(row["path"]).read_bytes()
            self.assertEqual(row["bytes"], len(raw))
            self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())

    def make_source(self, root):
        for name in SOURCE_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic source")

    def test_change_changes_digest_and_does_not_expose_absolute_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)
            original = capture_source(root)
            (root / SOURCE_FILES[0]).write_bytes(b"changed")
            changed = capture_source(root)
            self.assertNotEqual(
                original["inventory_sha256"], changed["inventory_sha256"]
            )
            self.assertNotIn(tmp, json.dumps(changed))

    def test_missing_symlink_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(OSError):
                capture_source(root)
            self.make_source(root)
            first = root / SOURCE_FILES[0]
            first.unlink()
            first.symlink_to(root / SOURCE_FILES[1])
            with self.assertRaises(OSError):
                capture_source(root)
            first.unlink()
            first.write_bytes(b"large")
            with patch("core.evaluation.provenance.MAX_SOURCE_BYTES", 2):
                with self.assertRaises(ValueError):
                    capture_source(root)

    def test_dry_run_records_same_receipt_in_request_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = generate_fixtures(root / "fixtures")
            summary = run_pilot(manifest, root / "run", dry_run=True)
            request = json.loads((root / "run/request.json").read_text())
            self.assertEqual(request["source_inventory"], summary["source_inventory"])
            self.assertEqual(summary["source_inventory"], capture_source())

    def test_inventory_failure_prevents_run_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = generate_fixtures(root / "fixtures")
            with patch(
                "apps.baseline.runner.capture_source",
                side_effect=ValueError("bad source"),
            ):
                with self.assertRaises(ValueError):
                    run_pilot(manifest, root / "run", dry_run=True)
            self.assertFalse((root / "run").exists())
