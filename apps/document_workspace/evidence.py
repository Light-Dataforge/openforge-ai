"""Saved, bounded evidence tables built from document-scoped keyword retrieval."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .model import evidence_excerpt
from .retrieval import retrieval_query
from .store import Store, _id, _now, _text

MAX_TABLES = 100


def _record(store: Store, project_id: str, table_id: str) -> dict[str, Any]:
    with store._db() as db:
        store._required(db, "projects", project_id)
        row = db.execute(
            "SELECT snapshot FROM evidence_tables WHERE id=? AND project_id=?",
            (table_id, project_id),
        ).fetchone()
    if row is None:
        raise KeyError("Evidence table not found.")
    return dict(json.loads(row[0]))


def get_table(store: Store, project_id: str, table_id: str) -> dict[str, Any]:
    return _record(store, project_id, table_id)


def list_tables(store: Store, project_id: str) -> list[dict[str, Any]]:
    with store._db() as db:
        store._required(db, "projects", project_id)
        rows = db.execute(
            "SELECT id,title,created_at,updated_at FROM evidence_tables "
            "WHERE project_id=? ORDER BY updated_at DESC,id",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_table(
    store: Store, project_id: str, title: Any, document_ids: Any, questions: Any
) -> dict[str, Any]:
    title = _text(title, "Table title", 100)
    if (
        not isinstance(document_ids, list)
        or not 1 <= len(document_ids) <= 10
        or any(not isinstance(value, str) for value in document_ids)
        or len(set(document_ids)) != len(document_ids)
    ):
        raise ValueError("Choose 1 to 10 distinct documents.")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 6:
        raise ValueError("Enter 1 to 6 research questions.")
    columns = [_text(question, "Research question", 300) for question in questions]
    if len(set(question.casefold() for question in columns)) != len(columns):
        raise ValueError("Each research question must be different.")
    detail = store.project_detail(project_id)
    by_id = {doc["id"]: doc for doc in detail["documents"]}
    if any(identifier not in by_id for identifier in document_ids):
        raise ValueError("Every document must belong to this project.")
    documents = [
        {key: by_id[identifier][key] for key in ("id", "name", "pages")}
        for identifier in document_ids
    ]
    cells = []
    for doc in documents:
        for index, question in enumerate(columns):
            sources = store.search(
                project_id, retrieval_query(question, []), doc["id"], limit=2
            )
            cells.append(
                {
                    "document_id": doc["id"],
                    "column": index,
                    "sources": [
                        dict(source, text=evidence_excerpt(question, source["text"]))
                        for source in sources
                    ],
                    "finding": "",
                    "review": "unreviewed",
                }
            )
    now = _now()
    record = {
        "id": _id(),
        "project_id": project_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "revision": 1,
        "columns": columns,
        "documents": documents,
        "cells": cells,
    }
    with store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        if (
            db.execute("SELECT count(*) FROM evidence_tables").fetchone()[0]
            >= MAX_TABLES
        ):
            raise OverflowError("Workspace limit of 100 evidence tables reached.")
        db.execute(
            "INSERT INTO evidence_tables VALUES (?,?,?,?,?,?)",
            (record["id"], project_id, title, now, now, json.dumps(record)),
        )
    return record


def update_cell(
    store: Store,
    project_id: str,
    table_id: str,
    document_id: Any,
    column: Any,
    finding: Any,
    review: Any,
    revision: Any,
) -> dict[str, Any]:
    finding = _text(finding, "Finding", 3000, empty=True)
    if review not in ("unreviewed", "supported", "unclear"):
        raise ValueError("Choose an available review label.")
    if type(column) is not int or type(revision) is not int:
        raise ValueError("Invalid table cell or revision.")
    # Re-read inside the same transaction so another tab cannot overwrite findings.
    with store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT snapshot FROM evidence_tables WHERE id=? AND project_id=?",
            (table_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError("Evidence table not found.")
        record = json.loads(row[0])
        if revision != record["revision"]:
            raise ValueError(
                "This table changed in another tab. Reopen it before saving."
            )
        cell = next(
            (
                cell
                for cell in record["cells"]
                if cell["document_id"] == document_id and cell["column"] == column
            ),
            None,
        )
        if cell is None:
            raise ValueError("Cell is not in this evidence table.")
        if review == "supported" and not cell["sources"]:
            raise ValueError("Inspect a matching source before marking supported.")
        cell.update(finding=finding, review=review)
        record["revision"] += 1
        record["updated_at"] = _now()
        db.execute(
            "UPDATE evidence_tables SET updated_at=?,snapshot=? WHERE id=?",
            (record["updated_at"], json.dumps(record), table_id),
        )
    return dict(record)


def export_csv(record: dict[str, Any]) -> str:
    def safe(value: str) -> str:
        # Avoid spreadsheet formula evaluation for filenames, questions and notes.
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Document",
            "Research question",
            "Review",
            "Finding",
            "Source locations",
            "Retrieved excerpts",
        ]
    )
    documents = {doc["id"]: doc["name"] for doc in record["documents"]}
    for cell in record["cells"]:
        writer.writerow(
            [
                safe(str(value))
                for value in [
                    documents[cell["document_id"]],
                    record["columns"][cell["column"]],
                    cell["review"],
                    cell["finding"],
                    "; ".join(
                        (
                            "page "
                            if source["document_name"].lower().endswith(".pdf")
                            else "section "
                        )
                        + str(source["page"])
                        for source in cell["sources"]
                    ),
                    "\n\n".join(source["text"] for source in cell["sources"])
                    or "No matching passage found; this does not establish absence.",
                ]
            ]
        )
    return "\ufeff" + output.getvalue()
