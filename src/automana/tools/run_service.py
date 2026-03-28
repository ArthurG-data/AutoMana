"""
automana-run  —  call any registered service from the command line.

Usage
-----
    automana-run <service.path> [--key value ...]

Examples
--------
    # list every registered service
    automana-run

    # call a service with no extra args
    automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42

    # values are auto-cast: int, float, true/false/null, or left as str
    automana-run card_catalog.card.search --name "Black Lotus" --limit 5 --digital false

    # pipe the JSON result into jq
    automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42 | jq .
"""

import asyncio
import json
import sys
import time
import traceback
from typing import Any

import click

# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def _coerce(value: str) -> Any:
    """Try to cast a CLI string to the most specific Python type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ---------------------------------------------------------------------------
# Bootstrap  (mirrors automana/worker/ressources.py)
# ---------------------------------------------------------------------------

async def _bootstrap():
    from automana.core.database import init_async_pool
    from automana.core.QueryExecutor import AsyncQueryExecutor
    from automana.core.service_manager import ServiceManager
    from automana.core.settings import get_settings

    settings = get_settings()
    pool = await init_async_pool(settings)
    await ServiceManager.initialize(pool, query_executor=AsyncQueryExecutor())
    return pool


async def _teardown(pool):
    from automana.core.database import close_async_pool
    await close_async_pool(pool)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Accept arbitrary --key value pairs after the service path.
# click.argument + allow_extra_args + ignore_unknown_options achieves this.
@click.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help=__doc__,
)
@click.argument("service_path", required=False, default=None)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw", is_flag=True, default=False, help="Print raw repr instead of JSON.")
def cli(service_path, extra_args, raw):
    asyncio.run(_main(service_path, extra_args, raw))


async def _main(service_path, extra_args, raw):
    from automana.core.logging_config import configure_logging
    configure_logging()

    # ── list mode ──────────────────────────────────────────────────────────
    if not service_path:
        pool = await _bootstrap()
        try:
            from automana.core.service_registry import ServiceRegistry
            services = sorted(ServiceRegistry.list_services())
            click.echo(f"\n{len(services)} registered services:\n")
            for s in services:
                click.echo(f"  {s}")
            click.echo()
        finally:
            await _teardown(pool)
        return

    # ── parse --key value pairs ────────────────────────────────────────────
    kwargs: dict[str, Any] = {}
    it = iter(extra_args)
    for token in it:
        if token.startswith("--"):
            key = token.lstrip("-")
            if "=" in key:
                key, val = key.split("=", 1)
            else:
                try:
                    val = next(it)
                except StopIteration:
                    click.echo(f"[error] flag --{key} has no value", err=True)
                    sys.exit(1)
            kwargs[key] = _coerce(val)
        else:
            click.echo(f"[error] unexpected token: {token!r}", err=True)
            sys.exit(1)

    # ── bootstrap ─────────────────────────────────────────────────────────
    click.echo(f"[automana-run] service  : {service_path}", err=True)
    if kwargs:
        click.echo(f"[automana-run] kwargs   : {kwargs}", err=True)

    pool = await _bootstrap()
    try:
        from automana.core.service_manager import ServiceManager

        t0 = time.perf_counter()
        result = await ServiceManager.execute_service(service_path, **kwargs)
        elapsed = time.perf_counter() - t0

        click.echo(f"[automana-run] elapsed  : {elapsed * 1000:.1f} ms", err=True)
        click.echo(f"[automana-run] result type: {type(result).__name__}", err=True)

        # ── output ────────────────────────────────────────────────────────
        if raw:
            click.echo(repr(result))
        else:
            click.echo(json.dumps(result, indent=2, default=str))

    except Exception:
        click.echo("\n[automana-run] FAILED\n", err=True)
        traceback.print_exc()
        sys.exit(1)
    finally:
        await _teardown(pool)


def main():
    cli()


if __name__ == "__main__":
    main()
