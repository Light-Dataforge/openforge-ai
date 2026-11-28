import tempfile
import unittest
from pathlib import Path

from apps.document_workspace import evidence, research
from apps.document_workspace.store import Store


class ResearchReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.project = self.store.create_project("Review")["id"]
        self.doc = self.store.add_document(
            self.project, "Policy.txt", b"Refunds within 45 days."
        )
        self.note = self.store.add_note(
            self.project, "Refund window is 45 days.", self.doc["id"], 1
        )
        self.project_note = self.store.add_note(
            self.project, "Investigate the exceptions."
        )
        self.table = evidence.create_table(
            self.store, self.project, "Policies", [self.doc["id"]], ["Refunds?"]
        )
        evidence.update_cell(
            self.store,
            self.project,
            self.table["id"],
            self.doc["id"],
            0,
            "Need to verify eligibility.",
            "unclear",
            1,
        )

    def create(self):
        choices = research.candidates(self.store, self.project)
        return research.create_report(
            self.store, self.project, "Research", [item["id"] for item in choices]
        )

    def edit(self, report, **changes):
        data = {
            key: report[key] for key in ("title", "summary", "conclusion", "revision")
        }
        data["sections"] = [
            {"id": item["id"], "text": item["text"]} for item in report["sections"]
        ]
        data.update(changes)
        return research.update_report(self.store, self.project, report["id"], data)

    def test_candidates_include_notes_and_only_reviewed_table_findings(self):
        choices = research.candidates(self.store, self.project)
        self.assertEqual(len(choices), 3)
        self.assertEqual(sum(bool(item["sources"]) for item in choices), 2)
        self.assertEqual(choices[-1]["review"], "unclear")
        evidence.update_cell(
            self.store,
            self.project,
            self.table["id"],
            self.doc["id"],
            0,
            "Unreviewed text",
            "unreviewed",
            2,
        )
        self.assertEqual(len(research.candidates(self.store, self.project)), 2)

    def test_saved_sources_do_not_change_after_note_edit_and_store_reopen(self):
        report = self.create()
        self.store.update_note(
            self.project, self.note["id"], "Changed later", self.note["text"]
        )
        saved = research.get_report(
            Store(Path(self.temp.name)), self.project, report["id"]
        )
        self.assertEqual(saved, report)
        self.assertIn(
            "Refund window is 45 days.", [item["text"] for item in saved["sections"]]
        )

    def test_reordering_removal_and_edits_preserve_server_owned_sources(self):
        report = self.create()
        last = report["sections"][-1]
        saved = self.edit(
            report,
            sections=[{"id": last["id"], "text": "Updated conclusion", "sources": []}],
            summary="Overview",
            conclusion="Next steps",
        )
        self.assertEqual(len(saved["sections"]), 1)
        self.assertEqual(saved["sections"][0]["sources"], last["sources"])
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["summary"], "Overview")

    def test_stale_edits_and_unknown_sections_cannot_overwrite(self):
        report = self.create()
        self.edit(report, title="Saved")
        with self.assertRaisesRegex(ValueError, "another tab"):
            self.edit(report, title="Stale")
        current = research.get_report(self.store, self.project, report["id"])
        with self.assertRaises(ValueError):
            self.edit(current, sections=[{"id": "foreign", "text": "bad"}])
        self.assertEqual(
            research.get_report(self.store, self.project, report["id"])["title"],
            "Saved",
        )

    def test_cross_project_selection_read_and_write_rejected(self):
        report = self.create()
        other = self.store.create_project("Other")["id"]
        with self.assertRaises(ValueError):
            research.create_report(
                self.store, other, "Invalid", ["note:" + self.note["id"]]
            )
        with self.assertRaises(KeyError):
            research.get_report(self.store, other, report["id"])
        with self.assertRaises(KeyError):
            research.update_report(
                self.store,
                other,
                report["id"],
                {
                    "title": "Bad",
                    "summary": "",
                    "conclusion": "",
                    "revision": 1,
                    "sections": [{"id": "x", "text": "bad"}],
                },
            )

    def test_exports_keep_sections_and_escape_html(self):
        report = self.create()
        saved = self.edit(
            report,
            title='<script>alert("title")</script>',
            summary='<img src=x onerror="bad()">',
            conclusion="Next steps",
        )
        md = research.markdown_report(saved)
        self.assertIn("section 1", md)
        self.assertIn("No linked source", md)
        self.assertIn("Review: unclear", md)
        rendered = research.html_report(saved)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("@media print", rendered)
        self.assertIn("section 1", rendered)

    def test_invalid_selections_and_text_budget(self):
        for selected in [[], ["missing"], ["note:" + self.note["id"]] * 2]:
            with self.assertRaises(ValueError):
                research.create_report(self.store, self.project, "Invalid", selected)
        report = self.create()
        with self.assertRaises(ValueError):
            self.edit(report, sections=[])
