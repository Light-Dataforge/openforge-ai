import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from apps.document_workspace import evidence
from apps.document_workspace.extractor import extract_document
from apps.document_workspace.store import Store


def word_bytes(body, *, declaration=""):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            declaration
            + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>" + body + "</w:body></w:document>",
        )
    return output.getvalue()


class DocumentFormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))
        self.project = self.store.create_project("Mixed research")["id"]

    def test_word_body_tables_and_unicode_are_searchable_with_original_bytes(self):
        raw = word_bytes(
            "<w:p><w:r><w:t>Delivery policy</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Returns within 45 days. Café.</w:t>"
            "</w:r></w:p></w:tc></w:tr></w:tbl>"
        )
        doc = self.store.add_document(self.project, "Policy.docx", raw)
        self.assertEqual(doc["format"], "docx")
        self.assertEqual(self.store.get_document(doc["id"])["raw"], raw)
        page = self.store.get_page(doc["id"], 1)
        self.assertIn("45 days. Café.", page["text"])
        self.assertEqual(
            self.store.search(self.project, "Returns")[0]["document_id"], doc["id"]
        )
        record = evidence.create_table(
            self.store, self.project, "Mixed", [doc["id"]], ["Returns?"]
        )
        self.assertIn("section 1", evidence.export_csv(record))

    def test_long_utf8_text_sections_preserve_content_and_last_section_search(self):
        text = "é" * 10000 + "\nRefunds take 19 days."
        doc = self.store.add_document(self.project, "Notes.txt", text.encode())
        self.assertEqual(doc["pages"], 2)
        extracted = "".join(self.store.get_page(doc["id"], n)["text"] for n in [1, 2])
        self.assertEqual(extracted, text)
        self.assertEqual(self.store.search(self.project, "Refunds")[0]["page"], 2)

    def test_markdown_is_plain_text_not_executed_or_fetched(self):
        text = '# Report\n<script>alert("x")</script>\n![image](https://example.invalid/private)'
        doc = self.store.add_document(self.project, "Research.md", text.encode())
        self.assertEqual(self.store.get_page(doc["id"], 1)["text"], text)
        self.assertEqual(
            Store(Path(self.tmp.name)).project_detail(self.project)["documents"][0][
                "format"
            ],
            "md",
        )

    def test_empty_binary_invalid_utf8_and_unsupported_format_are_rejected(self):
        for name, raw in [
            ("Bad.txt", b""),
            ("Bad.md", b"\xff\xfe"),
            ("Bad.txt", b"hello\x00world"),
            ("Bad.exe", b"hello"),
        ]:
            with self.assertRaises(ValueError):
                self.store.add_document(self.project, name, raw)
        self.assertFalse(self.store.project_detail(self.project)["documents"])

    def test_word_rejects_missing_body_entities_and_expanded_archive(self):
        with self.assertRaises(ValueError):
            extract_document(b"not a zip", "docx")
        entity = word_bytes(
            "<w:p><w:r><w:t>&secret;</w:t></w:r></w:p>",
            declaration='<!DOCTYPE document [<!ENTITY secret "unsafe">]>',
        )
        with self.assertRaisesRegex(ValueError, "XML declarations"):
            extract_document(entity, "docx")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("oversized", b"x" * (21 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "archive limit"):
            extract_document(output.getvalue(), "docx")
