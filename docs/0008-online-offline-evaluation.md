# ADR-0008 — Split online and offline evaluation

**Status:** Accepted

## Context
"Evaluation" means two different things with opposite constraints. Inline
scoring on the request path must be fast and deterministic. Deep quality
analysis (judge models, regression suites) is slow and must never sit on the hot
path. Conflating them produces either slow requests or shallow evaluation.

## Decision
Two distinct modes:

- **Online evaluation** — runs inside the request, in the evaluator service. A
  single **fast LLM judge** call, capped by a tight timeout. It is **best-effort**:
  if it errors or times out, the request still returns (degrade). Scores are
  emitted as `arc.eval.*` span attributes.
- **Offline evaluation** — runs **asynchronously on traces the Collector fans
  out to the evaluator**, with results stored in the evaluation DB. This is where
  heavier evaluators and (later) judge models live.

## Consequences
- The hot path stays fast and predictable; evaluation never fails a request.
- Heavy evaluation has a clean home (the span store) without touching the
  gateway.
- The cost: two code paths for "evaluation". We keep them honest by sharing the
  pure evaluator functions (functional core) between online and offline shells.
- **Trigger for offline:** the first time we need a judge model or a regression
  comparison across runs.
