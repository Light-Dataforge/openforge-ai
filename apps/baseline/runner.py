"""Bounded fixture validation and failure-preserving vision-language pilot runs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import time
from dataclasses import dataclass
from importlib import import_module, metadata
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

MAX_CASES = 20
MAX_MANIFEST_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
FIELDS = {"id", "image", "question", "answer", "image_sha256"}


class Adapter(Protocol):
    def answer(
        self, image_bytes: bytes, prompt: str, *, max_new_tokens: int = 64
    ) -> str: ...


@dataclass(frozen=True)
class Case:
    identifier: str
    image: str
    question: str
    expected_answer: str
    image_bytes: bytes
    image_sha256: str


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _text(value: Any, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"invalid {label}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"invalid Unicode in {label}") from exc
    return value


def _bounded_regular(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise ValueError("symlink inputs are not supported")
    flags = os.O_RDONLY | os.O_NONBLOCK
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("pilot inputs require no-follow local file support")
    fd = os.open(path, flags | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("input must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
    finally:
        os.close(fd)
    if len(raw) > limit:
        raise ValueError("input exceeds its byte limit")
    return raw


def load_cases(manifest: str | Path) -> tuple[tuple[Case, ...], str]:
    """Validate every record and frozen image before executing any adapter call."""
    source = Path(manifest)
    raw = _bounded_regular(source, MAX_MANIFEST_BYTES)
    root = source.parent.resolve(strict=True)
    lines = raw.decode("utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    if not 1 <= len(lines) <= MAX_CASES:
        raise ValueError("pilot requires 1 to 20 cases")
    cases = []
    ids: set[str] = set()
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)
        except (ValueError, RecursionError) as exc:
            raise ValueError(f"invalid JSON at line {number}") from exc
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError(f"invalid case fields at line {number}")
        identifier = _text(row["id"], "ID", 128)
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier)
            or identifier in ids
        ):
            raise ValueError("invalid or duplicate case ID")
        ids.add(identifier)
        question = _text(row["question"], "question")
        expected = _text(row["answer"], "reference answer")
        image = _text(row["image"], "image path")
        relative = PurePosixPath(image)
        if (
            relative.is_absolute()
            or "\\" in image
            or "\x00" in image
            or any(part in {"", ".", ".."} for part in image.split("/"))
        ):
            raise ValueError("image must be a canonical relative POSIX path")
        path = root
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError("symlink image paths are not supported")
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("image path escapes fixture root")
        expected_hash = _text(row["image_sha256"], "image SHA-256", 64)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("image SHA-256 must be lowercase hexadecimal")
        image_bytes = _bounded_regular(path, MAX_IMAGE_BYTES)
        digest = hashlib.sha256(image_bytes).hexdigest()
        if digest != expected_hash:
            raise ValueError(f"image SHA-256 mismatch at line {number}")
        cases.append(Case(identifier, image, question, expected, image_bytes, digest))
    return tuple(cases), hashlib.sha256(raw).hexdigest()


def _environment() -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for name in ("torch", "transformers", "Pillow", "accelerate"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "dependencies": versions,
    }


def _save_json(path: Path, document: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(document, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _default_adapter(*, allow_download: bool, device: str) -> Adapter:
    # No optional dependency or adapter import occurs on validation/dry-run paths.
    module = import_module("core.model_adapters.smolvlm")
    return cast(
        Adapter,
        module.SmolVLMAdapter.from_pretrained(
            allow_download=allow_download, device=device
        ),
    )


def run_pilot(
    manifest: str | Path,
    output_dir: str | Path,
    *,
    adapter: Adapter | None = None,
    dry_run: bool = False,
    allow_download: bool = False,
    device: str = "cpu",
    max_new_tokens: int = 64,
) -> dict[str, Any]:
    """Run up to twenty frozen cases into a new private no-clobber directory.

    Injected adapters are test/integration callers, never evidence of a real model
    baseline. This pilot records raw answers and failures, not confidence or scores.
    """
    if type(dry_run) is not bool or type(allow_download) is not bool:
        raise ValueError("run flags must be booleans")
    if not isinstance(device, str) or device not in {"cpu", "cuda"}:
        raise ValueError("device must be cpu or cuda")
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 256:
        raise ValueError("max_new_tokens must be an integer from 1 to 256")
    cases, manifest_hash = load_cases(manifest)
    output = Path(output_dir)
    output.mkdir(mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "kind": "dry-run" if dry_run else "pilot",
        "manifest_sha256": manifest_hash,
        "cases": len(cases),
        "model_execution_verified": False,
        "device_requested": device,
        "allow_download": allow_download,
        "max_new_tokens": max_new_tokens,
        "adapter_mode": "injected" if adapter is not None else "local-smolvlm",
        "environment": _environment(),
        "status": "running",
    }
    _save_json(output / "request.json", summary)
    failure: Exception | None = None
    if not dry_run and adapter is None:
        try:
            adapter = _default_adapter(allow_download=allow_download, device=device)
        except Exception as exc:
            failure = exc
    succeeded = failed = not_executed = answer_calls = 0
    results_path = output / "results.jsonl"
    with results_path.open("x", encoding="utf-8") as stream:
        os.chmod(results_path, 0o600)
        for case in cases:
            result: dict[str, Any] = {
                "id": case.identifier,
                "image": case.image,
                "image_sha256": case.image_sha256,
                "question": case.question,
                "reference_answer": case.expected_answer,
                "answer": None,
                "latency_ns": None,
                "error": None,
            }
            if dry_run:
                result["status"] = "not_executed"
                not_executed += 1
            elif failure is not None:
                result["status"] = "failed"
                result["error"] = {
                    "stage": "model_load",
                    "type": type(failure).__name__,
                    "message": str(failure)[:1024],
                }
                failed += 1
            else:
                assert adapter is not None
                start = time.perf_counter_ns()
                answer_calls += 1
                try:
                    answer = adapter.answer(
                        case.image_bytes, case.question, max_new_tokens=max_new_tokens
                    )
                    result["answer"] = _text(answer, "model answer", 16384)
                    result["status"] = "answered"
                    succeeded += 1
                except Exception as exc:
                    result["status"] = "failed"
                    result["error"] = {
                        "stage": "answer",
                        "type": type(exc).__name__,
                        "message": str(exc)[:1024],
                    }
                    failed += 1
                result["latency_ns"] = time.perf_counter_ns() - start
            stream.write(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    summary.update(
        {
            "status": "dry-run-complete"
            if dry_run
            else ("complete-with-failures" if failed else "complete"),
            "answered": succeeded,
            "failed": failed,
            "not_executed": not_executed,
            "answer_calls": answer_calls,
            "model_load_attempted": not dry_run
            and summary["adapter_mode"] == "local-smolvlm",
            "results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        }
    )
    _save_json(output / "run.json", summary)
    return summary
