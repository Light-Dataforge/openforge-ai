# Prepared local/free-compute baseline pilot

The pilot validates a small frozen fixture manifest, optionally runs a cached local
SmolVLM adapter, and saves raw per-task answers, failures and resource metadata.
It does not score confidence, reuse the exact-answer confidence evaluator, train a
model or establish benchmark results. Fixtures with answer-identifying filenames
are synthetic smoke data, not reliable evaluation evidence.

## Validate without loading a model

From an integrated checkout containing the fixture generator:

```python
from core.multimodal.fixtures import generate_fixtures
manifest = generate_fixtures("new-fixtures-directory")
```

The generator must receive a new directory, not an existing temporary root. Then:

```sh
python -m apps.baseline new-fixtures-directory/manifest.jsonl --output new-dry-run --dry-run
```

Dry-run validates all metadata, files and byte hashes, creates a new private output
directory and marks every task not_executed with null answer/latency. It never
imports the adapter, downloads weights or calls an injected adapter. Even if
--allow-download is supplied, dry-run does not load anything.

Each UTF-8 JSONL record has exactly id, image, question, answer and image_sha256.
There must be 1–20 unique IDs and no blank records or duplicate JSON keys. Image
paths are canonical relative POSIX paths under the manifest directory. Absolute,
dot/parent, backslash, symlink and nonregular input paths are rejected. SHA-256
must match actual captured bytes. Caps: 512 KiB manifest, 2 MiB per image, 4,096
characters/question/reference answer. Image format decoding belongs to the model
adapter; metadata validation alone does not establish valid image contents.

## Prepared real-mode command

After integrating the reviewed model-adapter and fixture branches, installing the
adapter's pinned requirements-vlm.txt and reviewing its model/license contract:

```sh
python -m apps.baseline new-fixtures-directory/manifest.jsonl --output new-cpu-run
```

The default adapter import is lazy. from_pretrained receives allow_download=False
and device="cpu". Without cached weights or optional dependencies, every case is
retained as a model_load failure; no task silently disappears. Explicit
--allow-download permits only the adapter's documented model artifact download.
--device cuda selects already available CUDA hardware; it does not allocate any
cloud resource or paid endpoint. The runner supplies a 64-token generation cap by
default (configurable 1–256).

For a future user-managed Kaggle Free session, this is prepared code only. No
Kaggle account, notebook session, allocation or inference run has been established
or executed by this work. Do not upgrade or select paid compute. If free resources
are unavailable, retain the actual failure evidence and stop rather than inventing
a run or allocating a paid alternative. No executed notebook is claimed here.

## Outputs and failure accounting

The output directory must not exist. A conflict aborts before model loading or
answer calls. Mode 0700 directory and mode 0600 files contain:

- request.json: validated request/software/hardware metadata and initial state.
- results.jsonl: one ordered raw answer or explicit error per task, including ID,
  image/reference hashes, question/reference answer, answer, latency and status.
- run.json: final counts, model-load/call accounting and SHA-256 of results.jsonl.

Only image bytes and the question are passed to answer(..., max_new_tokens=...).
IDs, filenames and reference answers remain output metadata and never enter the
model prompt. No confidence values or quality scores are invented. Injected test
adapters are labeled injected and are never represented as real-model results.
model_execution_verified remains false; metadata is not an execution attestation.

Each task is flushed/fsynced after writing. Ordinary per-answer errors are retained
and later cases continue. Model-load failure produces a failure row for every
case. Unexpected supervisor interruption can leave request.json and partial
results.jsonl without run.json: treat that directory as incomplete, preserve the
evidence and use a different new output directory for a retry. There is no hidden
resume, overwrite mode, atomic multi-file transaction or wall-time cancellation.
The model token cap is not a host memory/time/disk quota. The planning document's
30-minute pilot duration is an operator budget, not an enforced watchdog deadline.

CLI exits 0 for a complete dry-run or no failed tasks, 1 for recorded model/task
failures, 2 for malformed input, output conflicts or I/O setup errors. Error paths
emit no partial summary to stdout. Raw result/error metadata can contain private
inputs and local model diagnostics; inspect it before sharing. Installed package
versions are discovered without importing those model packages, and reported
hardware/software details are descriptive metadata, not measured GPU utilization.

## Reproduction and integration tests

`run_pilot(manifest, output_dir, adapter=fake_adapter)` supports injected contract
adapters. Tests deliberately use fake byte payloads and fake model answers, covering
routing, malformed IDs/JSON, symlinks/path traversal, byte/hash caps, full failure
accounting, dry-run nonexecution, private artifacts and CLI conflicts. These tests
are not real model inference. Real mode requires the peer adapter module only at
load time, so the unit suite passes before that branch is integrated.
