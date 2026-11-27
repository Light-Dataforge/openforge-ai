import unittest

from apps.document_workspace.evaluate_answers import grade


class AnswerDiagnosticTests(unittest.TestCase):
    def test_refusal_with_forbidden_claim_does_not_pass(self):
        result = grade(
            {"expected": "safe", "forbidden": ["ninety-nine"]},
            "Cannot answer; ninety-nine years.",
            "insufficient_evidence",
            1,
        )
        self.assertFalse(result["diagnostic_passed"])

    def test_source_fallback_is_not_scored_as_generated_answer(self):
        result = grade(
            {"expected": "supported", "facts": [["30 days"]]},
            "Here are excerpts: 30 days [1]",
            "source_excerpts",
            1,
        )
        self.assertFalse(result["diagnostic_passed"])

    def test_correct_fact_with_invalid_citation_does_not_pass(self):
        result = grade(
            {"expected": "supported", "facts": [["30 days"]]},
            "30 days [2]",
            "local_model",
            1,
        )
        self.assertFalse(result["diagnostic_passed"])
