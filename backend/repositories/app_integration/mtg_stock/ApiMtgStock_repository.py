import asyncio, httpx, hashlib, json, random
from asyncio.log import logger
from typing import Any, Dict, List, Optional, Union
from backend.exceptions.repository_layer_exceptions.api_errors import ExternalApiConnectionError
from backend.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
from backend.repositories.abstract_repositories.AbstractAPIRepository import  RepositoryError
from backend.utils.rate_limits import AsyncTokenBucket

class ApiMtgStockRepository(BaseApiClient):
    def __init__(self
                 , timeout: Optional[int] = 30
                 , rate_per_sec: float = 1.0
                 , burst: int = 1
                 , delay_base: Optional[int] = 180
                 , max_attempts: Optional[int] = 6
                 , max_concurrency: int=1
                 , etag_ttl: int = 3600
                 , environment: str | None = None
                 , **kwargs):
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
                "Gecko/20100101 Firefox/121.0"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            }


        self.DELAY_BASE = delay_base
        self.MAX_ATTEMPTS = max_attempts
        self.SEM = asyncio.Semaphore(max_concurrency)

        # persistent client used when entering context
        self.client: Optional[httpx.AsyncClient] = None

        super().__init__(timeout=timeout)
        # ETag cache: url -> {etag, body, expires_at}
        self._etag_cache: Dict[str, Dict[str, Any]] = {}
        self._etag_ttl = etag_ttl
        self.rate_limiter = AsyncTokenBucket(rate_per_sec=rate_per_sec, capacity=burst)

    def name(self) -> str:
        """Return the name of the repository"""
        return "API_mtgStockRepository"
    
    def default_headers(self) -> Dict[str, str]:
        return dict(self._headers)
    
    def _get_cached(self, url: str) -> Optional[bytes]:
        entry = self._etag_cache.get(url)
        if not entry:
            return None
        if entry["expires_at"] < asyncio.get_event_loop().time():
            self._etag_cache.pop(url, None)
            return None
        return entry["body"]

    def _store_cache(self, url: str, body: bytes, etag: Optional[str]):
        self._etag_cache[url] = {
            "etag": etag,
            "body": body,
            "expires_at": asyncio.get_event_loop().time() + self._etag_ttl,
        }

    def _get_base_url(self) -> str:
        return "https://api.mtgstocks.com"

    async def __aenter__(self):
        """Initialize the persistent HTTP client when entering the context."""
        self.client = httpx.AsyncClient(http2=True, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Close the persistent HTTP client when exiting the context."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _get_bytes_or_none(self, endpoint: str) -> Optional[bytes]:
        # We need 404 => None, so we call send() once to inspect status,
        # then parse content consistently.
        logger.debug("GET %s", endpoint)
        resp = await self.send("GET", endpoint)
        logger.debug("GET %s -> %s", endpoint, resp.status_code)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        logger.debug("GET %s len=%d", endpoint, len(resp.content))
        return resp.content
    
    async def request_bytes(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Optional[bytes]:
        """
        MTGStocks-specific request wrapper:
        - returns bytes (resp.content)
        - 404 -> None
        - 429 -> backoff + retry
        - uses persistent client if available
        """
        backoff = self.DELAY_BASE
        url = self.get_full_url(endpoint)

        merged_headers = dict(self._headers)
        if headers:
            merged_headers.update(headers)

        t = timeout or self.timeout

        for attempt in range(self.MAX_ATTEMPTS):
            try:
                if self.client is None:
                    # Fallback: create a short-lived client if not used in a context manager
                    async with httpx.AsyncClient(http2=True, timeout=t) as client:
                        resp = await client.request(method.upper(), url, params=params, headers=merged_headers)
                else:
                    resp = await self.client.request(method.upper(), url, params=params, headers=merged_headers)

                if resp.status_code == 404:
                    logger.warning("MTGStocks resource not found: %s", url)
                    return None

                if resp.status_code == 429:
                    logger.warning("MTGStocks rate limited (429): %s. Sleeping %ss", url, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue

                resp.raise_for_status()
                return resp.content

            except httpx.HTTPStatusError as e:
                # Let the base mapping turn this into a RepositoryError (generic),
                # OR override map_http_error in a subclass if you want MTGStocks-specific exceptions.
                raise self.map_http_error(e)
            
            except httpx.RequestError as e:
                # Network errors -> repository-level error
                raise ExternalApiConnectionError(
                    message=f"Failed to connect to {self.name}: {e}",
                    error_code="EXTERNAL_API_CONNECTION_ERROR",
                    error_data={"url": url},
                    source_exception=e,
                ) from e

            except RepositoryError:
                raise

            except Exception as e:
                # last attempt => raise; otherwise retry with backoff
                if attempt >= self.MAX_ATTEMPTS - 1:
                    raise
                logger.warning("Unexpected error calling MTGStocks (%s). Retrying in %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

        return None
    
    async def fetch_card_prices(self, card_id: int):
        return await self._get_bytes_or_none( f"/prints/{card_id}/prices")
    
    async def fetch_card_details(self, card_id: int):
        return await self._get_bytes_or_none(f"/prints/{card_id}")
    
    async def send(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
    ) -> httpx.Response:
        url = self.get_full_url(endpoint)
        backoff = self.DELAY_BASE

        for attempt in range(1, self.MAX_ATTEMPTS + 1):

            # 🔒 Rate limit before every attempt
            await self.rate_limiter.acquire()
            await asyncio.sleep(random.uniform(0.3, 1.2))
            hdrs = dict(headers or {})

            # 🔁 ETag support
            cache_entry = self._etag_cache.get(url)
            if cache_entry and cache_entry.get("etag"):
                hdrs["If-None-Match"] = cache_entry["etag"]

            resp = await super().send(
                method,
                endpoint,
                params=params,
                headers=hdrs,
                json=json,
                data=data,
                timeout=timeout,
            )

            # 🟢 304 Not Modified → reuse cached body
            if resp.status_code == 304:
                cached = self._get_cached(url)
                if cached is not None:
                    logger.debug("ETag hit for %s", url)
                    return httpx.Response(
                        status_code=200,
                        content=cached,
                        headers=resp.headers,
                        request=resp.request,
                    )

            # 🔁 Rate limited
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else backoff
                except ValueError:
                    wait = backoff

                jitter = wait * (0.7 + random.random() * 0.6)
                logger.warning(
                    "MTGStocks 429. Retry in %.2fs (attempt %d/%d)",
                    jitter, attempt, self.MAX_ATTEMPTS
                )
                await asyncio.sleep(jitter)
                backoff = min(backoff * 2, 30)
                continue

            # ❌ Not found → return immediately
            if resp.status_code == 404:
                return resp

            # ✅ Success → store ETag if present
            if resp.status_code < 400:
                etag = resp.headers.get("ETag")
                if etag:
                    self._store_cache(url, resp.content, etag)
                return resp

            return resp

        return resp
    

    async def fetch_card_price_data_batch(self, card_ids: List[int]):
        logger.debug(f"Fetching price data for {len(card_ids)} cards")
        tasks = [self.fetch_card_prices(card_id) for card_id in card_ids]
        result =  await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"Completed fetching price data for {len(card_ids)} cards")
        processed: List[Dict[str, Any]] = []
        item_ok = 0
        item_failed = 0
        bytes_processed = 0
        for cid, r in zip(card_ids, result):
           
            if isinstance(r, Exception):
                processed.append({"card_id": cid, "error": str(r)})
                item_failed += 1
            elif r is None:
                processed.append({"card_id": cid, "error": "Data not found"})
                item_failed += 1
            else:
                processed.append({"card_id": cid, "prices": r})
                item_ok += 1
                bytes_processed +=  len(r)
        return {"data": processed
                , "items_ok": item_ok
                , "items_failed": item_failed
                , "bytes_processed": bytes_processed}
    
    async def fetch_card_data_batches(self, card_ids: List[int]) -> List[Dict[str, Any]]:
        async def fetch_data(card_id: int) -> Dict[str, Any]:
            try:
                details, prices = await asyncio.gather(self.fetch_card_details(card_id)
                                                        , self.fetch_card_prices(card_id))

                if details is None and prices is None:
                    return {"card_id": card_id, "error": "Data not found"}

                return {"card_id": card_id, "data": {"details": details, "prices": prices}}

            except RepositoryError as e:
                return {"card_id": card_id, "error": str(e), "error_data": getattr(e, "error_data", {})}
            except Exception as e:
                return {"card_id": card_id, "error": str(e)}

        results = await asyncio.gather(*(fetch_data(cid) for cid in card_ids), return_exceptions=True)

        processed: List[Dict[str, Any]] = []
        item_ok = 0
        item_failed = 0
        bytes_processed = 0
        for cid, r in zip(card_ids, results):
            if r.get("error"):
                processed.append(r)
                item_failed += 1
            else:
                processed.append(r)
                item_ok += 1
                data = r.get("data", {})
                bytes_processed += len(data.get("details", b"")) + len(data.get("prices", b""))
        return {"data": processed, "items_ok": item_ok, "items_failed": item_failed, "bytes_processed": bytes_processed}
