"""Bounded child-process extraction of user PDF text with retained page numbers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def extract_pdf(raw: bytes) -> list[dict[str, Any]]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PDF_BYTES:
        raise ValueError("Upload a PDF smaller than 15 MiB.")
    if not raw.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a PDF.")
    with tempfile.TemporaryDirectory(prefix="openforge-extract-") as directory:
        root = Path(directory)
        source, output = root / "input.pdf", root / "pages.json"
        source.write_bytes(raw)
        os.chmod(source, 0o600)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.document_workspace.extract_worker",
                    str(source),
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "PDF extraction timed out. Try a smaller, text-based PDF."
            ) from exc
        if result.returncode:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            safe = (
                "Encrypted PDFs",
                "PDF must contain",
                "No searchable text",
                "PDF extracted text",
                "A PDF page",
            )
            if not message.startswith(safe):
                message = (
                    "This PDF could not be read within resource limits. "
                    "Try a smaller, text-based PDF."
                )
            raise ValueError(message[:240])
        with output.open("rb") as stream:
            encoded = stream.read(MAX_OUTPUT_BYTES + 1)
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise ValueError("PDF extracted text exceeds the supported output limit.")
        document = json.loads(encoded)
        pages = document["pages"]
        if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
            raise ValueError("Invalid extracted page data.")
        total = 0
        for index, page in enumerate(pages, 1):
            if (
                set(page) != {"number", "text"}
                or page["number"] != index
                or not isinstance(page["text"], str)
            ):
                raise ValueError("Invalid extracted page data.")
            total += len(page["text"])
        if total > 2_000_000 or not any(page["text"] for page in pages):
            raise ValueError("No usable extracted text within resource limits.")
        return pages


def extract_document(raw: bytes, kind: str) -> list[dict[str, Any]]:
    if kind == "pdf":
        return extract_pdf(raw)
    if kind not in {"docx", "txt", "md"}:
        raise ValueError("Choose a PDF, Word (.docx), Markdown, or plain-text file.")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_PDF_BYTES:
        raise ValueError("Upload a document smaller than 15 MiB.")
    with tempfile.TemporaryDirectory(prefix="openforge-text-") as directory:
        source, output = Path(directory) / "source", Path(directory) / "sections.json"
        source.write_bytes(raw)
        os.chmod(source, 0o600)
        output.touch(mode=0o600)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.document_workspace.text_worker",
                    str(source),
                    str(output),
                    kind,
                ],
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "Document extraction timed out. Try a smaller file."
            ) from exc
        if result.returncode:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            if not message.startswith(("Word document", "Document")):
                message = (
                    "Document could not be read. "
                    "Choose UTF-8 text or an unlocked .docx file."
                )
            raise ValueError(message[:240])
        with output.open("rb") as stream:
            encoded = stream.read(MAX_OUTPUT_BYTES + 1)
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise ValueError("Document extracted text exceeds the output limit.")
        pages = json.loads(encoded)["pages"]
        if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
            raise ValueError("Invalid document section data.")
        total = 0
        for index, page in enumerate(pages, 1):
            if (
                not isinstance(page, dict)
                or set(page) != {"number", "text"}
                or type(page["number"]) is not int
                or page["number"] != index
                or not isinstance(page["text"], str)
            ):
                raise ValueError("Invalid document section data.")
            total += len(page["text"])
        if total > 2_000_000 or not any(page["text"].strip() for page in pages):
            raise ValueError("No usable document text within resource limits.")
        return pages
