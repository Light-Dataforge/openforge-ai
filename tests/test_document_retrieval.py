import unittest

from apps.document_workspace.retrieval import retrieval_query


class RetrievalTests(unittest.TestCase):
    def test_misspelled_language_question_expands_to_technical_vocabulary(self):
        result = retrieval_query("What is his langugae?", [])
        self.assertIn("language", result)
        self.assertIn("python", result)

    def test_followup_uses_latest_named_user_subject_not_assistant_claim(self):
        result = retrieval_query(
            "What are his skills?",
            [
                {"role": "user", "content": "Who is Robert?"},
                {"role": "assistant", "content": "SecretName invented claim"},
            ],
        )
        self.assertIn("Robert", result)
        self.assertNotIn("SecretName", result)

    def test_standalone_question_does_not_inherit_previous_subject(self):
        self.assertNotIn(
            "Robert",
            retrieval_query(
                "What is the refund period?",
                [
                    {"role": "user", "content": "Who is Robert?"},
                ],
            ),
        )
