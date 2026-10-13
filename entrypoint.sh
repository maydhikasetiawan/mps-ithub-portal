#!/bin/sh
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Database migrations complete. Starting application..."
exec python app.py
