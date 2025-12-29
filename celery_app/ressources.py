from contextlib import contextmanager
from backend.core.database import close_async_pool, init_async_pool
from backend.core.service_manager import ServiceManager
from celery_app.async_runner import AsyncRunner
from celery_app.state import CeleryAppState
from backend.core.QueryExecutor import AsyncQueryExecutor
_state: CeleryAppState | None = None

def get_state() -> CeleryAppState:
    global _state
    if _state is None:
        _state = CeleryAppState()
    return _state

def init_backend_runtime() -> None:
    """Called once per Celery worker process."""
    app_state : CeleryAppState = get_state()
    if app_state.initialized:
        return
    
    app_state.async_runner = AsyncRunner()
    # init async services inside the runner
    async def _init():
        app_state.async_db_pool = await init_async_pool(app_state.settings)
        await ServiceManager.initialize(
            app_state.async_db_pool,  # or async pool if you have one
            query_executor=AsyncQueryExecutor(),  # your real executor
        )

    app_state.async_runner.run(_init())
    app_state.mark_initialized()

def shutdown_backend_runtime() -> None:
    state = get_state()
    if not state.initialized:
        return

    async def _shutdown():
        state = get_state()
    if not state.initialized:
        return

    # Close pool on the same loop it was created on
    if state.async_runner:
        async def _shutdown():
            if state.async_db_pool is not None:
                await close_async_pool(state.async_db_pool)
                state.async_db_pool = None

        state.async_runner.run(_shutdown())
        state.async_runner.stop()
        state.async_runner = None

    state.initialized = False