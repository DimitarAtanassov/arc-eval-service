# arc-eval-service

Audience: backend engineers integrating or operating the service. Reading time: 5 minutes.

arc-eval-service scores a completed AI interaction and returns one quality score
per metric. It is the evaluation boundary in the ARC control plane: `arc-model-lab`
calls it after inference, receives the scores, and stores them against its
inference records.

The service owns scoring: the metrics, their rubrics, and the judge-model calls.
Callers own what they do with the scores. Evaluation is LLM-as-a-judge, best
effort, and synchronous on the request. There is no OpenTelemetry and no async or
offline pipeline; observability is the two database tables, queried with SQL.

## The single endpoint

```
POST /v1/evaluate
```

Send one completed interaction. The service picks the metrics for the `task_type`,
scores each one with a judge model, persists the request and every result, and
returns the metrics that scored.

```jsonc
// request
{
  "task_type": "summarization",
  "input_text": "Paris is the capital of France and its largest city.",
  "output_text": "Paris is France's capital.",
  "prompt": "Summarize the text.",
  "metadata": { "inference_id": "inf-1", "model_id": "qwen-1.5b" }
}

// 200 OK
{
  "results": [
    {
      "metric_name": "faithfulness",
      "score": 0.91,
      "reasoning": "The summary is grounded in the source text.",
      "evaluator_name": "faithfulness",
      "evaluator_version": "v1"
    }
  ]
}
```

`task_type`, `input_text`, and `output_text` are required. A request that omits one
is rejected with `422`. The only other route is `GET /health`, a liveness check.

### How scoring works

- `task_type` selects the metrics. `summarization` runs `faithfulness` and
  `answer_relevance`. An unknown task type falls back to a default set. The
  mapping lives in [policy.py](src/arc_eval_service/services/policy.py). A request
  may instead name explicit `metrics` to score; an unknown metric name is rejected
  with `404` before anything is scored or persisted.
- Metric and judge prompts live in per-file YAML under
  [catalog/metric/](src/arc_eval_service/catalog/metric) and
  [catalog/judge/](src/arc_eval_service/catalog/judge), loaded and validated at
  startup. A metric is a rubric; a judge is an optional system prompt plus a
  model. The engine composes `[judge.system_prompt?] + metric.rubric` and requests
  a structured verdict from the model.
- Scoring is best effort per metric. A metric that fails (for example, no judge
  model is configured) is persisted with its error but omitted from the response,
  so a caller never stores an infrastructure failure as a real score of zero.
- With no model profile configured, `/v1/evaluate` returns `{"results": []}` and
  records the errored metrics. Configure a profile to get scores (see
  Configuration).

## Data model

```mermaid
erDiagram
    eval_requests ||--o{ evaluation_results : "scored into"

    eval_requests {
        uuid id PK
        text task_type
        text input_text
        text output_text
        text prompt
        text inference_id
        text model_id
        jsonb request_metadata
        timestamptz created_at
    }
    evaluation_results {
        uuid id PK
        uuid eval_request_id FK
        text inference_id
        text model_id
        text metric_name
        float score
        bool passed
        text reasoning
        text evaluator_name
        text evaluator_version
        jsonb judge
        jsonb prompt
        float latency_ms
        text error
        timestamptz created_at
    }
```

- `eval_requests`: one interaction submitted for evaluation, plus the caller's
  correlation ids lifted out of `metadata`.
- `evaluation_results`: one metric score per row. `inference_id` and `model_id`
  are denormalized from the request so score-by-metric and score-by-model queries
  need no join. Each row also carries `judge` (model, settings, system prompt) and
  `prompt` (metric template and input variables) as JSONB provenance.

Both tables are written on every call. One metric per row (not a JSON blob) keeps
the query paths (by metric, by model, over time) indexable in plain SQL. The
`judge` and `prompt` provenance is denormalized JSONB on purpose; see
[docs/db-design.md](docs/db-design.md).

## Project layout

