# Zero-cost multimodal baseline pilot

Status: research preparation only. No model weights have been downloaded, no
inference/training experiment has run, and no free GPU allocation is reserved.
The budget is $0; do not attach billing, buy credits, enable a paid API, rent a
worker or upgrade automatically. GPU shortages defer the run rather than spending.

## Candidate and license gate

Candidate: HuggingFaceTB/SmolVLM-256M-Instruct at immutable revision
`d039ab0d4b9311b617e8ffec1d06c8464364aeb3`. The public model metadata reports
Apache-2.0 and ungated access. It is an image/text-to-text model small enough to
justify a resource pilot, not a claim of adequate accuracy or measured local fit.
See the [publisher model card](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct)
and [metadata API](https://huggingface.co/api/models/HuggingFaceTB/SmolVLM-256M-Instruct).
The candidate JSON records the inspected revision; no moving branch is a run pin.

Before inference, review the pinned license/model card and dependency compatibility,
resolve and freeze stable package versions, and record the processor configuration.
Use safetensors and trust_remote_code=false; do not install Hub custom code or
optional remote kernels. The relevant [Transformers interface](https://huggingface.co/docs/transformers/model_doc/smolvlm)
is a starting reference, not a completed compatibility test for the candidate.

## Compute allocation

1. Local machine: CPU data preparation, unit tests and experiment validation.
   Current audited Python is 3.13.9 on Intel macOS, with no torch/transformers/Pillow
   installed in the system interpreter. No compatible local VLM runtime is verified.
2. Kaggle: attempt one legitimate free notebook session with accelerator access
   actually offered to the account. Check the displayed quota and stop it after use.
   [Official notebook documentation](https://www.kaggle.com/docs/notebooks).
3. Colab Free: alternative interactive notebook session if a suitable free GPU is
   offered. Availability, hardware and session limits are variable. Do not assume
   continuous service or deploy a server/distributed worker through the free tier.
   Do not rotate accounts to bypass limits. [Official FAQ](https://research.google.com/colaboratory/faq.html).

No provider account/session has yet been connected for this pilot. Never report a
GPU run from notebook source, dry-run output, synthetic fixtures or a reservation.

## Proposed bounded execution

Start with batch size 1, one image per example, maximum image edge 512 pixels,
maximum 64 generated tokens and at most 20 original synthetic smoke examples.
These are proposed pilot limits, not benchmark settings or guaranteed runtime.
Use greedy decoding, a recorded seed and an explicit processor/image-splitting
configuration. Record actual model load time, per-example latency, peak memory,
software/hardware and failures. Stop on incompatible software, out-of-memory,
quota loss or a 30-minute pilot budget; do not silently switch model or hardware.

Generate simple original shapes/charts with known answers to check the plumbing.
Keep these explicitly synthetic and separate from research evaluation. They can
reveal obvious pipeline errors but cannot support general reasoning claims.
Before a real baseline, select a public dataset with documented item licenses,
version and fixed development/evaluation selection. No benchmark has been chosen.

## Artifacts and verification

Export actual predictions with stable IDs, reference labels, image-byte hashes,
prompt text/hash, pinned model/data/processor revisions and the full experiment
manifest. Keep every reference task in accounting, including failures. The current
evaluator requires a finite confidence for answered records: design and document
confidence extraction/calibration before integrating real predictions. Do not
invent confidence values or call token likelihood calibrated answer confidence.
Synthetic manifests must remain synthetic; model manifests describe actual runs.

Use atomic bounded exports and verify hashes before scoring. Preserve the raw
answer separately from any declared normalization policy. The existing exact-string
scorer is not a complete multimodal benchmark scorer or evidence verifier.

## Training decision gate

First establish a reproducible unchanged-model baseline and useful error taxonomy.
Then, if actual free hardware and remaining quota permit, design a small LoRA pilot
with licensed training data and an independent evaluation split. Tune no thresholds
on held-out evaluation. Save adapter checkpoints and exact configs so interruption
can resume. Training is optional for the one-week MVP; from-scratch model training,
large-scale distributed training and unmeasured improvement claims are excluded.

## Acceptance of this planning increment

Pinned candidate/source and $0 boundaries documented; actual execution is still
pending runtime setup and allocation. This document is not a runnable notebook,
implemented model adapter, completed fine-tune or scientific result.
