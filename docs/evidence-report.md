# Offline evidence report

```sh
python -m apps.verification_demo --output verification-run
python -m apps.evidence_report verification-run --output evidence.html
```

Open evidence.html locally to inspect original scenes, synthetic candidate claims,
verified/contradicted/abstained/error counts and expandable pixel evidence. Images
are embedded; no server, scripts, model, credentials, network or Kaggle is needed.
This is a read-only export, not a hosted dashboard or general image-understanding
application. No model predictions, benchmark scores or calibration are claimed.

The exporter validates frozen summary/results/fixture hashes and complete unique
assertion accounting. It recomputes each non-error structured claim from actual
image bytes, matching the question's supported grammar, rather than trusting a
stored status or updated checksum. Error rows remain explicit errors. All text is
HTML-escaped, a restrictive content policy disables scripts/network access, and
raw paths are not displayed. The report is not signed evidence of execution or
image authenticity. Inspect question/evidence content before sharing private data.

Bounds: 32 KiB summary, 2 MiB results, at most 40 assertions/20 cases, 2 MiB total
embedded images and a 4 MiB final HTML. Existing fixture/path/profile limits still
apply. Unsupported or inconsistent input exits 2 with no partial stdout/report.
Reports require the deterministic synthetic pixel-demo schema, not arbitrary
experiment formats. Original inputs are never rewritten.

Publication uses private staging, fsync and same-directory atomic hard linking,
refusing any existing output including symlinks. Parent directories must already
exist. A post-link sync failure may leave a complete valid report; sudden process
termination may leave a private staging file. This is not a power-loss or network-
filesystem durability guarantee. Use trusted, stable local directories and frozen
regular input files; no hostile-filesystem isolation claim is made.

Tests cover actual demo rendering, image embedding, recomputed evidence rejecting
false decisions despite updated hashes, duplicate accounting, malformed claims,
script-like error text escaping, symlink inputs, output conflicts, byte limits and
real CLI success/failure behavior. The browser appearance has not been screenshot-
verified in the current environment; tests inspect the generated HTML structure.