```text
src/arc_eval_service/
  app.py            # builds the FastAPI app, mounts the routers
  api/              # HTTP boundary (the only FastAPI-aware layer)
    routes/         # evaluate.py, health.py
    schemas.py      # request and response wire DTOs (the arc-model-lab contract)
    dependencies.py # dependency injection (composition root)
  domain/           # framework-free core
    evaluation.py   # EvaluationCase, MetricScore
    errors.py       # domain errors, captured per-metric by the judge engine
  services/         # application layer
    evaluation_service.py  # score -> persist -> respond
    policy.py       # task_type -> metrics mapping
    mapping.py      # pure wire <-> domain <-> record mappers
  judging/          # judge engine, the JudgeModel port, registry, provider adapters
  catalog/          # the evaluator catalog
    metric/         # MetricDefinition, render, + one YAML per metric
    judge/          # JudgeDefinition + one YAML per judge
  db/
    engine.py       # async engine and session factory (Postgres only)
    models.py       # eval_requests, evaluation_results
    records.py      # persistence DTOs (repository write-model)
    repositories/   # one per table, with pure record <-> row mappers
  core/
    config.py       # settings, read from ARC_EVAL_* environment variables
    logging.py      # JSON structured logging
migrations/         # Alembic migrations
```

## Configuration

Configuration lives in one place: a `.env` file at the repo root. Copy the
template and edit it.

```bash
cp .env.example .env
```

`.env` is loaded automatically by `docker compose up` and by the runtime Make
targets (`make run`, `make migrate`, ...). It is git-ignored, so secrets stay
local. Every service setting is an `ARC_EVAL_*` variable; a value set directly in
the process environment takes precedence over the file.

| Variable | Required | Meaning |
| --- | --- | --- |
| `ARC_EVAL_DATABASE_URL` | yes | Async Postgres URL, for example `postgresql+psycopg://user:pass@host:5432/db`. |
| `ARC_EVAL_MODEL_PROFILES` | no | JSON list of judge-model profiles. The API key is referenced by env-var name (`api_key_env`), never inlined. |
| `ARC_EVAL_DEFAULT_MODEL` | no | Model profile used when a judge does not name one. |
| `ARC_EVAL_DEFAULT_JUDGE` | no | Judge used when a request does not name one. Defaults to `default`. |
| `ARC_EVAL_PROMPTS_PATH` | no | Path to a catalog directory (with `metric/` and `judge/`) overriding the bundled catalog. |
| `ARC_EVAL_APP_NAME` | no | Title shown in the API docs. Defaults to `arc-eval-service`. |
| `ARC_EVAL_SERVICE_NAME` | no | Service name in the health response. Defaults to `arc-eval-service`. |
| `ARC_EVAL_LOG_LEVEL` | no | Log level for the JSON logger. Defaults to `INFO`. |
| `OPENAI_API_KEY` | no | Example provider key. Any name works as long as a profile's `api_key_env` points at it; the value is read from the environment at call time. |

A judge-model profile names a provider, a model id, and the env var holding the
key. One OpenAI-compatible adapter covers OpenAI, Azure OpenAI, and self-hosted
servers (vLLM, Ollama, and similar) by changing `base_url`. The relevant lines in
`.env`:

```bash
ARC_EVAL_MODEL_PROFILES='[{"name":"default","provider":"openai_compatible","model":"gpt-4o-mini","api_key_env":"OPENAI_API_KEY"}]'
ARC_EVAL_DEFAULT_MODEL=default
OPENAI_API_KEY=sk-...
```

## Running locally

Copy the environment template once, then bring up Postgres and the service with
Docker Compose. The service runs `alembic upgrade head` before it serves, so the
schema is always current.

```bash
cp .env.example .env     # first time only
docker compose up
```

To run from source with auto-reload, start just the database, then run the app
against it. `make run` loads `.env`, whose default `ARC_EVAL_DATABASE_URL` points
at the compose Postgres on localhost.

```bash
docker compose up db
make run                 # loads .env, uvicorn on port 8001
```

Score an interaction:

```bash
curl -s localhost:8000/v1/evaluate \
  -H 'content-type: application/json' \
  -d '{"task_type":"summarization","input_text":"Paris is the capital of France.","output_text":"Paris is the capital.","metadata":{"inference_id":"inf-1"}}'
```

## Testing

Unit and contract tests have no external dependencies. Database-backed tests use a
Postgres testcontainer and skip themselves when Docker is not available.

```bash
make test-unit           # service logic, no model or database
make test-contract       # the /v1/evaluate request and response wire shapes
make test-integration    # the HTTP API against Postgres
make test-e2e            # score, persist, read the rows back
```

## Make targets

| Target | What it does |
| --- | --- |
| `make run` | run the app locally with auto-reload on port 8000 |
| `make lint` | check the lockfile, run Ruff format and check, run mypy strict |
| `make test` | run the full test suite with coverage |
| `make check` | run lint and the full test suite (the CI gate) |
| `make migrate` | apply database migrations to head |
| `make migration NAME=...` | autogenerate a migration from the models |
| `make docker` | build the container image |
