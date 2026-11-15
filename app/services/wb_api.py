import asyncio
import logging
import random
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

WB_ENDPOINTS = (
    "https://card.wb.ru/cards/v4/detail",
    "https://card.wb.ru/cards/v2/detail",
)
WB_BASE_PARAMS = {
    "appType": "1",
    "curr": "rub",
    "dest": "-1257786",
    "spp": "30",
}
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_RETRIES = 3
BACKOFF_BASE = 1.5
BATCH_SIZE = 100
TRANSIENT_STATUSES = (403, 429, 500, 502, 503)


class WBApiError(Exception):
    """Raised when the WB API is unreachable or returns garbage after retries."""


@dataclass(frozen=True)
class ProductInfo:
    nm: int
    name: str
    price: int | None


def _extract_products(data: dict) -> list[dict]:
    """v4 returns products at the root, v2 nests them under 'data'."""
    if isinstance(data.get("products"), list):
        return data["products"]
    nested = data.get("data")
    if isinstance(nested, dict) and isinstance(nested.get("products"), list):
        return nested["products"]
    return []


def _extract_price(product: dict) -> int | None:
    sizes = product.get("sizes") or []
    candidates: list[int] = []
    for size in sizes:
        price = (size.get("price") or {}).get("product")
        if price:
            candidates.append(int(price) // 100)
    return min(candidates) if candidates else None


def _parse_products(data: dict) -> dict[int, ProductInfo]:
    out: dict[int, ProductInfo] = {}
    for product in _extract_products(data):
        try:
            nm = int(product["id"])
        except (KeyError, TypeError, ValueError):
            continue
        out[nm] = ProductInfo(
            nm=nm,
            name=str(product.get("name") or "").strip(),
            price=_extract_price(product),
        )
    return out


class WBApiClient:
    """Wildberries card API client.

    Layered protection against WB WAF:
    1. Full browser-like headers (UA, Origin, Referer, Sec-Fetch-*).
    2. Endpoint fallback: v4 -> v2 response formats.
    3. Optional outbound proxy via PROXY_URL; if a proxied request fails,
       the client degrades gracefully and retries without it.
    4. Retries with exponential backoff on transient statuses and network errors.
    """

    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = (proxy_url or "").strip() or None
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=REQUEST_TIMEOUT,
                headers=BROWSER_HEADERS,
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def fetch_products(self, nms: list[int]) -> dict[int, ProductInfo]:
        """Fetch products by article numbers. Raises WBApiError on persistent failure."""
        if not nms:
            return {}

        unique = list(dict.fromkeys(nms))
        result: dict[int, ProductInfo] = {}
        for offset in range(0, len(unique), BATCH_SIZE):
            batch = unique[offset : offset + BATCH_SIZE]
            result.update(await self._fetch_batch(batch))
        return result

    async def _fetch_batch(self, batch: list[int]) -> dict[int, ProductInfo]:
        session = await self._ensure_session()
        nm_param = ";".join(str(nm) for nm in batch)

        proxy_attempts: list[str | None] = [self._proxy_url, None] if self._proxy_url else [None]
        last_error: Exception | None = None
        saw_success = False

        for endpoint in WB_ENDPOINTS:
            params = dict(WB_BASE_PARAMS, nm=nm_param)
            for proxy in proxy_attempts:
                try:
                    data = await self._request_json(session, endpoint, params, proxy)
                    saw_success = True
                    parsed = _parse_products(data if isinstance(data, dict) else {})
                    if parsed:
                        return parsed
                    logger.info("WB %s returned no products for nms=%s", endpoint, batch[:5])
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                    last_error = exc
                    logger.warning(
                        "WB %s via %s failed: %s",
                        endpoint,
                        "proxy" if proxy else "direct",
                        exc,
                    )
                    for attempt in range(1, MAX_RETRIES):
                        delay = BACKOFF_BASE**attempt + random.uniform(0, 0.5)
                        await asyncio.sleep(delay)
                        try:
                            data = await self._request_json(session, endpoint, params, proxy)
                            saw_success = True
                            parsed = _parse_products(data if isinstance(data, dict) else {})
                            if parsed:
                                return parsed
                        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as retry_exc:
                            last_error = retry_exc
                            logger.warning(
                                "WB retry %s/%s via %s failed: %s",
                                attempt,
                                MAX_RETRIES - 1,
                                "proxy" if proxy else "direct",
                                retry_exc,
                            )

        if saw_success:
            return {}
        logger.error("WB API failed on all endpoints: %s", last_error)
        raise WBApiError(str(last_error))

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        params: dict,
        proxy: str | None,
    ) -> dict:
        async with session.get(endpoint, params=params, proxy=proxy) as resp:
            if resp.status in TRANSIENT_STATUSES:
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"WB transient status {resp.status}",
                )
            if resp.status != 200:
                logger.warning("WB API HTTP %s from %s", resp.status, endpoint)
                return {}
            return await resp.json(content_type=None)

    async def get_price(self, nm: int) -> ProductInfo | None:
        products = await self.fetch_products([nm])
        return products.get(nm)
