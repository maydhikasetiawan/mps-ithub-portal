#!/bin/sh
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Database migrations complete. Starting application..."
exec gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 1 \
  --threads 4 \
  --timeout 45 \
  --graceful-timeout 30 \
  --forwarded-allow-ips="*" \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  app:app
