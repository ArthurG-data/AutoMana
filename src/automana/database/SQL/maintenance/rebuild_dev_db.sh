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

STAGES=(rebuild scryfall mtgstock mtgjson verify)

usage() {
  cat <<EOF
Usage: $0 [options]

Stage selection (mutually exclusive groups):
  --skip-rebuild       Equivalent to --from scryfall.
  --only <stage>       Run only this stage. Incompatible with --from/--until.
  --from <stage>       Start here (inclusive).
  --until <stage>      Stop here (inclusive).
  --preserve-data      Skip DROP DATABASE; apply schemas + migrations only.
                       Keeps all existing data and pricing work.
  --dry-run            Print plan + container preflight, then exit
                       without touching the DB or dispatching anything.
  -h, --help           This help.

Stages: ${STAGES[*]}

Examples:
  $0                              # full rebuild + all pipelines + verify
  $0 --skip-rebuild               # pipelines + verify, schema untouched
  $0 --only scryfall              # dispatch scryfall, nothing else
  $0 --from scryfall --until mtgstock   # pipelines up to mtgstock
  $0 --only rebuild               # schemas + grants only, no pipelines
  $0 --dry-run                    # sanity-check the plan without running

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
PRESERVE_DATA=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-rebuild)   SKIP_REBUILD=1; shift ;;
    --only)           ONLY_STAGE="${2:-}"; shift 2 ;;
    --from)           FROM_STAGE="${2:-}"; shift 2 ;;
    --until)          UNTIL_STAGE="${2:-}"; shift 2 ;;
    --preserve-data)  PRESERVE_DATA=1; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
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

# Container names are baked into the dev compose (deploy/docker-compose.dev.yml)
# and used only for the preflight healthcheck below — all other interactions
# go through $EXEC / $CELERY_EXEC. Override if you renamed containers.
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-automana-postgres-dev}"
CELERY_CONTAINER="${CELERY_CONTAINER:-automana-celery-dev}"
REDIS_CONTAINER="${REDIS_CONTAINER:-automana-redis-dev}"

SCHEMAS_DIR="src/automana/database/SQL/schemas"
MIGRATIONS_DIR="src/automana/database/SQL/migrations"

# Per-pipeline timeouts (seconds). Override via env if network / hardware
# differs. Scryfall is the heaviest (bulk download + card import + migrations).
SCRYFALL_TIMEOUT="${SCRYFALL_TIMEOUT:-3600}"
MTGSTOCK_TIMEOUT="${MTGSTOCK_TIMEOUT:-1800}"
MTGJSON_TIMEOUT="${MTGJSON_TIMEOUT:-1800}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"

# MTGStock reads exclusively from this directory inside the celery
# container — there is no download step. Guarded below before the
# mtgstock stage runs, and echoed here for the dry-run summary.
MTGSTOCK_DATA_DIR="${MTGSTOCK_DATA_DIR:-/data/automana_data/mtgstocks/raw/prints}"

# Per-stage log files land under a timestamped directory relative to
# the repo root. Override with $LOGDIR to pin a custom location.
LOGDIR="${LOGDIR:-logs/rebuild-$(date -u +%Y%m%d-%H%M%S)}"

if [[ ! -d "$SCHEMAS_DIR" ]]; then
  echo "Error: $SCHEMAS_DIR not found. Run from repo root." >&2
  exit 1
fi

# Returns 0 iff the container exists, is running, and (if it has a
# healthcheck) reports "healthy". Containers without a healthcheck are
# accepted as long as State.Status == "running" — this covers edge cases
# like a local override compose without healthchecks wired up.
_container_healthy() {
  local name="$1"
  local state health
  state=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null) || return 1
  [[ "$state" == "running" ]] || return 1
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$name" 2>/dev/null) || true
  [[ -z "$health" || "$health" == "healthy" ]]
}

echo "== Preflight: containers =="
# Only require the celery + redis pair when a pipeline stage will run.
# A rebuild-only invocation (e.g. --only rebuild) should not fail just
# because the worker container is down.
required_containers=("$POSTGRES_CONTAINER")
if should_run scryfall || should_run mtgstock || should_run mtgjson; then
  required_containers+=("$CELERY_CONTAINER" "$REDIS_CONTAINER")
fi
_dry_run_summary() {
  echo ""
  echo "== Dry run — no changes will be made =="
  echo "  Target DB   : $DBNAME (owner=$DBOWNER, superuser=$SUPERUSER)"
  echo "  Plan        : ${planned[*]}"
  echo "  Poll every  : ${POLL_INTERVAL}s"
  if should_run scryfall; then echo "  Scryfall    : daily_scryfall_data_pipeline (timeout ${SCRYFALL_TIMEOUT}s)"; fi
  if should_run mtgstock; then
    echo "  MTGStock    : mtgStock_download_pipeline (timeout ${MTGSTOCK_TIMEOUT}s)"
    echo "  Data dir    : $MTGSTOCK_DATA_DIR"
  fi
  if should_run mtgjson;  then echo "  MTGJson     : daily_mtgjson_data_pipeline (timeout ${MTGJSON_TIMEOUT}s)"; fi
  if should_run verify;   then echo "  Verify      : integrity_checks.sql + row counts"; fi
  echo ""
  echo "  No role ALTER, no DROP, no celery dispatch performed."
}

