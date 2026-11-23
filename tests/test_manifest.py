import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.experiments.manifest import evaluate_manifest, validate_metadata

ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.references = self.root / "references.jsonl"
        self.predictions = self.root / "predictions.jsonl"
        self.manifest = self.root / "manifest.json"
        self.references.write_bytes((ROOT / "examples/references.jsonl").read_bytes())
        self.predictions.write_bytes((ROOT / "examples/predictions.jsonl").read_bytes())
        self.metadata = json.loads(
            (ROOT / "examples/synthetic-manifest.json").read_text()
        )
        self.write()

    def write(self):
        self.manifest.write_text(json.dumps(self.metadata), encoding="utf-8")

    def model_declaration(self):
        self.metadata.update(
            {
                "run_kind": "model",
                "model": {
                    "id": "unit-test/not-an-executed-model",
                    "revision": "a" * 40,
                    "license": "test-only",
                },
                "prompt": {
                    "text": "unit test only",
                    "sha256": hashlib.sha256(b"unit test only").hexdigest(),
                },
                "generation": {"seed": 0, "temperature": 0.0, "max_new_tokens": 8},
            }
        )

    def test_synthetic_accounting_and_provenance(self):
        result = evaluate_manifest(self.manifest, self.references, self.predictions)
        self.assertEqual(result["run_kind"], "synthetic")
        self.assertFalse(result["model_execution_verified"])
        self.assertEqual(result["metrics"]["correct"], 1)
        self.assertEqual(
            result["manifest_sha256"],
            hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
        )
        self.assertNotIn("environment", result)
        self.assertNotIn("prompt", result)

    def test_declaration_does_not_attest_model_execution(self):
        self.model_declaration()
        self.write()
        result = evaluate_manifest(self.manifest, self.references, self.predictions)
        self.assertEqual(result["run_kind"], "model")
        self.assertFalse(result["model_execution_verified"])

    def test_mutated_artifacts_fail_instead_of_silently_rescoring(self):
        for file, old, new in [
            (self.references, b"blue", b"green"),
            (self.predictions, b"blue", b"red"),
        ]:
            original = file.read_bytes()
            file.write_bytes(original.replace(old, new))
            with (
                self.subTest(file=file),
                self.assertRaisesRegex(ValueError, "artifact mismatch"),
            ):
                evaluate_manifest(self.manifest, self.references, self.predictions)
            file.write_bytes(original)

    def test_missing_unknown_fields_and_schema(self):
        for key in self.metadata:
            row = copy.deepcopy(self.metadata)
            del row[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_metadata(row)
        for changes in [
            {"extra": 1},
            {"schema_version": True},
            {"run_kind": []},
            {"run_kind": "latest"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_metadata(dict(self.metadata, **changes))

    def test_missing_licenses_and_unpinned_revisions(self):
        self.model_declaration()
        for section, field in [
            ("model", "license"),
            ("dataset", "license"),
            ("preprocessing", "revision"),
            ("environment", "hardware"),
        ]:
            row = copy.deepcopy(self.metadata)
            del row[section][field]
            with self.subTest(section=section), self.assertRaises(ValueError):
                validate_metadata(row)
        for section in ["model", "dataset", "preprocessing"]:
            row = copy.deepcopy(self.metadata)
            row[section]["revision"] = "main"
            with self.subTest(section=section), self.assertRaises(ValueError):
                validate_metadata(row)
        for value in ["main", "a" * 39, "A" * 40, 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_metadata(dict(self.metadata, code_revision=value))

    def test_synthetic_cannot_claim_model_metadata(self):
        for field in ["model", "prompt", "generation"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_metadata(dict(self.metadata, **{field: {}}))

    def test_generation_boundaries_and_prompt_hash(self):
        self.model_declaration()
        for field, values in {
            "seed": [True, -1, 2**32, "0"],
            "temperature": [True, -1, 3, float("nan"), float("inf"), 10**1000],
            "max_new_tokens": [False, 0, 32769, 1.5],
        }.items():
            for value in values:
                row = copy.deepcopy(self.metadata)
                row["generation"][field] = value
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    validate_metadata(row)
        self.metadata["prompt"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "prompt SHA-256 mismatch"):
            validate_metadata(self.metadata)

    def test_environment_versions_and_unicode(self):
        for dependencies in [
            {"torch": ">=2"},
            {"torch": "latest"},
            {"invalid name": "1.0"},
            [],
            {"torch": None},
        ]:
            row = copy.deepcopy(self.metadata)
            row["environment"]["dependencies"] = dependencies
            with self.subTest(dependencies=dependencies), self.assertRaises(ValueError):
                validate_metadata(row)
        row = copy.deepcopy(self.metadata)
        row["environment"]["dependencies"] = {"torch": "2.5.1+cpu", "numpy": "2.1.0"}
        self.assertEqual(
            validate_metadata(row)["environment"]["dependencies"],
            row["environment"]["dependencies"],
        )
        for field, value in [
            ("python", "3.13"),
            ("hardware", "\ud800"),
            ("platform", ""),
        ]:
            row = copy.deepcopy(self.metadata)
            row["environment"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_metadata(row)

    def test_validation_detaches_metadata(self):
        result = validate_metadata(self.metadata)
        self.metadata["inputs"]["reference_sha256"] = "0" * 64
        self.assertNotEqual(result["inputs"], self.metadata["inputs"])

    def test_strict_json_and_size(self):
        valid = self.manifest.read_bytes()
        for raw in [
            b'{"schema_version":1,"schema_version":1}',
            b'{"x":NaN}',
            b"\xff",
            valid.decode().encode("utf-16"),
            b"[" * 2000 + b"]" * 2000,
        ]:
            self.manifest.write_bytes(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                evaluate_manifest(self.manifest, self.references, self.predictions)
        self.manifest.write_bytes(valid)
        with (
            patch("core.experiments.manifest.MAX_MANIFEST_BYTES", 10),
            self.assertRaises(ValueError),
        ):
            evaluate_manifest(self.manifest, self.references, self.predictions)

    def test_cli_success_and_failure_no_partial_report(self):
        command = [
            sys.executable,
            "-m",
            "core.experiments",
            str(self.manifest),
            str(self.references),
            str(self.predictions),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["metrics"]["total"], 3)
        self.metadata["inputs"]["prediction_sha256"] = "0" * 64
        self.write()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("artifact mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
