# Verify saved pilot answers, offline

```sh
python -m apps.pilot_verification pilot-run fixtures/manifest.jsonl --output verified-run
```

This composes the saved raw-answer pilot and the narrow pixel verifier. It reads
run.json/results.jsonl and a frozen fixture manifest, checks complete unique task
coverage, raw input hashes, durations, source counts and lifecycle consistency,
then verifies supported answer claims against the actual image bytes. No model,
network, GPU, Kaggle account or optional runtime is loaded. A new private output
directory contains results.jsonl and summary.json; existing directories are refused.

Normalizing answers means only strip surrounding whitespace and lowercase. It does
not remove punctuation, extract digits from prose, repair leading zeros or guess
which phrase is the answer. Supported canonical answers are checked through the
existing exact question grammar. Unsupported questions, narrative answers or
unsupported/ambiguous pixel profiles abstain. Failed source tasks remain failed;
dry-run tasks remain not_executed and do not invoke the pixel verifier.

Reference labels are checked only for source-record consistency and are not passed
to verification. Each verification uses image bytes, the question-routed claim and
candidate answer. Source error messages are omitted from new output; stage/type
remain for failure classification. Raw answers can still contain sensitive data:
inspect them before sharing. No confidence, accuracy or improvement score is
invented. Counts describe verification decisions, not correctness on a benchmark.

The source adapter mode is explicitly declared as injected or local-smolvlm.
Artifact binding does not authenticate model execution, source runtime metadata,
image provenance or licensing. source_execution_verified=false remains explicit;
performs_model_inference=false describes this replay tool, not a claim that no
upstream model ever ran. Synthetic integration adapters are not real model results.

Bounds: 20 tasks, 64 KiB run metadata, 2 MiB source/results JSONL, and the existing
2 MiB/image and narrow pixel-profile limits. Complete validation/computation precedes
output creation. Byte limits are not a CPU/memory sandbox. Use trusted immutable
regular files and stable local directories; filesystem races and authenticity are
not guaranteed. JSON duplicate keys, nonfinite values, mismatched IDs/hashes/counts,
invalid states and symlink input are rejected. I/O/validation errors exit2 with no
partial stdout. Exit0 means a valid completed verification report, not all claims
verified. Publication is not an atomic multi-file transaction: interrupted output
can leave a partial new directory, never an overwrite of an existing one.

Tests cover the actual generated images and pilot records, wrong/correct/case-
normalized/narrative answers, retained model-load/per-task failures, dry-run no-call
behavior, tampered files, rehashed duplicate IDs, bad states, calls/counts/schema,
symlinks, output conflicts and real CLI behavior. No live model was used.
