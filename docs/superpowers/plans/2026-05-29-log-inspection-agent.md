# Log Inspection Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two complementary log monitoring systems: Grafana alert rules that fire to Discord on error spikes, and a daily Celery beat task that queries Loki for the last 24h of errors, feeds them to Claude, and posts an AI-written digest to Discord.

**Architecture:** Grafana provisioning files define a Discord contact point and LogQL-based alert rule deployed alongside the logging stack on the VPS. The daily summary runs as a standard AutoMana service (`ops.log_analysis.daily_summary`) registered via `@ServiceRegistry.register`, wired into the existing Celery beat schedule at 07:30 AEST. It queries the Loki HTTP API directly with `httpx`, condenses the raw log lines into a Claude prompt, and posts the response to Discord using the same `httpx` pattern already in `health_alert_service.py`.

**Tech Stack:** Grafana alert provisioning (YAML), Loki query API (`/loki/api/v1/query_range`), `anthropic` Python SDK, `httpx`, Celery beat, `@ServiceRegistry.register`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `deploy/vps/grafana/provisioning/datasources/loki.yml` | Add explicit `uid: automana-loki` so alert rules can reference it |
| Create | `deploy/vps/grafana/provisioning/alerting/contact-points.yml` | Discord contact point using `GF_DISCORD_WEBHOOK_URL` env var |
| Create | `deploy/vps/grafana/provisioning/alerting/notification-policy.yml` | Route all alerts to Discord |
| Create | `deploy/vps/grafana/provisioning/alerting/alert-rules.yml` | Fire when >5 errors in any 5-minute window |
| Modify | `deploy/vps/docker-compose.logging.yml` | Pass `GF_DISCORD_WEBHOOK_URL` env var into Grafana |
| Modify | `src/automana/core/config/settings.py` | Add `LOKI_URL` and `ANTHROPIC_API_KEY` fields |
| Create | `src/automana/core/services/ops/log_analysis_service.py` | Query Loki, call Claude, post to Discord |
| Modify | `src/automana/worker/tasks/pipelines.py` | Add `log_analysis_daily_task` Celery task |
| Modify | `src/automana/worker/celeryconfig.py` | Add beat schedule entry at 07:30 AEST |
| Create | `tests/unit/core/services/ops/test_log_analysis_service.py` | Unit tests for pure helpers |

---

## Task 1: Update Grafana datasource with explicit UID

**Files:**
- Modify: `deploy/vps/grafana/provisioning/datasources/loki.yml`

- [ ] **Step 1: Add UID to datasource provisioning**

```yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    uid: automana-loki
    access: proxy
    url: http://loki:3100
    isDefault: true
    jsonData:
      maxLines: 5000
```

- [ ] **Step 2: Commit**

```bash
git add deploy/vps/grafana/provisioning/datasources/loki.yml
git commit -m "chore(logging): add explicit UID to Loki datasource for alert provisioning"
```

---

## Task 2: Grafana — Discord contact point and notification policy

**Files:**
- Create: `deploy/vps/grafana/provisioning/alerting/contact-points.yml`
- Create: `deploy/vps/grafana/provisioning/alerting/notification-policy.yml`
- Modify: `deploy/vps/docker-compose.logging.yml`

- [ ] **Step 1: Create contact-points.yml**

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: discord
    receivers:
      - uid: discord-receiver
        type: discord
        settings:
          url: ${GF_DISCORD_WEBHOOK_URL}
          message: "{{ len .Alerts.Firing }} alert(s) firing\n{{ range .Alerts.Firing }}• {{ .Labels.alertname }}: {{ .Annotations.summary }}\n{{ end }}"
        disableResolveMessage: false
```

- [ ] **Step 2: Create notification-policy.yml**

```yaml
apiVersion: 1
policies:
  - orgId: 1
    receiver: discord
    group_by: ['alertname']
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
    routes: []
```

- [ ] **Step 3: Pass Discord webhook URL into Grafana in docker-compose.logging.yml**

Add to the `grafana` service `environment` block:

```yaml
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?set GRAFANA_ADMIN_PASSWORD in .env.logging}
      GF_DISCORD_WEBHOOK_URL: ${DISCORD_WEBHOOK_URL:?set DISCORD_WEBHOOK_URL in .env.logging}
