"""Curated research reports with immutable source snapshots and editable prose."""

from __future__ import annotations

import html
import json
from typing import Any

from . import evidence
from .model import evidence_excerpt
from .reports import _label, location_label
from .store import Store, _id, _now, _text


def candidates(store: Store, project_id: str) -> list[dict[str, Any]]:
    detail = store.project_detail(project_id)
    choices = []
    for note in detail["notes"]:
        sources = []
        if note["document_id"] and note["page"]:
            page = store.get_page(note["document_id"], note["page"])
            sources = [
                {
                    "document_id": note["document_id"],
                    "document_name": note["document_name"],
                    "page": note["page"],
                    "text": evidence_excerpt(note["text"], page["text"]),
                }
            ]
        choices.append(
            {
                "id": "note:" + note["id"],
                "origin": "Saved note",
                "heading": note["document_name"] or "Project note",
                "text": note["text"],
                "sources": sources,
                "review": "note",
            }
        )
    for table in evidence.list_tables(store, project_id):
        record = evidence.get_table(store, project_id, table["id"])
        names = {doc["id"]: doc["name"] for doc in record["documents"]}
        for index, cell in enumerate(record["cells"]):
            if cell["finding"] and cell["review"] != "unreviewed":
                choices.append(
                    {
                        "id": f"table:{table['id']}:{index}",
                        "origin": table["title"],
                        "heading": record["columns"][cell["column"]],
                        "text": cell["finding"],
                        "sources": cell["sources"],
                        "review": cell["review"],
                        "document_name": names[cell["document_id"]],
                    }
                )
    return choices


def list_reports(store: Store, project_id: str) -> list[dict[str, Any]]:
    with store._db() as db:
        store._required(db, "projects", project_id)
        return [
            dict(row)
            for row in db.execute(
                "SELECT id,title,updated_at FROM research_reports WHERE project_id=? "
                "ORDER BY updated_at DESC,id",
                (project_id,),
            ).fetchall()
        ]


def get_report(store: Store, project_id: str, report_id: str) -> dict[str, Any]:
    with store._db() as db:
        store._required(db, "projects", project_id)
        row = db.execute(
            "SELECT snapshot FROM research_reports WHERE id=? AND project_id=?",
            (report_id, project_id),
        ).fetchone()
    if row is None:
        raise KeyError("Report not found.")
    return dict(json.loads(row[0]))


