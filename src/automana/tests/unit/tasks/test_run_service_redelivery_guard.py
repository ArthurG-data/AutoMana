"""Guard against broker redelivery re-running already-finished pipeline steps.

Context: tasks run with ``acks_late=True`` and the Redis broker uses the
default 1h ``visibility_timeout``. A pipeline step that outlives the timeout
(or any worker restart) gets the *same* message redelivered, re-running the
step even though its ingestion run already concluded. ``run_service`` carries
``ingestion_run_id`` in its context, so on a *redelivered* message it can check
whether that run is finished and no-op instead of redoing the work.

The guard is gated on Celery's ``redelivered`` delivery flag so that legitimate
post-``finish_run`` steps (e.g. the Scryfall integrity tail, which run after the
run is marked ``success``) are never skipped on their first delivery.
"""
import asyncio
from unittest.mock import MagicMock, patch

import automana.worker.main as main_mod


def _dummy_service(ingestion_run_id=None, foo=None):
    """A registered-service stand-in with an inspectable signature."""
    return {}


def _run_guard_case(redelivered, run_finished, context):
    """Drive run_service with the guard's collaborators mocked.

    Returns (result, executed_paths) where executed_paths lists every
    service_path passed to ServiceManager.execute_service in call order.
    """
    executed_paths = []

    async def fake_execute(service_path, **kwargs):
        executed_paths.append(service_path)
        if service_path == "ops.pipeline_services.is_run_finished":
            return {"is_finished": run_finished}
        return {}

    state = MagicMock()
    state.initialized = True
    state.loop = asyncio.new_event_loop()

    # run_service is a bound (bind=True) Celery task; drive it through a
    # pushed request context so self.request.delivery_info is controllable.
    main_mod.run_service.push_request(id="task-1", delivery_info={"redelivered": redelivered})
    try:
        with patch.object(main_mod, "get_state", return_value=state), \
             patch.object(main_mod.ServiceManager, "execute_service", new=fake_execute), \
             patch.object(main_mod.ServiceManager, "get_service_function", return_value=_dummy_service):
            result = main_mod.run_service.run(
                context,
                "mtg_stock.data_loader.run_list_id_load",
            )
    finally:
        main_mod.run_service.pop_request()
        state.loop.close()

    return result, executed_paths


def test_redelivered_finished_run_is_skipped():
    context = {"ingestion_run_id": 39, "foo": "bar"}
    result, executed = _run_guard_case(redelivered=True, run_finished=True, context=context)

    # No-op: returns context untouched, target service never executed.
    assert result == {"ingestion_run_id": 39, "foo": "bar"}
    assert executed == ["ops.pipeline_services.is_run_finished"]
    assert "mtg_stock.data_loader.run_list_id_load" not in executed


def test_redelivered_unfinished_run_still_executes():
    context = {"ingestion_run_id": 39, "foo": "bar"}
    result, executed = _run_guard_case(redelivered=True, run_finished=False, context=context)

    # Run still in flight → guard checks, then proceeds with the step.
    assert "ops.pipeline_services.is_run_finished" in executed
    assert "mtg_stock.data_loader.run_list_id_load" in executed


def test_first_delivery_of_finished_run_is_not_skipped():
    # Protects legitimate post-finish_run steps (e.g. integrity tail).
    context = {"ingestion_run_id": 39, "foo": "bar"}
    result, executed = _run_guard_case(redelivered=False, run_finished=True, context=context)

    assert "ops.pipeline_services.is_run_finished" not in executed
    assert "mtg_stock.data_loader.run_list_id_load" in executed


def test_no_ingestion_run_id_skips_guard_entirely():
    context = {"foo": "bar"}
    result, executed = _run_guard_case(redelivered=True, run_finished=True, context=context)

    assert "ops.pipeline_services.is_run_finished" not in executed
    assert "mtg_stock.data_loader.run_list_id_load" in executed
