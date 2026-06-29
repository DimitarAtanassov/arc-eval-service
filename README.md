# arc-eval-service

Online and offline **AI quality evaluation** for the ARC control plane. The
service computes quality signals and evaluation scores for AI interactions.

It is **not** an inference service, **not** a policy/guardrail service, and
**not** a routing or provider-management service. It owns evaluation only.

## Responsibilities

Owns:

- response quality evaluation
- online + offline evaluation
- regression scoring
- experiment comparisons
- evaluator execution orchestration

Does **not** own: inference, request routing, guardrails, provider management,
visualization.

## Architecture

```
src/arc_eval_service/
    api/            # FastAPI routes + request/response schemas (no logic)
    services/       # evaluation orchestration only
    evaluators/     # evaluator strategies + registry (Strategy + Registry)
    schemas/        # local Pydantic domain models
    core/           # config, DI wiring, errors, structured logging
    storage/        # persistence abstraction + in-memory and Postgres backends
    observability/  # OpenTelemetry tracing
migrations/         # Alembic migration environment + versions
```

Layering is strictly one-directional: `api -> services -> {evaluators, storage}`.
The api layer holds no business logic; evaluators hold no persistence or tracing.

### Evaluators (Strategy + Registry)

Every evaluator implements a single interface:

```python
class Evaluator(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    def evaluate(self, data: EvaluatorInput) -> EvaluationResult: ...
```

MVP evaluators (all pluggable via the registry — no plugin framework):

| name          | passes when                  | key config                          |
|---------------|------------------------------|-------------------------------------|
| `exact_match` | output equals reference      | `case_sensitive`, `strip`           |
| `regex`       | output matches a pattern     | `pattern`, `mode`, `case_sensitive` |
| `heuristic`   | response-quality checks pass | `min_length`, `forbid_refusal`, ... |
| `latency`     | `latency_ms` within budget   | `threshold_ms`                      |
| `token`       | total tokens within budget   | `max_total_tokens`                  |
| `cost`        | `cost_usd` within budget     | `max_cost_usd`                      |

The `latency`, `token` and `cost` evaluators share one shape — measure a metric,
compare it to a numeric budget, grade the overshoot — so they subclass
`BudgetEvaluator` (`evaluators/budget.py`) and supply only the metric and labels.

Adding a new evaluator: implement `Evaluator` (or `BudgetEvaluator` for a
budget-style check), then register it in
`evaluators/registry.py:default_registry`. Nothing else changes.

## API

| Method | Path                   | Purpose                                  |
|--------|------------------------|------------------------------------------|
| GET    | `/health`              | Liveness probe                           |
| POST   | `/v1/evaluate`         | Evaluate one interaction (sync or async) |
| POST   | `/v1/evaluate/batch`   | Evaluate a batch synchronously           |
| GET    | `/v1/evaluations`      | List recent evaluation records           |
| GET    | `/v1/evaluations/{id}` | Retrieve a stored evaluation record      |
| GET    | `/v1/evaluators`       | List registered evaluators               |

### Sync vs async execution

`POST /v1/evaluate` accepts a `mode` field:

- `"sync"` (default): the completed record is returned inline.
- `"async"`: a `pending` record is returned immediately; the evaluation runs in
  the background. Poll `GET /v1/evaluations/{id}` for the result.

### Example

```bash
curl -s localhost:8000/v1/evaluate -H 'content-type: application/json' -d '{
  "case": {
    "request_id": "req-1",
    "output": "the answer is 42",
    "reference": "the answer is 42",
    "latency_ms": 120,
    "cost_usd": 0.002
  },
  "evaluators": [
    {"name": "exact_match"},
    {"name": "regex", "config": {"pattern": "42"}},
    {"name": "latency", "config": {"threshold_ms": 500}},
    {"name": "cost", "config": {"max_cost_usd": 0.01}}
  ],
  "mode": "sync"
}'
```

## Observability

OpenTelemetry tracing is required and configured at startup (console exporter for
the MVP). Each request produces:

- a root span `arc.eval.evaluate` (attrs: `evaluation_id`, `request_id`, `evaluator_count`)
- one child span `arc.eval.evaluator` per evaluator (attrs: `evaluator_name`,
  `evaluation_id`, `request_id`, `latency_ms`, `score`)

Logs are structured single-line JSON.

## Persistence

The service writes through the `EvaluationStore` abstraction, which has two
backends selected by configuration:

- **In-memory** (default): used when `ARC_EVAL_DATABASE_URL` is unset. Ideal for
  local dev and tests; nothing to run.
- **Postgres**: used when `ARC_EVAL_DATABASE_URL` is set (async SQLAlchemy +
  psycopg3). Use the `postgresql+psycopg://` driver:

  ```bash
  export ARC_EVAL_DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/arc_eval"
  make migrate        # alembic upgrade head
  make run
  ```

Schema is managed by Alembic (`migrations/`). The initial migration creates the
`evaluations` table (results stored as JSONB). Common commands:

```bash
make migrate                       # apply migrations to head
make migration NAME="add column"   # autogenerate a new revision
make downgrade                     # roll back the last revision
```

## Running locally (uv)

```bash
# install all dependency groups into the venv
uv sync --all-groups

# run the API with auto-reload (http://localhost:8000, docs at /docs)
uv run uvicorn arc_eval_service.api.main:app --reload

# or via the Makefile
make run
```

## Make targets

```bash
make prepare           # uv sync --all-groups
make lintable          # ruff format + ruff check --fix
make lint              # ruff format --check, ruff check, mypy
make test              # full suite + coverage report (fail_under = 80)
make test-unit         # unit tests only
make test-integration  # integration tests only
make test-e2e          # e2e tests only
make check             # lint + test (CI gate)
make migrate           # apply Alembic migrations (needs ARC_EVAL_DATABASE_URL)
make openapi           # export openapi.json
make clean             # remove caches and build artifacts
```

CI runs `make lint` and `make test` on every push/PR
([.github/workflows/ci.yml](.github/workflows/ci.yml)). Postgres-backed
integration tests use `testcontainers[postgres]` and are skipped automatically
when Docker is unavailable.

## Docker

```bash
docker build -t arc-eval-service:latest .
docker run --rm -p 8000:8000 arc-eval-service:latest
```

## Tooling

- Python 3.13, `src/` layout, uv workspace compatible.
- Ruff (`F,E,W,C90,I,N,UP,YTT,ANN,ASYNC,S,BLE,B,A,C4,PT,PL,PERF,RUF`),
  max complexity 12, max args 8.
- mypy `strict = true`.
- pytest + pytest-asyncio; minimum coverage 80%.