def create_report(
    store: Store, project_id: str, title: Any, selected: Any
) -> dict[str, Any]:
    title = _text(title, "Report title", 100)
    if (
        not isinstance(selected, list)
        or not 1 <= len(selected) <= 20
        or any(not isinstance(value, str) for value in selected)
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("Choose 1 to 20 distinct findings.")
    by_id = {item["id"]: item for item in candidates(store, project_id)}
    if any(value not in by_id for value in selected):
        raise ValueError(
            "A selected finding is unavailable in this project. Refresh the list."
        )
    sections = [dict(by_id[value], id=_id(), origin_id=value) for value in selected]
    if sum(len(section["text"]) for section in sections) > 12000:
        raise ValueError(
            "Selected findings exceed 12,000 characters. Choose fewer findings."
        )
    now = _now()
    record = {
        "id": _id(),
        "project_id": project_id,
        "title": title,
        "summary": "",
        "conclusion": "",
        "sections": sections,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }
    with store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT count(*) FROM research_reports").fetchone()[0] >= 100:
            raise OverflowError("Workspace limit of 100 reports reached.")
        db.execute(
            "INSERT INTO research_reports VALUES (?,?,?,?,?)",
            (record["id"], project_id, title, now, json.dumps(record)),
        )
    return record


def update_report(
    store: Store, project_id: str, report_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    title = _text(data.get("title"), "Report title", 100)
    summary = _text(data.get("summary"), "Summary", 4000, empty=True)
    conclusion = _text(data.get("conclusion"), "Conclusion", 4000, empty=True)
    edits = data.get("sections")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 20:
        raise ValueError("Keep 1 to 20 report sections.")
    with store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT snapshot FROM research_reports WHERE id=? AND project_id=?",
            (report_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError("Report not found.")
        record = json.loads(row[0])
        if (
            type(data.get("revision")) is not int
            or data["revision"] != record["revision"]
        ):
            raise ValueError(
                "This report changed in another tab. Reopen it before saving."
            )
        originals = {item["id"]: item for item in record["sections"]}
        ordered = []
        seen = set()
        for edit in edits:
            if not isinstance(edit, dict) or not isinstance(edit.get("id"), str):
                raise ValueError("Invalid report section.")
            identifier = edit["id"]
            if identifier not in originals or identifier in seen:
                raise ValueError("Report sections must be distinct existing findings.")
            seen.add(identifier)
            ordered.append(
                dict(
                    originals[identifier],
                    text=_text(edit.get("text"), "Finding", 10000),
                )
            )
        if (
            len(summary) + len(conclusion) + sum(len(item["text"]) for item in ordered)
            > 12000
        ):
            raise ValueError("Report text must stay within 12,000 characters.")
        record.update(
            title=title,
            summary=summary,
            conclusion=conclusion,
            sections=ordered,
            revision=record["revision"] + 1,
            updated_at=_now(),
        )
        db.execute(
            "UPDATE research_reports SET title=?,updated_at=?,snapshot=? WHERE id=?",
            (title, record["updated_at"], json.dumps(record), report_id),
        )
    return dict(record)


def markdown_report(record: dict[str, Any]) -> str:
    lines = [
        "# " + _label(record["title"]),
        "",
        "## Overview",
        "",
        record["summary"] or "No overview added.",
        "",
    ]
    for index, section in enumerate(record["sections"], 1):
        lines.extend(
            [
                f"## {index}. {_label(section['heading'])}",
                "",
                section["text"],
                "",
                f"Origin: {_label(section['origin'])} · Review: {section['review']}",
                "",
            ]
        )
        for source in section["sources"]:
            lines.extend(
                [
                    f"Source: {_label(source['document_name'])}, "
                    f"{location_label(source['document_name'])} {source['page']}",
                    "",
                    "> " + source["text"].replace("\n", "\n> "),
                    "",
                ]
            )
        if not section["sources"]:
            lines.extend(
                ["No linked source. This finding needs independent verification.", ""]
            )
    lines.extend(
        [
            "## Conclusion and next steps",
            "",
            record["conclusion"] or "No conclusion added.",
            "",
            "Sources are saved snapshots. Review labels reflect the user's assessment, "
            "not automated verification.",
        ]
    )
    return "\n".join(lines) + "\n"


def html_report(record: dict[str, Any]) -> str:
    esc = html.escape

    def paragraphs(value: str) -> str:
        return "<p>" + esc(value).replace("\n", "<br>") + "</p>"

    sections = []
    for index, section in enumerate(record["sections"], 1):
        sources = (
            "".join(
                "<aside><strong>"
                + esc(source["document_name"])
                + ", "
                + location_label(source["document_name"])
                + " "
                + str(source["page"])
                + "</strong>"
                + paragraphs(source["text"])
                + "</aside>"
                for source in section["sources"]
            )
            or "<aside>No linked source. Verify this finding independently.</aside>"
        )
        sections.append(
            "<section><h2>"
            + str(index)
            + ". "
            + esc(section["heading"])
            + "</h2>"
            + paragraphs(section["text"])
            + "<small>"
            + esc(section["origin"])
            + " · "
            + esc(section["review"])
            + "</small>"
            + sources
            + "</section>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" conten'
        "t=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>" + esc(record["title"]) + "</title><style>"
        "body{font:16px/1.65 system-ui;color:#203b32;m"
        "ax-width:850px;margin:40px auto;padding:24px}"
        "h1{font:42px Georgia}h2{font-size:24px}aside{ba"
        "ckground:#f1f5ef;border-left:3px solid #779d80;"
        "padding:16px;margin:20px 0;font-size:14px}sma"
        "ll,footer{color:#63736b}section{margin:40px 0}"
        "@media print{body{margin:0;padding:0}aside"
        "{break-inside:avoid}h2{break-after:avoid}}"
        "</style><h1>"
        + esc(record["title"])
        + "</h1><h2>Overview</h2>"
        + paragraphs(record["summary"] or "No overview added.")
        + "".join(sections)
        + "<h2>Conclusion and next steps</h2>"
        + paragraphs(record["conclusion"] or "No conclusion added.")
        + "<footer>Sources are saved snapshots. Review labels are yo"
        "ur assessment, not automated verification.</footer></html>"
    )