```

Also add `DISCORD_WEBHOOK_URL=<your-discord-webhook-url>` to `~/automana/.env.logging` on the VPS.

- [ ] **Step 4: Commit**

```bash
git add deploy/vps/grafana/provisioning/alerting/ deploy/vps/docker-compose.logging.yml
git commit -m "feat(logging): add Grafana Discord contact point and notification policy"
```

---

## Task 3: Grafana — error rate alert rule

**Files:**
- Create: `deploy/vps/grafana/provisioning/alerting/alert-rules.yml`

- [ ] **Step 1: Create alert-rules.yml**

This fires when more than 5 ERROR-level log entries arrive across all containers in a 5-minute window.

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: AutoMana Error Alerts
    folder: AutoMana
    interval: 5m
    rules:
      - uid: automana-high-error-rate
        title: High Error Rate
        condition: B
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: automana-loki
            model:
              editorMode: code
              expr: 'sum(count_over_time({level="ERROR"}[5m]))'
              instant: true
              refId: A
          - refId: B
            datasourceUid: __expr__
            model:
              type: threshold
              refId: B
              expression: A
              conditions:
                - evaluator:
                    type: gt
                    params:
                      - 5
                  operator:
                    type: and
                  query:
                    params:
                      - B
                  reducer:
                    type: last
        noDataState: NoData
        execErrState: Error
        for: 5m
        annotations:
          summary: "More than 5 errors in the last 5 minutes across all containers"
        labels: {}
        isPaused: false
```

- [ ] **Step 2: Commit**

```bash
git add deploy/vps/grafana/provisioning/alerting/alert-rules.yml
git commit -m "feat(logging): add Grafana error rate alert rule (>5 errors / 5 min)"
```

---

## Task 4: Deploy Grafana alert provisioning to VPS

- [ ] **Step 1: Copy files to VPS**

```bash
scp deploy/vps/docker-compose.logging.yml root@103.6.171.115:~/automana/
scp -r deploy/vps/grafana root@103.6.171.115:~/automana/
```

- [ ] **Step 2: Add Discord webhook URL to .env.logging on VPS**

```bash
ssh root@103.6.171.115 "echo 'DISCORD_WEBHOOK_URL=<your-discord-webhook-url>' >> ~/automana/.env.logging"
```

- [ ] **Step 3: Restart Grafana to pick up provisioning**

```bash
ssh root@103.6.171.115 "cd ~/automana && docker compose -f docker-compose.logging.yml --env-file .env.logging up -d --force-recreate grafana"
```

- [ ] **Step 4: Verify in Grafana UI**

SSH tunnel: `ssh -L 3000:localhost:3000 root@103.6.171.115`

Open http://localhost:3000 → Alerting → Contact points: should show `discord`.
Open Alerting → Alert rules: should show `High Error Rate` in the `AutoMana` folder.

---

## Task 5: Add LOKI_URL and ANTHROPIC_API_KEY to settings

**Files:**
- Modify: `src/automana/core/config/settings.py`

- [ ] **Step 1: Add fields to the Settings class (after the `DISCORD_WEBHOOK_URL` line)**

```python
    DISCORD_WEBHOOK_URL: str | None = None
    LOKI_URL: str | None = Field(default=None, description="Loki base URL for log queries, e.g. http://103.6.171.115:3100")
    ANTHROPIC_API_KEY: str | None = None
```

- [ ] **Step 2: Add to .env.dev**

Add these two lines to `config/env/.env.dev`:
```
LOKI_URL=http://103.6.171.115:3100
ANTHROPIC_API_KEY=<your-anthropic-api-key>
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/config/settings.py
git commit -m "feat(config): add LOKI_URL and ANTHROPIC_API_KEY settings"
```

---

## Task 6: Add anthropic dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add anthropic to dependencies**

```bash
uv add anthropic
```

- [ ] **Step 2: Verify it installed**

```bash
python -c "import anthropic; print(anthropic.__version__)"
```

