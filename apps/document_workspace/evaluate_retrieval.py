"""Run the original small lexical-versus-hybrid diagnostic on a private temp store."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import tempfile
import time
from importlib import import_module
from pathlib import Path
from typing import Any

from .retrieval import retrieval_query
from .semantic import EMBED_MODEL, SEMANTIC_THRESHOLD, HybridRanker
from .store import Store


def evaluate(fixture: Path) -> dict[str, Any]:
    data = json.loads(fixture.read_text())
    pdf = import_module("pypdf")
    generic = import_module("pypdf.generic")
    writer = pdf.PdfWriter()
    for text in data["pages"]:
        page = writer.add_blank_page(width=612, height=792)
        font = generic.DictionaryObject(
            {
                generic.NameObject("/Type"): generic.NameObject("/Font"),
                generic.NameObject("/Subtype"): generic.NameObject("/Type1"),
                generic.NameObject("/BaseFont"): generic.NameObject("/Helvetica"),
            }
        )
        page[generic.NameObject("/Resources")] = generic.DictionaryObject(
            {
                generic.NameObject("/Font"): generic.DictionaryObject(
                    {generic.NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = generic.DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(
            ("BT /F1 10 Tf 40 740 Td (" + escaped + ") Tj ET").encode("ascii")
        )
        page[generic.NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    results = []
    ranker = HybridRanker()
    with tempfile.TemporaryDirectory(prefix="openforge-retrieval-eval-") as directory:
        store = Store(Path(directory))
        project = store.create_project("Original retrieval diagnostic", "")
        document = store.add_document(
            project["id"], "Diagnostic.pdf", buffer.getvalue()
        )
        candidates = store.search_candidates(project["id"], document["id"])
        for question in data["questions"]:
            started = time.monotonic()
            lexical = store.search(
                project["id"],
                retrieval_query(question["text"], []),
                document["id"],
                limit=4,
            )
            hybrid, mode = ranker.rank(question["text"], lexical, candidates, limit=4)
            expected = question["expected_page"]
            results.append(
                {
                    "question": question["text"],
                    "expected_page": expected,
                    "lexical_top_page": lexical[0]["page"] if lexical else None,
                    "hybrid_top_page": hybrid[0]["page"] if hybrid else None,
                    "mode": mode,
                    "seconds": round(time.monotonic() - started, 3),
                }
            )
    return {
        "scope": data["description"],
        "split": data.get("split", "calibration"),
        "embedding_model": EMBED_MODEL,
        "semantic_threshold": SEMANTIC_THRESHOLD,
        "fusion_k": 60,
        "machine": platform.machine(),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "cases": results,
        "lexical_correct": sum(
            row["lexical_top_page"] == row["expected_page"] for row in results
        ),
        "hybrid_correct": sum(
            row["hybrid_top_page"] == row["expected_page"] for row in results
        ),
        "total": len(results),
        "budget_usd": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
