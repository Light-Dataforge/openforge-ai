import unittest
from unittest.mock import patch

from apps.document_workspace.semantic import HybridRanker, unit_vector


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"chunk_id": "a", "text": "Credential recovery uses email.", "page": 1}
        ]

    def test_real_ranking_contract_can_find_paraphrase_without_lexical_hit(self):
        with patch(
            "apps.document_workspace.semantic._request",
            return_value={"embeddings": [[1.0, 0.0], [1.0, 0.0]]},
        ):
            rows, mode = HybridRanker().rank("Forgot login", [], self.rows)
        self.assertEqual(mode, "hybrid")
        self.assertEqual(rows, self.rows)

    def test_semantic_evidence_breaks_a_rank_fusion_tie_with_lexical_noise(self):
        noisy = {"chunk_id": "noise", "text": "Keyword only", "page": 2}
        with patch(
            "apps.document_workspace.semantic._request",
            return_value={"embeddings": [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]},
        ):
            rows, _ = HybridRanker().rank("Paraphrase", [noisy], [noisy, *self.rows])
        self.assertEqual(rows[0]["chunk_id"], "a")

    def test_unrelated_vectors_do_not_supply_new_evidence(self):
        with patch(
            "apps.document_workspace.semantic._request",
            return_value={"embeddings": [[1.0, 0.0], [0.0, 1.0]]},
        ):
            rows, mode = HybridRanker().rank("Unrelated question", [], self.rows)
        self.assertEqual(rows, [])
        self.assertEqual(mode, "hybrid")

    def test_missing_runtime_or_invalid_vectors_preserve_lexical_results(self):
        for value in [
            OSError("offline"),
            {"embeddings": [[float("nan")], [1.0]]},
            {"embeddings": [[1.0], [1.0, 2.0]]},
        ]:
            options = (
                {"side_effect": value}
                if isinstance(value, Exception)
                else {"return_value": value}
            )
            with patch("apps.document_workspace.semantic._request", **options):
                rows, mode = HybridRanker().rank("Query", self.rows, self.rows)
            self.assertEqual(rows, self.rows)
            self.assertEqual(mode, "keyword_fallback")

    def test_candidate_scope_is_preserved_across_cached_searches(self):
        ranker = HybridRanker()
        with patch(
            "apps.document_workspace.semantic._request",
            side_effect=lambda path, data, **kw: {
                "embeddings": [[1.0, 0.0] for _ in data["input"]]
            },
        ):
            ranker.rank("Query", [], self.rows)
            other = [{"chunk_id": "b", "text": "Other project evidence", "page": 1}]
            rows, _ = ranker.rank("Query", [], other)
        self.assertEqual([r["chunk_id"] for r in rows], ["b"])

    def test_large_projects_fall_back_without_partial_indexing(self):
        with patch(
            "apps.document_workspace.semantic._request",
            side_effect=AssertionError("not called"),
        ):
            rows, mode = HybridRanker().rank("Query", self.rows, self.rows * 201)
        self.assertEqual(mode, "keyword_fallback")
        self.assertEqual(rows, self.rows)

    def test_invalid_embedding_values_are_rejected(self):
        for value in [[], [0.0], [True], [float("inf")]]:
            with self.assertRaises(ValueError):
                unit_vector(value)
