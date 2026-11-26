import io
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
except ImportError as exc:
    raise unittest.SkipTest(
        "Document store tests need the document-workspace environment."
    ) from exc

from apps.document_workspace.extractor import extract_pdf
from apps.document_workspace.store import Store


def pdf_bytes(texts, *, encrypted=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        if text:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream = DecodedStreamObject()
            stream.set_data(
                ("BT /F1 12 Tf 50 740 Td (" + escaped + ") Tj ET").encode("ascii")
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.store = Store(self.root)
        self.project = self.store.create_project("Research", "A persistent project")
        self.raw = pdf_bytes(
            [
                "Welcome. Customer service is open Monday through Friday.",
                "Refund policy: customers may request a full refund "
                "within 30 days of purchase.",
            ]
        )

    def test_actual_pdf_upload_page_read_fts_citations_and_reopen(self):
        doc = self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        self.assertEqual(doc["pages"], 2)
        page = self.store.get_page(doc["id"], 2)
        self.assertIn("30 days", page["text"])
        results = self.store.search(self.project["id"], "What is the refund policy?")
        self.assertTrue(results)
        self.assertEqual(results[0]["page"], 2)
        self.assertIn(results[0]["text"], page["text"])
        reopened = Store(self.root)
        self.assertEqual(reopened.get_document(doc["id"])["raw"], self.raw)
        self.assertEqual(reopened.list_projects()[0]["document_count"], 1)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(reopened.path.stat().st_mode), 0o600)

    def test_invalid_encrypted_and_scanned_pdfs_do_not_leave_documents(self):
        for raw in [
            b"not pdf",
            b"%PDF-1.7 broken",
            pdf_bytes([""], encrypted=True),
            pdf_bytes([""]),
        ]:
            with self.subTest(size=len(raw)):
                with self.assertRaises(ValueError):
                    self.store.add_document(self.project["id"], "Bad.pdf", raw)
        self.assertEqual(self.store.project_detail(self.project["id"])["documents"], [])

    def test_duplicate_project_pdf_is_idempotent_and_atomic_storage_budget(self):
        first = self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        again = self.store.add_document(self.project["id"], "Other.pdf", self.raw)
        self.assertEqual(first["id"], again["id"])
        self.assertTrue(again["already_exists"])
        with patch("apps.document_workspace.store.MAX_STORAGE", len(self.raw)):
            with self.assertRaises(ValueError):
                self.store.add_document(
                    self.project["id"], "Second.pdf", pdf_bytes(["A distinct PDF."])
                )
        self.assertEqual(
            len(self.store.project_detail(self.project["id"])["documents"]), 1
        )

    def test_conversation_notes_citations_persist_and_scope_to_project(self):
        doc = self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        citations = self.store.search(self.project["id"], "refund")
        conversation = self.store.create_conversation(
            self.project["id"], "Refund question"
        )
        self.store.add_message(conversation["id"], "user", "What is the refund period?")
        saved = self.store.add_message(
            conversation["id"],
            "assistant",
            "The source says 30 days. [1]",
            citations,
            mode="source_excerpts",
        )
        self.store.add_note(
            self.project["id"], "Check this refund period.", doc["id"], 2
        )
        reopened = Store(self.root)
        messages = reopened.get_conversation(conversation["id"])["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1], saved)
        detail = reopened.project_detail(self.project["id"])
        self.assertEqual(detail["notes"][0]["page"], 2)
        other = self.store.create_project("Other")
        self.assertEqual(self.store.search(other["id"], "refund"), [])
        with self.assertRaises(ValueError):
            self.store.search(other["id"], "refund", document_id=doc["id"])
        with self.assertRaises(ValueError):
            self.store.add_note(other["id"], "Bad scope", doc["id"], 2)
        other_conversation = self.store.create_conversation(other["id"], "Other chat")
        with self.assertRaises(ValueError):
            self.store.add_message(
                other_conversation["id"], "assistant", "Bad", citations
            )
        forged = [dict(citations[0], text="Made-up passage")]
        with self.assertRaises(ValueError):
            self.store.add_message(conversation["id"], "assistant", "Bad", forged)

    def test_text_and_option_validation_missing_ids_and_chunk_overlap(self):
        for name in ["", True, "x" * 101]:
            with self.assertRaises(ValueError):
                self.store.create_project(name)
        with self.assertRaises(KeyError):
            self.store.add_document("missing", "File.pdf", self.raw)
        for name in ["../file.pdf", "x.txt", "bad\nname.pdf"]:
            with self.assertRaises(ValueError):
                self.store.add_document(self.project["id"], name, self.raw)
        with self.assertRaises(ValueError):
            self.store.search(self.project["id"], "question", limit=True)
        long = "Refund details " + ("alpha beta gamma delta " * 100)
        doc = self.store.add_document(self.project["id"], "Long.pdf", pdf_bytes([long]))
        page = self.store.get_page(doc["id"], 1)["text"]
        results = self.store.search(self.project["id"], "alpha", document_id=doc["id"])
        self.assertGreater(len(results), 1)
        self.assertTrue(all(row["text"] in page for row in results))
        with self.assertRaises(ValueError):
            self.store.get_page(doc["id"], True)
        with self.assertRaises(KeyError):
            self.store.get_page(doc["id"], 2)

    def test_extraction_timeout_is_actionable_and_creates_no_document(self):
        import subprocess

        with patch(
            "apps.document_workspace.extractor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 30),
        ):
            with self.assertRaisesRegex(ValueError, "timed out"):
                self.store.add_document(self.project["id"], "Timeout.pdf", self.raw)
        self.assertEqual(self.store.project_detail(self.project["id"])["documents"], [])

    def test_document_count_and_extracted_text_quotas_leave_no_ghost_rows(self):
        self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        other_pdf = pdf_bytes(["Distinct content that would add a new source."])
        with patch("apps.document_workspace.store.MAX_DOCUMENTS", 1):
            with self.assertRaisesRegex(ValueError, "document limit"):
                self.store.add_document(self.project["id"], "Another.pdf", other_pdf)
        with patch("apps.document_workspace.store.MAX_INDEXED_CHARS", 1):
            with self.assertRaisesRegex(ValueError, "extracted-text quota"):
                self.store.add_document(self.project["id"], "Another.pdf", other_pdf)
        self.assertEqual(
            len(self.store.project_detail(self.project["id"])["documents"]), 1
        )
        self.assertEqual(self.store.search(self.project["id"], "Distinct"), [])

    def test_plural_retrieval_and_existing_fts_migration_preserve_source_records(self):
        doc = self.store.add_document(
            self.project["id"],
            "Refunds.pdf",
            pdf_bytes(["Refunds are available within 30 days of purchase."]),
        )
        results = self.store.search(self.project["id"], "What is the refund policy?")
        self.assertEqual(results[0]["document_id"], doc["id"])
        with self.store._db() as db:
            db.execute("DROP TABLE chunks_fts")
            db.execute(
                "CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED,text)"
            )
            db.execute("INSERT INTO chunks_fts SELECT id,text FROM chunks")
        reopened = Store(self.root)
        found = reopened.search(self.project["id"], "What is the refund policy?")
        self.assertEqual(found[0]["document_id"], doc["id"])
        self.assertEqual(
            reopened.get_document(doc["id"])["raw"],
            self.store.get_document(doc["id"])["raw"],
        )
        self.assertEqual(reopened.list_projects()[0]["document_count"], 1)

    def test_paraphrased_refund_question_finds_actual_source(self):
        doc = self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        for question in ["Can I get my money back?", "Is reimbursement available?"]:
            found = self.store.search(
                self.project["id"], question, document_id=doc["id"]
            )
            self.assertTrue(found)
            self.assertEqual(found[0]["page"], 2)
            self.assertIn("30 days", found[0]["text"])

    def test_query_coverage_ranks_specific_evidence_above_repeated_single_term(self):
        doc = self.store.add_document(
            self.project["id"],
            "Coverage.pdf",
            pdf_bytes(
                [
                    "Refunds refunds refunds refunds refunds refunds refunds.",
                    "Refunds are processed after purchase verification.",
                ]
            ),
        )
        found = self.store.search(
            self.project["id"], "refund purchase", document_id=doc["id"]
        )
        self.assertEqual(found[0]["page"], 2)

    def test_education_paraphrase_finds_degree_page(self):
        doc = self.store.add_document(
            self.project["id"],
            "Education.pdf",
            pdf_bytes(
                [
                    "Employment: Robert builds distributed services.",
                    "Education: Bachelor degree from Example University.",
                ]
            ),
        )
        found = self.store.search(
            self.project["id"], "Where did he study?", document_id=doc["id"]
        )
        self.assertEqual(found[0]["page"], 2)

    def test_unrelated_followup_does_not_match_person_pronoun(self):
        doc = self.store.add_document(
            self.project["id"],
            "Profile.pdf",
            pdf_bytes(
                [
                    "Robert is an engineer. His experience includes Python services.",
                ]
            ),
        )
        self.assertEqual(
            self.store.search(
                self.project["id"], "What is his salary?", document_id=doc["id"]
            ),
            [],
        )

    def test_real_extraction_keeps_page_numbers_and_generic_summary_works(self):
        pages = extract_pdf(self.raw)
        self.assertEqual([p["number"] for p in pages], [1, 2])
        doc = self.store.add_document(self.project["id"], "Policy.pdf", self.raw)
        self.assertTrue(
            self.store.search(
                self.project["id"], "Summarize this document", document_id=doc["id"]
            )
        )
        self.assertTrue(
            self.store.search(
                self.project["id"], "What is this about?", document_id=doc["id"]
            )
        )


if __name__ == "__main__":
    unittest.main()
