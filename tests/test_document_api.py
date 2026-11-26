import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from test_document_store import pdf_bytes

from apps.document_workspace.server import Application


class DocumentAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(("127.0.0.1", 0), Path(self.tmp.name))
        self.thread = threading.Thread(target=self.app.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.app.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.project = self.request(
            "POST", "/api/projects", {"name": "Research", "description": ""}
        )[1]["project"]

    def tearDown(self):
        self.app.shutdown()
        self.app.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None, raw=None):
        values = {"X-OpenForge-Request": "1"}
        if raw is None and data is not None:
            raw = json.dumps(data).encode()
            values["Content-Type"] = "application/json"
        values.update(headers or {})
        req = urllib.request.Request(
            self.base + path, data=raw, headers=values, method=method
        )
        try:
            response = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            return response.status, json.loads(
                body
            ) if "application/json" in content_type else body

    def upload(self):
        raw = pdf_bytes(
            [
                "Product overview and support.",
                "Refunds are available within 30 days of purchase.",
            ]
        )
        status, value = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/documents",
            raw=raw,
            headers={"Content-Type": "application/pdf", "X-Filename": "Policy.pdf"},
        )
        self.assertEqual(status, 201, value)
        return value["document"], raw

    def test_research_brief_exports_only_selected_project_findings_and_sources(self):
        doc, _ = self.upload()
        self.request(
            "POST",
            f"/api/projects/{self.project['id']}/notes",
            {
                "text": "Refund window is 30 days.",
                "document_id": doc["id"],
                "page": 2,
            },
        )
        other = self.app.store.create_project("Private other project", "")
        self.app.store.add_note(other["id"], "Do not include this finding")
        status, raw = self.request("GET", f"/api/projects/{self.project['id']}/brief")
        self.assertEqual(status, 200)
        content = raw.decode()
        self.assertIn("Refund window is 30 days.", content)
        self.assertIn("Source: Policy.pdf, page 2", content)
        self.assertNotIn("Do not include", content)
        self.assertEqual(self.request("GET", "/api/projects/missing/brief")[0], 404)

    def test_actual_pdf_upload_retrieval_conversation_citation_notes_and_reload(self):
        doc, raw = self.upload()
        status, original = self.request("GET", f"/api/documents/{doc['id']}/file")
        self.assertEqual(status, 200)
        self.assertEqual(original, raw)
        _, page = self.request("GET", f"/api/documents/{doc['id']}/pages?page=2")
        self.assertIn("30 days", page["text"])
        _, found = self.request(
            "GET", f"/api/projects/{self.project['id']}/search?q=refunds"
        )
        self.assertEqual(found["results"][0]["page"], 2)
        _, conversation = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/conversations",
            {"title": "Policy question"},
        )
        cid = conversation["conversation"]["id"]
        with patch(
            "apps.document_workspace.model.health", return_value={"available": False}
        ):
            status, reply = self.request(
                "POST",
                f"/api/conversations/{cid}/messages",
                {"text": "What is the refund policy?", "document_id": doc["id"]},
            )
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply["messages"][1]["mode"], "source_excerpts")
        citation = reply["messages"][1]["citations"][0]
        self.assertEqual(citation["page"], 2)
        self.assertIn(citation["text"], page["text"])
        status, note = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/notes",
            {"text": "Check the refund period", "document_id": doc["id"], "page": 2},
        )
        self.assertEqual(status, 201, note)
        _, saved = self.request("GET", f"/api/conversations/{cid}")
        self.assertEqual(len(saved["messages"]), 2)
        _, detail = self.request("GET", f"/api/projects/{self.project['id']}")
        self.assertEqual(len(detail["documents"]), 1)
        self.assertEqual(len(detail["notes"]), 1)

    def test_model_adapter_response_is_saved_with_valid_real_citations(self):
        doc, _ = self.upload()
        _, item = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/conversations",
            {"title": "Cited answer"},
        )
        with (
            patch(
                "apps.document_workspace.model.health", return_value={"available": True}
            ),
            patch(
                "apps.document_workspace.model._request",
                return_value={
                    "message": {"content": "Refunds are available within 30 days [1]."}
                },
            ),
        ):
            status, result = self.request(
                "POST",
                f"/api/conversations/{item['conversation']['id']}/messages",
                {"text": "refunds", "document_id": doc["id"]},
            )
        self.assertEqual(status, 200, result)
        self.assertEqual(result["messages"][1]["mode"], "local_model")
        self.assertEqual(
            result["messages"][1]["citations"][0]["document_id"], doc["id"]
        )

    def test_origin_host_and_write_header_checks(self):
        self.assertEqual(
            self.request("GET", "/api/projects", headers={"Host": "attacker.example"})[
                0
            ],
            403,
        )
        self.assertEqual(
            self.request(
                "GET", "/api/projects", headers={"Origin": "https://attacker.example"}
            )[0],
            403,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/api/projects",
                {"name": "forbidden"},
                headers={"X-OpenForge-Request": ""},
            )[0],
            403,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/api/projects",
                {"name": "forbidden"},
                headers={"Origin": "https://attacker.example"},
            )[0],
            403,
        )
        self.assertEqual(self.request("OPTIONS", "/api/projects")[0], 403)

    def test_invalid_upload_cross_project_scope_and_missing_resources(self):
        status, _ = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/documents",
            raw=b"not a pdf",
            headers={"Content-Type": "application/pdf"},
        )
        self.assertEqual(status, 400)
        doc, _ = self.upload()
        _, other = self.request("POST", "/api/projects", {"name": "Other"})
        _, conversation = self.request(
            "POST",
            f"/api/projects/{other['project']['id']}/conversations",
            {"title": "Other question"},
        )
        status, _ = self.request(
            "POST",
            f"/api/conversations/{conversation['conversation']['id']}/messages",
            {"text": "refund", "document_id": doc["id"]},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET", "/api/documents/missing/pages")[0], 404)
        self.assertEqual(self.request("GET", "/api/unknown")[0], 404)
        self.assertEqual(self.request("GET", "/%2e%2e/store.py")[0], 404)

    def test_chat_busy_and_invalid_json_are_explicit_without_ghost_messages(self):
        _, conversation = self.request(
            "POST",
            f"/api/projects/{self.project['id']}/conversations",
            {"title": "Concurrent"},
        )
        cid = conversation["conversation"]["id"]
        self.app.chat_lock.acquire()
        try:
            self.assertEqual(
                self.request(
                    "POST", f"/api/conversations/{cid}/messages", {"text": "Question?"}
                )[0],
                503,
            )
        finally:
            self.app.chat_lock.release()
        _, item = self.request("GET", f"/api/conversations/{cid}")
        self.assertEqual(item["messages"], [])
        status, _ = self.request(
            "POST",
            "/api/projects",
            raw=b'{"name":"a","name":"b"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
