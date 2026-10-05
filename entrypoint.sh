#!/bin/sh
# Prepara o banco e os arquivos estáticos e sobe o gunicorn.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn setup.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile -
