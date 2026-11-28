"""Bounded Word/plain-text extraction; never execute embedded content or fetch links."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

LIMIT = 2_000_000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_word(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 2000
            or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024
        ):
            raise ValueError("Word document exceeds the expanded archive limit.")
        matches = [entry for entry in entries if entry.filename == "word/document.xml"]
        if len(matches) != 1 or matches[0].file_size > 8 * 1024 * 1024:
            raise ValueError("Word document has missing or oversized body text.")
        if matches[0].flag_bits & 1:
            raise ValueError("Word document is encrypted. Upload an unlocked copy.")
        xml = archive.read(matches[0]).decode("utf-8-sig")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("Word document contains unsupported XML declarations.")
    root = ElementTree.fromstring(xml)
    if root.tag != W + "document":
        raise ValueError("Word document body is not valid WordprocessingML.")
    paragraphs = []
    for paragraph in root.iter(W + "p"):
        text = "".join(
            element.text or ""
            if element.tag == W + "t"
            else "\t"
            if element.tag == W + "tab"
            else "\n"
            for element in paragraph.iter()
            if element.tag in {W + "t", W + "tab", W + "br", W + "cr"}
        ).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def extract(path: Path, kind: str) -> list[dict[str, str | int]]:
    text = read_word(path) if kind == "docx" else path.read_bytes().decode("utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or len(text) > LIMIT:
        raise ValueError("Document must contain 1 to two million text characters.")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError(
            "Document contains binary data. Choose UTF-8 text or a Word file."
        )
    return [
        {"number": index + 1, "text": text[start : start + 10000]}
        for index, start in enumerate(range(0, len(text), 10000))
    ]


def main() -> int:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
        selected = (
            resource.RLIMIT_AS
            if sys.platform.startswith("linux")
            else resource.RLIMIT_DATA
        )
        resource.setrlimit(selected, (768 * 1024 * 1024, 768 * 1024 * 1024))
    except (ImportError, OSError, ValueError):
        pass
    try:
        pages = extract(Path(sys.argv[1]), sys.argv[3])
        Path(sys.argv[2]).write_text(json.dumps({"pages": pages}), encoding="utf-8")
        return 0
    except (ValueError, UnicodeError) as exc:
        print(str(exc)[:240], file=sys.stderr)
    except Exception:
        print(
            "Document could not be read. Choose UTF-8 text or an unlocked .docx file.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