Expected: prints a version number (e.g. `0.40.0`).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(deps): add anthropic SDK for log analysis agent"
```

---

## Task 7: Write tests for log analysis helpers

**Files:**
- Create: `tests/unit/core/services/ops/test_log_analysis_service.py`

The service has three testable pure helpers:
- `extract_error_lines(loki_response)` — pulls log lines from Loki's JSON response
- `build_claude_prompt(error_lines, window_hours)` — builds the analysis prompt
- `format_discord_message(claude_text, error_count, window_hours)` — formats the final Discord post

- [ ] **Step 1: Write failing tests**

```python
from automana.core.services.ops.log_analysis_service import (
    extract_error_lines,
    build_claude_prompt,
    format_discord_message,
)


def _loki_response(lines: list[tuple[str, str]]) -> dict:
    return {
        "data": {
            "result": [
                {
                    "stream": {"container": "automana-backend-dev", "level": "ERROR"},
                    "values": [[str(i * 1_000_000_000), line] for i, line in enumerate(lines)],
                }
            ]
        }
    }


def test_extract_error_lines_returns_log_strings():
    resp = _loki_response([
        '{"level":"ERROR","msg":"db connection failed","logger":"automana.db"}',
        '{"level":"ERROR","msg":"task retry exceeded","logger":"automana.worker"}',
    ])
    lines = extract_error_lines(resp)
    assert len(lines) == 2
    assert "db connection failed" in lines[0]


def test_extract_error_lines_empty_result():
    resp = {"data": {"result": []}}
    assert extract_error_lines(resp) == []


def test_build_claude_prompt_includes_lines():
    lines = ["ERROR: db failed", "ERROR: task timeout"]
    prompt = build_claude_prompt(lines, window_hours=24)
    assert "db failed" in prompt
    assert "24" in prompt


def test_build_claude_prompt_truncates_at_500_lines():
    lines = [f"ERROR: line {i}" for i in range(600)]
    prompt = build_claude_prompt(lines, window_hours=24)
    assert "line 499" in prompt
    assert "line 500" not in prompt


def test_format_discord_message_includes_count():
    msg = format_discord_message("Summary here.", error_count=42, window_hours=24)
    assert "42" in msg
    assert "Summary here." in msg
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/core/services/ops/test_log_analysis_service.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — the module doesn't exist yet.

---

## Task 8: Implement log_analysis_service.py

**Files:**
- Create: `src/automana/core/services/ops/log_analysis_service.py`

- [ ] **Step 1: Write the service**

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
import httpx

from automana.core.config.settings import get_settings
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)

_CLAUDE_MODEL = "claude-sonnet-4-6"
_MAX_LINES = 500


def extract_error_lines(loki_response: dict) -> list[str]:
    lines = []
    for stream in loki_response.get("data", {}).get("result", []):
        for _ts, log_line in stream.get("values", []):
            lines.append(log_line)
    return lines


def build_claude_prompt(error_lines: list[str], window_hours: int) -> str:
    truncated = error_lines[:_MAX_LINES]
    joined = "\n".join(truncated)
    return (
        f"You are analysing application logs for AutoMana, a Magic: The Gathering "
        f"collection management backend. Below are all ERROR-level log entries from "
        f"the last {window_hours} hours across all services (backend, celery worker, "
        f"celery beat, postgres, redis).\n\n"
        f"Your task:\n"
        f"1. Group errors by root cause (not by service).\n"
        f"2. Identify the top 3 most critical issues and explain why they matter.\n"
        f"3. Flag anything that looks like data loss, auth failure, or a stuck pipeline.\n"
        f"4. Keep the total response under 1800 characters (Discord limit).\n"
        f"5. Use plain text — no markdown headers, no code blocks.\n\n"
        f"Log entries:\n{joined}"
    )


def format_discord_message(claude_text: str, error_count: int, window_hours: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"🤖 Daily log digest — {now}\n"
        f"Errors in last {window_hours}h: {error_count}\n\n"
        f"{claude_text}"
    )[:2000]


