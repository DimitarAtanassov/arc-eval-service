# arc-eval-service

Audience: backend engineers integrating or operating the service. Reading time: 6 minutes.

arc-eval-service scores completed AI interactions and returns one quality score per
metric. A caller sends a finished interaction (the input, the model's output, and
the metrics to score) and the service judges it with an LLM-as-a-judge. It owns the
metrics, their rubrics, the judges, and the judge-model calls. Callers own what they
do with the scores.

It is a **standalone evaluator**: it runs no inference and calls no other service.
It scores text it is given. Evaluation is best effort and synchronous on the
request. There is no async pipeline; observability is the database tables, queried
with SQL.

## Where it sits

The evaluator does not talk to arc-model-lab. arc-model-lab hosts models and
produces outputs; arc-platform is the orchestrator that connects the two. It runs
inference on the lab, collects the output, and sends the finished interaction here
to score.

```mermaid
flowchart LR
    User --> APP["arc-platform<br/>(orchestrator)"]
    APP -->|"run a model"| ML["arc-model-lab<br/>(model host)"]
    ML -->|"output"| APP
    APP -->|"score {input, output, metrics}"| EV["arc-eval-service<br/>(evaluator)"]
    EV -->|"scores"| APP
    EV --> DB[("Postgres")]
```

## Two surfaces

- **Evaluate** (`POST /v1/evaluate`): score one interaction now. Stateless from the
  caller's view: send input, output, and metrics; get one score per metric back.
- **Experiments** (`/v1/experiments`): score a **dataset** of interactions against a
  fixed metric set, and aggregate the results. An experiment owns its metrics and a
  dataset of completed interactions; a run scores every entry and rolls the scores up
  per metric.

Both reuse the same scoring core. An experiment run is the evaluate path applied
once per dataset entry, bounded so a large dataset cannot overwhelm the judge.

### Evaluate

```jsonc
// POST /v1/evaluate  (request)
{
  "input_text": "Paris is the capital of France and its largest city.",
  "output_text": "Paris is France's capital.",
  "metrics": ["faithfulness", "answer_relevance"]
}

// 200 OK
{
  "contract_version": "1.0.0",
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

- The request body is exactly `input_text`, `output_text`, and a non-empty `metrics`
  list. Any other field (or an empty `metrics`) is rejected with `422`
  (`extra="forbid"`). An unknown metric name is `404`, before anything is scored.
- Scoring is best effort per metric. A metric that fails (for example, no judge model
  configured) is persisted with its error but omitted from the response, so a caller
  never stores an infrastructure failure as a real zero. With no model profile
  configured, the response is `{"results": []}` and the errored rows are still saved.

### Experiments

An experiment is created with its metric set and, optionally, a seed dataset; more
entries are appended later. Running it scores the whole dataset and returns
per-metric aggregates. The full contract, request and response bodies included, is in
[docs/arc-evaluator.md](docs/arc-evaluator.md).

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/experiments` | Create an experiment (metrics, optional inline dataset). |
| `GET /v1/experiments` | List experiments, newest first. |
| `GET /v1/experiments/{id}` | Get one experiment (with its dataset size). |
| `POST /v1/experiments/{id}/dataset` | Append dataset entries. |
| `GET /v1/experiments/{id}/dataset` | List the dataset entries. |
| `POST /v1/experiments/{id}/run` | Score the metrics over the dataset. |
| `GET /v1/experiments/{id}/results` | Latest-run metric aggregates. |
| `GET /v1/experiments/{id}/compare/{other}` | Compare two experiments' aggregates. |

### Browse and health

`GET /v1/metrics` lists the metric catalog. `GET /v1/requests[/{id}]` and
`GET /v1/results` browse the persisted interactions and scores (filter results by
`metric`). `GET /health` is a liveness check.

## Data model

Five tables, owned by this service. Evaluate writes the first two; experiments add
the last three.

