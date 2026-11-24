# Free notebook workflow

Upload `notebooks/kaggle-free-workflow.ipynb` into a fresh Kaggle Free notebook.
No cloud execution is claimed: Kaggle account/runtime setup remains manual.
The notebook pins source commit b89b8dfdfb2ac6f977b493fc775d37bea5f7b02a,
checks the checkout hash, and refuses an existing source/artifact directory.

The default path generates six synthetic scenes, creates an unexecuted source run,
revalidates its accounting, exports HTML and creates a diagonal self-comparison.
It installs nothing, imports no optional model runtime, and downloads no weights.
The initial public Git checkout requires network access. All subsequent default
pipeline cells were exercised locally in a clean Python subprocess with site
packages disabled. This does not validate Kaggle, CUDA, optional model packages,
real model inference or notebook browser behavior.

Live inference requires explicit RUN_MODEL=true, manually prepared compatible
runtime packages and optionally ALLOW_DOWNLOAD=true for public weights. CPU is
default. No GPU allocation or paid fallback is automated. Supervise free-session
time and storage yourself; no training or hard time watchdog is implemented.
Raw results, checked records, reports and comparisons are retained under a new
openforge-artifacts directory. Preserve them before the free session expires.
Failures are retained, not treated as successful model results.

Review answers, questions, IDs and digests before sharing artifacts. Narrow
synthetic pixel checks are pipeline evidence, not model accuracy or authenticated
runtime provenance. A dry-to-live status transition is not an accuracy improvement.
The delivered notebook has no saved outputs or execution counts. No payment,
credits, account rotation, security changes or deployment is needed.
