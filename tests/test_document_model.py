import unittest
from unittest.mock import patch

from apps.document_workspace import model


class DocumentModelTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "document_name": "Policy.pdf",
                "page": 2,
                "text": "Customers may request refunds within 30 days.",
            }
        ]

    def test_long_fallback_selects_verbatim_evidence_without_dumping_page(self):
        source = (
            "Unrelated background. " * 80
            + "Programming languages include Python and Java."
        )
        excerpt = model.evidence_excerpt("What programming languages?", source)
        self.assertIn("Programming languages include Python and Java.", excerpt)
        self.assertLess(len(excerpt), 700)

    def test_model_receives_previous_questions_as_context_not_evidence(self):
        with (
            patch.object(model, "health", return_value={"available": True}),
            patch.object(
                model, "_request", return_value={"message": {"content": "30 days [1]."}}
            ) as request,
        ):
            model.answer(
                "And how long?",
                self.sources,
                history=[{"role": "user", "content": "What is the refund policy?"}],
            )
        prompt = request.call_args.args[1]["messages"][1]["content"]
        self.assertIn("context only, not evidence", prompt)
        self.assertIn("What is the refund policy?", prompt)

    def test_structured_answer_uses_validated_source_ids(self):
        with (
            patch.object(model, "health", return_value={"available": True}),
            patch.object(
                model,
                "_request",
                return_value={
                    "message": {
                        "content": (
                            '{"answer":"Refunds within 30 days.","source_ids":[1]}'
                        )
                    }
                },
            ),
        ):
            content, mode = model.answer("Refund period?", self.sources)
        self.assertEqual(mode, "local_model")
        self.assertEqual(content, "Refunds within 30 days. [1]")

    def test_structured_answer_rejects_invalid_source_ids(self):
        for refs in ["[0]", "[2]", "[true]", "[]"]:
            with (
                patch.object(model, "health", return_value={"available": True}),
                patch.object(
                    model,
                    "_request",
                    return_value={
                        "message": {
                            "content": '{"answer":"Unsupported","source_ids":'
                            + refs
                            + "}"
                        }
                    },
                ),
            ):
                content, mode = model.answer("Refund period?", self.sources)
            self.assertEqual(mode, "source_excerpts")
            self.assertNotIn("Unsupported", content)

    def test_programming_languages_excludes_tools_and_preserves_evidence(self):
        sources = [
            dict(
                self.sources[0],
                text=(
                    "Tech: Java, Python, Scala, Apache Spark, Kafka, AWS, S3, DynamoDB."
                ),
            )
        ]
        with patch.object(model, "_request", side_effect=AssertionError("not needed")):
            content, mode = model.answer(
                "What programming languages does he use?", sources
            )
        self.assertEqual(mode, "source_excerpts")
        self.assertIn("Python [1]", content)
        self.assertIn("Scala [1]", content)
        self.assertNotIn("AWS", content)
        self.assertNotIn("Spark", content)
        self.assertNotIn("Ruby", content)

    def test_missing_or_malformed_runtime_is_explicitly_unavailable(self):
        for outcome in [OSError("unavailable"), {"models": None}, {"models": []}]:
            options = (
                {"side_effect": outcome}
                if isinstance(outcome, Exception)
                else {"return_value": outcome}
            )
            with patch.object(model, "_request", **options):
                self.assertFalse(model.health()["available"])

    def test_no_sources_never_calls_model_or_invents_answer(self):
        with patch.object(model, "_request", side_effect=AssertionError("not called")):
            content, mode = model.answer("What is the refund policy?", [])
        self.assertEqual(mode, "source_excerpts")
        self.assertIn("couldn’t find", content)

    def test_source_only_preserves_actual_passage_and_labels_mode(self):
        with patch.object(model, "health", return_value={"available": False}):
            content, mode = model.answer("What is the refund policy?", self.sources)
        self.assertEqual(mode, "source_excerpts")
        self.assertIn(self.sources[0]["text"], content)
        self.assertIn("[1]", content)

    def test_local_answer_requires_actual_source_reference(self):
        with (
            patch.object(model, "health", return_value={"available": True}),
            patch.object(
                model,
                "_request",
                return_value={
                    "message": {"content": "Refunds are available within 30 days [1]."}
                },
            ) as request,
        ):
            content, mode = model.answer("What is the refund policy?", self.sources)
        self.assertEqual(mode, "local_model")
        self.assertIn("30 days", content)
        self.assertEqual(request.call_args.args[0], "/api/chat")
        payload = request.call_args.args[1]
        self.assertFalse(payload["stream"])
        self.assertIn("untrusted data", payload["messages"][0]["content"])
        self.assertNotIn("tools", payload)

    def test_invalid_citations_or_local_failure_returns_evidence_not_fake_ai(self):
        for outcome in [
            {"message": {"content": "A claim with no source"}},
            {"message": {"content": "A claim [9]"}},
            {"message": None},
            OSError("private provider error"),
        ]:
            options = (
                {"side_effect": outcome}
                if isinstance(outcome, Exception)
                else {"return_value": outcome}
            )
            with (
                patch.object(model, "health", return_value={"available": True}),
                patch.object(model, "_request", **options),
            ):
                content, mode = model.answer("Question?", self.sources)
            self.assertEqual(mode, "source_excerpts")
            self.assertIn(self.sources[0]["text"], content)
            self.assertNotIn("private provider error", content)
