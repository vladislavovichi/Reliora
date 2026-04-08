#!/bin/sh

set -eu

echo "Applying database migrations..."
alembic -c migrations/alembic.ini upgrade head

echo "Starting application..."
exec python -m app.main
