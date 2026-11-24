import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.pilot_workflow.runner import run_workflow


class Answers:
    def __init__(self):
        self.values = iter(["blue", "blue", "narrative", None, "left", "blue"])

    def answer(self, image_bytes, prompt, *, max_new_tokens=64):
        value = next(self.values)
        if value is None:
            raise RuntimeError("private-source-error")
        return value


class PilotWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "workflow"

    def test_default_real_pipeline_retains_six_unexecuted_cases(self):
        with patch(
            "apps.baseline.runner._default_adapter",
            side_effect=AssertionError("not called"),
        ):
            summary = run_workflow(self.root)
        self.assertEqual(summary["verification_counts"]["not_executed"], 6)
        self.assertEqual(summary["source_counts"]["answered"], 0)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["mode"], "dry-run")
        self.assertFalse(summary["model_execution_verified"])
        self.assertTrue((self.root / "report.html").is_file())
        self.assertEqual(
            json.loads((self.root / "source-audit.json").read_text())["status"],
            "matches",
        )
        self.assertEqual(json.loads((self.root / "workflow.json").read_text()), summary)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(
            stat.S_IMODE((self.root / "workflow.json").stat().st_mode), 0o600
        )
        self.assertTrue(
            all((self.root / name).exists() for name in summary["artifacts"].values())
        )

    def test_injected_failures_and_abstentions_are_retained_not_success(self):
        summary = run_workflow(self.root, live=True, adapter=Answers())
        self.assertEqual(summary["source_adapter_mode"], "injected")
        self.assertEqual(summary["status"], "complete-with-source-failures")
        self.assertEqual(
            summary["verification_counts"],
            {
                "verified": 3,
                "contradicted": 1,
                "abstained": 1,
                "failed": 1,
                "not_executed": 0,
            },
        )
        self.assertNotIn(
            "private-source-error", (self.root / "report.html").read_text()
        )
        self.assertNotIn("private-source-error", json.dumps(summary))

    def test_model_load_failure_still_retains_all_evidence(self):
        with patch(
            "apps.baseline.runner._default_adapter",
            side_effect=ImportError("no runtime"),
        ):
            summary = run_workflow(self.root, live=True)
        self.assertEqual(summary["source_counts"]["failed"], 6)
        self.assertEqual(summary["verification_counts"]["failed"], 6)
        self.assertEqual(summary["status"], "complete-with-source-failures")
        self.assertTrue((self.root / "report.html").exists())

    def test_invalid_options_fail_before_creation(self):
        for options in [
            {"allow_download": True},
            {"device": "cuda"},
            {"live": 1},
            {"max_new_tokens": True},
            {"max_new_tokens": 129},
            {"adapter": Answers()},
            {"live": True, "adapter": Answers(), "allow_download": True},
        ]:
            with self.assertRaises(ValueError):
                run_workflow(self.root, **options)
            self.assertFalse(self.root.exists())

    def test_conflicts_never_overwrite_and_infrastructure_failure_has_no_completion(
        self,
    ):
        self.root.mkdir()
        (self.root / "keep").write_text("keep")
        with self.assertRaises(FileExistsError):
            run_workflow(self.root)
        self.assertEqual((self.root / "keep").read_text(), "keep")
        fresh = self.root / "fresh"
        with patch(
            "apps.pilot_workflow.runner.build_report", side_effect=OSError("failure")
        ):
            with self.assertRaises(OSError):
                run_workflow(fresh)
        self.assertTrue((fresh / "source/run.json").exists())
        self.assertFalse((fresh / "workflow.json").exists())

    def test_changed_source_observation_prevents_completion(self):
        with patch(
            "apps.pilot_workflow.runner.audit_source",
            return_value={"status": "different"},
        ):
            with self.assertRaises(ValueError):
                run_workflow(self.root)
        self.assertFalse((self.root / "workflow.json").exists())

    def test_cli_without_site_packages_has_no_optional_model_imports(self):
        code = (
            "import sys; from apps.pilot_workflow.__main__ import main; "
            f'sys.argv=["workflow","--output",{str(self.root)!r}]; '
            'result=main(); assert "torch" not in sys.modules; '
            'assert "transformers" not in sys.modules; raise SystemExit(result)'
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", code],
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cases"], 6)
        failed = subprocess.run(
            [sys.executable, "-m", "apps.pilot_workflow", "--output", str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertNotIn(str(self.root), failed.stderr)

    def test_cli_source_failures_exit_one_after_retaining_completion(self):
        code = (
            "import sys; from unittest.mock import patch; "
            "from apps.pilot_workflow.__main__ import main; "
            f"sys.argv=['workflow','--live','--output',{str(self.root)!r}]; "
            "guard=patch('apps.baseline.runner._default_adapter', "
            "side_effect=ImportError('synthetic missing runtime')); "
            "guard.start(); raise SystemExit(main())"
        )
        done = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout)["source_counts"]["failed"], 6)
        self.assertTrue((self.root / "workflow.json").exists())
        self.assertTrue((self.root / "report.html").exists())
