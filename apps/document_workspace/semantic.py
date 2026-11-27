"""Bounded local embedding retrieval with explicit lexical fallback."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import OrderedDict
from typing import Any

from .model import _request

EMBED_MODEL = "all-minilm:22m"
SEMANTIC_THRESHOLD = 0.55


def unit_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4096:
        raise ValueError("Invalid embedding shape")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("Invalid embedding value")
    norm = math.sqrt(sum(x * x for x in value))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Invalid embedding norm")
    return [x / norm for x in value]


class HybridRanker:
    def __init__(self) -> None:
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def rank(
        self,
        question: str,
        lexical: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        limit: int = 6,
    ) -> tuple[list[dict[str, Any]], str]:
        if len(candidates) > 200 or not self._lock.acquire(blocking=False):
            return lexical[:limit], "keyword_fallback"
        try:
            deadline = time.monotonic() + 20
            texts = [question[:1000]] + [row["text"][:1000] for row in candidates]
            keys = [hashlib.sha256(text.encode()).hexdigest() for text in texts]
            missing = list(dict.fromkeys(key for key in keys if key not in self._cache))
            lookup = dict(zip(keys, texts, strict=True))
            for start in range(0, len(missing), 8):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Embedding budget exhausted")
                batch = missing[start : start + 8]
                result = _request(
                    "/api/embed",
                    {
                        "model": EMBED_MODEL,
                        "input": [lookup[key] for key in batch],
                        "truncate": True,
                        "keep_alive": "5m",
                    },
                    timeout=min(remaining, 15),
                )
                vectors = result.get("embeddings")
                if not isinstance(vectors, list) or len(vectors) != len(batch):
                    raise ValueError("Invalid embedding response")
                for key, vector in zip(batch, vectors, strict=True):
                    self._cache[key] = unit_vector(vector)
            vectors = [self._cache[key] for key in keys]
            if any(len(vector) != len(vectors[0]) for vector in vectors):
                raise ValueError("Inconsistent dimensions")
            similarities = [
                sum(a * b for a, b in zip(vectors[0], vector, strict=True))
                for vector in vectors[1:]
            ]
            semantic = sorted(
                zip(candidates, similarities, strict=True), key=lambda pair: -pair[1]
            )
            scores: dict[str, float] = {}
            rows = {row["chunk_id"]: row for row in candidates}
            for rank, row in enumerate(lexical, 1):
                rows[row["chunk_id"]] = row
                scores[row["chunk_id"]] = 1 / (60 + rank)
            for rank, (row, similarity) in enumerate(semantic, 1):
                if similarity >= SEMANTIC_THRESHOLD:
                    key = row["chunk_id"]
                    scores[key] = scores.get(key, 0) + 1 / (60 + rank)
            semantic_scores = {
                row["chunk_id"]: similarity for row, similarity in semantic
            }
            ordered = sorted(
                scores, key=lambda key: (-scores[key], -semantic_scores.get(key, -1))
            )
            return [dict(rows[key]) for key in ordered[:limit]], "hybrid"
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            self._cache.clear()
            return lexical[:limit], "keyword_fallback"
        finally:
            while len(self._cache) > 512:
                self._cache.popitem(last=False)
            self._lock.release()
