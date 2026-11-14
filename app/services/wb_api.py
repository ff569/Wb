import asyncio
import logging
import random
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

WB_CARD_URL = "https://card.wb.ru/cards/v4/detail"
WB_PARAMS = {
    "appType": "1",
    "curr": "rub",
    "dest": "-1257786",
    "spp": "30",
}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_RETRIES = 3
BACKOFF_BASE = 1.5
BATCH_SIZE = 100


class WBApiError(Exception):
    """Raised when the WB API is unreachable or returns garbage after retries."""


@dataclass(frozen=True)
class ProductInfo:
    nm: int
    name: str
    price: int | None


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
    for product in data.get("products") or []:
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
    """Wildberries card API client with timeouts, retries and batch fetching."""

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WBDetector/1.0)"},
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()

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
        params = dict(WB_PARAMS, nm=";".join(str(nm) for nm in batch))
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.get(WB_CARD_URL, params=params) as resp:
                    if resp.status in (429, 500, 502, 503):
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message="WB API transient error",
                        )
                    if resp.status != 200:
                        logger.warning("WB API HTTP %s for nms=%s", resp.status, batch[:5])
                        return {}
                    data = await resp.json()
                    return _parse_products(data if isinstance(data, dict) else {})
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE**attempt + random.uniform(0, 0.5)
                    logger.warning(
                        "WB API attempt %s/%s failed (%s), retrying in %.1fs",
                        attempt,
                        MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        logger.error("WB API failed after %s attempts: %s", MAX_RETRIES, last_error)
        raise WBApiError(str(last_error))

    async def get_price(self, nm: int) -> ProductInfo | None:
        products = await self.fetch_products([nm])
        return products.get(nm)
