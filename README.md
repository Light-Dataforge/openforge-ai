# OpenForge AI

Early research foundation for reliable multimodal reasoning agents.
Implemented today: an offline exact-answer evaluator with strict JSONL contracts,
explicit abstention accounting, conditional Brier score, SHA-256 provenance,
and versioned experiment-manifest validation.
A combined multimodal pilot adds original PNG fixtures, a bounded raw-answer
runner and an optional pinned local model adapter. No live model run, training or
general agent execution is claimed.
No model-quality claims or benchmark improvements are made.

## Run and test

Python 3.12+; no dependencies, network, credentials or GPU required. From this directory:

```sh
python3 -m core.evaluation examples/references.jsonl examples/predictions.jsonl
python3 -m core.experiments examples/synthetic-manifest.json examples/references.jsonl examples/predictions.jsonl
python3 -m unittest discover -s tests -v
```

Each reference has exactly `id` and nonempty string `answer`. Each prediction has
exactly `id`, `answer`, `confidence`. IDs must be unique and both files must cover
exactly the same IDs. An abstention requires null answer and null confidence.
An answered prediction requires confidence in [0,1], interpreted as probability
of exact correctness. Duplicate keys, invalid UTF-8, surrogate strings, nonfinite
numbers, blank records and extra fields fail validation. Limits: 8 MiB/file,
10,000 records/file, 4,096 characters/string. The CLI exits 2 on invalid input and
prints no partial report. Outputs use stdout; input files are never rewritten.

Coverage is answered/total; accuracy_all is correct/total, counting abstention as
not correct; accuracy_answered is correct/answered. Brier score is the mean of
(confidence - correctness)^2 over answered predictions. Conditional metrics are
null when all records abstain. Always compare conditional metrics with coverage.
Matching is case-sensitive, exact string equality without normalization.

The three example records are original synthetic accounting fixtures, not model
outputs or a multimodal benchmark. Their scores only demonstrate the evaluator.

For development checks, install `requirements-dev.txt`, then run `ruff check core tests`,
`ruff format --check core tests` and `mypy`. Only development tooling has dependencies.

## Architecture and development

`core/evaluation/metrics.py` validates inputs and calculates pure metrics;
`__main__.py` provides a failure-safe CLI. Tests exercise the actual CLI as well
as validation and metric semantics. CI checks Python 3.12–3.14; consult the current GitHub
checks for execution results. Future components will be added when implemented, rather than
creating empty model, service, dashboard and infrastructure directories now.

See [experiment manifests](docs/experiment-manifests.md),
[architecture](docs/architecture.md), [research](docs/research.md),
[governance](docs/governance.md), [contributing](CONTRIBUTING.md) and
[security](SECURITY.md). Initial roadmap: review experiment contracts; integrate
one licensed VLM; establish a pinned baseline; compare budget-matched verification;
then add permission-scoped tools and a research dashboard.

Current limitations: exact matching cannot judge free-form correctness, ground
answers in images or verify evidence. No calibration curve, uncertainty interval,
latency/cost tracking, semantic judge, persistent experiment store or dependency
security scanner exists. Inputs are bounded local files, not untrusted streams.
MIT license applies to original code and synthetic fixtures only.

The [zero-cost compute pilot](docs/free-compute-pilot.md) documents the pinned
model candidate, resource limits and execution gates. It is planning only; no
model download, inference or training is claimed.

Start with the [combined multimodal pilot](docs/multimodal-pilot.md) for a fully
model-free dry-run and the remaining gates before a real Kaggle Free model run.

## Run the CPU pixel-verification demo

`python -m apps.verification_demo --output verification-results` checks twelve
synthetic claims against actual pixels and retains evidence. No model or Kaggle
account is needed. It is a narrow geometric conformance demo, not general visual
reasoning. See [supported claims and limits](docs/verification-demo.md).

Export a local, read-only [pixel-evidence report](docs/evidence-report.md) with
`python -m apps.evidence_report verification-results --output evidence.html`.
It embeds the scenes and revalidates decisions without a browser service or GPU.
