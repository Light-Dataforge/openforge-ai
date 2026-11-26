"""Portable research briefs from saved project data."""

from __future__ import annotations

from typing import Any


def _label(value: Any) -> str:
    return (
        str(value or "").replace("\r", " ").replace("\n", " ").replace("#", "").strip()
    )


def research_brief(detail: dict[str, Any]) -> str:
    project = detail["project"]
    lines = [
        f"# {_label(project['name'])}",
        "",
        str(project.get("description", "")),
        "",
        "## Source documents",
        "",
    ]
    for document in detail["documents"]:
        lines.append(f"- {_label(document['name'])} — {document['pages']} pages")
    if not detail["documents"]:
        lines.append("No documents uploaded.")
    lines.extend(["", "## Saved findings", ""])
    for index, note in enumerate(detail["notes"], 1):
        lines.extend([f"### Finding {index}", "", note["text"], ""])
        if note.get("document_id"):
            source = _label(note.get("document_name") or "Source document")
            page = f", page {note['page']}" if note.get("page") else ""
            lines.extend([f"Source: {source}{page}", ""])
    if not detail["notes"]:
        lines.append("No findings saved yet.")
    return "\n".join(lines).strip() + "\n"
