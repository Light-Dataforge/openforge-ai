# Architecture decision 001: offline evaluation before model execution

Status: proposed foundation, implemented locally; not jointly approved.

Start with a dependency-free CPU evaluator to establish failure accounting and
reproducible input hashes before downloading models. Use the requested `core/`
monorepo layout, populated only with real capabilities. API, worker, dashboard,
model adapters and infrastructure remain roadmap items. This reduces operational
complexity and makes baseline reporting independently testable.

The evaluator reads bounded byte snapshots, validates complete files, joins by
ID, computes metrics in sorted ID order and emits one JSON report. Hashes identify
bytes actually read, not a filesystem snapshot spanning both files. Concurrent
edits are outside the contract; freeze inputs before evaluating. Reordering rows
changes provenance hashes but not scores. Reports contain no answers or IDs.

A future experiment manifest must bind hashes to dataset/model revisions, model
and dataset licenses, preprocessing, prompt/strategy, seed, decoding, software,
hardware, revision, elapsed time and failure classification. A metrics report
alone is insufficient evidence of an executed model experiment.

No inter-project dependency is required. ForgeTrain may eventually schedule jobs,
DataForge may supply manifests and AgentForge may supply permission-scoped traces.
Adapters must use versioned explicit contracts; do not import sibling checkout
paths or assume compatible licenses.
