import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.evaluation.metrics import evaluate
from core.experiments.manifest import evaluate_manifest
from core.local_files import read_regular


class RegularInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO support required")
    def test_fifos_in_all_five_cli_positions_fail_promptly_without_stdout(self):
        fifo = self.root / "no-writer.pipe"
        os.mkfifo(fifo)
        refs, preds, manifest = (
            "examples/references.jsonl",
            "examples/predictions.jsonl",
            "examples/synthetic-manifest.json",
        )
        cases = [
            ("core.evaluation", [str(fifo), preds]),
            ("core.evaluation", [refs, str(fifo)]),
            ("core.experiments", [str(fifo), refs, preds]),
            ("core.experiments", [manifest, str(fifo), preds]),
            ("core.experiments", [manifest, refs, str(fifo)]),
        ]
        for module, args in cases:
            with self.subTest(module=module, args=args):
                result = subprocess.run(
                    [sys.executable, "-m", module, *args],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("regular file", result.stderr)

    def test_symlink_and_directory_inputs_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(Path("examples/references.jsonl").resolve())
        with self.assertRaises((OSError, ValueError)):
            evaluate(alias, "examples/predictions.jsonl")
        with self.assertRaises((OSError, ValueError)):
            evaluate_manifest(
                alias, "examples/references.jsonl", "examples/predictions.jsonl"
            )
        with self.assertRaises((OSError, ValueError)):
            read_regular(self.root, 100)

    def test_descriptor_closed_on_success_oversize_and_nonregular_rejection(self):
        path = self.root / "file"
        path.write_bytes(b"1234")
        actual_close = os.close
        for selected, limit in [(path, 4), (path, 3), (self.root, 100)]:
            closed = []

            def close(fd, closed=closed):
                closed.append(fd)
                actual_close(fd)

            with patch("core.local_files.os.close", side_effect=close):
                try:
                    read_regular(selected, limit)
                except (OSError, ValueError):
                    pass
            self.assertEqual(len(closed), 1)
            with self.assertRaises(OSError):
                os.fstat(closed[0])

    def test_exact_limit_and_invalid_limits(self):
        path = self.root / "bounded"
        path.write_bytes(b"1234")
        self.assertEqual(read_regular(path, 4), b"1234")
        with self.assertRaises(ValueError):
            read_regular(path, 3)
        for limit in [True, 0, -1, 1.5]:
            with self.assertRaises(ValueError):
                read_regular(path, limit)

    def test_regular_examples_still_evaluate_and_input_bytes_unchanged(self):
        refs = Path("examples/references.jsonl")
        preds = Path("examples/predictions.jsonl")
        before = (refs.read_bytes(), preds.read_bytes())
        direct = evaluate(refs, preds)
        manifest = evaluate_manifest("examples/synthetic-manifest.json", refs, preds)
        self.assertEqual(direct, manifest["metrics"])
        self.assertEqual(before, (refs.read_bytes(), preds.read_bytes()))
