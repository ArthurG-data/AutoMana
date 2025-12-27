#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"\
  -v admin_pw="$(cat /run/secrets/admin_db_password)" \
  -v backend_pw="$(cat /run/secrets/backend_db_password)" \
  -v celery_pw="$(cat /run/secrets/celery_db_password)" \
  -v agent_pw="$(cat /run/secrets/agent_db_password)" \
  -v readonly_pw="$(cat /run/secrets/readonly_db_password)" \
  -f /docker-entrypoint-initdb.d/02-app-roles.sql.tpl