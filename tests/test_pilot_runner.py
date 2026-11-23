import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.baseline.runner import load_cases, run_pilot


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def answer(self, image_bytes, prompt, *, max_new_tokens=64):
        self.calls.append((image_bytes, prompt, max_new_tokens))
        if prompt == "fail this case":
            raise RuntimeError("synthetic adapter failure")
        return "fake-only answer"


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.image = self.root / "image.png"
        self.image.write_bytes(b"not-a-real-image; fake-adapter-only")
        self.manifest = self.root / "manifest.jsonl"
        self.row = {
            "id": "test-1",
            "image": "image.png",
            "question": "what is here?",
            "answer": "synthetic",
            "image_sha256": hashlib.sha256(self.image.read_bytes()).hexdigest(),
        }
        self.output = self.root / "run"
        self.write([self.row])

    def write(self, rows):
        self.manifest.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def results(self):
        return [
            json.loads(line)
            for line in (self.output / "results.jsonl").read_text().splitlines()
        ]

    def test_injected_adapter_records_raw_answers_hashes_and_no_confidence(self):
        fake = FakeAdapter()
        report = run_pilot(self.manifest, self.output, adapter=fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(
            fake.calls[0], (self.image.read_bytes(), self.row["question"], 64)
        )
        self.assertEqual(report["adapter_mode"], "injected")
        self.assertFalse(report["model_execution_verified"])
        self.assertFalse(report["model_load_attempted"])
        (result,) = self.results()
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["answer"], "fake-only answer")
        self.assertGreaterEqual(result["latency_ns"], 0)
        self.assertNotIn("confidence", result)
        self.assertEqual(
            report["results_sha256"],
            hashlib.sha256((self.output / "results.jsonl").read_bytes()).hexdigest(),
        )
        self.assertEqual(json.loads((self.output / "run.json").read_text()), report)
        self.assertIn("python", report["environment"])
        self.assertIn("machine", report["environment"])

    def test_failure_task_remains_and_later_task_still_runs(self):
        self.write(
            [
                self.row,
                dict(self.row, id="test-2", question="fail this case"),
                dict(self.row, id="test-3"),
            ]
        )
        report = run_pilot(self.manifest, self.output, adapter=FakeAdapter())
        self.assertEqual(
            (report["answered"], report["failed"], report["answer_calls"]), (2, 1, 3)
        )
        self.assertEqual(report["status"], "complete-with-failures")
        results = self.results()
        self.assertEqual([row["id"] for row in results], ["test-1", "test-2", "test-3"])
        self.assertEqual(results[1]["error"]["stage"], "answer")
        self.assertIsNone(results[1]["answer"])

    def test_dry_run_never_imports_downloads_or_calls_an_adapter(self):
        fake = FakeAdapter()
        with (
            patch(
                "apps.baseline.runner.import_module",
                side_effect=AssertionError("no adapter import"),
            ),
            patch(
                "apps.baseline.runner._default_adapter",
                side_effect=AssertionError("no model load"),
            ),
        ):
            report = run_pilot(
                self.manifest,
                self.output,
                adapter=fake,
                dry_run=True,
                allow_download=True,
            )
        self.assertEqual(fake.calls, [])
        self.assertEqual(report["not_executed"], 1)
        self.assertEqual(report["answer_calls"], 0)
        self.assertFalse(report["model_load_attempted"])
        (result,) = self.results()
        self.assertEqual(result["status"], "not_executed")
        self.assertIsNone(result["latency_ns"])
        self.assertIsNone(result["answer"])

    def test_default_loader_is_lazy_offline_cpu_and_failure_accounts_every_task(self):
        self.write([self.row, dict(self.row, id="test-2")])
        with patch(
            "apps.baseline.runner._default_adapter",
            side_effect=RuntimeError("no cached weights"),
        ) as loader:
            report = run_pilot(self.manifest, self.output)
        loader.assert_called_once_with(allow_download=False, device="cpu")
        self.assertEqual(report["failed"], 2)
        self.assertEqual(report["answer_calls"], 0)
        self.assertTrue(
            all(row["error"]["stage"] == "model_load" for row in self.results())
        )

    def test_download_and_cuda_only_forwarded_when_explicit(self):
        with patch(
            "apps.baseline.runner._default_adapter", return_value=FakeAdapter()
        ) as loader:
            run_pilot(
                self.manifest,
                self.output,
                allow_download=True,
                device="cuda",
                max_new_tokens=8,
            )
        loader.assert_called_once_with(allow_download=True, device="cuda")

    def test_token_cap_matches_adapter_before_output_or_loading(self):
        for maximum in [True, 0, 129, 256, 1.5]:
            with (
                self.subTest(maximum=maximum),
                patch(
                    "apps.baseline.runner._default_adapter",
                    side_effect=AssertionError("must not load"),
                ),
            ):
                with self.assertRaises(ValueError):
                    run_pilot(self.manifest, self.output, max_new_tokens=maximum)
                self.assertFalse(self.output.exists())
        fake = FakeAdapter()
        run_pilot(self.manifest, self.output, adapter=fake, max_new_tokens=128)
        self.assertEqual(fake.calls[0][2], 128)

    def test_invalid_adapter_output_is_a_retained_failure(self):
        fake = FakeAdapter()
        with patch.object(fake, "answer", return_value=""):
            report = run_pilot(self.manifest, self.output, adapter=fake)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(self.results()[0]["error"]["type"], "ValueError")

    def test_output_conflict_does_not_execute_or_overwrite(self):
        self.output.mkdir()
        canary = self.output / "existing"
        canary.write_text("keep")
        fake = FakeAdapter()
        with patch(
            "apps.baseline.runner._default_adapter",
            side_effect=AssertionError("must not load"),
        ):
            with self.assertRaises(FileExistsError):
                run_pilot(self.manifest, self.output, adapter=fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(canary.read_text(), "keep")
        self.assertEqual(list(self.output.iterdir()), [canary])

    def test_all_input_validation_finishes_before_first_adapter_call(self):
        self.write([self.row, dict(self.row, id="test-2", image_sha256="0" * 64)])
        fake = FakeAdapter()
        with self.assertRaisesRegex(ValueError, "mismatch"):
            run_pilot(self.manifest, self.output, adapter=fake)
        self.assertFalse(self.output.exists())
        self.assertEqual(fake.calls, [])

    def test_schema_ids_unicode_and_record_limits(self):
        for rows in [
            [],
            [self.row, self.row],
            [dict(self.row, extra=1)],
            [dict(self.row, id="")],
            [dict(self.row, question="\ud800")],
            [dict(self.row, image_sha256="A" * 64)],
            [dict(self.row, id=str(i)) for i in range(21)],
        ]:
            self.write(rows)
            with self.subTest(rows=rows[:1]), self.assertRaises(ValueError):
                load_cases(self.manifest)
        for raw in [b"\xff", b"\n", b'{"id":1,"id":2}', b'{"x":NaN}']:
            self.manifest.write_bytes(raw)
            with self.assertRaises(ValueError):
                load_cases(self.manifest)

    def test_escape_symlink_and_nonregular_images(self):
        for image in [
            "/etc/passwd",
            "../image.png",
            "./image.png",
            "x//y",
            "x\\y",
            "image.png\x00",
        ]:
            self.write([dict(self.row, image=image)])
            with self.subTest(image=image), self.assertRaises(ValueError):
                load_cases(self.manifest)
        alias = self.root / "alias.png"
        alias.symlink_to(self.image)
        self.write([dict(self.row, image="alias.png")])
        with self.assertRaises(ValueError):
            load_cases(self.manifest)
        folder = self.root / "folder"
        folder.mkdir()
        (self.root / "alias-dir").symlink_to(folder)
        self.write([dict(self.row, image="alias-dir/image.png")])
        with self.assertRaises(ValueError):
            load_cases(self.manifest)
        os.mkfifo(self.root / "pipe")
        self.write([dict(self.row, image="pipe")])
        with self.assertRaises(ValueError):
            load_cases(self.manifest)

    def test_byte_caps_and_manifest_symlink(self):
        with (
            patch("apps.baseline.runner.MAX_IMAGE_BYTES", 4),
            self.assertRaises(ValueError),
        ):
            load_cases(self.manifest)
        with (
            patch("apps.baseline.runner.MAX_MANIFEST_BYTES", 4),
            self.assertRaises(ValueError),
        ):
            load_cases(self.manifest)
        alias = self.root / "alias.jsonl"
        alias.symlink_to(self.manifest)
        with self.assertRaises(ValueError):
            load_cases(alias)

    def test_private_artifacts_and_cli_dry_run_failure_codes(self):
        command = [
            sys.executable,
            "-m",
            "apps.baseline",
            str(self.manifest),
            "--output",
            str(self.output),
            "--dry-run",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["not_executed"], 1)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o600
                for path in self.output.iterdir()
            )
        )
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("pilot failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
