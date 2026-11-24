"""Conservative geometric claim checks for the bounded synthetic raster palette."""

from __future__ import annotations

import hashlib
import importlib
from typing import Any

COLORS = frozenset({"red", "green", "blue"})
SHAPES = frozenset({"square", "rectangle", "circle"})
MAX_COMPONENTS = 1024
MAX_BYTES = 2 * 1024 * 1024


def _observe(raw: bytes) -> dict[str, Any]:
    module = importlib.import_module("core.verification.raster")
    result: dict[str, Any] = module.observe(raw)
    return result


def _claim(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise ValueError("claim must be a structured object with a known kind")
    fields = {
        "color": {"kind", "shape", "answer"},
        "count": {"kind", "color", "shape", "answer"},
        "relation": {
            "kind",
            "subject_color",
            "subject_shape",
            "object_color",
            "object_shape",
            "answer",
        },
        "tallest": {"kind", "answer"},
    }
    if value["kind"] not in fields or set(value) != fields[value["kind"]]:
        raise ValueError("unknown claim kind or invalid fields")
    if any(
        not isinstance(item, str) or not item or len(item) > 64
        for item in value.values()
    ):
        raise ValueError("claim values must be bounded nonempty strings")
    for key in ("color", "subject_color", "object_color"):
        if key in value and value[key] not in COLORS:
            raise ValueError("unsupported claim color")
    for key in ("shape", "subject_shape", "object_shape"):
        if key in value and value[key] not in SHAPES:
            raise ValueError("unsupported claim shape")
    answer = value["answer"]
    if value["kind"] == "count":
        if (
            not answer.isascii()
            or not answer.isdecimal()
            or len(answer) > 4
            or str(int(answer)) != answer
            or int(answer) > MAX_COMPONENTS
        ):
            raise ValueError("count answer must be canonical decimal from 0 to 1024")
    elif value["kind"] == "relation":
        if answer not in {"left", "right"}:
            raise ValueError("relation answer must be left or right")
    elif answer not in COLORS:
        raise ValueError("color answer must be red, green or blue")
    return dict(value)


def _observations(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != COLORS:
        raise ValueError("invalid observation colors")
    result: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for color in sorted(COLORS):
        rows = value[color]
        if not isinstance(rows, list):
            raise ValueError("components must be lists")
        total += len(rows)
        if total > MAX_COMPONENTS:
            raise ValueError("too many components")
        result[color] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "left",
                "top",
                "right",
                "bottom",
                "pixels",
                "shape",
            }:
                raise ValueError("invalid component fields")
            for coordinate in ("left", "top", "right", "bottom"):
                if type(row[coordinate]) is not int or not 0 <= row[coordinate] <= 512:
                    raise ValueError("invalid component coordinate")
            width, height = row["right"] - row["left"], row["bottom"] - row["top"]
            if (
                width <= 0
                or height <= 0
                or type(row["pixels"]) is not int
                or not 1 <= row["pixels"] <= width * height
            ):
                raise ValueError("invalid component extent or pixels")
            if not isinstance(row["shape"], str) or row["shape"] not in SHAPES | {
                "unknown"
            }:
                raise ValueError("invalid observed shape")
            if (
                row["shape"] in {"square", "rectangle"}
                and row["pixels"] != width * height
            ):
                raise ValueError("rectangular shapes must be filled")
            if row["shape"] == "square" and width != height:
                raise ValueError("square must have equal edges")
            result[color].append(dict(row))
        result[color].sort(
            key=lambda row: (
                row["top"],
                row["left"],
                row["bottom"],
                row["right"],
                row["pixels"],
                row["shape"],
            )
        )
    return result


def _expected(
    claim: dict[str, str], observed: dict[str, list[dict[str, Any]]]
) -> tuple[str | None, str]:
    kind = claim["kind"]
    if kind == "color":
        if any(row["shape"] == "unknown" for rows in observed.values() for row in rows):
            return None, "unknown_color_candidate"
        candidates = [
            color
            for color, rows in observed.items()
            for row in rows
            if row["shape"] == claim["shape"]
        ]
        return (
            (candidates[0], "unique_shape_color")
            if len(candidates) == 1
            else (None, "ambiguous_color")
        )
    if kind == "count":
        rows = observed[claim["color"]]
        if any(row["shape"] == "unknown" for row in rows):
            return None, "unknown_count_shape"
        return str(
            sum(row["shape"] == claim["shape"] for row in rows)
        ), "exact_component_count"
    if kind == "relation":
        subject_rows = observed[claim["subject_color"]]
        object_rows = observed[claim["object_color"]]
        if any(row["shape"] == "unknown" for row in subject_rows + object_rows):
            return None, "unknown_relation_shape"
        subjects = [
            row for row in subject_rows if row["shape"] == claim["subject_shape"]
        ]
        objects = [row for row in object_rows if row["shape"] == claim["object_shape"]]
        if len(subjects) != 1 or len(objects) != 1:
            return None, "ambiguous_relation"
        subject, obj = subjects[0], objects[0]
        if subject["right"] <= obj["left"]:
            return "left", "disjoint_horizontal_bounds"
        if subject["left"] >= obj["right"]:
            return "right", "disjoint_horizontal_bounds"
        return None, "overlapping_horizontal_bounds"
    all_rows = [(color, row) for color, rows in observed.items() for row in rows]
    if any(row["shape"] == "unknown" for _, row in all_rows):
        return None, "unknown_bar_candidate"
    bars = [
        (color, row)
        for color, row in all_rows
        if row["shape"] in {"square", "rectangle"}
    ]
    if len(bars) < 2:
        return None, "insufficient_bars"
    if len({row["bottom"] for _, row in bars}) != 1:
        return None, "nonaligned_bars"
    ordered = sorted((row for _, row in bars), key=lambda row: row["left"])
    if any(
        left["right"] > right["left"]
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        return None, "overlapping_bars"
    tallest = max(row["bottom"] - row["top"] for _, row in bars)
    winners = [color for color, row in bars if row["bottom"] - row["top"] == tallest]
    return (
        (winners[0], "unique_tallest_bar") if len(winners) == 1 else (None, "tied_bars")
    )


def verify_claim(image_bytes: bytes, claim: dict[str, Any]) -> dict[str, Any]:
    """Verify only supported structured claims from observed geometry, never IDs.

    Invalid claims/types raise ValueError. Unsupported/invalid raster observations
    abstain with no expected answer or invented confidence. This is a bounded
    palette/shape oracle, not a general-purpose visual reasoning evaluator.
    """
    parsed = _claim(claim)
    if not isinstance(image_bytes, bytes):
        raise ValueError("image_bytes must be bytes")
    evidence: dict[str, Any] = {"image_bytes": len(image_bytes)}
    if len(image_bytes) <= MAX_BYTES:
        evidence["image_sha256"] = hashlib.sha256(image_bytes).hexdigest()
    expected = None
    if len(image_bytes) > MAX_BYTES:
        reason = "raster_byte_limit"
    else:
        try:
            observed = _observations(_observe(image_bytes))
        except ImportError:
            reason = "observer_unavailable"
        except ValueError:
            reason = "unsupported_raster_or_observation"
        else:
            evidence["components"] = observed
            expected, reason = _expected(parsed, observed)
    status = (
        "abstained"
        if expected is None
        else ("verified" if parsed["answer"] == expected else "contradicted")
    )
    return {
        "status": status,
        "expected": expected,
        "claimed": parsed["answer"],
        "reason": reason,
        "evidence": evidence,
    }
