# syntax=docker/dockerfile:1
# Container image for arc-eval-service. Build from the repo root:
#   docker build -t arc-eval-service:latest .

FROM python:3.13-slim AS runtime

# uv: fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

# NOTE: deliberately not /app (reserved name avoided per platform conventions).
WORKDIR /srv

# Dependency metadata + source (hatchling packages live under src/).
COPY pyproject.toml README.md ./
COPY src ./src

RUN uv venv && uv pip install -e .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "arc_eval_service.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
