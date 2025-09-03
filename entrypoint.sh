#!/usr/bin/env sh
set -euo pipefail

# Run DB migrations only when explicitly enabled to avoid race conditions
if [ "${TCE_RUN_MIGRATIONS:-false}" = "true" ] && [ -f "/app/alembic.ini" ]; then
  echo "Running DB migrations..."
  alembic upgrade head || {
    echo "Alembic migration failed" >&2
    exit 1
  }
fi

echo "Starting service: $@"
exec "$@"
