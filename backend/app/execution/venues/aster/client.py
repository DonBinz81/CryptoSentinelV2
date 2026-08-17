"""Aster Pro API V3 client — READ ONLY.

Authentication is NOT the usual API key + HMAC: Aster V3 signs the request with an
Ethereum key (EIP-712). Verified on the official V3 documentation:

    user      account wallet address (our sub-account)
    signer    API wallet address
    nonce     current time in MICROseconds, rejected if off by more than 10s
    signature EIP-712 signature of the urlencoded parameter string

The typed data is fixed: domain "AsterSignTransaction" v1, chainId 1666, zero
verifying contract; the signed message is the parameter string itself.
The signing key is the API wallet's private key, never the sub-account's.

This module exposes only GET endpoints. There is deliberately no method that can
create, modify or cancel an order, or move funds.
"""

from __future__ import annotations

import threading
import time
import urllib.parse
from typing import Any

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

from backend.app.core.logging import get_logger

logger = get_logger("execution.venue.aster")

# Fixed EIP-712 envelope required by Aster V3.
_TYPED_DATA: dict[str, Any] = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Message": [{"name": "msg", "type": "string"}],
    },
    "primaryType": "Message",
    "domain": {
        "name": "AsterSignTransaction",
        "version": "1",
        "chainId": 1666,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    },
    "message": {"msg": ""},
}

_nonce_lock = threading.Lock()
_last_second = 0
_counter = 0


def _next_nonce() -> int:
    """Microsecond nonce, strictly increasing even within the same second."""
    global _last_second, _counter
    with _nonce_lock:
        now = int(time.time())
        if now == _last_second:
            _counter += 1
        else:
            _last_second = now
            _counter = 0
        return now * 1_000_000 + _counter


def short_address(address: str | None) -> str:
    """Addresses may be shown, but abbreviated: 0x1234...abcd."""
    if not address or len(address) < 10:
        return "-"
    return f"{address[:6]}...{address[-4:]}"


class AsterError(RuntimeError):
    """Aster refused or could not serve the request."""

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class AsterClient:
    """Read-only Aster V3 client for the configured sub-account."""

    def __init__(
        self,
        *,
        base_url: str,
        account_address: str,
        api_wallet_address: str,
        api_wallet_private_key: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user = account_address
        self._signer = api_wallet_address
        self._key = api_wallet_private_key
        self._timeout = timeout_seconds

    @property
    def account_address(self) -> str:
        return self._user

    def signer_matches_key(self) -> bool:
        """True when the configured API wallet address matches its private key.

        Catches the most likely configuration mistake — address and key from two
        different API wallets — before any request is signed.
        """
        try:
            derived = Account.from_key(self._key).address
        except Exception:
            return False
        return derived.lower() == (self._signer or "").lower()

    def _sign(self, params: dict[str, Any]) -> str:
        """Sign the urlencoded parameter string with the API wallet key."""
        payload = urllib.parse.urlencode(params)
        typed = {**_TYPED_DATA, "message": {"msg": payload}}
        message = encode_typed_data(full_message=typed)
        signed = Account.sign_message(message, private_key=self._key)
        return signed.signature.hex()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Signed GET. Only read endpoints are ever passed to this method."""
        query = dict(params or {})
        query["user"] = self._user
        query["signer"] = self._signer
        query["nonce"] = str(_next_nonce())
        signature = self._sign(query)
        if not signature.startswith("0x"):
            signature = "0x" + signature
        query["signature"] = signature

        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=query)
        except httpx.TimeoutException as exc:
            raise AsterError("timeout", code="TIMEOUT") from exc
        except httpx.HTTPError as exc:
            # Never include the query string: it carries the signature.
            raise AsterError(f"network error: {type(exc).__name__}", code="NETWORK") from exc

        if response.status_code != 200:
            code, msg = None, response.text[:200]
            try:
                body = response.json()
                code = str(body.get("code")) if isinstance(body, dict) else None
                msg = str(body.get("msg", msg)) if isinstance(body, dict) else msg
            except Exception:
                pass
            raise AsterError(msg, code=code, status=response.status_code)

        return response.json()

    async def public_exchange_info(self) -> Any:
        """Unsigned: proves the endpoint is reachable before testing credentials."""
        url = f"{self._base_url}/fapi/v3/exchangeInfo"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise AsterError("timeout", code="TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise AsterError(f"network error: {type(exc).__name__}", code="NETWORK") from exc
        if response.status_code != 200:
            raise AsterError(response.text[:200], status=response.status_code)
        return response.json()

    # ── Read-only endpoints ────────────────────────────────────────────────
    async def account(self) -> Any:
        return await self._get("/fapi/v3/accountWithJoinMargin")

    async def balance(self) -> Any:
        return await self._get("/fapi/v3/balance")

    async def position_risk(self) -> Any:
        return await self._get("/fapi/v3/positionRisk")

    async def commission_rate(self, symbol: str) -> Any:
        return await self._get("/fapi/v3/commissionRate", {"symbol": symbol})
