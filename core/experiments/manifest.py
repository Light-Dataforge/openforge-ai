"""Validate declared provenance and bind evaluation to the bytes actually read.

A valid declaration is not proof of model execution, licensing rights or hardware.
No artifacts are downloaded and no model, prompt or command is executed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from core.evaluation.metrics import evaluate

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_TEXT = 16384


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _record(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} requires exactly: {', '.join(sorted(fields))}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError(f"invalid {label}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"invalid Unicode in {label}") from exc
    return value


def _hex(value: Any, lengths: tuple[int, ...], label: str) -> str:
    text = _text(value, label)
    if len(text) not in lengths or not re.fullmatch(r"[0-9a-f]+", text):
        raise ValueError(f"{label} must be a full lowercase hexadecimal digest")
    return text


def validate_metadata(document: Any) -> dict[str, Any]:
    """Validate a version-1 declaration and return a detached JSON copy.

    Synthetic fixture declarations require null model/prompt/generation fields.
    Model declarations require pinned model, prompt and generation metadata.
    Dependencies are declared exact versions, not an installed-environment audit.
    """
    row = _record(
        document,
        {
            "schema_version",
            "run_kind",
            "model",
            "dataset",
            "inputs",
            "prompt",
            "preprocessing",
            "generation",
            "environment",
            "code_revision",
        },
        "manifest",
    )
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("unsupported manifest schema version")
    kind = row["run_kind"]
    if not isinstance(kind, str) or kind not in {"synthetic", "model"}:
        raise ValueError("run_kind must be synthetic or model")
    dataset = _record(row["dataset"], {"id", "revision", "license"}, "dataset")
    _text(dataset["id"], "dataset ID")
    _text(dataset["license"], "dataset license declaration")
    _hex(dataset["revision"], (40, 64), "dataset revision")
    inputs = _record(row["inputs"], {"reference_sha256", "prediction_sha256"}, "inputs")
    for key, value in inputs.items():
        _hex(value, (64,), key)
    processor = _record(row["preprocessing"], {"id", "revision"}, "preprocessing")
    _text(processor["id"], "preprocessing ID")
    _hex(processor["revision"], (40, 64), "preprocessing revision")
    _hex(row["code_revision"], (40, 64), "code revision")
    environment = _record(
        row["environment"],
        {"python", "platform", "hardware", "dependencies"},
        "environment",
    )
    for key in ("platform", "hardware"):
        _text(environment[key], key)
    if not re.fullmatch(
        r"3\.[0-9]+\.[0-9]+", _text(environment["python"], "Python version")
    ):
        raise ValueError("Python version requires a full 3.x.y version")
    dependencies = environment["dependencies"]
    if not isinstance(dependencies, dict) or len(dependencies) > 256:
        raise ValueError("dependencies must be a version map with at most 256 entries")
    for name, version in dependencies.items():
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", _text(name, "dependency name")
        ):
            raise ValueError("invalid dependency name")
        if not re.fullmatch(
            r"[0-9][A-Za-z0-9.+_-]{0,127}", _text(version, "dependency version")
        ):
            raise ValueError("dependency versions must be exact, not ranges or aliases")
    if kind == "synthetic":
        if any(row[key] is not None for key in ("model", "prompt", "generation")):
            raise ValueError(
                "synthetic fixtures require null model, prompt and generation"
            )
    else:
        model = _record(row["model"], {"id", "revision", "license"}, "model")
        _text(model["id"], "model ID")
        _text(model["license"], "model license declaration")
        _hex(model["revision"], (40, 64), "model revision")
        prompt = _record(row["prompt"], {"text", "sha256"}, "prompt")
        text = _text(prompt["text"], "prompt text")
        expected = _hex(prompt["sha256"], (64,), "prompt SHA-256")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise ValueError("prompt SHA-256 mismatch")
        config = _record(
            row["generation"], {"seed", "temperature", "max_new_tokens"}, "generation"
        )
        if type(config["seed"]) is not int or not 0 <= config["seed"] < 2**32:
            raise ValueError("seed must be an unsigned 32-bit integer")
        temperature = config["temperature"]
        if (
            type(temperature) not in (int, float)
            or not 0 <= temperature <= 2
            or not math.isfinite(temperature)
        ):
            raise ValueError("temperature must be finite and between 0 and 2")
        if (
            type(config["max_new_tokens"]) is not int
            or not 1 <= config["max_new_tokens"] <= 32768
        ):
            raise ValueError("max_new_tokens must be an integer from 1 to 32768")
    detached: dict[str, Any] = json.loads(json.dumps(row, allow_nan=False))
    return detached


def evaluate_manifest(
    manifest: str | Path, references: str | Path, predictions: str | Path
) -> dict[str, Any]:
    """Validate metadata and evaluate matching artifacts, without executing a model.

    Paths are explicit CLI/library inputs, not executable or downloadable manifest
    instructions. Reports omit prompt text, model names and environment details.
    """
    with open(manifest, "rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds 1 MiB")
    try:
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
    except RecursionError as exc:
        raise ValueError("manifest nesting is too deep") from exc
    metadata = validate_metadata(document)
    result = evaluate(references, predictions)
    for key, expected in metadata["inputs"].items():
        if result[key] != expected:
            raise ValueError(f"artifact mismatch: {key}")
    return {
        "schema_version": 1,
        "run_kind": metadata["run_kind"],
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "model_execution_verified": False,
        "metrics": result,
    }
