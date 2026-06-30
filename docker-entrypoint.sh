#!/usr/bin/env sh
# Container entrypoint for arc-eval-service.
#
# Runs database migrations to head before starting the server, but ONLY when a
# database is configured. With no ARC_EVAL_DATABASE_URL the service uses its
# in-memory store (local `docker run`, tests) and migrations are skipped.
#
# `alembic upgrade head` is idempotent and additive: it applies only revisions
# the database has not yet seen and never drops existing data, so it is safe to
# run on every boot — including against a pre-existing, populated volume.
set -eu

if [ -n "${ARC_EVAL_DATABASE_URL:-}" ]; then
  # Compose gates startup on the DB healthcheck, but retry anyway so a slow or
  # restarting database doesn't crash-loop the service.
  attempts=0
  max_attempts=10
  until alembic upgrade head; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      echo "arc-eval-service: migrations failed after ${max_attempts} attempts" >&2
      exit 1
    fi
    echo "arc-eval-service: database not ready, retry ${attempts}/${max_attempts}…" >&2
    sleep 2
  done
  echo "arc-eval-service: migrations at head"
else
  echo "arc-eval-service: ARC_EVAL_DATABASE_URL unset — using in-memory store, skipping migrations"
fi

exec "$@"
