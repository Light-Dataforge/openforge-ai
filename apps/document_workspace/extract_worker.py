"""Private PDF text extraction subprocess; not a general PDF sandbox."""

from __future__ import annotations

import json
import logging
import sys
from importlib import import_module
from pathlib import Path

MAX_PAGES = 200
MAX_CHARS = 2_000_000
MAX_STREAM = 8 * 1024 * 1024


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_STREAM, MAX_STREAM))
        memory_limit = 768 * 1024 * 1024
        selected = (
            resource.RLIMIT_AS
            if sys.platform.startswith("linux")
            else resource.RLIMIT_DATA
        )
        resource.setrlimit(selected, (memory_limit, memory_limit))
    except (ImportError, OSError, ValueError):
        pass
    try:
        PdfReader = import_module("pypdf").PdfReader

        reader = PdfReader(sys.argv[1], strict=False)
        if reader.is_encrypted:
            raise ValueError(
                "Encrypted PDFs are not supported. Upload an unlocked copy."
            )
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError("PDF must contain 1 to 200 pages.")
        pages = []
        total = 0
        for number, page in enumerate(reader.pages, 1):
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_STREAM:
                raise ValueError(
                    "A PDF page exceeds the supported content-stream limit."
                )
            text = (page.extract_text() or "").replace("\x00", "").strip()
            total += len(text)
            if total > MAX_CHARS:
                raise ValueError("PDF extracted text exceeds two million characters.")
            pages.append({"number": number, "text": text})
        if not any(page["text"] for page in pages):
            raise ValueError(
                "No searchable text found. Scanned PDFs need OCR, which is not enabled."
            )
        Path(sys.argv[2]).write_text(
            json.dumps({"pages": pages}, ensure_ascii=True), encoding="utf-8"
        )
        return 0
    except ValueError as exc:
        print(str(exc)[:240], file=sys.stderr)
    except Exception:
        print(
            "This PDF could not be read. Try an unlocked, text-based PDF.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
