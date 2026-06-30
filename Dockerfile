# syntax=docker/dockerfile:1
# Container image for arc-eval-service. Build from the repo root:
#   docker build -t arc-eval-service:latest .

# --- Builder: resolve dependencies (incl. the arc-telemetry Git source) into a
# self-contained venv. git is needed because arc-telemetry is a Git dependency.
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependency metadata + source (hatchling packages live under src/).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Reproducible install from the lockfile; runtime deps only (no dev/lint/test).
RUN uv sync --frozen --no-default-groups

# --- Runtime: slim image with just the prebuilt venv + source. No git, no uv.
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/.venv/bin:$PATH"

# NOTE: deliberately not /app (reserved name avoided per platform conventions).
WORKDIR /srv

COPY --from=builder /srv /srv

# Migration assets + entrypoint: the container runs `alembic upgrade head` on
# boot (when a database is configured) so the schema is always current.
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "arc_eval_service.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