async def _query_loki(loki_url: str, window_hours: int) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=window_hours)
    params = {
        "query": '{level="ERROR"}',
        "start": str(int(start.timestamp() * 1e9)),
        "end": str(int(end.timestamp() * 1e9)),
        "limit": "2000",
        "direction": "forward",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{loki_url}/loki/api/v1/query_range", params=params)
        resp.raise_for_status()
    return resp.json()


def _call_claude(prompt: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _post_to_discord(webhook_url: str, body: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(webhook_url, json={"content": body})
    if not (200 <= resp.status_code < 300):
        logger.warning(
            "discord_post_non_2xx",
            extra={"http_status": resp.status_code},
        )


@ServiceRegistry.register("ops.log_analysis.daily_summary")
async def run_daily_log_summary() -> dict:
    """Query Loki for the last 24h of ERROR logs, summarise with Claude, post to Discord."""
    settings = get_settings()

    if not settings.LOKI_URL:
        logger.warning("log_analysis_skipped_no_loki_url")
        return {"skipped": True, "reason": "LOKI_URL not set"}

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("log_analysis_skipped_no_anthropic_key")
        return {"skipped": True, "reason": "ANTHROPIC_API_KEY not set"}

    window_hours = 24
    loki_response = await _query_loki(settings.LOKI_URL, window_hours)
    error_lines = extract_error_lines(loki_response)
    error_count = len(error_lines)

    logger.info("log_analysis_fetched_errors", extra={"error_count": error_count})

    if error_count == 0:
        payload = format_discord_message(
            "No errors logged in the last 24 hours. All systems nominal.",
            error_count=0,
            window_hours=window_hours,
        )
    else:
        prompt = build_claude_prompt(error_lines, window_hours)
        claude_text = _call_claude(prompt, settings.ANTHROPIC_API_KEY)
        payload = format_discord_message(claude_text, error_count, window_hours)

    if settings.DISCORD_WEBHOOK_URL:
        await _post_to_discord(settings.DISCORD_WEBHOOK_URL, payload)
        logger.info("log_analysis_digest_posted")
    else:
        logger.warning("log_analysis_discord_webhook_unset")

    return {
        "error_count": error_count,
        "window_hours": window_hours,
        "posted": bool(settings.DISCORD_WEBHOOK_URL),
    }
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/core/services/ops/test_log_analysis_service.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/services/ops/log_analysis_service.py \
        tests/unit/core/services/ops/test_log_analysis_service.py
git commit -m "feat(ops): add log analysis service — Loki query + Claude digest + Discord post"
```

---

## Task 9: Wire Celery task and beat schedule

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Add Celery task to pipelines.py**

Find the section where other ops tasks are defined (e.g. `pipeline_health_alert_task`) and add:

```python
@app.task(name="automana.worker.tasks.pipelines.log_analysis_daily_task", bind=True)
def log_analysis_daily_task(self) -> dict:
    return run_service("ops.log_analysis.daily_summary")
```

Also add the import at the top of the file alongside other ops service imports:
```python
from automana.core.services.ops.log_analysis_service import run_daily_log_summary  # noqa: F401 — registers service
```

- [ ] **Step 2: Add beat schedule entry in celeryconfig.py**

Add after the `pipeline-health-pm` entry:

```python
    "log-analysis-daily": {
        "task": "automana.worker.tasks.pipelines.log_analysis_daily_task",
        "schedule": crontab(hour=7, minute=30),  # 07:30 AEST — after all nightly pipelines
    },
```

- [ ] **Step 3: Verify the service registers correctly**

```bash
python -c "
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.ops.log_analysis_service import run_daily_log_summary  # noqa
assert 'ops.log_analysis.daily_summary' in ServiceRegistry.list_services(), 'not registered'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py src/automana/worker/celeryconfig.py
git commit -m "feat(worker): add daily log analysis Celery task (07:30 AEST)"
```

---

## Task 10: Manual smoke test

- [ ] **Step 1: Trigger the service manually**

```bash
python src/automana/tools/run_service.py ops.log_analysis.daily_summary
```

Expected output: JSON with `error_count`, `window_hours`, `posted: true/false`.
Check Discord — the digest should appear within ~30 seconds.

- [ ] **Step 2: Verify Grafana alerts work**

In Grafana → Alerting → Alert rules → click `High Error Rate` → Evaluate now.
Confirm it evaluates without errors (no data is fine for now — it just means no errors currently).

- [ ] **Step 3: Final commit**

If any tweaks were needed during smoke test:

```bash
git add -p
git commit -m "fix(ops): adjust log analysis prompt/format after smoke test"
```
