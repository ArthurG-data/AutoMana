"""
automana-run  —  call any registered service from the command line.

Usage
-----
    automana-run <service.path> [--key value ...]
    automana-run <svc1> [--key value ...] <svc2> [--key value ...]   # chain

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

    # chain: outputs of each step are merged into the next step's kwargs
    # (explicit per-step kwargs override accumulated output)
    automana-run staging.scryfall.download_bulk_manifests --ingestion_run_id 1 --bulk_uri <uri> \\
                 staging.scryfall.update_data_uri_in_ops_repository --ingestion_run_id 1
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

    # ── parse steps: split extra_args on bare (non-flag) tokens ──────────────
    # Each non-flag token is treated as the start of a new service step.
    steps: list[tuple[str, dict[str, Any]]] = []
    current_svc = service_path
    current_kwargs: dict[str, Any] = {}

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
            current_kwargs[key] = _coerce(val)
        else:
            # bare token → start of next chained service
            steps.append((current_svc, current_kwargs))
            current_svc = token
            current_kwargs = {}

    steps.append((current_svc, current_kwargs))

    # ── bootstrap ─────────────────────────────────────────────────────────
    pool = await _bootstrap()
    try:
        from automana.core.service_manager import ServiceManager

        accumulated: dict[str, Any] = {}
        result: Any = None

        for i, (svc, kwargs) in enumerate(steps):
            merged = {**accumulated, **kwargs}  # explicit kwargs win
            click.echo(f"[automana-run] step {i+1}/{len(steps)}: {svc}", err=True)
            if merged:
                click.echo(f"[automana-run] kwargs   : {merged}", err=True)

            t0 = time.perf_counter()
            result = await ServiceManager.execute_service(svc, **merged)
            elapsed = time.perf_counter() - t0

            click.echo(f"[automana-run] elapsed  : {elapsed * 1000:.1f} ms", err=True)
            if isinstance(result, dict):
                accumulated.update(result)

        # ── output (final step result) ─────────────────────────────────────
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
