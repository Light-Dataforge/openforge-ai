import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.evaluation.metrics import evaluate


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.refs = Path(self.tmp.name) / "refs.jsonl"
        self.preds = Path(self.tmp.name) / "preds.jsonl"
        self.write(self.refs, [{"id": str(i), "answer": "yes"} for i in range(3)])
        self.rows = [
            {"id": "0", "answer": "yes", "confidence": 0.8},
            {"id": "1", "answer": "no", "confidence": 0.6},
            {"id": "2", "answer": None, "confidence": None},
        ]
        self.write(self.preds, self.rows)

    def write(self, path, rows):
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def test_accounting_and_hashes(self):
        report = evaluate(self.refs, self.preds)
        self.assertEqual(
            (report["answered"], report["abstained"], report["correct"]), (2, 1, 1)
        )
        self.assertEqual(report["coverage"], 2 / 3)
        self.assertEqual(report["accuracy_all"], 1 / 3)
        self.assertEqual(report["accuracy_answered"], 0.5)
        self.assertAlmostEqual(report["brier_answered"], 0.2)
        self.assertEqual(
            report["reference_sha256"],
            hashlib.sha256(self.refs.read_bytes()).hexdigest(),
        )

    def test_all_abstentions(self):
        for row in self.rows:
            row.update(answer=None, confidence=None)
        self.write(self.preds, self.rows)
        result = evaluate(self.refs, self.preds)
        self.assertEqual(result["accuracy_all"], 0)
        self.assertIsNone(result["accuracy_answered"])
        self.assertIsNone(result["brier_answered"])

    def test_missing_extra_and_duplicate_ids(self):
        for rows in [
            self.rows[:2],
            self.rows + [self.rows[0]],
            self.rows + [{"id": "extra", "answer": "yes", "confidence": 1}],
        ]:
            with self.subTest(rows=rows):
                self.write(self.preds, rows)
                with self.assertRaises(ValueError):
                    evaluate(self.refs, self.preds)

    def test_invalid_confidence(self):
        for value in [True, -0.1, 1.1, float("nan"), float("inf"), None, "0.5"]:
            self.rows[0]["confidence"] = value
            self.write(self.preds, self.rows)
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate(self.refs, self.preds)

    def test_abstention_cannot_have_confidence(self):
        self.rows[2]["confidence"] = 0
        self.write(self.preds, self.rows)
        with self.assertRaises(ValueError):
            evaluate(self.refs, self.preds)

    def test_strict_json_and_fields(self):
        for raw in [
            "",
            "\n",
            "{}\n",
            "[]\n",
            '{"id":"0","id":"1","answer":"yes","confidence":1}\n',
            '{"id":"0","answer":"\\ud800","confidence":1}\n',
        ]:
            self.preds.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                evaluate(self.refs, self.preds)

    def test_exact_matching_and_order(self):
        self.rows[0]["answer"] = "Yes"
        self.write(self.preds, list(reversed(self.rows)))
        self.assertEqual(evaluate(self.refs, self.preds)["correct"], 0)

    def test_cli_failure_has_no_report(self):
        self.preds.write_text("{}\n")
        result = subprocess.run(
            [sys.executable, "-m", "core.evaluation", str(self.refs), str(self.preds)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("evaluation failed", result.stderr)

    def test_cli_success(self):
        result = subprocess.run(
            [sys.executable, "-m", "core.evaluation", str(self.refs), str(self.preds)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), evaluate(self.refs, self.preds))

    def test_large_confidence_rejected(self):
        self.rows[0]["confidence"] = 10**1000
        self.write(self.preds, self.rows)
        with self.assertRaises(ValueError):
            evaluate(self.refs, self.preds)

    def test_unicode_line_separator_inside_answer(self):
        self.refs.write_text('{"id":"x","answer":"a\u2028b"}\n', encoding="utf-8")
        self.preds.write_text(
            '{"id":"x","answer":"a\u2028b","confidence":1}\n', encoding="utf-8"
        )
        self.assertEqual(evaluate(self.refs, self.preds)["correct"], 1)

    def test_no_final_newline_and_crlf(self):
        self.preds.write_bytes(self.preds.read_bytes().replace(b"\n", b"\r\n").rstrip())
        self.assertEqual(evaluate(self.refs, self.preds)["answered"], 2)

    def test_byte_limit(self):
        from unittest.mock import patch

        with (
            patch("core.evaluation.metrics.MAX_BYTES", 10),
            self.assertRaises(ValueError),
        ):
            evaluate(self.refs, self.preds)


if __name__ == "__main__":
    unittest.main()
