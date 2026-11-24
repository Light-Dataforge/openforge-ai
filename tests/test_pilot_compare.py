import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from apps.pilot_compare.runner import compare_pilots
from apps.pilot_verification.runner import verify_pilot
from core.multimodal.fixtures import generate_fixtures


class Scripted:
    def __init__(self, values):
        self.values = iter(values)

    def answer(self, image_bytes, prompt, *, max_new_tokens=64):
        value = next(self.values)
        if value is None:
            raise RuntimeError("private-error-marker")
        return value


class PilotCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = generate_fixtures(self.root / "fixtures")
        self.before = self.root / "before"
        self.after = self.root / "after"
        run_pilot(
            self.manifest,
            self.before,
            adapter=Scripted(["red", "blue", "3", "2", "left", "blue"]),
        )
        run_pilot(
            self.manifest,
            self.after,
            adapter=Scripted(
                ["blue", " BLUE ", "private-answer-marker", None, "left", "blue"]
            ),
        )
        self.output = self.root / "comparison.json"

    def compare(self):
        return compare_pilots(self.before, self.after, self.manifest, self.output)

    def test_real_pixels_account_for_every_pair_without_exporting_answers(self):
        result = self.compare()
        self.assertEqual(result["cases"], 6)
        self.assertEqual(result["before"]["counts"]["verified"], 6)
        self.assertEqual(
            result["after"]["counts"],
            {
                "verified": 3,
                "contradicted": 1,
                "abstained": 1,
                "failed": 1,
                "not_executed": 0,
            },
        )
        self.assertEqual(result["transitions"]["verified"], result["after"]["counts"])
        self.assertEqual(
            sum(sum(row.values()) for row in result["transitions"].values()), 6
        )
        for status, count in result["before"]["counts"].items():
            self.assertEqual(sum(result["transitions"][status].values()), count)
        for status, count in result["after"]["counts"].items():
            self.assertEqual(
                sum(row[status] for row in result["transitions"].values()), count
            )
        text = self.output.read_text()
        self.assertNotIn("private-answer-marker", text)
        self.assertNotIn("private-error-marker", text)
        self.assertNotIn(str(self.root), text)
        self.assertFalse(result["performs_model_inference"])
        self.assertFalse(result["source_execution_verified"])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(list(self.root.glob(".pilot-compare-*")), [])

    def test_dry_run_is_retained_and_not_called_an_improvement(self):
        dry = self.root / "dry"
        run_pilot(self.manifest, dry, dry_run=True)
        result = compare_pilots(dry, self.before, self.manifest, self.output)
        self.assertEqual(result["transitions"]["not_executed"]["verified"], 6)
        self.assertNotIn("accuracy", result)
        self.assertNotIn("improvement", result)

    def test_identical_sources_are_diagonal_and_deterministic(self):
        first = compare_pilots(self.before, self.before, self.manifest, self.output)
        other = self.root / "other.json"
        second = compare_pilots(self.before, self.before, self.manifest, other)
        self.assertEqual(first, second)
        self.assertEqual(self.output.read_bytes(), other.read_bytes())
        self.assertEqual(first["transitions"]["verified"]["verified"], 6)
        self.assertTrue(
            all(not pair["normalized_answer_changed"] for pair in first["pairs"])
        )

    def test_corrupt_second_source_leaves_no_output_or_staging(self):
        with (self.after / "results.jsonl").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaises(ValueError):
            self.compare()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".pilot-compare-*")), [])

    def test_manifest_change_between_runs_is_rejected(self):
        calls = 0

        def changed(*args):
            nonlocal calls
            result = verify_pilot(*args)
            calls += 1
            if calls == 2:
                result["manifest_sha256"] = "f" * 64
            return result

        with patch("apps.pilot_compare.runner.verify_pilot", side_effect=changed):
            with self.assertRaises(ValueError):
                self.compare()
        self.assertFalse(self.output.exists())

    def test_conflict_symlink_and_bound_fail_without_overwrite(self):
        self.output.write_text("keep")
        with self.assertRaises(FileExistsError):
            self.compare()
        self.assertEqual(self.output.read_text(), "keep")
        self.output.unlink()
        self.output.symlink_to(self.root / "missing")
        with self.assertRaises(FileExistsError):
            self.compare()
        self.output.unlink()
        with patch("apps.pilot_compare.runner.MAX_RESULTS_BYTES", 100):
            with self.assertRaises(ValueError):
                self.compare()
        self.assertFalse(self.output.exists())

    def test_cli_and_source_immutability(self):
        before = {
            p: p.read_bytes()
            for directory in (self.before, self.after)
            for p in directory.iterdir()
        }
        args = [
            sys.executable,
            "-m",
            "apps.pilot_compare",
            str(self.before),
            str(self.after),
            str(self.manifest),
            "--output",
            str(self.output),
        ]
        done = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["cases"], 6)
        failed = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertNotIn(str(self.root), failed.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
