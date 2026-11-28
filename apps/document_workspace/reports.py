"""Portable research briefs from saved project data."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _label(value: Any) -> str:
    return (
        str(value or "").replace("\r", " ").replace("\n", " ").replace("#", "").strip()
    )


def location_label(name: str) -> str:
    return (
        "section" if Path(name).suffix.lower() in {".docx", ".txt", ".md"} else "page"
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
        lines.append(
            f"- {_label(document['name'])} — {document['pages']} "
            f"{location_label(document['name'])}s"
        )
    if not detail["documents"]:
        lines.append("No documents uploaded.")
    lines.extend(["", "## Saved findings", ""])
    for index, note in enumerate(detail["notes"], 1):
        lines.extend([f"### Finding {index}", "", note["text"], ""])
        if note.get("document_id"):
            source = _label(note.get("document_name") or "Source document")
            page = (
                f", {location_label(source)} {note['page']}" if note.get("page") else ""
            )
            lines.extend([f"Source: {source}{page}", ""])
    if not detail["notes"]:
        lines.append("No findings saved yet.")
    return "\n".join(lines).strip() + "\n"


def conversation_record(thread: dict[str, Any]) -> str:
    lines = [f"# {_label(thread['conversation']['title'])}", ""]
    for message in thread["messages"]:
        role = "Question" if message["role"] == "user" else "Answer"
        lines.extend([f"## {role}", "", message["content"], ""])
        if message["role"] != "assistant":
            continue
        mode = {
            "local_model": "Local model",
            "insufficient_evidence": "Insufficient evidence",
        }.get(message.get("mode"), "Source excerpts")
        lines.extend([f"Response mode: {mode}", ""])
        references = {
            int(value) for value in re.findall(r"\[(\d+)\]", message["content"])
        }
        for number, source in enumerate(message["citations"], 1):
            if number in references:
                lines.extend(
                    [
                        f"Source [{number}]: {_label(source['document_name'])}, "
                        f"{location_label(source['document_name'])} {source['page']}",
                        "",
                        "> " + source["text"].replace("\n", "\n> "),
                        "",
                    ]
                )
    if not thread["messages"]:
        lines.append("No messages saved yet.")
    return "\n".join(lines).strip() + "\n"
