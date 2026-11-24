# One-command local pilot workflow

```sh
python -m apps.pilot_workflow --output NEW_DIRECTORY
```

The default path creates six original synthetic images, records a dry run with zero
answer calls, verifies all saved task states, exports self-contained HTML and audits
the observed source receipt. It needs no model packages, network, credentials or GPU.
It installs nothing and allocates no cloud resource. Existing output directories,
including symlinks, are refused. The root is private mode0700; completion/audit JSON
uses the existing private exclusive publisher.

After manually preparing the compatible optional runtime, a caller may explicitly
select `--live`. Model downloads require the additional `--allow-download` flag;
CPU remains default, CUDA requires `--device cuda`. Model options without live mode
are rejected before output creation. The Python API also supports explicitly
injected adapters for testing; these remain labeled injected, not model results.
No training, paid endpoint, runtime installation, GPU allocation or paid fallback
is automated. Resource time is operator-supervised, not a hard watchdog.

Stages produce fixtures/manifest.jsonl, source/, verification/, report.html,
source-audit.json and workflow.json. The final JSON records complete source and
verification counts plus reproduction digests; it is written only after all stages
finish and the observed source receipt matches. A repeated verification inside the
report must match the first check. Infrastructure errors can leave a partial new
directory without workflow.json; retained source evidence is never deleted.

Source model-load/answer failures are data, not infrastructure success: they remain
in every downstream artifact and produce complete-with-source-failures. CLI exit1
signals such source failures after evidence publication; exit0 completes without
source failures (including a dry run); exit2 signals invalid options/I/O/stage errors.
An exit0 dry run does not mean a model ran or answered correctly. No model accuracy,
confidence, general image understanding or runtime authenticity is established.
model_execution_verified remains false. Source directories/host must be trusted and
frozen; there is no atomic multi-file snapshot or hostile-filesystem isolation.

Raw source records contain reference labels, answers and failure messages; reports
contain questions, answers and task metadata. Review artifacts before sharing.
Observed source hashes neither authenticate declarations nor prove loaded code.
This wrapper is local only: it does not set up Kaggle, execute a cloud notebook,
publish results, merge code or deploy a service.
