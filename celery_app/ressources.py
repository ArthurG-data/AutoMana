from backend.core.database import close_async_pool, init_async_pool
from backend.core.service_manager import ServiceManager
from celery_app.state import CeleryAppState
from backend.core.QueryExecutor import AsyncQueryExecutor
import asyncio

_state: CeleryAppState | None = None

def get_state() -> CeleryAppState:
    global _state
    if _state is None:
        _state = CeleryAppState()
    return _state

def init_backend_runtime() -> None:
    app_state = get_state()
    if app_state.initialized:
        return

    # Single event loop per worker process
    app_state.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(app_state.loop)

    async def _init():
        app_state.async_db_pool = await init_async_pool(app_state.settings)
        await ServiceManager.initialize(
            app_state.async_db_pool,
            query_executor=AsyncQueryExecutor(),
        )

    app_state.loop.run_until_complete(_init())
    app_state.mark_initialized()

def shutdown_backend_runtime() -> None:
    state = get_state()
    if not state.initialized:
        return

    if state.loop and state.async_db_pool:
        async def _shutdown():
            await close_async_pool(state.async_db_pool)
            state.async_db_pool = None
        state.loop.run_until_complete(_shutdown())

    state.loop = None
    state.initialized = False