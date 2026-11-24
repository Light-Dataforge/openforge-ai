import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from apps.pilot_report.renderer import build_report
from core.multimodal.fixtures import generate_fixtures


class Answer:
    def answer(self, image_bytes, prompt, *, max_new_tokens=64):
        return '</pre><script>alert("test")</script>'


class PilotReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = generate_fixtures(self.root / "fixtures")
        self.run = self.root / "run"
        run_pilot(self.manifest, self.run, adapter=Answer())
        self.output = self.root / "report.html"

    def test_rechecks_answers_escapes_active_content_and_publishes_private_file(self):
        summary = build_report(self.run, self.manifest, self.output)
        text = self.output.read_text()
        self.assertEqual(summary["counts"]["abstained"], 6)
        self.assertEqual(text.count("<article>"), 6)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("default-src 'none'", text)
        self.assertNotIn(str(self.root), text)
        self.assertFalse(summary["performs_model_inference"])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(list(self.root.glob(".pilot-report-*")), [])

    def test_hash_tampering_does_not_publish_or_leave_staging(self):
        with (self.run / "results.jsonl").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaises(ValueError):
            build_report(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".pilot-report-*")), [])

    def test_source_failure_message_is_not_exported(self):
        class Failure:
            def answer(self, image_bytes, prompt, *, max_new_tokens=64):
                raise RuntimeError("private-error-marker")

        failed = self.root / "failed"
        run_pilot(self.manifest, failed, adapter=Failure())
        result = build_report(failed, self.manifest, self.output)
        self.assertEqual(result["counts"]["failed"], 6)
        self.assertNotIn("private-error-marker", self.output.read_text())
        self.assertIn("RuntimeError", self.output.read_text())

    def test_dry_run_preserves_all_six_unexecuted_tasks(self):
        dry = self.root / "dry"
        run_pilot(self.manifest, dry, dry_run=True)
        result = build_report(dry, self.manifest, self.output)
        self.assertEqual(result["counts"]["not_executed"], 6)
        self.assertIn("dry-run", self.output.read_text())

    def test_refuses_existing_file_symlink_and_racing_destination(self):
        self.output.write_text("keep")
        with self.assertRaises(FileExistsError):
            build_report(self.run, self.manifest, self.output)
        self.output.unlink()
        self.output.symlink_to(self.root / "missing")
        with self.assertRaises(FileExistsError):
            build_report(self.run, self.manifest, self.output)
        self.output.unlink()
        real_link = os.link

        def racing_link(source, target, **kwargs):
            Path(target).write_text("racer")
            return real_link(source, target, **kwargs)

        with patch("apps.evidence_report.renderer.os.link", side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                build_report(self.run, self.manifest, self.output)
        self.assertEqual(self.output.read_text(), "racer")
        self.assertEqual(list(self.root.glob(".evidence-report-*")), [])

    def test_report_size_limit_aborts_without_output(self):
        with patch("apps.pilot_report.renderer.MAX_REPORT", 100):
            with self.assertRaises(ValueError):
                build_report(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_cli_success_and_failure_have_no_partial_success(self):
        args = [
            sys.executable,
            "-m",
            "apps.pilot_report",
            str(self.run),
            str(self.manifest),
            "--output",
            str(self.output),
        ]
        done = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["cases"], 6)
        conflict = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(conflict.returncode, 2)
        self.assertEqual(conflict.stdout, "")
        self.assertNotIn(str(self.root), conflict.stderr)

    def test_source_rows_remain_unchanged(self):
        before = {
            p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()
        }
        build_report(self.run, self.manifest, self.output)
        self.assertEqual(
            before,
            {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()},
        )
