# Initial research protocol

Related work reviewed at abstract level, not exhaustively reproduced:

- ReAct, arXiv:2210.03629v3, https://arxiv.org/abs/2210.03629:
  interleaves model reasoning and external actions; relevant tool-use baseline.
- Reflexion, arXiv:2303.11366v4, https://arxiv.org/abs/2303.11366:
  uses verbal feedback and episodic memory; relevant recovery baseline.
- MMMU, arXiv:2311.16502v4, https://arxiv.org/abs/2311.16502:
  multimodal subject-knowledge/reasoning evaluation; candidate benchmark, not
  downloaded or used here. Dataset licensing and task scoring need separate review.

These are established approaches. OpenForge makes no novelty claim. We have not
reproduced their reported results. The local evaluator is not an MMMU scorer.

Question: does evidence-conditioned verification improve reliability at comparable
compute cost for image-grounded tasks? Hypothesis (unverified): it reduces wrong
accepted answers at matched coverage relative to direct prediction and verbal
self-reflection alone. A verifier can share model errors; this is a central risk.

Proposed design: select one license-compatible open VLM fitting measured resources;
record exact model revision, license, preprocessing, image limits and runtime;
use a frozen, licensed held-out subset with documented selection and provenance.
Compare direct prediction, budget-matched additional generation, reflection and
evidence-conditioned verification on paired examples. Fix prompts before test;
tune thresholds on a separate development split. Use identical task/decoding
budgets; record retries, timeouts, failures, tokens, latency and memory.

Primary metrics: correctness on all tasks, coverage, accuracy conditional on
answering and risk-coverage curves. Secondary: Brier score and confidence intervals
from paired resampling with a recorded seed. Never silently discard failed runs.
Predefine sample size and stopping rule after a resource pilot, before held-out
comparison. Report negative results, correlated errors, contamination risks,
limited sample power and verifier bias. No such experiment has run yet.

Every experiment report must include question, hypothesis, baseline, design,
dataset provenance/license/version, model/configuration, metrics, actual results,
limitations and reproduction command. Preserve raw predictions, manifest and code
revision. Do not infer scientific findings from the three synthetic CLI fixtures.

Model selection criteria: license compatible with intended use; image support;
fully pinned artifacts; documented processor; CPU feasibility or separately
approved GPU budget; controlled generation; failure observability. No model has
been selected or downloaded. GPU training and paid inference are out of scope
until resources and approval exist.
