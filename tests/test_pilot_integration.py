"""Cross-module contracts only: injected answers are not model inference."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import run_pilot
from core.multimodal.fixtures import generate_fixtures


class PilotIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = generate_fixtures(self.root / "fixtures")
        self.rows = [
            json.loads(line) for line in self.manifest.read_text().splitlines()
        ]

    def test_generated_visual_cases_dry_run_without_model_import(self):
        output = self.root / "dry-run"
        with patch(
            "apps.baseline.runner.import_module",
            side_effect=AssertionError("dry-run must not import a model"),
        ):
            report = run_pilot(self.manifest, output, dry_run=True)
        self.assertEqual(report["cases"], len(self.rows))
        self.assertEqual(report["not_executed"], len(self.rows))
        self.assertEqual(report["answer_calls"], 0)
        self.assertFalse(report["model_load_attempted"])
        self.assertFalse(report["model_execution_verified"])
        self.assertEqual(
            report["results_sha256"],
            hashlib.sha256((output / "results.jsonl").read_bytes()).hexdigest(),
        )
        results = [
            json.loads(line)
            for line in (output / "results.jsonl").read_text().splitlines()
        ]
        self.assertEqual(
            [row["id"] for row in results], [row["id"] for row in self.rows]
        )
        self.assertTrue(
            all(
                row["answer"] is None and row["status"] == "not_executed"
                for row in results
            )
        )

    def test_injected_failure_preserves_every_case_and_prompt_contract(self):
        expected = [
            (row["question"], (self.manifest.parent / row["image"]).read_bytes())
            for row in self.rows
        ]
        calls = []

        class ContractAdapter:
            def answer(self, image_bytes, prompt, *, max_new_tokens=64):
                calls.append((prompt, image_bytes, max_new_tokens))
                if len(calls) == 1:
                    raise RuntimeError("synthetic contract failure")
                return "contract response; not model inference"

        output = self.root / "injected"
        report = run_pilot(self.manifest, output, adapter=ContractAdapter())
        self.assertEqual([(prompt, raw) for prompt, raw, _ in calls], expected)
        self.assertTrue(all(limit == 64 for _, _, limit in calls))
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["answered"], len(self.rows) - 1)
        self.assertEqual(report["adapter_mode"], "injected")
        self.assertFalse(report["model_execution_verified"])
        results = [
            json.loads(line)
            for line in (output / "results.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(results), len(self.rows))
        self.assertEqual(results[0]["status"], "failed")
        self.assertTrue(all("confidence" not in row for row in results))

    def test_changed_fixture_fails_before_model_load_and_output_creation(self):
        image = self.manifest.parent / self.rows[0]["image"]
        image.write_bytes(image.read_bytes() + b"changed")
        output = self.root / "must-not-exist"
        with patch(
            "apps.baseline.runner.import_module",
            side_effect=AssertionError("invalid artifacts must not load models"),
        ):
            with self.assertRaises(ValueError):
                run_pilot(self.manifest, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
