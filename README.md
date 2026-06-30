# arc-eval-service

The arc-eval-service stores AI interactions so they can be evaluated for quality
later. It is one service in the ARC control plane.

Right now the service is a storage foundation. It exposes one endpoint that
receives an LLM interaction and saves it. It does not run any evaluation. The
tables that hold metrics and evaluation results are in place, ready for the
evaluation logic that will be added later.

The service does not use OpenTelemetry. It is a plain FastAPI service over
Postgres.

## What it does

- Accepts one LLM interaction over a single endpoint and stores it.
- Stores the prompt template once per distinct template (it deduplicates).
- Stores the rendered prompt, the values that filled the template, the system
  message, the LLM response, and the LLM config.

## What it does not do

- It does not run evaluation. The ingest endpoint only stores data.
- It does not call any model. There is no network call on the request path.
- It does not roll results up into a single score.

## The single endpoint

```
POST /v1/eval-inputs
```

Send one LLM interaction. The service stores the template (deduplicated) and the
input, then returns the two ids.

```jsonc
// request
{
  "prompt_template": "Answer using the context.\nQ: {question}\nContext: {context}",
  "template_context": {
    "question": "What is the capital of France?",
    "context": "The capital of France is Paris."
  },
  "rendered_prompt": "Answer using the context.\nQ: What is the capital of France?\nContext: The capital of France is Paris.",
  "system_message": "You are a careful assistant.",
  "llm_response": { "role": "assistant", "content": "Paris." },
  "llm_config": { "model": "gpt-4o", "temperature": 0.0 }
}

// 201 Created
{
  "eval_input_id": "0f2b9a3e-...",
  "prompt_template_id": "7c1d4f88-..."
}
```

`prompt_template` and `rendered_prompt` are required. A request that omits them
is rejected with `422`. Sending the same `prompt_template` again returns the same
`prompt_template_id`; the template row is stored once.

The only other route is `GET /health`, a liveness check.

## Data model

```mermaid
erDiagram
    prompt_templates ||--o{ eval_inputs : "rendered into"
    prompt_templates ||--o{ metrics : "optional ref"
    eval_inputs ||--o{ evaluation_runs : "evaluated by"
    metrics ||--o{ evaluation_runs : "scored with"

    prompt_templates {
        uuid id PK
        text template
        text content_hash UK
        timestamptz created_at
    }
    eval_inputs {
        uuid id PK
        uuid prompt_template_id FK
        jsonb template_context
        text rendered_prompt
        text system_message
        jsonb llm_response
        jsonb llm_config
        timestamptz created_at
    }
    metrics {
        uuid id PK
        text name UK
        text prompt
        uuid prompt_template_id FK
        jsonb input_variables
        timestamptz created_at
    }
    evaluation_runs {
        uuid id PK
        uuid eval_input_id FK
        uuid metric_id FK
        jsonb judge_config
        float score
        bool passed
        text label
        text explanation
        text error
        timestamptz created_at
    }
```

- `prompt_templates`: the raw template with placeholders. A `content_hash` unique
  index keeps one row per distinct template, so a template that arrives on every
  request is stored once.
- `eval_inputs`: the interaction to evaluate. It links to its template, holds the
  context key and value pairs (placeholder to value), the rendered prompt, the
  system message, the LLM response, and the LLM config.
- `metrics`: a metric definition. A name, plus an optional inline `prompt` or an
  optional template reference with its `input_variables`.
- `evaluation_runs`: one metric run against one input. It links to the input and
  the metric, holds the judge config used, and the result columns. The ingest
  endpoint does not write this table.

The ingest endpoint writes `prompt_templates` and `eval_inputs` only. The
`metrics` and `evaluation_runs` tables are the foundation for the evaluation
logic that comes later.

## Project layout

```text
src/arc_eval_service/
  app.py            # builds the FastAPI app, the health route, error handlers
  core/
    config.py       # settings, read from ARC_EVAL_* environment variables
    deps.py         # dependency injection (builds the database and services)
    errors.py       # domain errors, mapped to HTTP status codes by app.py
    logging.py      # JSON structured logging
  ingestion/        # the single endpoint
    schemas.py      # request, response, and domain models
    service.py      # store the template (deduplicated), then the eval input
    router.py       # POST /v1/eval-inputs
  db/
    engine.py       # async engine and session factory (Postgres only)
    models.py       # the four tables
    repositories/   # prompt_templates and eval_inputs, with pure row mappers
  metrics/          # metric definitions library (kept for the evaluation logic)
  judging/          # judge model adapters and scoring engine (kept for later)
  evaluation/
    schemas.py      # shared domain types used by metrics/ and judging/
migrations/         # Alembic migrations
```

The `metrics/` and `judging/` packages are kept as libraries for the evaluation
logic that will run later. The ingest endpoint does not use them.

## Configuration

All settings are read from `ARC_EVAL_*` environment variables.

| Variable | Required | Meaning |
| --- | --- | --- |
| `ARC_EVAL_DATABASE_URL` | yes | Async Postgres URL, for example `postgresql+psycopg://user:pass@host:5432/db`. |
| `ARC_EVAL_APP_NAME` | no | Title shown in the API docs. Defaults to `arc-eval-service`. |
| `ARC_EVAL_SERVICE_NAME` | no | Service name in the health response. Defaults to `arc-eval-service`. |
| `ARC_EVAL_LOG_LEVEL` | no | Log level for the JSON logger. Defaults to `INFO`. |

## Persistence

The service uses Postgres only. The database URL is required. Storage uses async
SQLAlchemy 2.0 with psycopg3. The schema is managed by Alembic, applied with
`make migrate`. There are four tables: `prompt_templates`, `eval_inputs`,
`metrics`, and `evaluation_runs`.

## Running locally

Bring up Postgres and the service with Docker Compose. The service runs
`alembic upgrade head` before it serves, so the schema is always current.

```bash
docker compose up
```

To run the service from source with auto-reload, start just the database first,
then run the app. The app needs `ARC_EVAL_DATABASE_URL` to point at that
database.

```bash
docker compose up db
export ARC_EVAL_DATABASE_URL=postgresql+psycopg://arc:arc@localhost:5432/arc_eval
make run                 # uvicorn on port 8000
```

## Testing

Unit tests have no external dependencies. Database-backed tests use a Postgres
testcontainer and skip themselves when Docker is not available.

```bash
make test-unit           # fast tests, no external dependencies
make test-integration    # exercise the HTTP API against Postgres
make test-e2e            # the full store, then read-back flow
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
