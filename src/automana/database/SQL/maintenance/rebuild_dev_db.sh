#!/usr/bin/env bash
# ============================================================
# Full dev-DB rebuild.
#
# Drops the `automana` database outright, recreates it, and
# replays every schema file in numerical order. Files under
# migrations/ are NOT replayed — they are upgrade deltas for
# long-lived DBs, not part of a canonical fresh install.
# The schema files + infra/db/init/02-app-roles.sql.tpl grant
# stanza represent the complete source of truth for rebuilds.
#
# After the script finishes:
#   1. Restart the backend + celery workers.
#   2. Re-trigger the Scryfall / MTGJson / MTGStock pipelines.
#      Data lands in the correct schemas because the committed
#      procs and search_path are clean.
#
# Roles are cluster-level and survive the DROP DATABASE —
# migration 10 is idempotent via IF NOT EXISTS. Extensions
# are reinstalled automatically by the schema files
# (`CREATE EXTENSION IF NOT EXISTS ...`).
#
# Usage:
#   ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh
# ============================================================

set -euo pipefail

# ============================================================
# Stage flags
# ------------------------------------------------------------
# Stages, in execution order:
#   rebuild   DROP + CREATE DATABASE + schemas + grants
#   scryfall  daily_scryfall_data_pipeline (includes migrations)
#   mtgstock  mtgStock_download_pipeline (reads disk, no network)
#   mtgjson   daily_mtgjson_data_pipeline
#
# Default: all four.
# ============================================================

STAGES=(rebuild scryfall mtgstock mtgjson)

usage() {
  cat <<EOF
Usage: $0 [options]

Stage selection (mutually exclusive groups):
  --skip-rebuild       Equivalent to --from scryfall.
  --only <stage>       Run only this stage. Incompatible with --from/--until.
  --from <stage>       Start here (inclusive).
  --until <stage>      Stop here (inclusive).
  -h, --help           This help.

Stages: ${STAGES[*]}

Examples:
  $0                              # full rebuild + all pipelines
  $0 --skip-rebuild               # pipelines only (assumes schema is intact)
  $0 --only scryfall              # dispatch scryfall, skip everything else
  $0 --from scryfall --until mtgstock   # pipelines up to mtgstock
  $0 --only rebuild               # schemas + grants only, no pipelines

Notes:
  --skip-rebuild against a DB with a today-dated run already in
  ops.ingestion_runs will fail on start_pipeline (UNIQUE constraint
  on pipeline_name + source_id + run_key). A full rebuild wipes it;
  otherwise clear it manually.
EOF
}

SKIP_REBUILD=0
ONLY_STAGE=""
FROM_STAGE=""
UNTIL_STAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-rebuild)   SKIP_REBUILD=1; shift ;;
    --only)           ONLY_STAGE="${2:-}"; shift 2 ;;
    --from)           FROM_STAGE="${2:-}"; shift 2 ;;
    --until)          UNTIL_STAGE="${2:-}"; shift 2 ;;
    -h|--help)        usage; exit 0 ;;
    *)                echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -n "$ONLY_STAGE" ]]; then
  if [[ -n "$FROM_STAGE" || -n "$UNTIL_STAGE" || $SKIP_REBUILD -eq 1 ]]; then
    echo "ERROR: --only cannot combine with --from/--until/--skip-rebuild." >&2
    exit 2
  fi
fi

if [[ $SKIP_REBUILD -eq 1 && -z "$FROM_STAGE" ]]; then
  FROM_STAGE="scryfall"
fi

# Look up a stage's position in $STAGES by name. Prints the index to
# stdout on hit, prints nothing + returns 1 on miss. Callers are
# responsible for emitting a user-facing error — this keeps the helper
# reusable by `should_run` (where a miss is fatal, not a user error).
_stage_idx() {
  local s="$1" i
  for i in "${!STAGES[@]}"; do
    [[ "${STAGES[$i]}" == "$s" ]] && { echo "$i"; return 0; }
  done
  return 1
}

_validate_stage() {
  local label="$1" value="$2"
  if ! _stage_idx "$value" >/dev/null; then
    echo "ERROR: $label: unknown stage '$value' (valid: ${STAGES[*]})" >&2
    exit 2
  fi
}

[[ -n "$ONLY_STAGE"  ]] && _validate_stage "--only"  "$ONLY_STAGE"
[[ -n "$FROM_STAGE"  ]] && _validate_stage "--from"  "$FROM_STAGE"
[[ -n "$UNTIL_STAGE" ]] && _validate_stage "--until" "$UNTIL_STAGE"

