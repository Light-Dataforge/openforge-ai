# Structured claims for bounded synthetic visual checks

`core.verification.claims.verify_claim(image_bytes: bytes, claim: dict) -> dict`
uses observed raster components, never a fixture ID, filename, question answer,
reference label or stored lookup table. It is a deliberately narrow geometric
oracle for the supported red/green/blue palette and square/rectangle/circle
categories. It is not general image understanding or a model-answer benchmark.

The observer is imported lazily from `core.verification.raster.observe`. This
module can be independently tested with injected observations; real-pixel behavior
must additionally be exercised when integrated with the raster observer. Observer
absence, unsupported rasters or malformed observations abstain instead of being
counted as verified. Unexpected implementation faults are not silently converted
to positive results.

## Claim contracts

Each object must have exactly its listed fields and bounded string values:

| Kind | Exact fields | Answer |
| --- | --- | --- |
| color | kind, shape, answer | red / green / blue |
| count | kind, color, shape, answer | Canonical decimal string 0–1024 |
| relation | kind, subject_color, subject_shape, object_color, object_shape, answer | left / right |
| tallest | kind, answer | red / green / blue |

Requested colors/shapes must be from the defined palette/categories; `unknown`
cannot be requested as a shape. Wrong types, unknown keys/kinds, moving prose,
unsupported enum values, leading-zero counts and out-of-range counts raise
ValueError, distinct from abstention about valid claims. Text is not parsed into
claims or normalized silently.

## Conservative decision rules

- Color: exactly one component matching the requested shape across all palette
  colors. Multiple/absent candidates abstain, even if multiple candidates share
  the same color. Unknown components also abstain since they may match the shape.
- Count: count exact shape matches in the requested color. Known different shapes
  are excluded; zero is valid. Any unknown shape in that color causes abstention,
  while unknown components in another color do not change the count.
- Relation: both selectors must resolve uniquely. Unknown shapes in relevant
  colors, absent/duplicate selectors, identical objects or horizontal overlap
  abstain. Exclusive bounds establish left/right only when horizontally disjoint;
  touching exclusive edges are nonoverlapping.
- Tallest: at least two filled square/rectangle bars, the same bottom baseline,
  horizontally nonoverlapping boxes, and exactly one largest height. Unknown
  components, missing bars, different baselines, overlapping bars or tied heights
  abstain. Known circles are not treated as bars.

Results contain exactly status, expected, claimed, reason, evidence. Status is
verified when the uniquely derived answer equals the claim, contradicted when it
differs, otherwise abstained with expected=null. No confidence is invented.
Evidence binds bounded image bytes with SHA-256 and includes copied observed
component geometry, rather than labels. Oversized input abstains without invoking
the observer or hashing more than the allowed 2 MiB. Coordinates must be integer
0–512 with positive exclusive extents; pixels must fit the box, filled rectangles
must have full area, squares equal edges, and total components cannot exceed 1024.
These limits describe this oracle's supported input, not arbitrary raster safety.

This is synthetic plumbing verification, not proof of perceptual correctness,
general reasoning, real-world evidence reliability or a model improvement. External
model/free-GPU inference is not invoked. No billable resource or service is used.
