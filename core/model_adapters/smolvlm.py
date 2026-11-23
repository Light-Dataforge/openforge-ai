"""Pinned, bounded single-image SmolVLM adapter with an offline loading default."""

from __future__ import annotations

import importlib
import warnings
from io import BytesIO
from typing import Any

MODEL_ID = "HuggingFaceTB/SmolVLM-256M-Instruct"
MODEL_REVISION = "d039ab0d4b9311b617e8ffec1d06c8464364aeb3"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_SIDE = 1024
MAX_IMAGE_PIXELS = 1024 * 1024
MAX_PROMPT_CHARS = 2048
MAX_INPUT_TOKENS = 2048
MAX_NEW_TOKENS = 128


def _runtime() -> tuple[Any, Any, Any]:
    try:
        return (
            importlib.import_module("torch"),
            importlib.import_module("transformers"),
            importlib.import_module("PIL.Image"),
        )
    except ImportError as exc:
        raise RuntimeError(
            "Optional VLM runtime missing; see requirements-vlm.txt"
        ) from exc


class SmolVLMAdapter:
    """No network, model loading or optional imports occur at module import time.

    The constructor permits explicit runtime injection for contract tests. Such
    tests do not establish model inference, decoder correctness or model quality.
    """

    def __init__(
        self,
        *,
        processor: Any,
        model: Any,
        torch: Any,
        image_module: Any,
        device: str = "cpu",
    ) -> None:
        if not isinstance(device, str) or device not in {"cpu", "cuda"}:
            raise ValueError("device must be cpu or cuda")
        self._processor = processor
        self._model = model
        self._torch = torch
        self._image_module = image_module
        self._device = device
        self._dtype = torch.float32 if device == "cpu" else torch.float16

    @classmethod
    def from_pretrained(
        cls, *, allow_download: bool = False, device: str = "cpu"
    ) -> SmolVLMAdapter:
        if type(allow_download) is not bool:
            raise ValueError("allow_download must be a boolean")
        if not isinstance(device, str) or device not in {"cpu", "cuda"}:
            raise ValueError("device must be cpu or cuda")
        torch, transformers, image = _runtime()
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA explicitly requested but unavailable")
        shared = {
            "revision": MODEL_REVISION,
            "local_files_only": not allow_download,
            "trust_remote_code": False,
            "token": False,
        }
        try:
            processor = transformers.AutoProcessor.from_pretrained(
                MODEL_ID, use_fast=False, **shared
            )
            model = transformers.AutoModelForImageTextToText.from_pretrained(
                MODEL_ID,
                use_safetensors=True,
                use_kernels=False,
                allow_all_kernels=False,
                attn_implementation="eager",
                dtype=torch.float32 if device == "cpu" else torch.float16,
                **shared,
            )
            model.to(device)
            model.eval()
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                "Pinned model load failed; offline mode needs a cached snapshot"
            ) from exc
        return cls(
            processor=processor,
            model=model,
            torch=torch,
            image_module=image,
            device=device,
        )

    def answer(
        self, image_bytes: bytes, prompt: str, *, max_new_tokens: int = 64
    ) -> str:
        if (
            not isinstance(image_bytes, bytes)
            or not 1 <= len(image_bytes) <= MAX_IMAGE_BYTES
        ):
            raise ValueError("image must be 1 byte to 2 MiB of PNG or JPEG bytes")
        if not (
            image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            or image_bytes.startswith(b"\xff\xd8\xff")
        ):
            raise ValueError("only PNG or JPEG image bytes are supported")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_PROMPT_CHARS
        ):
            raise ValueError("prompt must contain 1 to 2048 characters")
        try:
            prompt.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("prompt must be valid Unicode") from exc
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= MAX_NEW_TOKENS:
            raise ValueError("max_new_tokens must be an integer from 1 to 128")
        image_module = self._image_module
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", image_module.DecompressionBombWarning)
                with image_module.open(
                    BytesIO(image_bytes), formats=["PNG", "JPEG"]
                ) as opened:
                    width, height = opened.size
                    if (
                        width <= 0
                        or height <= 0
                        or max(width, height) > MAX_IMAGE_SIDE
                        or width * height > MAX_IMAGE_PIXELS
                        or getattr(opened, "n_frames", 1) != 1
                    ):
                        raise ValueError(
                            "image dimensions/frames exceed the single-image limits"
                        )
                    opened.load()
                    decoded = opened.convert("RGB")
        except (
            OSError,
            ValueError,
            image_module.DecompressionBombWarning,
            image_module.DecompressionBombError,
        ) as exc:
            raise ValueError("invalid or oversized single PNG/JPEG image") from exc
        try:
            messages = [
                {
                    "role": "user",
                    "content": [{"type": "image"}, {"type": "text", "text": prompt}],
                }
            ]
            text = self._processor.apply_chat_template(
                messages, add_generation_prompt=True
            )
            inputs = self._processor(
                text=text,
                images=[decoded],
                return_tensors="pt",
                do_image_splitting=False,
                size={"longest_edge": 512},
            )
            input_length = inputs["input_ids"].shape[1]
            if not 1 <= input_length <= MAX_INPUT_TOKENS:
                raise ValueError("processed input exceeds 2048 tokens")
            inputs = inputs.to(self._device, dtype=self._dtype)
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **inputs,
                    do_sample=False,
                    num_beams=1,
                    max_new_tokens=max_new_tokens,
                )
            answers = self._processor.batch_decode(
                generated[:, input_length:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            if (
                not isinstance(answers, list)
                or len(answers) != 1
                or not isinstance(answers[0], str)
            ):
                raise RuntimeError("model decoder returned an invalid single answer")
            answer = answers[0].strip()
            if not answer or len(answer) > 8192:
                raise RuntimeError("model answer is empty or exceeds output limits")
            return answer
        finally:
            decoded.close()
