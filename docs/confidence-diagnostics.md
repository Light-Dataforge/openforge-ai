# Confidence diagnostics for exact-answer predictions

```sh
python -m apps.confidence_diagnostics REFERENCES PREDICTIONS --bins 10
```

Uses the evaluator's strict bounded reference/prediction contract and complete ID
join. Matching is exact and case-sensitive. No confidence is inferred or invented:
answered predictions must supply finite probabilities of exact correctness, and
abstentions must supply null answer/confidence. Both input byte hashes are retained.
No IDs, answer strings, prompt text or absolute paths are exported.

## Reliability bins

Choose an integer2–50 bins (default10). Edges are the recorded float values i/bins.
Intervals include their lower edge and exclude the next edge; confidence1 belongs
to the final bin. At an interior edge, a prediction joins the upper bin. Empty bins
have count0 and null means/gaps. Nonempty bins report mean declared confidence,
observed exact correctness and absolute gap. ECE is the count-weighted absolute gap
over answered predictions; with no answers it is null. Always inspect coverage.

ECE is a descriptive, bin-dependent summary, not proof of calibration. It can look
small with little data, correlated samples, selective abstention or poorly chosen
bins. No uncertainty interval, causal statement, statistical test or new model
result is produced. The supplied example records are synthetic accounting fixtures.

## Selective risk and coverage

Answered predictions are grouped by equal confidence and admitted in descending
confidence order. Every threshold admits its entire tie group, so task ID/input
order cannot create favorable within-tie rankings. At each threshold, coverage is
cumulative answered/total references, and risk is cumulative wrong/cumulative
answered. Abstentions remain in the total denominator and never receive a made-up
confidence. The final point reaches answered/total coverage, not necessarily1.
With all predictions abstained, the curve is empty. No synthetic zero-coverage point
or area-under-curve score is invented.

Use separate development data to select thresholds before held-out evaluation;
these diagnostics alone do not select a policy or establish improvement. Exact
correctness does not judge visual grounding or free-form semantic correctness.
No model, optional runtime, network or paid resource is needed. Strict regular-file
input and trusted/stable ancestor/host limits apply. CLI invalid input returns2
without partial success JSON; inputs are never modified.
