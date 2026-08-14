#!/bin/sh
set -e

cd /app

echo "[cms] migrate..."
python cms/manage.py migrate --noinput

echo "[cms] collectstatic..."
python cms/manage.py collectstatic --noinput

if [ "${CMS_IMPORT_ON_START:-false}" = "true" ] || [ "${CMS_IMPORT_ON_START:-}" = "1" ]; then
  echo "[cms] import_knowledge_md..."
  python cms/manage.py import_knowledge_md
fi

echo "[cms] gunicorn :8001"
exec gunicorn cms.config.wsgi:application \
  --bind 0.0.0.0:8001 \
  --workers "${CMS_GUNICORN_WORKERS:-2}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
