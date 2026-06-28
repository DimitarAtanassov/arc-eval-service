# ADR-0004: Inline guardrails, best-effort evaluation

- **Status:** Accepted
- **Date:** 2026-06-28
- **Deciders:** Platform engineering

## Context

The draft placed evaluation inline in the request lifecycle, before returning the
response. Guardrails and evaluation have very different roles: guardrails are a
**gate** (they decide whether a request/response is allowed), while evaluation is
a **measurement** (it scores quality after the fact). Putting a measurement on the
critical path adds latency and a failure mode for no functional benefit.

## Decision

- **Request and response guardrails are inline and blocking.** An unsafe prompt
  must not reach a provider; an unsafe completion must not reach the client.
- **Evaluation is best-effort and off the critical path.** For MVP the gateway
  calls the evaluator after the client response has been sent; the call has a
  short timeout and never affects the response. Evaluation results are persisted
  via the telemetry pipeline.

## Consequences

- **Easier:** low, predictable p99 latency; evaluator outages cannot break
  inference; evaluators can be slow/expensive without client impact.
- **Harder:** evaluation results are eventually consistent (they appear a moment
  after the trace).
- **Revisit when:** online eval volume or cost justifies a fully async consumer.
  Phase 2 moves evaluation to a consumer that reads completed traces and runs
  evaluators out of band, backed by a durable, at-least-once job queue with
  idempotent upserts keyed by `(trace_id, evaluator)`.

## Alternatives considered

- **Inline blocking evaluation** (the draft) — adds latency and a failure mode on
  the hot path; couples response delivery to a measurement.
- **Fully async from day one** — needs a durable queue and a consumer before any
  consumer of the data exists (YAGNI for MVP).
