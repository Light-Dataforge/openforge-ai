"""Conservative query expansion for document questions and follow-ups."""

from __future__ import annotations

import re
from typing import Any


def retrieval_query(question: str, history: list[dict[str, Any]]) -> str:
    query = re.sub(r"\blangugae\b", "language", question, flags=re.IGNORECASE)
    query = re.sub(r"\blangauges\b", "languages", query, flags=re.IGNORECASE)
    terms = set(re.findall(r"\w+", query.lower()))
    expansions = []
    if terms & {"language", "languages", "skills", "stack"}:
        expansions.extend(
            [
                "programming",
                "python",
                "java",
                "javascript",
                "typescript",
                "sql",
                "skills",
                "tech",
            ]
        )
    if terms & {"who", "background"}:
        expansions.extend(["professional profile", "experience"])
    # Resolve only to the most recent explicit named subject, never to assistant
    # text or an earlier project's content. Keep the current question dominant.
    if terms & {"his", "her", "their", "he", "she", "they"}:
        for message in reversed(history[-8:]):
            if message.get("role") != "user":
                continue
            previous = message.get("content", "")
            names = re.findall(r"\b[A-Z][a-z]{2,}\b", previous)
            names = [
                name
                for name in names
                if name.lower()
                not in {
                    "what",
                    "who",
                    "where",
                    "when",
                    "how",
                    "tell",
                    "please",
                    "does",
                    "can",
                }
            ]
            if names:
                expansions.extend(names[:3])
                break
    return query + (" " + " ".join(expansions) if expansions else "")


STOP_WORDS = {
    "what",
    "which",
    "where",
    "when",
    "does",
    "that",
    "this",
    "with",
    "from",
    "have",
    "about",
    "would",
    "could",
    "should",
    "please",
    "tell",
    "document",
    "documents",
    "the",
    "are",
    "and",
    "for",
    "how",
    "can",
    "you",
    "give",
    "your",
    "its",
    "into",
    "is",
    "it",
    "of",
    "to",
    "in",
    "an",
    "a",
    "on",
    "or",
    "be",
    "as",
    "by",
    "at",
    "me",
    "my",
    "we",
    "us",
}

SYNONYMS = (
    {"refund", "refunds", "reimbursement", "reimburse", "moneyback"},
    {"purchase", "purchases", "buy", "bought", "purchasing"},
    {"support", "assistance", "helpdesk"},
    {
        "education",
        "degree",
        "university",
        "college",
        "studied",
        "study",
        "studies",
        "school",
    },
    {"salary", "compensation", "wages", "pay", "remuneration"},
    {"role", "position", "occupation", "profession"},
)
STOP_WORDS.update(
    {"who", "his", "her", "their", "he", "she", "they", "did", "do", "was", "were"}
)


def query_groups(question: str) -> list[set[str]]:
    question = re.sub(r"\bmoney\s+back\b", "refund", question, flags=re.IGNORECASE)
    words = list(dict.fromkeys(re.findall(r"\w{2,}", question.lower())))
    return [
        next((group for group in SYNONYMS if word in group), {word})
        for word in words
        if word not in STOP_WORDS
    ][:12]


def rank_passages(question: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = query_groups(question)

    def coverage(row: dict[str, Any]) -> int:
        words = set(re.findall(r"\w{2,}", row["text"].lower()))
        return sum(bool(group & words) for group in groups)

    return sorted(rows, key=lambda row: (-coverage(row), row["score"]))