# Now that --only is validated under its own label, fold it into the
# from/until range so the rest of the script only has to look at those.
if [[ -n "$ONLY_STAGE" ]]; then
  FROM_STAGE="$ONLY_STAGE"
  UNTIL_STAGE="$ONLY_STAGE"
fi

FROM_IDX=0
UNTIL_IDX=$(( ${#STAGES[@]} - 1 ))
[[ -n "$FROM_STAGE"  ]] && FROM_IDX=$(_stage_idx "$FROM_STAGE")
[[ -n "$UNTIL_STAGE" ]] && UNTIL_IDX=$(_stage_idx "$UNTIL_STAGE")

if (( FROM_IDX > UNTIL_IDX )); then
  echo "ERROR: --from '$FROM_STAGE' (#$FROM_IDX) comes after --until '$UNTIL_STAGE' (#$UNTIL_IDX)." >&2
  exit 2
fi

should_run() {
  local stage="$1" idx
  idx=$(_stage_idx "$stage") || {
    # Internal caller bug: asked about a stage that isn't in $STAGES.
    # Fatal, not a flag-parsing error.
    echo "INTERNAL: should_run called with unknown stage '$stage'" >&2
    exit 3
  }
  (( idx >= FROM_IDX && idx <= UNTIL_IDX ))
}

# Pretty-print the planned stages so the operator sees what's about to
# happen before the first destructive step (the DROP DATABASE).
planned=()
for s in "${STAGES[@]}"; do
  should_run "$s" && planned+=("$s")
done
echo "== Plan: ${planned[*]} =="

DBNAME="${DBNAME:-automana}"
DBOWNER="${DBOWNER:-automana_admin}"
# Bootstrap superuser. After the app_admin demote (see
# maintenance/demote_app_admin.sql) automana_admin is the only
# LOGIN + SUPERUSER role in the cluster, so it owns DROP/CREATE DATABASE
# duties. Override via $SUPERUSER if your env differs.
SUPERUSER="${SUPERUSER:-automana_admin}"
EXEC="${EXEC:-dcdev-automana exec -T postgres}"
CELERY_EXEC="${CELERY_EXEC:-dcdev-automana exec -T celery-worker}"

SCHEMAS_DIR="src/automana/database/SQL/schemas"
MIGRATIONS_DIR="src/automana/database/SQL/migrations"

# Per-pipeline timeouts (seconds). Override via env if network / hardware
# differs. Scryfall is the heaviest (bulk download + card import + migrations).
SCRYFALL_TIMEOUT="${SCRYFALL_TIMEOUT:-3600}"
MTGSTOCK_TIMEOUT="${MTGSTOCK_TIMEOUT:-1800}"
MTGJSON_TIMEOUT="${MTGJSON_TIMEOUT:-1800}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"

if [[ ! -d "$SCHEMAS_DIR" ]]; then
  echo "Error: $SCHEMAS_DIR not found. Run from repo root." >&2
  exit 1
fi

echo "== Preflight: role sanity check =="
# `02-app-roles.sql.tpl` runs only on first-time volume init. A rebuild
# never re-runs it, so we verify every role we depend on already exists.
# Abort loudly if any is missing — the template must be re-run manually
# (easiest: docker volume rm + container recreate).
$EXEC psql -U "$SUPERUSER" -d postgres <<'SQL' || { echo "Preflight failed — fix roles before rebuild."; exit 1; }
DO $$
DECLARE
  required_roles text[] := ARRAY[
    'db_owner', 'app_admin', 'app_rw', 'app_ro', 'agent_reader',
    'automana_admin', 'app_backend', 'app_celery',
    'app_readonly', 'app_agent'
  ];
  r text;
  missing text[] := '{}';
BEGIN
  FOREACH r IN ARRAY required_roles LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      missing := missing || r;
    END IF;
  END LOOP;
  IF array_length(missing, 1) > 0 THEN
    RAISE EXCEPTION 'Missing required roles: %. Re-run infra/db/init/02-app-roles.sql.tpl.',
      array_to_string(missing, ', ');
  END IF;

  -- db_owner sometimes drifts to LOGIN via ad-hoc ALTERs; pin it back.
  ALTER ROLE db_owner NOLOGIN;
END $$;
SQL

if should_run rebuild; then
  echo "== Terminating connections to $DBNAME =="
  $EXEC psql -U "$SUPERUSER" -d postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = '$DBNAME' AND pid <> pg_backend_pid();"

  echo "== Dropping $DBNAME =="
  $EXEC psql -U "$SUPERUSER" -d postgres -c "DROP DATABASE IF EXISTS $DBNAME;"

  echo "== Recreating $DBNAME (owner=$DBOWNER) =="
  $EXEC psql -U "$SUPERUSER" -d postgres -c "CREATE DATABASE $DBNAME OWNER $DBOWNER;"

  echo "== Applying schemas =="
  for f in "$SCHEMAS_DIR"/*.sql; do
    [[ "$(basename "$f")" == "integrity_checks.sql" ]] && continue   # ops-time only
    echo "  → $(basename "$f")"
    # ON_ERROR_STOP=1 makes psql abort on the first error instead of
    # continuing and cascading 50 follow-on errors. Combined with
    # `set -e` above, the whole script stops at the first failure so
    # the operator sees exactly which file / statement broke.
    $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null
  done

  echo "== Applying schema grants =="
  # DROP DATABASE wipes every per-database privilege (schema-level and
  # object-level grants). The init template `02-app-roles.sql.tpl` only
  # runs on volume init, not on a DROP+CREATE DATABASE cycle, so the
  # app_rw / app_ro / app_admin / agent_reader roles would have no
  # privileges on the newly-created schemas. Re-apply here.
  $EXEC psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DBNAME" \
    < src/automana/database/SQL/maintenance/apply_schema_grants.sql > /dev/null

  echo "== Skipping migrations =="
  # A rebuild rebuilds from the canonical state defined in the schema files
  # + infra/db/init/02-app-roles.sql.tpl (which already applies the full
  # grant stanza on every schema). The files under migrations/ are historical
  # deltas intended for upgrading long-lived databases from older shapes —
  # running them against a fresh DB at best no-ops via IF EXISTS guards,
  # at worst fails (e.g. `08_schema_change_price.sql` ALTERs a compressed
  # TimescaleDB hypertable that already has the target columns).
  #
  # If you need a specific migration's effect on this fresh DB, apply it
  # manually after reviewing it. Most are obsolete the moment the schema
  # file catches up to what they were deploying.
  echo "  (migrations/ not replayed — schema files are authoritative for rebuilds.)"
else
  echo "== Skipping stage: rebuild =="
fi

# ============================================================
# Pipeline orchestration
# ------------------------------------------------------------
# Replaces the old "operator triggers pipelines manually" flow.
# Each pipeline is dispatched to Celery, then `ops.ingestion_runs`
# is polled on (pipeline_name, run_key) until the terminal state
# is reached (success | failed | partial) or the stage times out.
#
# A failure in one stage aborts the rebuild — later stages have
# hard data dependencies on earlier ones (MTGStock/MTGJson resolve
# card IDs via `card_catalog.card_version`, which scryfall populates).
# ============================================================

# run_pipeline <label> <celery_task_name> <timeout_seconds>
run_pipeline() {
  local label="$1"
  local task_name="$2"
  local timeout="${3:-1800}"

  echo ""
  echo "== Pipeline: $label =="
  echo "  task     : $task_name"
  echo "  timeout  : ${timeout}s"

  # Worker liveness. `celery call` will happily enqueue a task when no
  # worker is running — the task just sits forever. Ping upfront so we
  # fail in seconds rather than after $timeout.
  if ! $CELERY_EXEC celery -A automana.worker.main:app inspect ping --timeout 10 >/dev/null 2>&1; then
    echo "ERROR: no Celery workers reachable. Start celery-worker and retry." >&2
    return 1
  fi

  # Dispatch. `celery call` may print a deprecation warning or banner
  # alongside the UUID depending on version, so extract the UUID
  # explicitly instead of trusting "just trim whitespace".
  local raw task_id
  raw=$($CELERY_EXEC celery -A automana.worker.main:app call "$task_name" 2>&1) || {
    echo "ERROR: celery call failed for $task_name:" >&2
    echo "$raw" >&2
    return 1
  }
  task_id=$(printf '%s\n' "$raw" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | tail -n1)
  if [[ -z "$task_id" ]]; then
    echo "ERROR: could not extract task id from celery output:" >&2
    echo "$raw" >&2
    return 1
  fi
  echo "  dispatched: $task_id"

  # Poll ops.ingestion_runs by celery_task_id (the dispatcher task id is
  # stored verbatim on the run row via start_pipeline/start_run). This
  # avoids a UTC-date-boundary race that would exist if we polled by the
  # run_key we computed in bash — the task-side run_key comes from
  # datetime.utcnow() at task-start time, which can differ from our bash
  # $(date -u) if we dispatch near midnight.
  local start_ts=$SECONDS
  local last_step="" elapsed=0 status="" current_step=""
  while :; do
    elapsed=$((SECONDS - start_ts))
    if (( elapsed > timeout )); then
      printf "\n"
      echo "ERROR: pipeline $task_name timed out after ${timeout}s (last step: ${current_step:-pending})." >&2
      _dump_run_steps "$task_id"
      return 1
    fi

    # -At: tuple only, no header. -F '|' picks a delimiter unlikely to
    # appear in step names. Single query returns "status|current_step".
    local row
    row=$($EXEC psql -U "$SUPERUSER" -d "$DBNAME" -At -F '|' -c "
      SELECT COALESCE(status,''), COALESCE(current_step,'')
      FROM ops.ingestion_runs
      WHERE celery_task_id = '$task_id'
      LIMIT 1;" 2>/dev/null | head -n1) || row=""
    status="${row%%|*}"
    current_step="${row#*|}"
    [[ "$row" != *"|"* ]] && current_step=""

    case "$status" in
      success)
        printf "\r%-78s\n" "  done in ${elapsed}s (success)"
        return 0
        ;;
      failed|partial)
        printf "\n"
        echo "ERROR: pipeline $task_name ended with status=$status (step=${current_step:-n/a})." >&2
        _dump_run_steps "$task_id"
        return 1
        ;;
      running|pending|"")
        # Only reprint when the step name changes, otherwise we flood the log.
        if [[ "$current_step" != "$last_step" ]]; then
          printf "\r%-78s\n" "  [${elapsed}s] step=${current_step:-<starting>}"
          last_step="$current_step"
        else
          printf "\r  [%4ds] step=%-48s" "$elapsed" "${current_step:-<starting>}"
        fi
        sleep "$POLL_INTERVAL"
        ;;
    esac
  done
}

# Print the step breakdown of a (possibly failed) run. Called on timeout
# or terminal-failure; never from the success path.
_dump_run_steps() {
  local task_id="$1"
  echo "  --- run steps for celery_task_id=$task_id ---" >&2
  $EXEC psql -U "$SUPERUSER" -d "$DBNAME" -c "
    SELECT s.step_name, s.status, s.error_code,
           EXTRACT(epoch FROM (COALESCE(s.ended_at, now()) - s.started_at))::int AS sec
    FROM ops.ingestion_run_steps s
    JOIN ops.ingestion_runs r ON r.id = s.ingestion_run_id
    WHERE r.celery_task_id = '$task_id'
    ORDER BY s.id;" >&2 || true
}

# MTGStock reads exclusively from /data/mtgstocks/raw/prints/ — there is
# no download step. An empty directory produces a silent "success" with
# zero rows loaded, which defeats the whole point of a rebuild. The
# guard only matters if the mtgstock stage is actually going to run.
MTGSTOCK_DATA_DIR="${MTGSTOCK_DATA_DIR:-/data/mtgstocks/raw/prints}"
if should_run mtgstock; then
  if ! $CELERY_EXEC bash -c "find '$MTGSTOCK_DATA_DIR' -type f -print -quit 2>/dev/null | grep -q ."; then
    echo "ERROR: $MTGSTOCK_DATA_DIR is empty or missing inside the celery-worker container." >&2
    echo "       MTGStock has no download step — it loads from disk. Seed the directory first." >&2
    exit 1
  fi
fi

if should_run scryfall; then
  run_pipeline "Scryfall" \
    daily_scryfall_data_pipeline \
    "$SCRYFALL_TIMEOUT"
fi

if should_run mtgstock; then
  run_pipeline "MTGStock (from already-downloaded data)" \
    mtgStock_download_pipeline \
    "$MTGSTOCK_TIMEOUT"
fi

if should_run mtgjson; then
  run_pipeline "MTGJson" \
    daily_mtgjson_data_pipeline \
    "$MTGJSON_TIMEOUT"
fi

echo ""
echo "== Done =="
echo "Stages executed: ${planned[*]}"
echo "Inspect row counts via:"
echo "  dcdev-automana exec -T postgres psql -U app_readonly -d $DBNAME -c \"SELECT 'card_version' AS t, count(*) FROM card_catalog.card_version UNION ALL SELECT 'price_observation', count(*) FROM pricing.price_observation;\""
