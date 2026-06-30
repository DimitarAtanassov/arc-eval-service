# syntax=docker/dockerfile:1
# Container image for arc-eval-service. Build from the repo root:
#   docker build -t arc-eval-service:latest .

# --- Builder: resolve dependencies into a self-contained venv.
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /srv

# Dependency metadata + source (hatchling packages live under src/).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Reproducible install from the lockfile; runtime deps only (no dev/lint/test).
RUN uv sync --frozen --no-default-groups

# --- Runtime: slim image with just the prebuilt venv + source. No git, no uv.
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/.venv/bin:$PATH"

# NOTE: deliberately not /app (reserved name avoided per platform conventions).
WORKDIR /srv

COPY --from=builder /srv /srv

# Migration assets: the compose stack runs `alembic upgrade head` before serving
# so the schema is always current. Run standalone, the service expects an
# already-migrated database (see docker-compose.yaml).
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000

CMD ["uvicorn", "arc_eval_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
