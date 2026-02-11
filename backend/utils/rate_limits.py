import asyncio
import time

class AsyncTokenBucket:
    def __init__(self, rate_per_sec: float, capacity: int):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.updated_at

                # refill
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed * self.rate
                )
                self.updated_at = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                wait_s = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_s)