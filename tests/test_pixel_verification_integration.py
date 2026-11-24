"""Actual pixel checks; no model or filename/answer lookup is involved."""

import json
import tempfile
import unittest
from pathlib import Path

from apps.verification_demo.runner import run_demo
from core.multimodal.fixtures import _png, _rectangle
from core.verification.claims import verify_claim


class PixelVerificationIntegrationTests(unittest.TestCase):
    def test_full_demo_retains_correct_and_wrong_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            summary = run_demo(output)
            results = [
                json.loads(line)
                for line in (output / "results.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(results), 12)
            self.assertEqual(sum(row["status"] == "verified" for row in results), 6)
            self.assertEqual(sum(row["status"] == "contradicted" for row in results), 6)
            self.assertEqual(sum(row["status"] == "abstained" for row in results), 0)
            self.assertIsInstance(summary, dict)

    def test_changed_pixels_override_a_previously_correct_answer(self):
        pixels = bytearray(bytes((255, 255, 255)) * (128 * 96))
        for x in (8, 38, 68, 98):
            _rectangle(pixels, (x, 30, x + 12, 42), (20, 150, 50))
        result = verify_claim(
            _png(pixels),
            {"kind": "count", "color": "green", "shape": "square", "answer": "3"},
        )
        self.assertEqual(result["status"], "contradicted")
        self.assertEqual(result["expected"], "4")

    def test_ambiguous_geometry_abstains(self):
        pixels = bytearray(bytes((255, 255, 255)) * (128 * 96))
        _rectangle(pixels, (20, 20, 30, 60), (20, 150, 50))
        _rectangle(pixels, (20, 50, 60, 60), (20, 150, 50))
        result = verify_claim(
            _png(pixels),
            {"kind": "count", "color": "green", "shape": "square", "answer": "1"},
        )
        self.assertEqual(result["status"], "abstained")
        self.assertIsNone(result["expected"])

    def test_invalid_raster_never_verifies_a_claim(self):
        result = verify_claim(
            b"not a supported PNG",
            {"kind": "color", "shape": "square", "answer": "red"},
        )
        self.assertEqual(result["status"], "abstained")
        self.assertIsNone(result["expected"])


if __name__ == "__main__":
    unittest.main()
