# Combined multimodal pilot

This combines original visual fixtures, a bounded raw-answer runner and an optional
pinned local vision-language adapter. The default check requires no model runtime,
weights, API keys or network. From the repository root, using new output paths:

```sh
mkdir -p work
python -c "from core.multimodal.fixtures import generate_fixtures; print(generate_fixtures('work/pilot-fixtures'))"
python -m apps.baseline work/pilot-fixtures/manifest.jsonl --output work/pilot-dry-run --dry-run
```

Create the `work` parent first if it does not exist. The fixture function and
runner each refuse to overwrite an existing output directory. The dry-run validates
all six generated PNGs and their hashes, writes one result row per task, marks every
task not_executed and performs no model imports, downloads or answer generation.
The output directory has request.json, results.jsonl and run.json. Synthetic smoke
tasks are original MIT fixtures, not a benchmark or evidence of reasoning quality.

## Optional live model run

Kaggle Free is the requested future provider; its account is not set up yet. No
notebook session, free GPU allocation, model execution or training is established.
The [free-compute protocol](free-compute-pilot.md) governs the $0 boundary. Do not
add billing, buy credits, switch accounts to evade quotas, or start a paid endpoint.

After the adapter's explicit runtime setup and local artifact preparation, real
inference uses the same CLI without --dry-run. By default, only already-cached
pinned artifacts may load; --allow-download is an explicit decision to fetch public
model files, not permission for remote code or a paid model API. CUDA must be
explicitly selected and actually available; no automatic paid/GPU fallback exists.
See [adapter setup](pilot-model-adapter.md) and [runner behavior](pilot-free-runner.md).

Only image bytes and the question are supplied to the adapter. IDs, filenames and
reference answers remain outside prompts; synthetic fixture IDs expose labels and
must never be used as extra model evidence. Raw generated answers and per-task
failures are retained. No invented confidence or calibrated probability is produced,
and raw pilot results are not passed into the confidence-requiring evaluator.

## Integration evidence and remaining gates

Cross-module tests use the actual generated fixture files and runner. They verify
model-free dry-run, input-hash failure before output/model load, exact prompt routing,
complete task accounting and injected adapter failure retention. Injected responses
are contract tests, not VLM predictions. CPU CI runs the combined suite; a dedicated
Pillow job independently decodes the PNG fixtures and reruns the integration checks.

This increment does not establish that the optional model runtime works on Kaggle,
that answers are reliable, or that training improves them. Next gates are account
setup, dependency/driver compatibility, an actual bounded unchanged-model run,
complete provenance exports, independent evaluation selection, and only then a
separately designed free-resource fine-tuning pilot. No hard watchdog or GPU-memory
sandbox is supplied by input/token caps; runtime/time budgets require supervision.
