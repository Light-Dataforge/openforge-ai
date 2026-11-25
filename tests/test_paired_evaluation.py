import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.evaluation.paired import compare_predictions


class PairedEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.refs = self.root / "references.jsonl"
        self.before = self.root / "before.jsonl"
        self.after = self.root / "after.jsonl"
        self.reference_rows = [
            {"id": f"private-task-{i}", "answer": "private-reference"} for i in range(9)
        ]
        self.first_rows = []
        self.second_rows = []
        for index in range(9):
            self.first_rows.append(self.prediction(index, index // 3))
            self.second_rows.append(self.prediction(index, index % 3))
        self.save()

    def prediction(self, index, status):
        return {
            "id": f"private-task-{index}",
            "answer": ["private-reference", "private-wrong-answer", None][status],
            "confidence": None if status == 2 else 0.8,
        }

    def write(self, path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def save(self):
        self.write(self.refs, self.reference_rows)
        self.write(self.before, self.first_rows)
        self.write(self.after, self.second_rows)

    def compare(self, **options):
        return compare_predictions(
            self.refs,
            self.before,
            self.after,
            seed=options.pop("seed", 42),
            replicates=options.pop("replicates", 100),
            **options,
        )

    def test_all_nine_transitions_and_source_totals(self):
        result = self.compare()
        self.assertEqual(result["total"], 9)
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(
            result["before"],
            {
                "total": 9,
                "answered": 6,
                "abstained": 3,
                "correct": 3,
                "coverage": 2 / 3,
                "accuracy_all": 1 / 3,
            },
        )
        self.assertEqual(result["accuracy_all_delta"], 0)
        for row in result["transitions"].values():
            self.assertEqual(row, {"correct": 1, "incorrect": 1, "abstained": 1})
        for status in ("correct", "incorrect", "abstained"):
            self.assertEqual(sum(result["transitions"][status].values()), 3)
            self.assertEqual(
                sum(row[status] for row in result["transitions"].values()), 3
            )
        self.assertFalse(result["model_execution_verified"])

    def test_degenerate_identical_all_win_and_all_loss_intervals(self):
        for first_status, second_status, expected in [
            (0, 0, 0),
            (1, 0, 1),
            (0, 1, -1),
            (2, 2, 0),
        ]:
            self.first_rows = [self.prediction(i, first_status) for i in range(9)]
            self.second_rows = [self.prediction(i, second_status) for i in range(9)]
            self.save()
            result = self.compare()
            self.assertEqual(result["accuracy_all_delta"], expected)
            self.assertEqual(result["bootstrap"]["lower"], expected)
            self.assertEqual(result["bootstrap"]["upper"], expected)
            if first_status == second_status == 2:
                self.assertEqual(result["before"]["coverage"], 0)
                self.assertEqual(result["transitions"]["abstained"]["abstained"], 9)

    def test_rng_draws_are_paired_and_percentile_indices_are_explicit(self):
        # Cycle across all nine paired rows each replicate; their deltas sum0.
        class Cycle:
            def __init__(self):
                self.calls = 0

            def randrange(self, size):
                value = self.calls % size
                self.calls += 1
                return value

        rng = Cycle()
        with patch(
            "core.evaluation.paired.random.Random", return_value=rng
        ) as constructor:
            result = self.compare(replicates=101, seed=17)
        constructor.assert_called_once_with(17)
        self.assertEqual(rng.calls, 9 * 101)
        self.assertEqual(result["bootstrap"]["lower_index"], 2)
        self.assertEqual(result["bootstrap"]["upper_index"], 97)
        self.assertEqual(result["bootstrap"]["lower"], 0)
        self.assertEqual(result["bootstrap"]["upper"], 0)
        self.assertEqual(result["bootstrap"]["task_draws"], 909)

    def test_seeded_determinism_row_order_and_same_read_hashes(self):
        first = self.compare(replicates=120)
        self.assertEqual(first, self.compare(replicates=120))
        self.reference_rows.reverse()
        self.first_rows.reverse()
        self.second_rows.reverse()
        self.save()
        reordered = self.compare(replicates=120)
        for key in [
            "reference_sha256",
            "before_prediction_sha256",
            "after_prediction_sha256",
        ]:
            self.assertNotEqual(first.pop(key), reordered.pop(key))
        self.assertEqual(first, reordered)
        self.assertLessEqual(first["bootstrap"]["lower"], first["bootstrap"]["upper"])
        self.assertGreaterEqual(first["bootstrap"]["lower"], -1)
        self.assertLessEqual(first["bootstrap"]["upper"], 1)

    def test_strict_seed_replicates_and_draw_budget_before_rng(self):
        for seed in [True, -1, 2**32, 1.5]:
            with self.assertRaises(ValueError):
                self.compare(seed=seed)
        for replicates in [True, 99, 5001, 100.5]:
            with self.assertRaises(ValueError):
                self.compare(replicates=replicates)
        with (
            patch("core.evaluation.paired.MAX_DRAWS", 899),
            patch(
                "core.evaluation.paired.random.Random",
                side_effect=AssertionError("not called"),
            ),
        ):
            with self.assertRaises(ValueError):
                self.compare()
        with patch("core.evaluation.paired.MAX_DRAWS", 900):
            self.assertEqual(self.compare()["bootstrap"]["task_draws"], 900)

    def test_missing_extra_duplicate_and_nonfinite_inputs_fail(self):
        invalid = [
            self.second_rows[:-1],
            self.second_rows + [self.second_rows[0]],
            self.second_rows + [{"id": "extra", "answer": None, "confidence": None}],
        ]
        for rows in invalid:
            self.write(self.after, rows)
            with self.assertRaises(ValueError):
                self.compare()
        for value in [float("nan"), float("inf"), True]:
            rows = copy.deepcopy(self.second_rows)
            rows[0]["confidence"] = value
            self.write(self.after, rows)
            with self.assertRaises(ValueError):
                self.compare()

    def test_privacy_and_source_immutability(self):
        files = [self.refs, self.before, self.after]
        original = {path: path.read_bytes() for path in files}
        text = json.dumps(self.compare())
        for marker in [
            "private-task",
            "private-reference",
            "private-wrong-answer",
            str(self.root),
        ]:
            self.assertNotIn(marker, text)
        self.assertEqual(original, {path: path.read_bytes() for path in files})

    def test_cli_success_failure_and_required_seed(self):
        args = [
            sys.executable,
            "-m",
            "apps.paired_evaluation",
            str(self.refs),
            str(self.before),
            str(self.after),
        ]
        result = subprocess.run(
            [*args, "--seed", "42", "--replicates", "100"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.compare())
        missing = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(missing.stdout, "")
        self.write(self.after, [])
        failed = subprocess.run([*args, "--seed", "42"], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertNotIn(str(self.root), failed.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_and_symlink_cli_inputs_fail_promptly(self):
        fifo = self.root / "no-writer"
        os.mkfifo(fifo)
        symlink = self.root / "alias"
        symlink.symlink_to(self.after)
        for path in (fifo, symlink):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.paired_evaluation",
                    str(self.refs),
                    str(self.before),
                    str(path),
                    "--seed",
                    "42",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(str(path), result.stderr)
