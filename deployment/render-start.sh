#!/bin/sh
# Render free plan: no pre-deploy step, so migrations run before the server starts.
set -e
python manage.py migrate --noinput
exec daphne -b 0.0.0.0 -p "${PORT:-8000}" app.asgi:application
