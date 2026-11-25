# Paired exact-answer evaluation

```sh
python -m apps.paired_evaluation REFERENCES BEFORE AFTER --seed 42 --replicates 1000
```

For a synthetic accounting demonstration, use `examples/references.jsonl`,
`examples/predictions.jsonl` and `examples/synthetic-paired-after.jsonl` as the
three inputs. These records are manually defined fixtures, not model outputs.

All three inputs use the existing strict bounded evaluator contracts. Each task ID
must occur exactly once in each file, with identical complete ID sets. Inputs are
read once for validation and byte hashes. Matching is exact and case-sensitive;
confidence values are validated but are not used to invent correctness or weight
sampling. No model is run, and no confidence value is generated.

## Complete paired accounting

Each source task is correct, incorrect or abstained. The complete3x3 before-row/
after-column table accounts for every reference task once. Per-source coverage is
answered/total; accuracy_all is correct/total. Abstentions remain in the denominator
and count as not correct. The point difference is after accuracy_all minus before
accuracy_all, computed as (after correct - before correct)/total. An abstention-to-
incorrect transition does not improve this metric; coverage still changes.

## Reproducible paired bootstrap

Sort task IDs, then store each task's after-minus-before correctness difference
(-1,0,1). For each replicate, sample total task indices with replacement, retaining
the pairing, and average their differences. Sampling before/after independently
would destroy that pairing and is not performed.

The local random.Random(seed).randrange(total) stream is used. Seed must be an
integer0–2^32-1, excluding bool. Replicates must be an integer100–5000. The workload
is explicitly limited to total*replicates <=2,000,000 draws; larger requests fail
rather than silently reducing repetitions or discarding tasks. Default1000 thus
supports up to2000 tasks;10000 tasks require at most200 replicates. No input rows
are silently sampled down. Python runtime/method metadata is retained because a
seed alone is not a universal cross-runtime reproducibility guarantee.

Sort replicate means. The nominal95% empirical percentile interval uses zero-based
indexes (B-1)*25//1000 and (B-1)*975//1000, where B is replicate count. No interpolation,
normal approximation, p-value or significance label is produced. Identical outcomes
have a degenerate zero interval; all-positive/all-negative differences have
corresponding degenerate intervals. These facts describe this resampling procedure,
not certainty about a population effect.

## Interpretation and limits

This is exploratory tooling, not a guarantee of95% population coverage or a causal
finding. It assumes exchangeable independent task sampling; clustered/related
samples, contamination, small samples, adaptive selection and correlated model
errors can invalidate interpretation. Monte Carlo error depends on replicate count.
Predefine data selection, seeds, stopping rules and evaluation policies; assess
sample size and use an appropriate clustered design when needed. No such design
is inferred automatically. Fair compute budgets and held-out separation must be
established independently; prediction files cannot prove them.

Reports contain counts, aggregate differences/intervals, configuration and input
hashes, never IDs, answers or source paths. Declared predictions/hashes do not prove
model execution, visual grounding or scientific validity. Example fixtures are
synthetic accounting records, not model results. Regular-file/byte/record limits
and trusted/stable ancestor assumptions apply. Invalid inputs or workload bounds
return CLI2 with no partial success JSON. Inputs are never changed; no GPU, model
runtime, network, paid resource or deployment is required.
