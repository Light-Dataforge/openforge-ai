import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.verification_demo.runner import (
    TEMPLATES,
    claim_for,
    run_demo,
    wrong_candidate,
)
from core.multimodal.fixtures import generate_fixtures


def fake_verifier(image_bytes, claim):
    return {
        "expected": None,
        "claimed": claim["answer"],
        "status": "abstained",
        "reason": "injected contract-only verifier",
        "evidence": {"image_sha256": hashlib.sha256(image_bytes).hexdigest()},
    }


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "demo"

    def rows(self):
        return [
            json.loads(line)
            for line in (self.output / "results.jsonl").read_text().splitlines()
        ]

    def test_exact_question_routing_not_metadata(self):
        for question, expected in TEMPLATES.items():
            claim = claim_for(
                question,
                "red"
                if expected["kind"] in {"color", "tallest"}
                else "3"
                if expected["kind"] == "count"
                else "left",
            )
            self.assertEqual(
                {key: value for key, value in claim.items() if key != "answer"},
                expected,
            )
            self.assertNotIn("id", claim)
            self.assertNotIn("image", claim)
        for question in [
            "synthetic-color-red-square-v1",
            "images/color-red-square.png",
            "What color is the square?",
            "Count everything in this photo",
        ]:
            with self.subTest(question=question), self.assertRaises(ValueError):
                claim_for(question, "red")

    def test_wrong_candidate_is_explicit_deterministic_synthetic_input(self):
        self.assertEqual(wrong_candidate({"kind": "color", "answer": "red"}), "blue")
        self.assertEqual(wrong_candidate({"kind": "tallest", "answer": "blue"}), "red")
        self.assertEqual(wrong_candidate({"kind": "count", "answer": "3"}), "4")
        self.assertEqual(
            wrong_candidate({"kind": "relation", "answer": "left"}), "right"
        )

    def test_all_assertions_hashes_and_metadata_retained_without_inference(self):
        summary = run_demo(self.output, verifier=fake_verifier)
        rows = self.rows()
        self.assertEqual(summary["cases"], 6)
        self.assertEqual(summary["assertions"], 12)
        self.assertEqual(
            summary["counts"],
            {"verified": 0, "contradicted": 0, "abstained": 12, "error": 0},
        )
        self.assertEqual(len(rows), 12)
        self.assertTrue(
            all(row["evidence"]["image_sha256"] == row["image_sha256"] for row in rows)
        )
        self.assertFalse(summary["model_inference_executed"])
        self.assertFalse(summary["benchmark_result"])
        self.assertEqual(summary["verifier_mode"], "injected")
        self.assertEqual(
            json.loads((self.output / "summary.json").read_text()), summary
        )
        self.assertEqual(
            summary["results_sha256"],
            hashlib.sha256((self.output / "results.jsonl").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            [row["candidate_source"] for row in rows[:2]],
            ["fixture_candidate", "deliberately_wrong_candidate"],
        )
        self.assertNotEqual(rows[0]["candidate"], rows[1]["candidate"])

    def test_renamed_ids_and_images_cannot_change_claim_routing(self):
        def opaque_fixtures(directory):
            manifest = generate_fixtures(directory)
            rows = [json.loads(line) for line in manifest.read_text().splitlines()]
            for index, row in enumerate(rows):
                old = manifest.parent / row["image"]
                image = f"opaque-{index}.png"
                old.rename(manifest.parent / image)
                row.update(id=f"opaque-{index}", image=image)
            manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return manifest

        observed = []

        def verifier(image, claim):
            observed.append(claim)
            return fake_verifier(image, claim)

        with patch(
            "apps.verification_demo.runner.generate_fixtures",
            side_effect=opaque_fixtures,
        ):
            run_demo(self.output, verifier=verifier)
        self.assertEqual(
            observed[0], {"kind": "color", "shape": "square", "answer": "red"}
        )
        self.assertEqual(
            observed[4],
            {"kind": "count", "color": "green", "shape": "square", "answer": "3"},
        )
        self.assertTrue(all(row["id"].startswith("opaque-") for row in self.rows()))

    def test_verifier_errors_are_accounted_and_later_assertions_continue(self):
        calls = 0

        def verifier(image, claim):
            nonlocal calls
            calls += 1
            if calls in {2, 8}:
                raise ValueError("injected malformed claim")
            return fake_verifier(image, claim)

        summary = run_demo(self.output, verifier=verifier)
        self.assertEqual(calls, 12)
        self.assertEqual(summary["counts"]["error"], 2)
        self.assertEqual(summary["counts"]["abstained"], 10)
        self.assertEqual(len(self.rows()), 12)
        self.assertEqual(self.rows()[1]["error"]["type"], "ValueError")

    def test_invalid_verifier_result_does_not_invent_verified_status(self):
        summary = run_demo(
            self.output, verifier=lambda image, claim: {"status": "verified"}
        )
        self.assertEqual(summary["counts"]["error"], 12)
        self.assertEqual(summary["counts"]["verified"], 0)

    def test_missing_lazy_verifier_is_retained_as_failure_not_fake_evidence(self):
        with patch(
            "apps.verification_demo.runner.import_module",
            side_effect=ImportError("peer not integrated"),
        ):
            summary = run_demo(self.output)
        self.assertEqual(summary["counts"]["error"], 12)
        self.assertTrue(all(row["evidence"] is None for row in self.rows()))

    def test_conflict_never_overwrites_or_calls_fixture_or_verifier(self):
        self.output.mkdir()
        canary = self.output / "keep"
        canary.write_text("original")
        with patch(
            "apps.verification_demo.runner.generate_fixtures",
            side_effect=AssertionError("must not generate"),
        ):
            with self.assertRaises(FileExistsError):
                run_demo(self.output, verifier=fake_verifier)
        self.assertEqual(canary.read_text(), "original")
        self.assertEqual(list(self.output.iterdir()), [canary])

    def test_bad_generated_input_fails_before_verification(self):
        def malformed(directory):
            directory.mkdir()
            manifest = directory / "manifest.jsonl"
            manifest.write_text("{}\n")
            return manifest

        with (
            patch(
                "apps.verification_demo.runner.generate_fixtures", side_effect=malformed
            ),
            patch(
                "apps.verification_demo.runner._verify",
                side_effect=AssertionError("must not import"),
            ),
        ):
            with self.assertRaises(ValueError):
                run_demo(self.output)
        self.assertFalse((self.output / "results.jsonl").exists())
        self.assertFalse((self.output / "summary.json").exists())

    def test_cli_conflict_has_no_partial_summary(self):
        self.output.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.verification_demo",
                "--output",
                str(self.output),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("verification demo failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
