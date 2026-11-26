"""SQLite persistence, page-aware PDF storage and lexical source retrieval."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .extractor import MAX_PDF_BYTES, extract_pdf
from .retrieval import query_groups, rank_passages

MAX_STORAGE = 200 * 1024 * 1024  # Uploaded PDF bytes, not physical SQLite disk usage.
MAX_DOCUMENTS = 200
MAX_INDEXED_CHARS = 20_000_000
DOC_COLUMNS = "id,project_id,name,pages,bytes,sha256,created_at"


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, label: str, maximum: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not empty and not value.strip())
    ):
        raise ValueError(
            f"{label} must be {'at most' if empty else '1 to'} {maximum} characters."
        )
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"Invalid {label} text.") from exc
    if "\x00" in value:
        raise ValueError(f"Invalid {label} text.")
    return value.strip()


class Store:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.data_dir, 0o700)
        self.path = self.data_dir / "workspace.sqlite3"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT
                    NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES
                    projects(id),name TEXT NOT NULL,
                    pages INTEGER NOT NULL,bytes INTEGER NOT NULL,sha256 TEXT
                    NOT NULL,raw BLOB NOT NULL,
                    created_at TEXT NOT NULL,UNIQUE(project_id,sha256));
                CREATE TABLE IF NOT EXISTS pages (
                    document_id TEXT NOT NULL REFERENCES documents(id),number
                    INTEGER NOT NULL,text TEXT NOT NULL,
                    PRIMARY KEY(document_id,number));
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES
                    documents(id),
                    page INTEGER NOT NULL,ordinal INTEGER NOT NULL,text TEXT NOT NULL);
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING
                    fts5(chunk_id UNINDEXED,text,tokenize='porter unicode61');
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES
                    projects(id),title TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES
                    conversations(id),role TEXT NOT NULL,
                    content TEXT NOT NULL,citations TEXT NOT NULL,mode
                    TEXT,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES
                    projects(id),text TEXT NOT NULL,
                    document_id TEXT REFERENCES documents(id),page
                    INTEGER,created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS documents_project ON documents(project_id);
                    CREATE INDEX IF NOT EXISTS conversations_project ON
                    conversations(project_id);
                    CREATE INDEX IF NOT EXISTS messages_conversation ON
                    messages(conversation_id,seq);
                    CREATE INDEX IF NOT EXISTS chunks_document ON
                    chunks(document_id,page,ordinal);
            """)
            # Preserve stored documents/pages/messages while upgrading lexical search.
            definition = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='chunks_fts'"
            ).fetchone()[0]
            if "porter unicode61" not in definition.lower():
                db.execute("BEGIN IMMEDIATE")
                db.execute("DROP TABLE chunks_fts")
                db.execute(
                    "CREATE VIRTUAL TABLE chunks_fts USING fts5("
                    "chunk_id UNINDEXED,text,tokenize='porter unicode61')"
                )
                db.execute(
                    "INSERT INTO chunks_fts (chunk_id,text) SELECT id,text FROM chunks"
                )
        os.chmod(self.path, 0o600)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _required(db: sqlite3.Connection, table: str, identifier: str) -> sqlite3.Row:
        if table not in {"projects", "documents", "conversations"}:
            raise ValueError("Unsupported record type.")
        columns = DOC_COLUMNS if table == "documents" else "*"
        row = db.execute(
            f"SELECT {columns} FROM {table} WHERE id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise KeyError("Record not found.")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _document(row: sqlite3.Row) -> dict[str, Any]:
        return {
            key: row[key]
            for key in (
                "id",
                "project_id",
                "name",
                "pages",
                "bytes",
                "sha256",
                "created_at",
            )
        }

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        record = {
            "id": _id(),
            "name": _text(name, "Project name", 100),
            "description": _text(description, "Description", 2000, empty=True),
            "created_at": _now(),
        }
        with self._db() as db:
            db.execute(
                "INSERT INTO projects VALUES (:id,:name,:description,:created_at)",
                record,
            )
        return dict(record, document_count=0, conversation_count=0)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("""SELECT p.*,
                    (SELECT count(*) FROM documents d WHERE d.project_id=p.id)
                    document_count,
                    (SELECT count(*) FROM conversations c WHERE
                    c.project_id=p.id) conversation_count
                FROM projects p ORDER BY p.created_at DESC,p.id""").fetchall()
            return [dict(row) for row in rows]

    def project_detail(self, project_id: str) -> dict[str, Any]:
        with self._db() as db:
            project = dict(self._required(db, "projects", project_id))
            docs = db.execute(
                f"SELECT {DOC_COLUMNS} FROM documents WHERE project_id=? "
                "ORDER BY created_at,id",
                (project_id,),
            ).fetchall()
            conversations = db.execute(
                "SELECT * FROM conversations WHERE project_id=? "
                "ORDER BY created_at DESC,id",
                (project_id,),
            ).fetchall()
            notes = db.execute(
                """SELECT n.*,d.name document_name FROM notes n
                LEFT JOIN documents d ON d.id=n.document_id
                WHERE n.project_id=? ORDER BY n.created_at DESC,n.id""",
                (project_id,),
            ).fetchall()
            project.update(
                document_count=len(docs), conversation_count=len(conversations)
            )
            return {
                "project": project,
                "documents": [self._document(row) for row in docs],
                "conversations": [dict(row) for row in conversations],
                "notes": [dict(row) for row in notes],
            }

    def get_document(self, document_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = self._required(db, "documents", document_id)
            raw = db.execute(
                "SELECT raw FROM documents WHERE id=?", (document_id,)
            ).fetchone()[0]
            return dict(self._document(row), raw=bytes(raw))

    def get_page(self, document_id: str, page: int) -> dict[str, Any]:
        if type(page) is not int or page < 1:
            raise ValueError("Page must be a positive integer.")
        with self._db() as db:
            document = self._document(self._required(db, "documents", document_id))
            row = db.execute(
                "SELECT text FROM pages WHERE document_id=? AND number=?",
                (document_id, page),
            ).fetchone()
            if row is None:
                raise KeyError("Page not found.")
            return {
                "document": document,
                "page": page,
                "pages": document["pages"],
                "text": row["text"],
            }

    @staticmethod
    def _check_capacity(
        db: sqlite3.Connection, added_bytes: int, added_chars: int
    ) -> None:
        count, uploaded_bytes = db.execute(
            "SELECT count(*),COALESCE(sum(bytes),0) FROM documents"
        ).fetchone()
        if count >= MAX_DOCUMENTS:
            raise ValueError("Workspace document limit of 200 reached.")
        if uploaded_bytes + added_bytes > MAX_STORAGE:
            raise ValueError("Uploaded PDF byte quota of 200 MiB reached.")
        text_chars = db.execute(
            "SELECT COALESCE(sum(length(text)),0) FROM pages"
        ).fetchone()[0]
        if text_chars + added_chars > MAX_INDEXED_CHARS:
            raise ValueError(
                "Workspace extracted-text quota of 20 million characters reached."
            )

    def add_document(self, project_id: str, name: str, raw: bytes) -> dict[str, Any]:
        name = _text(name, "Document name", 255)
        if (
            not name.lower().endswith(".pdf")
            or "/" in name
            or "\\" in name
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
        ):
            raise ValueError("Choose a PDF filename without directory components.")
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_PDF_BYTES:
            raise ValueError("Upload a PDF smaller than 15 MiB.")
        digest = hashlib.sha256(raw).hexdigest()
        with self._db() as db:
            self._required(db, "projects", project_id)
            duplicate = db.execute(
                f"SELECT {DOC_COLUMNS} FROM documents WHERE project_id=? AND sha256=?",
                (project_id, digest),
            ).fetchone()
            if duplicate is not None:
                return dict(self._document(duplicate), already_exists=True)
            self._check_capacity(db, len(raw), 0)
        pages = extract_pdf(raw)
        record = {
            "id": _id(),
            "project_id": project_id,
            "name": name,
            "pages": len(pages),
            "bytes": len(raw),
            "sha256": digest,
            "created_at": _now(),
        }
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._required(db, "projects", project_id)
            duplicate = db.execute(
                f"SELECT {DOC_COLUMNS} FROM documents WHERE project_id=? AND sha256=?",
                (project_id, digest),
            ).fetchone()
            if duplicate is not None:
                return dict(self._document(duplicate), already_exists=True)
            self._check_capacity(db, len(raw), sum(len(page["text"]) for page in pages))
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                (
                    record["id"],
                    project_id,
                    name,
                    len(pages),
                    len(raw),
                    digest,
                    raw,
                    record["created_at"],
                ),
            )
            for page in pages:
                db.execute(
                    "INSERT INTO pages VALUES (?,?,?)",
                    (record["id"], page["number"], page["text"]),
                )
                text = page["text"]
                for ordinal, start in enumerate(range(0, len(text), 1600)):
                    fragment = text[start : start + 1800].strip()
                    if not fragment:
                        continue
                    chunk = _id()
                    db.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?)",
                        (chunk, record["id"], page["number"], ordinal, fragment),
                    )
                    db.execute("INSERT INTO chunks_fts VALUES (?,?)", (chunk, fragment))
        return dict(record, already_exists=False)

    def search(
        self, project_id: str, q: str, document_id: str | None = None, limit: int = 6
    ) -> list[dict[str, Any]]:
        q = _text(q, "Question", 4000)
        if type(limit) is not int or not 1 <= limit <= 12:
            raise ValueError("Search limit must be 1 to 12.")
        with self._db() as db:
            self._required(db, "projects", project_id)
            if document_id is not None:
                document = self._required(db, "documents", document_id)
                if document["project_id"] != project_id:
                    raise ValueError("Document is not in this project.")
            groups = query_groups(q)
            tokens = list(
                dict.fromkeys(word for group in groups for word in sorted(group))
            )
            scope = "d.project_id=?" + (" AND d.id=?" if document_id else "")
            parameters: list[Any] = [project_id] + (
                [document_id] if document_id else []
            )
            overview = not tokens or any(
                word in {"summarize", "summarise", "summary", "overview"}
                for word in tokens
            )
            if overview:
                rows = db.execute(
                    f"""
                    SELECT c.id chunk_id,c.document_id,d.name
                    document_name,c.page,c.text,0.0 score
                    FROM chunks c JOIN documents d ON d.id=c.document_id WHERE {scope}
                    ORDER BY c.ordinal,c.page,d.created_at,d.id LIMIT ?""",
                    (*parameters, limit),
                ).fetchall()
            elif tokens:
                query = " OR ".join(
                    '"' + token.replace('"', '""') + '"' for token in tokens
                )
                rows = db.execute(
                    f"""
                    SELECT c.id chunk_id,c.document_id,d.name
                    document_name,c.page,c.text,bm25(chunks_fts) score
                    FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id
                    JOIN documents d ON d.id=c.document_id
                    WHERE chunks_fts MATCH ? AND {scope} ORDER BY
                    score,c.document_id,c.page,c.ordinal LIMIT ?""",
                    (query, *parameters, 60),
                ).fetchall()
            else:
                rows = []
            results = [dict(row) for row in rows]
            return (rank_passages(q, results) if not overview else results)[:limit]

    def create_conversation(self, project_id: str, title: str) -> dict[str, Any]:
        record = {
            "id": _id(),
            "project_id": project_id,
            "title": _text(title, "Conversation title", 150),
            "created_at": _now(),
        }
        with self._db() as db:
            self._required(db, "projects", project_id)
            db.execute(
                "INSERT INTO conversations VALUES (:id,:project_id,:title,:created_at)",
                record,
            )
        return record

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        with self._db() as db:
            conversation = dict(self._required(db, "conversations", conversation_id))
            rows = db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY seq",
                (conversation_id,),
            ).fetchall()
            messages = []
            for row in rows:
                message = {
                    key: row[key]
                    for key in (
                        "id",
                        "conversation_id",
                        "role",
                        "content",
                        "mode",
                        "created_at",
                    )
                }
                message["citations"] = json.loads(row["citations"])
                messages.append(message)
            return {"conversation": conversation, "messages": messages}

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(role, str) or role not in {"user", "assistant"}:
            raise ValueError("Invalid message role.")
        content = _text(content, "Message", 30_000)
        if mode is not None and (
            not isinstance(mode, str)
            or mode not in {"local_model", "source_excerpts", "unavailable"}
        ):
            raise ValueError("Invalid message mode.")
        if not isinstance(citations, (list, type(None))) or (
            citations is not None and len(citations) > 12
        ):
            raise ValueError("Invalid citations.")
        encoded = json.dumps(citations or [], ensure_ascii=True, allow_nan=False)
        if len(encoded) > 160_000:
            raise ValueError("Citation data too large.")
        record = {
            "id": _id(),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "mode": mode,
            "created_at": _now(),
        }
        with self._db() as db:
            conversation = self._required(db, "conversations", conversation_id)
            for citation in citations or []:
                if (
                    not isinstance(citation, dict)
                    or not isinstance(citation.get("document_id"), str)
                    or not isinstance(citation.get("chunk_id"), str)
                ):
                    raise ValueError("Invalid citation document.")
                doc = self._required(db, "documents", citation["document_id"])
                if doc["project_id"] != conversation["project_id"]:
                    raise ValueError("Citation document is not in this project.")
                chunk = db.execute(
                    "SELECT document_id,page,text FROM chunks WHERE id=?",
                    (citation.get("chunk_id"),),
                ).fetchone()
                if (
                    chunk is None
                    or chunk["document_id"] != doc["id"]
                    or type(citation.get("page")) is not int
                    or citation.get("page") != chunk["page"]
                    or citation.get("text") != chunk["text"]
                    or citation.get("document_name") != doc["name"]
                ):
                    raise ValueError("Citation must match an existing source passage.")
            db.execute(
                "INSERT INTO messages "
                "(id,conversation_id,role,content,citations,mode,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    record["id"],
                    conversation_id,
                    role,
                    content,
                    encoded,
                    mode,
                    record["created_at"],
                ),
            )
        return record

    def add_note(
        self,
        project_id: str,
        text: str,
        document_id: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        text = _text(text, "Note", 10_000)
        with self._db() as db:
            self._required(db, "projects", project_id)
            if document_id is not None:
                doc = self._required(db, "documents", document_id)
                if doc["project_id"] != project_id:
                    raise ValueError("Document is not in this project.")
                if type(page) is not int or not 1 <= page <= doc["pages"]:
                    raise ValueError("Choose a valid document page for this note.")
            elif page is not None:
                raise ValueError("A page note requires a document.")
            record = {
                "id": _id(),
                "project_id": project_id,
                "text": text,
                "document_id": document_id,
                "page": page,
                "created_at": _now(),
            }
            db.execute(
                "INSERT INTO notes VALUES "
                "(:id,:project_id,:text,:document_id,:page,:created_at)",
                record,
            )
            return record

    def update_note(
        self, project_id: str, note_id: str, text: str, expected_text: Any
    ) -> dict[str, Any]:
        text = _text(text, "Note", 10_000)
        if not isinstance(expected_text, str) or len(expected_text) > 10_000:
            raise ValueError("The original note text is required.")
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM notes WHERE id=? AND project_id=?",
                (note_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(note_id)
            if row["text"] != expected_text:
                raise ValueError(
                    "This note changed elsewhere. Reload the workspace before editing."
                )
            changed = db.execute(
                "UPDATE notes SET text=? WHERE id=? AND project_id=? AND text=?",
                (text, note_id, project_id, expected_text),
            ).rowcount
            if changed != 1:
                raise ValueError("This note changed elsewhere. Reload before editing.")
            return dict(row, text=text)
