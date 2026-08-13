"""Failover JSON-RPC client for BSC."""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.app.core.logging import get_logger

logger = get_logger("execution.rpc")


class RpcUnavailableError(RuntimeError):
    """Raised when every configured RPC endpoint fails."""


class MultiRpcClient:
    def __init__(
        self,
        urls: list[str],
        timeout_seconds: float = 8.0,
        rpc_api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._urls = [url.rstrip("/") for url in urls]
        self._timeout = timeout_seconds
        self._ids = count(1)
        self._rpc_api_key = rpc_api_key
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._urls)

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        if not self._urls:
            raise RpcUnavailableError("No BSC RPC endpoints are configured")
        errors: list[str] = []
        if self._client is not None:
            return await self._call_with_client(self._client, method, params, errors)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._call_with_client(client, method, params, errors)

    async def _call_with_client(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: list[Any] | None,
        errors: list[str],
    ) -> Any:
        for index, url in enumerate(self._urls):
            try:
                response = await client.post(
                    url,
                    headers=self._headers_for_url(url),
                    json={
                        "jsonrpc": "2.0",
                        "id": next(self._ids),
                        "method": method,
                        "params": params or [],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise RuntimeError(str(payload["error"].get("message", "RPC error")))
                logger.info("rpc_call_completed", method=method, endpoint_index=index)
                return payload["result"]
            except (httpx.HTTPError, ValueError, KeyError, RuntimeError) as exc:
                error_type = type(exc).__name__
                errors.append(error_type)
                logger.warning(
                    "rpc_endpoint_failed",
                    method=method,
                    endpoint_index=index,
                    error_type=error_type,
                )
        raise RpcUnavailableError(f"All BSC RPC endpoints failed for {method}: {errors}")

    def _headers_for_url(self, url: str) -> dict[str, str] | None:
        hostname = (urlparse(url).hostname or "").lower()
        if self._rpc_api_key and (hostname == "tatum.io" or hostname.endswith(".tatum.io")):
            return {"x-api-key": self._rpc_api_key}
        return None

    async def wait_for_receipt(
        self,
        transaction_hash: str,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> dict[str, Any] | None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            receipt = await self.call("eth_getTransactionReceipt", [transaction_hash])
            if receipt is not None:
                return receipt
            await asyncio.sleep(poll_seconds)
        return None
