# ADR-0011: Pluggable models for guardrails and evaluation (arc + BYO)

- **Status:** Accepted
- **Date:** 2026-06-28
- **Deciders:** Platform engineering

## Context

Guardrails are now **LLM-as-a-guardrail** + **cosine-similarity** and evaluation
is **LLM-as-a-judge**, so both depend on models: a guardrail classifier LLM, an
embedding model, and a judge LLM. Tenants differ in cost, latency, residency and
availability needs, so no single hosted model fits everyone. We must default to a
sensible model yet let tenants bring their own.

## Decision

Every model use sits behind a small **port**: `GuardrailModel`, `EmbeddingModel`,
`JudgeModel`. Each resolves a binding per tenant — the **arc provider** default,
or a **BYO** model whose credentials come from the BYOK secret manager
([ADR-0010](0010-byok-provider-credentials.md)). Bindings are config; the call is
the only I/O. Adding a vendor is a new adapter, not a core change (open/closed).

## Consequences

- **Easier:** swap or self-host guardrail/embedding/judge models without code
  changes; arc-provided defaults give zero-config; one resolution path for all
  models (DRY).
- **Harder:** guardrails and online eval now make model calls on the hot path —
  bounded by tight timeouts, caching, and best-effort degrade.
- **Revisit when:** routing/failover across models is needed — that is `arc-router`
  (Phase 3), not this ADR.

## Alternatives considered

- **Single hosted model for all tenants** — simplest, but ignores cost/latency/
  residency and availability. Rejected.
- **Heuristic guardrails/evaluators** — cheap and fast, but the explicit goal is
  model-quality safety and judging. Rejected.
