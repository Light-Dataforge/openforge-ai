import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from apps.source_audit.runner import audit_source, validate_inventory
from core.evaluation.provenance import SOURCE_FILES, capture_source
from core.multimodal.fixtures import generate_fixtures


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = generate_fixtures(self.root / "fixtures")
        self.run = self.root / "run"
        run_pilot(self.manifest, self.run, dry_run=True)

    def test_real_receipt_matches_and_sources_unchanged(self):
        before = (self.run / "run.json").read_bytes()
        result = audit_source(self.run)
        self.assertEqual(result["status"], "matches")
        self.assertEqual(result["changed_files"], [])
        self.assertFalse(result["execution_verified"])
        self.assertEqual(before, (self.run / "run.json").read_bytes())
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_different_observed_file_is_reported_without_content(self):
        current = copy.deepcopy(capture_source())
        current["files"][0]["sha256"] = "f" * 64
        encoded = json.dumps(
            current["files"], sort_keys=True, separators=(",", ":")
        ).encode()
        current["inventory_sha256"] = hashlib.sha256(encoded).hexdigest()
        with patch("apps.source_audit.runner.capture_source", return_value=current):
            result = audit_source(self.run)
        self.assertEqual(result["status"], "different")
        self.assertEqual(result["changed_files"], [SOURCE_FILES[0]])

    def test_old_receipt_reports_unavailable_without_source_read(self):
        (self.run / "run.json").write_text('{"schema_version":1}')
        with patch(
            "apps.source_audit.runner.capture_source",
            side_effect=AssertionError("not called"),
        ):
            self.assertEqual(audit_source(self.run)["status"], "unavailable")

    def test_strict_shape_types_order_hash_and_attestation_rejected(self):
        base = capture_source()
        for mutate in [
            lambda v: v.update(schema_version=True),
            lambda v: v.update(execution_verified=True),
            lambda v: v["files"].reverse(),
            lambda v: v["files"][0].update(bytes=True),
            lambda v: v["files"][0].update(path="../secret"),
            lambda v: v["files"][0].update(sha256="INVALID"),
            lambda v: v.update(inventory_sha256="0" * 64),
        ]:
            value = copy.deepcopy(base)
            mutate(value)
            with self.assertRaises(ValueError):
                validate_inventory(value)

    def test_duplicate_json_keys_and_special_metadata_rejected(self):
        path = self.run / "run.json"
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            audit_source(self.run)
        path.unlink()
        path.symlink_to(self.manifest)
        with self.assertRaises((OSError, ValueError)):
            audit_source(self.run)

    def test_cli_exit_codes_and_redacted_invalid_input(self):
        args = [sys.executable, "-m", "apps.source_audit", str(self.run)]
        good = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        (self.run / "run.json").write_text('{"schema_version":1}')
        absent = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(absent.returncode, 1)
        (self.run / "run.json").write_text("bad")
        bad = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertNotIn(str(self.root), bad.stderr)
