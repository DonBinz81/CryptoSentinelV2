"""Shared HTTP provider plumbing with cache, throttling, and credit accounting."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.data.market_data.base import ProviderError
from backend.app.core.logging import get_logger
from backend.app.data.market_data.cache import TTLCache
from backend.app.data.market_data.rate_limit import AsyncRateLimiter


logger = get_logger("market_data.http")

_LOGGABLE_PARAM_KEYS = {
    "convert",
    "id",
    "ids",
    "interval",
    "limit",
    "page",
    "start",
    "symbol",
    "time_end",
    "time_period",
    "time_start",
}


def _params_summary(params: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "param_keys": sorted(
            key for key, value in params.items() if value is not None and key in _LOGGABLE_PARAM_KEYS
        )
    }
    for key in ("start", "limit", "page", "convert", "time_period", "interval"):
        if params.get(key) is not None:
            summary[key] = params[key]
    for key in ("id", "ids", "symbol"):
        value = params.get(key)
        if value:
            summary[f"{key}_count"] = len(str(value).split(","))
    return summary


class CachedHttpProvider:
    """Base helper for provider adapters."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        requests_per_minute: int,
        cache_ttl_seconds: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = AsyncRateLimiter(requests_per_minute)
        self.cache = TTLCache(cache_ttl_seconds)
        self._client = client
        self._request_locks: dict[str, asyncio.Lock] = {}
        self.credits_used = 0
        self.requests_made = 0

    @staticmethod
    def _cache_key(path: str, params: Mapping[str, Any]) -> str:
        normalized = sorted((key, str(value)) for key, value in params.items() if value is not None)
        return f"{path}?{urlencode(normalized)}"

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        estimated_credits: int = 0,
        cache_ttl_seconds: int | None = None,
    ) -> Any:
        key = self._cache_key(path, params)
        cached = self.cache.get(key)
        if cached is not None:
            logger.info("provider_cache_hit", endpoint=path, **_params_summary(params))
            return cached

        request_lock = self._request_locks.setdefault(key, asyncio.Lock())
        async with request_lock:
            cached = self.cache.get(key)
            if cached is not None:
                logger.info("provider_cache_wait_hit", endpoint=path, **_params_summary(params))
                return cached
            return await self._perform_request(
                path,
                params=params,
                headers=headers,
                estimated_credits=estimated_credits,
                cache_ttl_seconds=cache_ttl_seconds,
                cache_key=key,
            )

    async def _perform_request(
        self,
        path: str,
        *,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None,
        estimated_credits: int,
        cache_ttl_seconds: int | None,
        cache_key: str,
    ) -> Any:
        started = perf_counter()
        logger.info("provider_request_started", endpoint=path, **_params_summary(params))
        await self.rate_limiter.acquire()
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning(
                "provider_request_failed",
                endpoint=path,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
                **_params_summary(params),
            )
            raise ProviderError(f"Provider request failed for {path}: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        self.requests_made += 1
        status = payload.get("status", {}) if isinstance(payload, dict) else {}
        self.credits_used += int(status.get("credit_count") or estimated_credits)
        self.cache.set(cache_key, payload, cache_ttl_seconds)
        data = payload.get("data") if isinstance(payload, dict) else None
        item_count = len(payload) if isinstance(payload, list) else len(data) if isinstance(data, list) else None
        logger.info(
            "provider_request_completed",
            endpoint=path,
            status_code=response.status_code,
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
            item_count=item_count,
            credit_count=int(status.get("credit_count") or estimated_credits),
            **_params_summary(params),
        )
        return payload
