#!/usr/bin/env bash
set -euo pipefail
cd /workspace/famillejerichotache-
exec /workspace/family-venv/bin/gunicorn --bind "${HOST:-127.0.0.1}:${PORT:-5000}" --workers 1 --threads 4 --preload 'app:create_app()'
