"""Single-user loopback document workspace with private persistent local storage."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import model
from .retrieval import retrieval_query
from .store import Store

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 15 * 1024 * 1024
MAX_JSON = 64 * 1024
mimetypes.add_type("text/javascript", ".mjs")


def text(value: Any, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Enter nonempty text within the allowed length.")
    value.encode("utf-8")
    return value.strip()


def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate JSON fields are not accepted.")
        result[key] = value
    return result


class Application(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], data_dir: Path):
        self.store = Store(data_dir)
        self.chat_lock = threading.BoundedSemaphore(1)
        self.upload_lock = threading.BoundedSemaphore(1)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: Application
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Filenames, document text, questions and conversation paths stay out of logs.
        return

    def _allowed(self, *, write: bool = False) -> bool:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self._json(
                {"error": "This application accepts loopback requests only."}, 403
            )
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            self._json({"error": "Cross-origin access is not allowed."}, 403)
            return False
        if write and self.headers.get("X-OpenForge-Request") != "1":
            self._json({"error": "This action must originate from the workspace."}, 403)
            return False
        if self.headers.get("Transfer-Encoding"):
            self._json({"error": "Chunked request bodies are not supported."}, 400)
            return False
        return True

    def _send(
        self,
        raw: bytes,
        content_type: str,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self'; frame-src 'self' blob:; "
            "object-src 'self' blob:; base-uri 'none'; form-action 'self'",
        )
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(
            json.dumps(value, ensure_ascii=True, allow_nan=False).encode(),
            "application/json; charset=utf-8",
            status,
        )

    def _body(self, maximum: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise ValueError("A valid Content-Length is required.") from exc
        if length < 0:
            raise ValueError("A request body length is required.")
        if length > maximum:
            raise OverflowError("This request exceeds its size limit.")
        self.connection.settimeout(30)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("The upload was incomplete. Please retry.")
        return raw

    def _data(self) -> dict[str, Any]:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Expected a JSON request.")
        value = json.loads(
            self._body(MAX_JSON),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Invalid JSON number.")
            ),
        )
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value

    def do_OPTIONS(self) -> None:
        self._json({"error": "Cross-origin requests are not enabled."}, 403)

    def do_GET(self) -> None:
        if not self._allowed():
            return
        try:
            self._get()
        except KeyError:
            self._json(
                {"error": "That project, document, or conversation was not found."}, 404
            )
        except (ValueError, UnicodeError, RecursionError):
            self._json({"error": "Invalid request."}, 400)
        except (OSError, sqlite3.Error):
            self._json(
                {"error": "The local workspace could not read this resource."}, 500
            )

    def _get(self) -> None:
        url = urlsplit(self.path)
        path = unquote(url.path)
        query = parse_qs(url.query)
        store = self.server.store
        if path == "/api/health":
            state = model.health()
            self._json(
                {
                    "ok": True,
                    "model": state,
                    "mode": "local_ai" if state["available"] else "source_only",
                }
            )
        elif path == "/api/projects":
            self._json({"projects": store.list_projects()})
        elif match := re.fullmatch(r"/api/projects/([^/]+)/search", path):
            question = text(query.get("q", [""])[0])
            self._json(
                {
                    "results": store.search(
                        match[1],
                        question,
                        document_id=query.get("document_id", [None])[0],
                    )
                }
            )
        elif match := re.fullmatch(r"/api/projects/([^/]+)", path):
            self._json(store.project_detail(match[1]))
        elif match := re.fullmatch(r"/api/documents/([^/]+)/pages", path):
            page = int(query.get("page", ["1"])[0])
            self._json(store.get_page(match[1], page))
        elif match := re.fullmatch(r"/api/documents/([^/]+)/file", path):
            document = store.get_document(match[1])
            self._send(
                document["raw"],
                "application/pdf",
                headers={
                    "Content-Disposition": "inline; filename*=UTF-8''"
                    + quote(document["name"], safe="")
                },
            )
        elif match := re.fullmatch(r"/api/conversations/([^/]+)", path):
            self._json(store.get_conversation(match[1]))
        elif path.startswith("/api/"):
            self._json({"error": "Unknown API route."}, 404)
        else:
            target = (STATIC / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                self._json({"error": "Page not found."}, 404)
                return
            self._send(
                target.read_bytes(),
                mimetypes.guess_type(target)[0] or "application/octet-stream",
            )

    def do_POST(self) -> None:
        if not self._allowed(write=True):
            return
        try:
            self._post()
        except KeyError:
            self._json(
                {"error": "That project, document, or conversation was not found."}, 404
            )
        except OverflowError as exc:
            self._json({"error": str(exc)}, 413)
        except (ValueError, UnicodeError, RecursionError) as exc:
            self._json({"error": str(exc)[:500] or "Invalid request."}, 400)
        except (OSError, sqlite3.Error):
            self._json(
                {
                    "error": "The local workspace could not complete this action. "
                    "Your saved data is retained."
                },
                500,
            )

    def _post(self) -> None:
        path = unquote(urlsplit(self.path).path)
        store = self.server.store
        if path == "/api/projects":
            data = self._data()
            self._json(
                {
                    "project": store.create_project(
                        text(data.get("name"), 80),
                        data.get("description", ""),
                    )
                },
                201,
            )
        elif match := re.fullmatch(r"/api/projects/([^/]+)/documents", path):
            if self.headers.get("Content-Type", "").split(";")[0] != "application/pdf":
                raise ValueError("Choose a PDF file.")
            if not self.server.upload_lock.acquire(blocking=False):
                self._json({"error": "Another PDF is being indexed. Please wait."}, 503)
                return
            try:
                name = text(
                    unquote(self.headers.get("X-Filename", "document.pdf")), 180
                )
                raw = self._body(MAX_UPLOAD)
                self._json({"document": store.add_document(match[1], name, raw)}, 201)
            finally:
                self.server.upload_lock.release()
        elif match := re.fullmatch(r"/api/projects/([^/]+)/conversations", path):
            data = self._data()
            self._json(
                {
                    "conversation": store.create_conversation(
                        match[1], text(data.get("title", "New conversation"), 120)
                    )
                },
                201,
            )
        elif match := re.fullmatch(r"/api/projects/([^/]+)/notes", path):
            data = self._data()
            self._json(
                {
                    "note": store.add_note(
                        match[1],
                        text(data.get("text"), 10000),
                        data.get("document_id"),
                        data.get("page"),
                    )
                },
                201,
            )
        elif match := re.fullmatch(r"/api/conversations/([^/]+)/messages", path):
            data = self._data()
            question = text(data.get("text"))
            thread = store.get_conversation(match[1])
            conversation = thread["conversation"]
            if not self.server.chat_lock.acquire(blocking=False):
                self._json(
                    {"error": "An answer is already being prepared. Please wait."}, 503
                )
                return
            try:
                sources = store.search(
                    conversation["project_id"],
                    retrieval_query(question, thread["messages"]),
                    document_id=data.get("document_id"),
                    limit=4,
                )
                content, mode = model.answer(
                    question, sources, history=thread["messages"]
                )
                user = store.add_message(match[1], "user", question, [], None)
                assistant = store.add_message(
                    match[1], "assistant", content, sources, mode
                )
                self._json({"messages": [user, assistant]})
            finally:
                self.server.chat_lock.release()
        else:
            self._json({"error": "Unknown API route."}, 404)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    application = Application(("127.0.0.1", args.port), args.data_dir)
    print(
        f"OpenForge document workspace: http://127.0.0.1:{application.server_port}",
        flush=True,
    )
    try:
        application.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        application.server_close()


if __name__ == "__main__":
    main()
