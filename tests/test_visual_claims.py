import copy
import hashlib
import unittest
from unittest.mock import patch

from core.verification.claims import verify_claim


def rectangle(left=10, top=10, right=30, bottom=30, shape="square"):
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "pixels": (right - left) * (bottom - top),
        "shape": shape,
    }


def observations(**colors):
    return dict({"red": [], "green": [], "blue": []}, **colors)


class VisualClaimTests(unittest.TestCase):
    def verify(self, claim, observed):
        with patch("core.verification.claims._observe", return_value=observed):
            return verify_claim(b"synthetic pixels for unit-test observer", claim)

    def test_color_verifies_and_contradicts_with_bound_evidence(self):
        observed = observations(red=[rectangle()])
        result = self.verify(
            {"kind": "color", "shape": "square", "answer": "red"}, observed
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["expected"], "red")
        self.assertEqual(
            result["evidence"]["image_sha256"],
            hashlib.sha256(b"synthetic pixels for unit-test observer").hexdigest(),
        )
        result = self.verify(
            {"kind": "color", "shape": "square", "answer": "blue"}, observed
        )
        self.assertEqual(result["status"], "contradicted")
        self.assertEqual(result["claimed"], "blue")
        self.assertNotIn("confidence", result)

    def test_ambiguous_absent_and_unknown_color_candidates_abstain(self):
        claim = {"kind": "color", "shape": "square", "answer": "red"}
        for observed in [
            observations(),
            observations(red=[rectangle()], blue=[rectangle()]),
            observations(red=[rectangle()], green=[dict(rectangle(), shape="unknown")]),
        ]:
            result = self.verify(claim, observed)
            self.assertEqual(result["status"], "abstained")
            self.assertIsNone(result["expected"])

    def test_count_exact_shape_zero_and_wrong_answer(self):
        observed = observations(green=[rectangle(), rectangle(left=40, right=60)])
        claim = {"kind": "count", "color": "green", "shape": "square", "answer": "2"}
        self.assertEqual(self.verify(claim, observed)["status"], "verified")
        self.assertEqual(
            self.verify(dict(claim, answer="3"), observed)["status"], "contradicted"
        )
        self.assertEqual(
            self.verify(dict(claim, color="blue", answer="0"), observed)["status"],
            "verified",
        )
        self.assertEqual(
            self.verify(dict(claim, shape="circle", answer="0"), observed)["status"],
            "verified",
        )

    def test_unknown_matching_count_color_abstains(self):
        claim = {"kind": "count", "color": "green", "shape": "circle", "answer": "0"}
        self.assertEqual(
            self.verify(
                claim, observations(green=[dict(rectangle(), shape="unknown")])
            )["status"],
            "abstained",
        )
        self.assertEqual(
            self.verify(claim, observations(red=[dict(rectangle(), shape="unknown")]))[
                "status"
            ],
            "verified",
        )

    def relation(self, answer="left"):
        return {
            "kind": "relation",
            "subject_color": "red",
            "subject_shape": "square",
            "object_color": "blue",
            "object_shape": "circle",
            "answer": answer,
        }

    def test_unique_nonoverlapping_relation_both_directions(self):
        circle = dict(rectangle(left=50, right=70), pixels=300, shape="circle")
        observed = observations(red=[rectangle()], blue=[circle])
        self.assertEqual(self.verify(self.relation(), observed)["status"], "verified")
        self.assertEqual(
            self.verify(self.relation("right"), observed)["status"], "contradicted"
        )
        observed = observations(red=[rectangle(left=90, right=110)], blue=[circle])
        self.assertEqual(
            self.verify(self.relation("right"), observed)["status"], "verified"
        )

    def test_relation_missing_duplicate_overlapping_or_identical_abstains(self):
        circle = dict(rectangle(), pixels=300, shape="circle")
        for observed in [
            observations(red=[rectangle()]),
            observations(
                red=[rectangle(), rectangle(left=50, right=70)], blue=[circle]
            ),
            observations(red=[rectangle()], blue=[circle]),
        ]:
            self.assertEqual(
                self.verify(self.relation(), observed)["status"], "abstained"
            )
        identical = {
            "kind": "relation",
            "subject_color": "red",
            "subject_shape": "square",
            "object_color": "red",
            "object_shape": "square",
            "answer": "left",
        }
        self.assertEqual(
            self.verify(identical, observations(red=[rectangle()]))["status"],
            "abstained",
        )

    def test_tallest_filled_aligned_bars_and_contradiction(self):
        observed = observations(
            red=[rectangle(left=10, top=40, right=20, bottom=80, shape="rectangle")],
            blue=[rectangle(left=40, top=20, right=50, bottom=80, shape="rectangle")],
        )
        self.assertEqual(
            self.verify({"kind": "tallest", "answer": "blue"}, observed)["status"],
            "verified",
        )
        self.assertEqual(
            self.verify({"kind": "tallest", "answer": "red"}, observed)["status"],
            "contradicted",
        )

    def test_tallest_requires_multiple_aligned_unique_known_bars(self):
        bar = rectangle(left=10, top=40, right=20, bottom=80, shape="rectangle")
        other = rectangle(left=40, top=40, right=50, bottom=80, shape="rectangle")
        for observed in [
            observations(red=[bar]),
            observations(red=[bar], blue=[other]),
            observations(red=[bar], blue=[dict(other, bottom=79, pixels=390)]),
            observations(red=[bar], blue=[dict(other, shape="unknown")]),
        ]:
            self.assertEqual(
                self.verify({"kind": "tallest", "answer": "blue"}, observed)["status"],
                "abstained",
            )

    def test_tallest_overlapping_bars_abstain(self):
        observed = observations(
            red=[rectangle(left=10, top=40, right=30, bottom=80, shape="rectangle")],
            blue=[rectangle(left=20, top=20, right=40, bottom=80, shape="rectangle")],
        )
        result = self.verify({"kind": "tallest", "answer": "blue"}, observed)
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["reason"], "overlapping_bars")

    def test_invalid_claim_schemas_types_values_and_bounds(self):
        good = {"kind": "count", "color": "red", "shape": "square", "answer": "1"}
        invalid = [
            None,
            [],
            {},
            dict(good, extra="x"),
            dict(good, kind="freeform"),
            dict(good, color="yellow"),
            dict(good, shape="unknown"),
            dict(good, answer=True),
            dict(good, answer="01"),
            dict(good, answer="1025"),
            dict(good, answer="１"),
            dict(good, answer="x" * 65),
        ]
        for claim in invalid:
            with self.subTest(claim=claim), self.assertRaises(ValueError):
                self.verify(claim, observations())
        with self.assertRaises(ValueError):
            verify_claim("not bytes", good)

    def test_invalid_observations_abstain_instead_of_verifying(self):
        claim = {"kind": "color", "shape": "square", "answer": "red"}
        for value in [
            {},
            observations(red="bad"),
            observations(red=[dict(rectangle(), left=True)]),
            observations(red=[dict(rectangle(), right=513)]),
            observations(red=[dict(rectangle(), pixels=2)]),
            observations(red=[rectangle()] * 1025),
        ]:
            self.assertEqual(self.verify(claim, value)["status"], "abstained")

    def test_unsupported_raster_and_absent_observer_abstain(self):
        claim = {"kind": "color", "shape": "square", "answer": "red"}
        for error in [ValueError("unsupported raster"), ImportError("observer absent")]:
            with patch("core.verification.claims._observe", side_effect=error):
                result = verify_claim(b"not a raster", claim)
            self.assertEqual(result["status"], "abstained")
            self.assertIsNone(result["expected"])
        with patch(
            "core.verification.claims._observe",
            side_effect=AssertionError("do not decode"),
        ):
            self.assertEqual(
                verify_claim(b"x" * (2 * 1024 * 1024 + 1), claim)["status"], "abstained"
            )

    def test_observations_and_claims_are_not_mutated(self):
        observed = observations(red=[rectangle()])
        original = copy.deepcopy(observed)
        claim = {"kind": "color", "shape": "square", "answer": "red"}
        result = self.verify(claim, observed)
        result["evidence"]["components"]["red"][0]["left"] = 99
        self.assertEqual(observed, original)
        self.assertEqual(claim["answer"], "red")


if __name__ == "__main__":
    unittest.main()
