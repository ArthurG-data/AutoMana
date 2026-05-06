import pytest
from fastapi import Request
from starlette.responses import Response
from automana.api.middleware.metrics_middleware import MetricsMiddleware
from automana.core.metrics.buffer import MetricsBuffer


@pytest.fixture
def clear_buffer():
    MetricsBuffer.get_instance().clear()
    yield
    MetricsBuffer.get_instance().clear()


@pytest.mark.asyncio
async def test_metrics_middleware_captures_request(clear_buffer):
    """Middleware should capture request timing and cache hit status."""
    buffer = MetricsBuffer.get_instance()
    middleware = MetricsMiddleware(app=None)

    # Mock a simple next() coroutine
    async def mock_next(request):
        response = Response(status_code=200)
        return response

    request = Request(scope={
        'type': 'http',
        'method': 'GET',
        'path': '/api/test',
        'query_string': b'',
        'headers': [],
    })
    request.state.cache_hit = True

    response = await middleware.dispatch(request, mock_next)

    # Verify buffer captured the metric
    api_buf, _ = buffer.flush()
    assert len(api_buf) == 1

    # Extract the bucket key
    bucket_key = list(api_buf.keys())[0]
    hour_key, endpoint, status = bucket_key
    assert endpoint == '/api/test'
    assert status == 200

    bucket = api_buf[bucket_key]
    assert bucket.request_count == 1
    assert bucket.cache_hit_count == 1
