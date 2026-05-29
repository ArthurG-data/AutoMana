from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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
