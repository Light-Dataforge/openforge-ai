import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.evaluation.diagnostics import diagnose


class ConfidenceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.refs = self.root / "refs.jsonl"
        self.preds = self.root / "preds.jsonl"
        self.references = [
            {"id": str(i), "answer": "private-reference"} for i in range(4)
        ]
        self.predictions = [
            {"id": "0", "answer": "private-reference", "confidence": 0.8},
            {"id": "1", "answer": "private-wrong", "confidence": 0.8},
            {"id": "2", "answer": "private-reference", "confidence": 0.2},
            {"id": "3", "answer": None, "confidence": None},
        ]
        self.write()

    def write(self):
        self.refs.write_text("".join(json.dumps(r) + "\n" for r in self.references))
        self.preds.write_text("".join(json.dumps(r) + "\n" for r in self.predictions))

    def test_bins_and_conditional_ece_against_hand_calculation(self):
        report = diagnose(self.refs, self.preds, bins=2)
        self.assertFalse(report["model_execution_verified"])
        low, high = report["bins"]
        self.assertEqual((low["count"], high["count"]), (1, 2))
        self.assertAlmostEqual(low["mean_confidence"], 0.2)
        self.assertEqual(low["accuracy"], 1)
        self.assertAlmostEqual(low["gap"], 0.8)
        self.assertAlmostEqual(high["mean_confidence"], 0.8)
        self.assertEqual(high["accuracy"], 0.5)
        self.assertAlmostEqual(report["ece_answered"], (0.8 + 2 * 0.3) / 3)
        self.assertEqual(
            (report["total"], report["answered"], report["abstained"]), (4, 3, 1)
        )
        self.assertEqual(report["coverage"], 0.75)
        self.assertEqual(
            report["reference_sha256"],
            hashlib.sha256(self.refs.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["prediction_sha256"],
            hashlib.sha256(self.preds.read_bytes()).hexdigest(),
        )
        text = json.dumps(report)
        self.assertNotIn("private-reference", text)
        self.assertNotIn("private-wrong", text)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn('"id"', text)

    def test_whole_ties_and_abstention_denominator(self):
        report = diagnose(self.refs, self.preds)
        curve = report["risk_coverage"]
        self.assertEqual(len(curve), 2)
        self.assertEqual(
            curve[0],
            {
                "threshold": 0.8,
                "retained": 2,
                "correct": 1,
                "coverage": 0.5,
                "risk": 0.5,
            },
        )
        self.assertEqual(curve[1]["retained"], 3)
        self.assertEqual(curve[1]["coverage"], 0.75)
        self.assertAlmostEqual(curve[1]["risk"], 1 / 3)
        self.assertEqual(sum(row["count"] for row in report["bins"]), 3)

    def test_row_order_does_not_change_diagnostics_except_byte_hashes(self):
        first = diagnose(self.refs, self.preds)
        self.references.reverse()
        self.predictions.reverse()
        self.write()
        second = diagnose(self.refs, self.preds)
        for report in (first, second):
            report.pop("reference_sha256")
            report.pop("prediction_sha256")
        self.assertEqual(first, second)

    def test_all_abstention_and_empty_bins_use_null_metrics(self):
        for row in self.predictions:
            row.update(answer=None, confidence=None)
        self.write()
        report = diagnose(self.refs, self.preds)
        self.assertEqual(report["coverage"], 0)
        self.assertIsNone(report["ece_answered"])
        self.assertEqual(report["risk_coverage"], [])
        for row in report["bins"]:
            self.assertEqual(row["count"], 0)
            for key in ["mean_confidence", "accuracy", "gap"]:
                self.assertIsNone(row[key])

    def test_exact_and_adjacent_float_edges_and_endpoints(self):
        edge = 3 / 10
        values = [0.0, math.nextafter(edge, 0), edge, math.nextafter(edge, 1), 1.0]
        self.references = [{"id": str(i), "answer": "yes"} for i in range(len(values))]
        self.predictions = [
            {"id": str(i), "answer": "yes", "confidence": value}
            for i, value in enumerate(values)
        ]
        self.write()
        report = diagnose(self.refs, self.preds, bins=10)
        self.assertEqual(
            [r["count"] for r in report["bins"]], [1, 0, 1, 2, 0, 0, 0, 0, 0, 1]
        )
        self.assertFalse(report["bins"][3]["upper_inclusive"])
        self.assertTrue(report["bins"][-1]["upper_inclusive"])
        self.assertEqual(report["risk_coverage"][-1]["threshold"], 0)
        self.assertEqual(report["risk_coverage"][-1]["coverage"], 1)

    def test_invalid_bin_bounds_mismatch_and_confidence_fail(self):
        for bins in [True, 1, 51, 2.0, "10"]:
            with self.assertRaises(ValueError):
                diagnose(self.refs, self.preds, bins=bins)
        self.references.pop()
        self.write()
        with self.assertRaises(ValueError):
            diagnose(self.refs, self.preds)
        self.references.append({"id": "3", "answer": "private-reference"})
        for value in [True, float("nan"), float("inf"), -0.1, 1.1]:
            self.predictions[0]["confidence"] = value
            self.write()
            with self.assertRaises(ValueError):
                diagnose(self.refs, self.preds)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO support required")
    def test_cli_rejects_fifo_promptly_with_coarse_error(self):
        fifo = self.root / "no-writer.pipe"
        os.mkfifo(fifo)
        for refs, preds in [(fifo, self.preds), (self.refs, fifo)]:
            done = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.confidence_diagnostics",
                    str(refs),
                    str(preds),
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            self.assertEqual(done.returncode, 2)
            self.assertEqual(done.stdout, "")
            self.assertNotIn(str(self.root), done.stderr)

    def test_actual_cli_success_failure_and_no_source_modification(self):
        before = (self.refs.read_bytes(), self.preds.read_bytes())
        args = [
            sys.executable,
            "-S",
            "-m",
            "apps.confidence_diagnostics",
            str(self.refs),
            str(self.preds),
            "--bins",
            "2",
        ]
        done = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            json.loads(done.stdout), diagnose(self.refs, self.preds, bins=2)
        )
        self.assertEqual(before, (self.refs.read_bytes(), self.preds.read_bytes()))
        bad = subprocess.run(args[:-1] + ["51"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertNotIn(str(self.root), bad.stderr)

    def test_duplicate_keys_and_leaf_symlinks_rejected(self):
        original = copy.deepcopy(self.predictions)
        self.preds.write_text('{"id":"0","id":"0","answer":null,"confidence":null}\n')
        with self.assertRaises(ValueError):
            diagnose(self.refs, self.preds)
        self.predictions = original
        self.write()
        alias = self.root / "alias"
        alias.symlink_to(self.preds)
        with self.assertRaises((OSError, ValueError)):
            diagnose(self.refs, alias)