```mermaid
erDiagram
    eval_requests ||--o{ evaluation_results : "scored into"
    experiments ||--o{ experiment_dataset_entries : "has"
    experiments ||--o{ experiment_runs : "has"
    experiment_runs ||--o{ experiment_run_items : "has"
    experiment_run_items }o--|| experiment_dataset_entries : "scores"
    experiment_run_items }o--|| eval_requests : "produces"
```

- `eval_requests` / `evaluation_results`: one interaction and one metric score per
  row, written on every scored interaction (whether standalone evaluate or an
  experiment run entry).
- `experiments`: a name, a metric set, and a description.
- `experiment_dataset_entries`: one completed interaction (`input_text`,
  `output_text`, optional `system_text`) per row.
- `experiment_runs` / `experiment_run_items`: one run of the metrics over the
  dataset, and one row per dataset entry it scored linking to that entry's
  `eval_requests` row. Aggregation joins run items back to `evaluation_results`.

One metric per row (not a JSON blob) keeps the query paths (by metric, over time)
indexable in plain SQL. Column-level detail and the design rationale are in
[docs/db-design.md](docs/db-design.md).

## Project layout

```text
src/arc_eval_service/
  app.py            # builds the FastAPI app, mounts the routers
  api/              # HTTP boundary (the only FastAPI-aware layer)
    routes/         # evaluate.py, experiments.py, reads.py, health.py
    schemas.py      # evaluate wire DTOs
    experiment_schemas.py  # experiment + dataset wire DTOs
    dependencies.py # dependency injection (composition root)
    errors.py       # domain error -> HTTP mapping
  domain/           # framework-free core
    evaluation.py   # EvaluationCase, MetricScore
    experiment.py   # metric aggregates
    errors.py       # domain errors
  services/         # application layer
    evaluation_service.py  # score -> persist -> respond (the scoring core)
    experiment_service.py  # create, dataset, run (over the scoring core)
    interaction.py  # the Interaction value object the scoring core takes
    mapping.py      # pure wire <-> domain <-> record mappers
  judging/          # judge engine, the JudgeModel port, registry, provider adapters
  catalog/          # the evaluator catalog (metric/ and judge/, one YAML each)
  db/
    engine.py       # async engine and session factory (Postgres only)
    models.py       # the five tables
    records.py      # persistence DTOs (repository write-model)
    repositories/   # one module per table, with pure record <-> row mappers
  core/
    config.py       # settings, read from ARC_EVAL_* environment variables
    logging.py      # JSON structured logging
migrations/         # Alembic migrations
```

## Configuration

Configuration lives in one place: a `.env` file at the repo root. Copy the template
and edit it.

```bash
cp .env.example .env
```

`.env` is loaded automatically by `docker compose up` and by the runtime Make
targets (`make run`, `make migrate`, ...). It is git-ignored, so secrets stay local.
Every service setting is an `ARC_EVAL_*` variable; a value set directly in the
process environment takes precedence over the file.

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

A judge-model profile names a provider, a model id, and the env var holding the key.
One OpenAI-compatible adapter covers OpenAI, Azure OpenAI, and self-hosted servers
(vLLM, Ollama, and similar) by changing `base_url`:

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
against it. `make run` loads `.env`, whose default `ARC_EVAL_DATABASE_URL` points at
the compose Postgres on localhost.

```bash
docker compose up db
make run                 # loads .env; ARC_EVAL_API_PORT sets the port (default 8000)
```

Score an interaction:

```bash
curl -s localhost:8000/v1/evaluate \
  -H 'content-type: application/json' \
  -d '{"input_text":"Paris is the capital of France.","output_text":"Paris is the capital.","metrics":["faithfulness","answer_relevance"]}'
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
| `make run` | run the app locally with auto-reload (port from ARC_EVAL_API_PORT, default 8000) |
| `make lint` | check the lockfile, run Ruff format and check, run mypy strict |
| `make test` | run the full test suite with coverage |
| `make check` | run lint and the full test suite (the CI gate) |
| `make migrate` | apply database migrations to head |
| `make migration NAME=...` | autogenerate a migration from the models |
| `make docker` | build the container image |
