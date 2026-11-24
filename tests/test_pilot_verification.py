import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from apps.pilot_verification.runner import verify_pilot
from core.multimodal.fixtures import generate_fixtures


class ScriptedAnswers:
    """Synthetic integration inputs, not model inference."""

    def __init__(self):
        self.position = 0

    def answer(self, image_bytes, prompt, *, max_new_tokens=64):
        answers = ["blue", " BLUE ", "There are three.", None, "left", "blue"]
        answer = answers[self.position]
        self.position += 1
        if answer is None:
            raise RuntimeError("synthetic failure containing private-path-marker")
        return answer


class PilotVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = generate_fixtures(self.root / "fixtures")
        self.run = self.root / "source"
        run_pilot(self.manifest, self.run, adapter=ScriptedAnswers())
        self.output = self.root / "verified"

    def rewrite(self, rows):
        raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (self.run / "results.jsonl").write_bytes(raw)
        info_path = self.run / "run.json"
        info = json.loads(info_path.read_text())
        info["results_sha256"] = hashlib.sha256(raw).hexdigest()
        info_path.write_text(json.dumps(info))

    def rows(self):
        return [
            json.loads(line)
            for line in (self.run / "results.jsonl").read_text().splitlines()
        ]

    def test_real_pixels_verify_normalized_answers_and_preserve_failures(self):
        result = verify_pilot(self.run, self.manifest, self.output)
        self.assertEqual(
            result["counts"],
            {
                "verified": 3,
                "contradicted": 1,
                "abstained": 1,
                "failed": 1,
                "not_executed": 0,
            },
        )
        self.assertEqual(result["source_declared_adapter_mode"], "injected")
        self.assertFalse(result["source_execution_verified"])
        self.assertFalse(result["performs_model_inference"])
        text = (self.output / "results.jsonl").read_text()
        rows = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["id"] for r in rows}, {r["id"] for r in self.rows()})
        self.assertNotIn("private-path-marker", text)
        self.assertTrue(all("confidence" not in row for row in rows))
        self.assertTrue(
            any(
                row["raw_answer"] == " BLUE " and row["normalized_answer"] == "blue"
                for row in rows
            )
        )
        self.assertTrue(
            any(row["reason"] == "unsupported_answer_or_question" for row in rows)
        )

    def test_dry_run_tasks_remain_unexecuted_without_verifier_calls(self):
        source = self.root / "dry"
        run_pilot(self.manifest, source, dry_run=True)
        with patch(
            "apps.pilot_verification.runner.verify_claim",
            side_effect=AssertionError("must not verify absent answers"),
        ):
            result = verify_pilot(source, self.manifest, self.output)
        self.assertEqual(result["counts"]["not_executed"], 6)
        self.assertEqual(result["counts"]["verified"], 0)

    def test_model_load_failure_retained_without_messages(self):
        source = self.root / "load-failed"
        with patch(
            "apps.baseline.runner.import_module",
            side_effect=RuntimeError("private-path-marker"),
        ):
            run_pilot(self.manifest, source)
        result = verify_pilot(source, self.manifest, self.output)
        self.assertEqual(result["counts"]["failed"], 6)
        self.assertNotIn(
            "private-path-marker", (self.output / "results.jsonl").read_text()
        )

    def test_changed_image_or_source_bytes_abort_before_output(self):
        original = (self.run / "results.jsonl").read_bytes()
        (self.run / "results.jsonl").write_bytes(original + b" ")
        with self.assertRaises(ValueError):
            verify_pilot(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())
        (self.run / "results.jsonl").write_bytes(original)
        first = json.loads(self.manifest.read_text().splitlines()[0])
        image = self.manifest.parent / first["image"]
        image.write_bytes(image.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            verify_pilot(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_recomputed_hash_does_not_allow_duplicate_or_missing_ids(self):
        rows = self.rows()
        rows[-1] = rows[0]
        self.rewrite(rows)
        with self.assertRaises(ValueError):
            verify_pilot(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_row_state_and_no_guessing_narrative(self):
        rows = self.rows()
        rows[0]["latency_ns"] = True
        self.rewrite(rows)
        with self.assertRaises(ValueError):
            verify_pilot(self.run, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_summary_counts_calls_and_kind_rejected_when_inconsistent(self):
        path = self.run / "run.json"
        original = json.loads(path.read_text())
        for field, value in [
            ("answer_calls", 0),
            ("model_load_attempted", True),
            ("kind", "unknown"),
            ("schema_version", True),
            ("answered", False),
        ]:
            info = dict(original)
            info[field] = value
            path.write_text(json.dumps(info))
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_pilot(self.run, self.manifest, self.output)
            self.assertFalse(self.output.exists())
        path.write_text(json.dumps(original))

    def test_symlink_and_nonfinite_source_input_rejected(self):
        path = self.run / "run.json"
        saved = self.run / "original.json"
        path.rename(saved)
        path.symlink_to(saved)
        with self.assertRaises((OSError, ValueError)):
            verify_pilot(self.run, self.manifest, self.output)
        path.unlink()
        path.write_text('{"x":NaN}')
        with self.assertRaises(ValueError):
            verify_pilot(self.run, self.manifest, self.output)

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        marker = self.output / "marker"
        marker.write_text("preserve")
        with self.assertRaises(FileExistsError):
            verify_pilot(self.run, self.manifest, self.output)
        self.assertEqual(marker.read_text(), "preserve")

    def test_cli_success_and_failure_no_partial_stdout(self):
        command = [
            sys.executable,
            "-m",
            "apps.pilot_verification",
            str(self.run),
            str(self.manifest),
            "--output",
            str(self.output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"]["contradicted"], 1)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("pilot verification failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
