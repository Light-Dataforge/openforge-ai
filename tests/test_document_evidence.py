import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_document_store import pdf_bytes

from apps.document_workspace import evidence
from apps.document_workspace.store import Store


class EvidenceTableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.project = self.store.create_project("Policies")["id"]
        self.first = self.store.add_document(
            self.project, "Alpha.pdf", pdf_bytes(["Refunds within 30 days."])
        )
        self.second = self.store.add_document(
            self.project, "Beta.pdf", pdf_bytes(["Support is provided on weekdays."])
        )

    def create(self):
        return evidence.create_table(
            self.store,
            self.project,
            "Policy review",
            [self.first["id"], self.second["id"]],
            ["Refund policy?", "Support?"],
        )

    def test_document_scoped_cells_and_persistence_after_reopen(self):
        record = self.create()
        self.assertEqual(len(record["cells"]), 4)
        for cell in record["cells"]:
            self.assertTrue(
                all(
                    source["document_id"] == cell["document_id"]
                    for source in cell["sources"]
                )
            )
        self.assertTrue(record["cells"][0]["sources"])
        self.assertFalse(record["cells"][2]["sources"])
        reopened = Store(Path(self.temp.name))
        self.assertEqual(
            evidence.get_table(reopened, self.project, record["id"]), record
        )
        self.assertEqual(
            evidence.list_tables(reopened, self.project)[0]["id"], record["id"]
        )

    def test_cross_project_sources_and_reads_are_rejected(self):
        record = self.create()
        other = self.store.create_project("Other")["id"]
        with self.assertRaises(ValueError):
            evidence.create_table(
                self.store, other, "Invalid", [self.first["id"]], ["Refund?"]
            )
        with self.assertRaises(KeyError):
            evidence.get_table(self.store, other, record["id"])
        with self.assertRaises(KeyError):
            evidence.update_cell(
                self.store,
                other,
                record["id"],
                self.first["id"],
                0,
                "wrong project",
                "unclear",
                1,
            )

    def test_revision_conflict_preserves_saved_finding(self):
        record = self.create()
        saved = evidence.update_cell(
            self.store,
            self.project,
            record["id"],
            self.first["id"],
            0,
            "30-day window",
            "supported",
            1,
        )
        self.assertEqual(saved["revision"], 2)
        with self.assertRaisesRegex(ValueError, "another tab"):
            evidence.update_cell(
                self.store,
                self.project,
                record["id"],
                self.first["id"],
                0,
                "stale overwrite",
                "unclear",
                1,
            )
        self.assertEqual(
            evidence.get_table(self.store, self.project, record["id"])["cells"][0][
                "finding"
            ],
            "30-day window",
        )

    def test_missing_source_cannot_be_marked_supported(self):
        record = self.create()
        with self.assertRaisesRegex(ValueError, "matching source"):
            evidence.update_cell(
                self.store,
                self.project,
                record["id"],
                self.second["id"],
                0,
                "Guess",
                "supported",
                1,
            )

    def test_invalid_dimensions_and_cell_selection_do_not_write(self):
        for docs, questions in [
            ([], ["Refund?"]),
            ([self.first["id"]] * 2, ["Refund?"]),
            ([self.first["id"]], ["refund", "REFUND"]),
            ([self.first["id"]], ["q"] * 7),
        ]:
            with self.assertRaises(ValueError):
                evidence.create_table(self.store, self.project, "Test", docs, questions)
        self.assertFalse(evidence.list_tables(self.store, self.project))
        record = self.create()
        for column in [True, -1, 6]:
            with self.assertRaises(ValueError):
                evidence.update_cell(
                    self.store,
                    self.project,
                    record["id"],
                    self.first["id"],
                    column,
                    "bad",
                    "unclear",
                    1,
                )

    def test_csv_preserves_newlines_and_neutralizes_formulas(self):
        record = self.create()
        saved = evidence.update_cell(
            self.store,
            self.project,
            record["id"],
            self.first["id"],
            0,
            '=HYPERLINK("example")\nSecond line',
            "unclear",
            1,
        )
        rows = list(
            csv.reader(io.StringIO(evidence.export_csv(saved).lstrip("\ufeff")))
        )
        self.assertEqual(len(rows), 5)
        self.assertTrue(rows[1][3].startswith("'=HYPERLINK"))
        self.assertIn("\nSecond line", rows[1][3])
        self.assertEqual(rows[1][4], "1")
        self.assertIn("does not establish absence", rows[3][-1])

    def test_capacity_limit_is_enforced(self):
        with patch.object(evidence, "MAX_TABLES", 0), self.assertRaises(OverflowError):
            self.create()
        self.assertFalse(evidence.list_tables(self.store, self.project))
