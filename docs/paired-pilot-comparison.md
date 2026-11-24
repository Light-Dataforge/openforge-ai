# Paired offline pilot comparisons

```sh
python -m apps.pilot_compare BEFORE_RUN AFTER_RUN MANIFEST --output NEW_COMPARISON.json
```

Both source runs are revalidated independently against one frozen manifest, including
source hashes, complete task coverage, counts and lifecycle declarations. Supported
claims are recomputed from actual image bytes. Manifest hash, task IDs, image digests
and question text must agree between checks. Inputs must remain trusted and frozen;
this is not an atomic multi-file snapshot or source-runtime attestation.

The comparison retains all five statuses in a complete before-row/after-column
transition matrix: verified, contradicted, abstained, failed, not_executed. Every task
is represented exactly once. Row/column totals match source counts. Per-task flags
indicate normalized-answer/reason changes, without assigning a numerical quality
score. A transition from dry-run to verified is not called a model improvement.
Self-comparison is allowed and produces diagonal transitions. Source declarations
and hashes are retained; timestamps and filesystem paths are excluded.

No model is loaded or inference performed. Synthetic geometry checks do not establish
model accuracy, general image understanding, statistical significance or causality.
The report omits raw answers, reference labels, questions and failure messages, but
IDs, image/source digests, counts and change flags still reveal metadata: review it
before sharing. Normalization is the verification bridge's strip/lower rule.

Source bounds apply independently to both runs (at most20 cases each). Final JSON
is capped at2 MiB. Private temporary directories under the existing output parent
are cleaned on ordinary exit. The existing private exclusive hard-link publisher
refuses existing files, symlinks and racing destinations. Process death can leave
staging files; post-publication sync failure can leave a complete report despite
failure. No network, runtime downloads, cloud account or paid resource is needed.
