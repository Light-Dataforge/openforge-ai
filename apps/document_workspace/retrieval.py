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
        expansions.extend(["professional summary", "experience"])
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
