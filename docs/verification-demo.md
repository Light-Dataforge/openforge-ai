# CPU pixel verification demo

From the repository root, choose a new output directory:

```sh
python -m apps.verification_demo --output verification-results
```

The CLI creates six original synthetic PNG scenes and checks twelve explicit
assertions: one fixture-derived candidate and one intentionally wrong candidate
per scene. The deterministic verifier receives image bytes and a structured claim;
it never receives fixture IDs, filenames or reference-answer metadata as evidence.
Question routing supports only the six exact fixture question templates.

Supported claims are color, exact component count, disjoint horizontal relation
and uniquely tallest aligned bars. The bounded RGB PNG reader checks actual pixel
geometry. A report includes verified, contradicted, abstained or error for each
assertion, expected/claimed values, evidence and the input-image hash. Output is
private and refuses to overwrite existing directories. Failures remain accounted
for. CLI verification does not execute a model, make API calls or train anything.

The current original scenes produce six verified and six contradicted assertions.
These are software conformance observations, not benchmark scores, VLM predictions,
calibrated confidence, scientific novelty or evidence of general reasoning quality.
An integration test independently renders four green squares and confirms that a
candidate answer of three is contradicted from those pixels rather than labels.

## Boundaries

This is a narrow exact-palette/filter-0 RGB PNG prototype, not a general image,
photo, OCR, antialiased-shape, document or chart verifier. Read [raster limits](pixel-raster.md)
and [claim semantics](visual-claims.md). Unknown shapes, unsupported images,
ambiguous objects, overlapping relations and tied/nonaligned bars abstain when
appropriate; malformed structured claims fail validation. External images and
natural-language questions are not unrestricted inputs to this demo.

No GPU, Kaggle account, third-party runtime or paid resource is needed. Evidence
hashes identify bytes processed, not image authenticity. The output writes are
not an atomic multi-file transaction; interruption can leave a partial newly
created result directory. Do not interpret partial artifacts as a completed run.
Independent review remains required before merge or production use.
