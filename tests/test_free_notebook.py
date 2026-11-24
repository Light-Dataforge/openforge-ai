import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FreeNotebookTests(unittest.TestCase):
    def notebook(self):
        return json.loads(Path("notebooks/kaggle-free-workflow.ipynb").read_text())

    def test_empty_outputs_pinned_source_and_explicit_live_opt_ins(self):
        notebook = self.notebook()
        self.assertEqual(notebook["nbformat"], 4)
        codes = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        for cell in codes:
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            ast.parse("".join(cell["source"]))
        setup = "".join(codes[0]["source"])
        self.assertIn("b89b8dfdfb2ac6f977b493fc775d37bea5f7b02a", setup)
        self.assertIn("actual != REVISION", setup)
        self.assertIn('checkout", "--detach"', setup)
        live = ast.parse("".join(codes[-1]["source"]))
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in live.body
            if isinstance(node, ast.Assign)
        }
        self.assertIs(assignments["RUN_MODEL"], False)
        self.assertIs(assignments["ALLOW_DOWNLOAD"], False)
        self.assertEqual(assignments["DEVICE"], "cpu")

    def test_default_cells_execute_local_pipeline_without_optional_model_imports(self):
        codes = [
            "".join(cell["source"])
            for cell in self.notebook()["cells"]
            if cell["cell_type"] == "code"
        ]
        # Exercise all operational cells after checkout in a clean subprocess,
        # using this local snapshot. No clone, network, runtime install or weights.
        repo = Path.cwd()
        script = (
            "from pathlib import Path\nimport json,sys\n"
            + f"REPO=Path({str(repo)!r})\n"
            + "\n".join(codes[1:])
            + '\nassert "torch" not in sys.modules\n'
            + 'assert "transformers" not in sys.modules\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(repo))
            result = subprocess.run(
                [sys.executable, "-S", "-c", script],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            root = Path(tmp) / "openforge-artifacts"
            self.assertTrue((root / "dry-report.html").is_file())
            comparison = json.loads((root / "dry-self-comparison.json").read_text())
            self.assertEqual(
                comparison["transitions"]["not_executed"]["not_executed"], 6
            )
            self.assertFalse((root / "live-run").exists())
