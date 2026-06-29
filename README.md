# arc-eval-service

**LLM-as-a-judge** quality evaluation for the ARC control plane. The service
scores AI interactions with judge models you choose — Anthropic, OpenAI, a
company-allowed model, or a **self-hosted** endpoint — stores every interaction
it judged, and can **re-run** evaluations on stored data. It also accepts
interactions **offline via OpenTelemetry** (gateway → collector → here).

It is **not** an inference, guardrail, routing or provider-management service. It
owns evaluation only, and evaluation means LLM-as-a-judge — nothing else.

In the wired stack the gateway calls this service for **online scoring**, and
because each record echoes the judged interaction (its `case`), the evaluator is
the **system of record** that **arc-platform** reads to render the console. See
[arc-docs › services/arc-evaluator](../docs/arc-docs/docs/services/arc-evaluator.md)
and [Running the Stack](../docs/arc-docs/docs/onboarding/running-the-stack.md).

## Design

Judges and models are **orthogonal** — any judge runs on any model:

```text
src/arc_eval_service/
  api/            # FastAPI routes + schemas (shell)
  services/       # evaluation orchestration: evaluate / rerun
  judges/         # Judge strategy + registry (pure: build_prompt + parse)
    builtins/     #   faithfulness, answer_relevance, safety, custom
  models/         # JudgeModel port + adapters (anthropic, openai_compat) + profiles
  ingest/         # OTLP-in: span -> case mapping + offline scheduling
  storage/        # repository: in-memory + Postgres backends
  core/           # config, DI wiring, errors
migrations/       # Alembic versions
```

| Pattern | Where | Why |
| --- | --- | --- |
| **Strategy + Registry** | `judges/` | add a metric by registering a judge (prompt + parser) |
| **Ports & Adapters** | `models/`, `ingest/` | add a vendor / self-hosted endpoint; OTLP ingest is an inbound adapter |
| **Functional core / shell** | judge `build_prompt`/`parse` vs orchestrator | test judging without a model |
| **Repository** | `storage/` | swap in-memory ↔ Postgres behind one contract |
| **Constructor injection** | `core/deps.py` | fakes in tests; no globals |

### Judges (built-in)

| name | grades | requires |
| --- | --- | --- |
| `faithfulness` | answer is grounded in the context (no hallucination) | `output`, `context` |
| `answer_relevance` | answer addresses the question | `input`, `output` |
| `safety` | output is safe / policy-compliant | `output` |
| `custom` | a caller-supplied rubric (`config.prompt`) | `output` |

Each judge instructs the model to return strict JSON
`{"score": 0..1, "label": "...", "explanation": "..."}`; the parser tolerates
fenced/loose JSON. A model/parse/validation failure **degrades that judge** into
an errored result — it never fails the whole request. Add a judge by
implementing `judges/base.py:LLMJudge` and registering it in
`judges/registry.py:default_registry`.

### Models & BYOK (profiles)

A **profile** is a named, server-side model config; the API key is referenced by
**env-var name** and resolved at call time — never stored in the profile, a
request body, a span or a log. Self-hosted models plug in as an
`openai_compatible` profile with a `base_url` (vLLM, Ollama, LM Studio, TGI, ...).

```bash
export ANTHROPIC_API_KEY=sk-...
export ARC_EVAL_MODEL_PROFILES='[
  {"name":"claude","provider":"anthropic","model":"claude-opus-4-8","api_key_env":"ANTHROPIC_API_KEY"},
  {"name":"local","provider":"openai_compatible","model":"llama3","base_url":"http://localhost:9099/v1"}
]'
export ARC_EVAL_DEFAULT_MODEL=claude
```

A request picks a profile by name (and may override the model id):

```jsonc
{ "judge": "faithfulness", "model": "claude", "model_override": "claude-sonnet-4-6" }
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET  | `/health` | liveness |
| POST | `/v1/evaluate` | judge one interaction (sync or async) |
| POST | `/v1/evaluate/batch` | judge a batch synchronously |
| GET  | `/v1/evaluations` | list recent records |
| GET  | `/v1/evaluations/{id}` | get a stored record |
| POST | `/v1/evaluations/{id}/rerun` | re-judge a stored case (optionally new judges/models) |
| GET  | `/v1/judges` | list judges + what each requires |
| GET  | `/v1/models` | list configured model profiles (no secrets) |
| POST | `/v1/otlp/traces` | offline ingest: OTLP/HTTP JSON from the collector |

### Example

```bash
curl -s localhost:8000/v1/evaluate -H 'content-type: application/json' -d '{
  "case": {
    "request_id": "req-1",
    "input": "What is the capital of France?",
    "output": "Paris.",
    "context": ["France'\''s capital is Paris."]
  },
  "judges": [{"judge": "faithfulness", "model": "claude"}, {"judge": "safety"}],
  "mode": "sync"
}'
```

## Offline evaluation via OpenTelemetry

The gateway emits content-bearing `arc.llm.call` spans (under
`ARC_OTEL_CAPTURE_CONTENT=true`); the collector fans traces out to
`POST /v1/otlp/traces`; the evaluator maps each span to a case and judges it with
`ARC_EVAL_DEFAULT_JUDGE` on `ARC_EVAL_DEFAULT_MODEL`. The span→case mapping is a
pure function (`ingest/otlp.py`). PII note: capturing prompt+completion is
**opt-in**.

## Re-running on stored data

Records persist the `case` and the judge `specs`, so a re-run re-judges the same
interaction — with the same or different judges/models — and stores a **new**
record linked via `rerun_of`:

```bash
curl -s -X POST localhost:8000/v1/evaluations/$ID/rerun -H 'content-type: application/json' \
  -d '{"judges":[{"judge":"safety","model":"local"}]}'
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ARC_EVAL_MODEL_PROFILES` | `[]` | JSON list of `{name,provider,model,base_url?,api_key_env?}` |
| `ARC_EVAL_DEFAULT_MODEL` | — | default profile name when a request omits `model` |
| `ARC_EVAL_DEFAULT_JUDGE` | `safety` | judge used for offline ingestion |
| `ARC_EVAL_INGEST_ENABLED` | `true` | enable `POST /v1/otlp/traces` |
| `ARC_EVAL_DATABASE_URL` | — | Postgres URL (`postgresql+psycopg://...`); in-memory when unset |
| `ARC_OTEL_*` | — | shared telemetry (endpoint, capture, etc.) via arc-telemetry |

## Persistence

In-memory by default (nothing to run). Set `ARC_EVAL_DATABASE_URL` for Postgres
(async SQLAlchemy + psycopg3); schema is managed by Alembic (`make migrate`).

## Running & quality gate

```bash
make run                 # uvicorn on :8000 (in-memory store, no profiles needed)
make check               # uv lock --check + ruff + mypy strict + tests (≥80% cov)
```

Tests need no network: judges run on a **stub model**, adapters are tested with
`respx`, the OTLP mapper from a canned payload. Postgres-backed tests use
`testcontainers` and skip when Docker is unavailable.
