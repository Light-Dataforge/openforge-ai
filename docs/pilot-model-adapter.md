# Pinned SmolVLM single-image pilot adapter

The pilot adapter implements this interface without importing optional ML packages
until the explicit loader is called:

```python
from core.model_adapters.smolvlm import SmolVLMAdapter

adapter = SmolVLMAdapter.from_pretrained(allow_download=False, device="cpu")
answer = adapter.answer(image_bytes, "Which option is shown?", max_new_tokens=64)
```

The fixed public model is `HuggingFaceTB/SmolVLM-256M-Instruct` at revision
`d039ab0d4b9311b617e8ffec1d06c8464364aeb3`. Its pinned card declares Apache-2.0
and its config uses `Idefics3ForConditionalGeneration`. This is the original
SmolVLM-256M snapshot, not a similarly named SmolVLM2 video model. The current
Transformers generic `AutoModelForImageTextToText` mapping includes Idefics3.
[Model card and config](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct/tree/d039ab0d4b9311b617e8ffec1d06c8464364aeb3)
[Official mapping](https://github.com/huggingface/transformers/blob/v5.24.0/src/transformers/models/auto/modeling_auto.py)

## Optional runtime and free notebook setup

The direct package pins in requirements-vlm.txt were checked against official
registry metadata on November 23, 2026:

| Package | Pin | Registry Python requirement |
| --- | --- | --- |
| torch | 2.15.0 | >=3.11 |
| transformers | 5.24.0 | >=3.11 |
| Pillow | 13.0.0 | >=3.11 |
| safetensors | 0.8.0 | >=3.10 |

The registry listed no published advisories for these exact versions at check
time. Earlier candidate pins torch 2.7.1, transformers 4.57.6 and Pillow 11.3.0
had listed advisories and were not retained. This is a dated advisory/metadata
check, not proof of safety, a full transitive dependency audit or actual runtime
compatibility testing. The selected direct dependencies are pinned; transitive
versions must still be captured from the actual pilot environment.
[torch metadata](https://pypi.org/pypi/torch/2.15.0/json),
[Transformers metadata](https://pypi.org/pypi/transformers/5.24.0/json),
[Pillow metadata](https://pypi.org/pypi/Pillow/13.0.0/json),
[safetensors metadata](https://pypi.org/pypi/safetensors/0.8.0/json).

For an explicitly chosen free Linux CPU notebook with Python 3.12/3.13, install
the official CPU torch build first, then the optional package list:

```sh
python -m pip install 'torch==2.15.0' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-vlm.txt
```

The CPU index was checked for a Python 3.12 Linux x86_64 wheel listing; no wheel
was downloaded or installed for this task. A local +cpu build satisfies the public
version pin. Installing the requirements directly into a clean Linux environment
without selecting CPU first can download the default CUDA runtime dependencies.
This setup is not asserted to work on the audited Intel Mac; use a clean supported
free Linux notebook. No paid accelerator is required or automatically allocated.

CUDA is an independent explicit choice (`device="cuda"`), accepted only when the
installed torch runtime reports CUDA available. A free notebook must already
provide a GPU allocation and a driver-compatible official torch build at the
pinned public version. Inspect the provider's runtime and the
[official PyTorch installation selector](https://pytorch.org/get-started/locally/)
before choosing a CUDA wheel. No Kaggle account/runtime, driver, CUDA compatibility
or GPU inference has been tested here. If unavailable, stop or explicitly choose
a CPU setup; the adapter never silently switches hardware or provisions anything.
No heavyweight runtime package, model weights or GPU allocation was obtained here.

## Loader and inference bounds

Both processor and model use the exact revision, local_files_only by default,
trust_remote_code=false and token=false. Explicit allow_download=true permits
public artifact downloads from the model hub; it does not enable paid inference.
Weights must be safetensors. use_kernels and allow_all_kernels are explicitly
false; eager attention is selected rather than remote attention kernels. The model moves to the explicitly selected device and
uses eval/inference mode; generation is greedy with one beam.

Only PNG/JPEG bytes up to 2 MiB are accepted. Pillow header dimensions are checked
before pixel loading: at most 1,024 pixels per side, 1,048,576 pixels total and one
frame. Decompression-bomb warnings/errors are rejected. Images are converted to
RGB; preprocessing disables image splitting and caps its longest edge at 512.
Prompts must be nonblank valid Unicode, at most 2,048 characters. Processed input
is capped at 2,048 tokens. Output requests are 1–128 new tokens, default 64; only
tokens after the input prefix are decoded. Empty/invalid/oversized decoded answers
fail. The caller must record failures, rather than silently skipping examples.

These bounds do not impose a hard wall-clock or process memory limit. Decoder,
model, native libraries and cache are trusted; this is not a sandbox. Greedy
sampling is not a cross-platform reproducibility guarantee. No confidence score,
evidence-verification improvement or model accuracy is established by the adapter.
Use a separate worker/supervisor for cancellation and hard resource enforcement.

## Validation and current unknowns

The unit tests inject synthetic processor/model/torch/image objects and make no
real model call. Their fake image fixture is explicitly not an actual PNG. They
check offline/pinning/security kwargs, explicit CUDA rejection, optional-import
behavior, byte/prompt/token/dimension limits, output prefix slicing and cleanup.
They establish the adapter contract, not Pillow decoding, package interoperability,
weight availability, CPU/GPU feasibility or multimodal quality. A real frozen
image/text pilot must still run with the exact environment and cached/downloaded
snapshot, preserving actual outputs and failures. No such run is claimed here.
