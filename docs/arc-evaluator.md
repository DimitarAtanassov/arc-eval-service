# Service — arc-evaluator

**Role:** measure response quality, and own the span/trace store. **Online**
(inline, best-effort) on the hot path, and **offline** on spans the OTel
Collector fans out to it. Both modes share the same evaluators and write results
to the **evaluation database**. The same OTLP ingest persists every span it
receives, so the evaluator serves the real span tree to `arc-platform`
([ADR-0006](../adr/0006-postgres-span-store.md)). The online/offline split is
[ADR-0008](../adr/0008-online-offline-evaluation.md).

For Phase 1: **LLM-as-a-judge only** — no heuristic or deterministic metrics. A
fast judge runs online; heavier judges run offline. Judge models come from the
**arc provider** by default; tenants may bring their own judge models (BYO) to
fit cost, latency and availability.

---

## API

```
POST /v1/evaluate            # score a completed interaction, inline
POST /v1/otlp/traces         # OTLP/HTTP ingest from the collector (gzip-aware)
GET  /v1/traces/{trace_id}   # the real span tree for one trace
GET  /health
```

```jsonc
// request
{ "request": {...}, "response": {...}, "tenant": "acme", "judges": ["faithfulness"] }

// response
{ "scores": { "faithfulness": 0.87 }, "labels": { "faithfulness": "pass" }, "passed": true }
```

---

## Internal design — judge registry + model port

```mermaid
flowchart TD
    REG["Judge registry"] --> F["FaithfulnessJudge"]
    REG --> R["RelevanceJudge"]
    REG --> S["SafetyJudge"]
    REG --> RUN["render prompt → call judge model → parse score"]
    RUN --> PORT["JudgeModel (port)"]
    PORT --> ARC["arc provider (default)"]
    PORT --> BYO["tenant BYO judge model"]
```

- Each **judge is a pure prompt + parser**: `(request, response) -> Score`; the
  model call is the only I/O, behind a port.
- The **registry** maps a name to a judge; the active set is config-driven.
  Adding a metric = write a prompt + parser, register it.
- **Models are pluggable** via the `JudgeModel` port: arc provider by default,
  tenant BYO model otherwise — see [ADR-0011](../adr/0011-pluggable-models.md).

```
arc_evaluator/
  judges/         # prompt + parser per metric (pure)
  registry.py     # name → judge
  models/         # JudgeModel port + arc/BYO adapters
  api/            # FastAPI routes (shell)
  config.py       # active judges, thresholds, model bindings
  main.py
```

Scores are emitted as `arc.eval.*` span attributes and persisted to the
**evaluation database** for query by `arc-platform`.

---

## Span store + OTLP ingest

The evaluator also owns the **span/trace store** ([ADR-0006](../adr/0006-postgres-span-store.md)).
The Collector fans every span to `POST /v1/otlp/traces` as OTLP/HTTP JSON; the
evaluator normalises and upserts each span (idempotent on `span_id`) and serves
the real span tree at `GET /v1/traces/{trace_id}` so `arc-platform` renders the
actual `arc.llm.*` (inference) and `arc.eval.*` (evaluation) attributes instead
of a waterfall reconstructed from latencies.

```mermaid
flowchart LR
    COL["OTel Collector"] -->|gzip OTLP/JSON| ING["POST /v1/otlp/traces"]
    ING --> STORE[("span store")]
    ING -->|inbound inference spans only| JUDGE["offline judging"]
    PLAT["arc-platform"] -->|GET /v1/traces/id| STORE
```

Two rules keep ingest spec-conformant and loop-free:

- **gzip-aware receiver.** OTLP/HTTP exporters compress request bodies by
  default; an ASGI middleware decompresses them so ingest does not `400` on a
  gzipped batch.
- **No feedback loop.** The evaluator stores every span but offline-judges only
  spans from *other* services (it skips spans whose resource `service.name` is
  the evaluator), and its `/v1/otlp/traces` path is excluded from
  self-instrumentation. Otherwise judging its own judge calls (which are
  `arc.llm.call` spans) would feed the Collector and re-ingest without end.

---

## Constraints

Online evaluation is on the hot path, so it is **strictly bounded**:

- a single fast judge model call, capped by a tight timeout
- **best-effort**: any error or timeout degrades gracefully — a request is never
  failed because scoring failed
- heavy/multi-judge evaluation runs offline on collector-fed traces

---

## Testing

- **Unit:** each judge's prompt builder + parser tested against a fake model.
- **Aggregation:** pass/fail-against-threshold logic.
- **Budget:** a guard test asserting the online judge stays within its timeout.

## What it does **not** own
Benchmark dataset curation, orchestration, the gateway response. It reports and
stores scores; it does not decide the response.