for c in "${required_containers[@]}"; do
  if _container_healthy "$c"; then
    echo "  ✓ $c"
  else
    # `docker inspect` on a missing container exits non-zero. Under
    # `set -euo pipefail`, a failing subshell in an assignment aborts
    # the script before we can print the error — so append `|| true`
    # to force success. We also strip the trailing newline that
    # docker-inspect emits even on empty output.
    state=$({ docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || true; } | tr -d '\n')
    health=$({ docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null || true; } | tr -d '\n')
    [[ -z "$state" ]] && state="missing"
    echo "ERROR: $c is not ready (state=$state${health:+, health=$health})." >&2
    echo "       Start the dev stack: dcdev-automana up -d" >&2
    exit 1
  fi
done

if [[ $DRY_RUN -eq 1 ]]; then
  _dry_run_summary
  exit 0
fi

mkdir -p "$LOGDIR"
echo "== Logs → $LOGDIR/ =="

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

# _run_stage <name> <fn>
# Runs `fn` with stdout+stderr tee'd to $LOGDIR/<name>.log while still
# streaming to the terminal. Exit code of `fn` is propagated through
# pipefail so `set -e` still aborts the script on stage failure.
_run_stage() {
  local name="$1" fn="$2"
  "$fn" 2>&1 | tee "$LOGDIR/$name.log"
  return "${PIPESTATUS[0]}"
}

# Stage block wrappers. Extracted into named functions so _run_stage
# can tee each block's output to its own log file.
do_rebuild() {
  echo "== Terminating connections to $DBNAME =="
  if [[ $PRESERVE_DATA -eq 1 ]]; then
    echo "== Preserving existing data: skipping DROP DATABASE =="
    echo "== Applying schemas (idempotent CREATE OR REPLACE) =="
    for f in "$SCHEMAS_DIR"/*.sql; do
      [[ "$(basename "$f")" == "integrity_checks.sql" ]] && continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null || true
    done

    echo "== Applying schema grants =="
    $EXEC psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DBNAME" \
      < src/automana/database/SQL/maintenance/apply_schema_grants.sql > /dev/null || true

    echo "== Applying migrations (incremental updates) =="
    for f in "$MIGRATIONS_DIR"/*.sql; do
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null || true
    done
  else
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
      [[ "$(basename "$f")" == "integrity_checks.sql" ]] && continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null
    done

    echo "== Applying schema grants =="
    $EXEC psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DBNAME" \
      < src/automana/database/SQL/maintenance/apply_schema_grants.sql > /dev/null

    echo "== Skipping migrations =="
    echo "  (migrations/ not replayed — schema files are authoritative for rebuilds.)"
  fi
}

do_scryfall() {
  run_pipeline "Scryfall" daily_scryfall_data_pipeline "$SCRYFALL_TIMEOUT"
}

do_mtgstock() {
  # Data-dir guard runs inside the stage so it's captured in the log
  # alongside the pipeline output.
  if ! $CELERY_EXEC bash -c "find '$MTGSTOCK_DATA_DIR' -type f -print -quit 2>/dev/null | grep -q ."; then
    echo "ERROR: $MTGSTOCK_DATA_DIR is empty or missing inside the celery-worker container." >&2
    echo "       MTGStock has no download step — it loads from disk. Seed the directory first." >&2
    return 1
  fi
  run_pipeline "MTGStock (from already-downloaded data)" mtgStock_download_pipeline "$MTGSTOCK_TIMEOUT"
}

do_mtgjson() {
  run_pipeline "MTGJson" daily_mtgjson_data_pipeline "$MTGJSON_TIMEOUT"
}

do_verify() {
  echo "== Verify: integrity checks + row counts =="

  $EXEC psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DBNAME" -c "
    DO \$\$ BEGIN
      IF to_regclass('ops.integrity_checks_card_catalog') IS NOT NULL THEN
        TRUNCATE ops.integrity_checks_card_catalog;
      END IF;
    END \$\$;
  " > /dev/null

  echo "  → running integrity_checks.sql"
  $EXEC psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DBNAME" \
    < "$SCHEMAS_DIR/integrity_checks.sql" > /dev/null

  echo ""
  echo "  --- integrity results ---"
  $EXEC psql -U "$SUPERUSER" -d "$DBNAME" -c "
    SELECT check_name, status, bad_records_count
    FROM ops.integrity_checks_card_catalog
    ORDER BY id;" || true

  echo ""
  echo "  --- row counts ---"
  $EXEC psql -U "$SUPERUSER" -d "$DBNAME" -c "
    SELECT 'card_catalog.unique_cards_ref'         AS table_name, count(*) FROM card_catalog.unique_cards_ref
    UNION ALL SELECT 'card_catalog.card_version',              count(*) FROM card_catalog.card_version
    UNION ALL SELECT 'pricing.price_observation',              count(*) FROM pricing.price_observation
    UNION ALL SELECT 'pricing.mtgjson_card_prices_staging',    count(*) FROM pricing.mtgjson_card_prices_staging
    UNION ALL SELECT 'ops.ingestion_runs',                     count(*) FROM ops.ingestion_runs
    ORDER BY 1;"

  echo ""
  echo "  --- ingestion run status summary ---"
  $EXEC psql -U "$SUPERUSER" -d "$DBNAME" -c "
    SELECT pipeline_name, status, count(*) AS runs
    FROM ops.ingestion_runs
    GROUP BY 1,2
    ORDER BY 1,2;"
}

if should_run rebuild; then
  _run_stage rebuild do_rebuild
else
  echo "== Skipping stage: rebuild =="
fi

if should_run scryfall; then _run_stage scryfall do_scryfall; fi
if should_run mtgstock; then _run_stage mtgstock do_mtgstock; fi
if should_run mtgjson;  then _run_stage mtgjson  do_mtgjson;  fi

if should_run verify; then _run_stage verify do_verify; fi

echo ""
echo "== Done =="
echo "Stages executed: ${planned[*]}"
echo "Logs: $LOGDIR/"
