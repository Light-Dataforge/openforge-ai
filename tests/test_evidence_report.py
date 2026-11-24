import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from apps.evidence_report.renderer import build_report
from apps.verification_demo.runner import run_demo


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs)["src"])
        self.scripts += tag == "script"


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "run"
        run_demo(self.run)
        self.output = self.root / "report.html"

    def rewrite(self, rows, counts=None):
        raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (self.run / "results.jsonl").write_bytes(raw)
        path = self.run / "summary.json"
        summary = json.loads(path.read_text())
        summary["results_sha256"] = hashlib.sha256(raw).hexdigest()
        if counts is not None:
            summary["counts"] = counts
        path.write_text(json.dumps(summary))

    def rows(self):
        return [
            json.loads(line)
            for line in (self.run / "results.jsonl").read_text().splitlines()
        ]

    def test_export_embeds_real_images_and_recomputed_counts(self):
        result = build_report(self.run, self.output)
        parser = Parser()
        text = self.output.read_text()
        parser.feed(text)
        self.assertEqual(len(parser.images), 6)
        self.assertTrue(
            all(src.startswith("data:image/png;base64,") for src in parser.images)
        )
        self.assertEqual(parser.scripts, 0)
        self.assertEqual(
            result["counts"],
            {"verified": 6, "contradicted": 6, "abstained": 0, "error": 0},
        )
        self.assertEqual(
            result["report_sha256"],
            hashlib.sha256(self.output.read_bytes()).hexdigest(),
        )
        self.assertNotIn(str(self.root), text)
        self.assertIn("Content-Security-Policy", text)

    def test_updated_checksum_does_not_hide_false_evidence(self):
        rows = self.rows()
        rows[0]["status"] = "contradicted"
        self.rewrite(rows)
        with self.assertRaisesRegex(ValueError, "recomputed pixel"):
            build_report(self.run, self.output)
        self.assertFalse(self.output.exists())

    def test_malformed_claim_fails_cleanly(self):
        rows = self.rows()
        rows[0]["claim"] = None
        self.rewrite(rows)
        with self.assertRaises(ValueError):
            build_report(self.run, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_and_incomplete_accounting_rejected(self):
        rows = self.rows()
        rows[-1] = rows[0]
        self.rewrite(rows)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_report(self.run, self.output)

    def test_script_like_error_data_is_escaped(self):
        rows = self.rows()
        rows[0].update(
            status="error",
            candidate="<script>alert(1)</script>",
            expected=None,
            evidence={"text": "<img src=x onerror=alert(1)>"},
            error={"type": "SyntheticError"},
            claim=None,
        )
        self.rewrite(
            rows, {"verified": 5, "contradicted": 6, "abstained": 0, "error": 1}
        )
        build_report(self.run, self.output)
        text = self.output.read_text()
        parser = Parser()
        parser.feed(text)
        self.assertEqual(parser.scripts, 0)
        self.assertEqual(len(parser.images), 6)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("&lt;img", text)

    def test_hash_mismatch_and_nonfinite_json_rejected(self):
        path = self.run / "results.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            build_report(self.run, self.output)
        (self.run / "summary.json").write_text('{"x":NaN}')
        with self.assertRaises(ValueError):
            build_report(self.run, self.output)

    def test_existing_output_and_symlink_not_replaced(self):
        self.output.write_text("preserve")
        with self.assertRaises(FileExistsError):
            build_report(self.run, self.output)
        self.assertEqual(self.output.read_text(), "preserve")
        link = self.root / "link.html"
        link.symlink_to(self.output)
        with self.assertRaises(FileExistsError):
            build_report(self.run, link)
        self.assertEqual(self.output.read_text(), "preserve")

    def test_symlink_input_and_output_size_limit(self):
        source = self.run / "summary.json"
        actual = self.run / "original.json"
        source.rename(actual)
        source.symlink_to(actual)
        with self.assertRaises(OSError):
            build_report(self.run, self.output)
        source.unlink()
        actual.rename(source)
        with (
            patch("apps.evidence_report.renderer.MAX_REPORT", 10),
            self.assertRaises(ValueError),
        ):
            build_report(self.run, self.output)
        self.assertFalse(self.output.exists())

    def test_summary_version_and_counter_types(self):
        path = self.run / "summary.json"
        original = json.loads(path.read_text())
        changed = dict(original, schema_version=2)
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            build_report(self.run, self.output)
        original["counts"]["error"] = False
        path.write_text(json.dumps(original))
        with self.assertRaises(ValueError):
            build_report(self.run, self.output)
        self.assertFalse(self.output.exists())

    def test_cli_success_and_failure_no_partial_stdout(self):
        command = [
            sys.executable,
            "-m",
            "apps.evidence_report",
            str(self.run),
            "--output",
            str(self.output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["assertions"], 12)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("report export failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
