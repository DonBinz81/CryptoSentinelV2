"""Trust Wallet Agent Kit CLI bridge for spot execution."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.execution.models import GasDecision

logger = get_logger("execution.spot_twak")


class TwakError(RuntimeError):
    """Raised when the official TWAK CLI rejects an operation."""

    def __init__(
        self,
        operation: str,
        return_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        if return_code is None or detail is None:
            super().__init__(operation)
            self.operation = "policy"
            self.return_code = return_code
            self.detail = operation
            return
        super().__init__(f"TWAK {operation} failed ({return_code}): {detail}")
        self.operation = operation
        self.return_code = return_code
        self.detail = detail


@dataclass(frozen=True)
class TwakCommandResult:
    payload: dict[str, Any]
    return_code: int


class TwakClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.twak_cli_path
            and self._settings.twak_access_id
            and self._settings.twak_hmac_secret
        )

    async def quote(
        self,
        *,
        amount_atomic: int,
        from_asset: str,
        to_asset: str,
        wallet_address: str,
        from_domain: str,
        to_domain: str,
        slippage_pct: Decimal,
    ) -> dict[str, Any]:
        if amount_atomic <= 0:
            raise TwakError("Quote amount must be positive")
        return await self._amber_request(
            "POST",
            "/amber-api/v1/route",
            body={
                "fromAsset": from_asset,
                "fromAddress": wallet_address,
                "fromDomain": from_domain,
                "amount": str(amount_atomic),
                "toAsset": to_asset,
                "toAddress": wallet_address,
                "toDomain": to_domain,
                "slippage": str(slippage_pct),
                "sortBy": "outcome",
                "contractCall": False,
                "thorchain": {"streaming": True},
            },
        )

    async def domains(self) -> dict[str, Any]:
        return await self._amber_request("GET", "/amber-api/v1/domains")

    async def providers(self) -> dict[str, Any]:
        return await self._amber_request("GET", "/amber-api/v1/providers")

    async def route_step(self, step_id: str) -> dict[str, Any]:
        if not step_id:
            raise TwakError("Amber route step ID is required")
        return await self._amber_request(
            "POST",
            "/amber-api/v1/route/step",
            body={"stepId": step_id},
        )

    async def wallet_address(self, *, wallet_password: str) -> dict[str, Any]:
        return (
            await self._run(
                [
                    "wallet",
                    "address",
                    "--chain",
                    self._settings.twak_chain,
                    "--json",
                ],
                wallet_password=wallet_password,
            )
        ).payload

    async def send_token(
        self,
        *,
        to_address: str,
        amount: str,
        token: str,
        wallet_password: str,
    ) -> dict[str, Any]:
        """Invia token o BNB nativi a un indirizzo tramite TWAK CLI."""
        result = await self._run(
            [
                "send",
                "--to",
                to_address,
                "--amount",
                amount,
                "--token",
                token,
                "--chain",
                self._settings.twak_chain,
                "--yes",
                "--json",
            ],
            wallet_password=wallet_password,
        )
        return result.payload

    async def execute_swap(
        self,
        *,
        amount_atomic: int,
        from_asset: str,
        to_asset: str,
        wallet_address: str,
        from_domain: str,
        to_domain: str,
        slippage_pct: Decimal,
        gas_decision: GasDecision,
    ) -> dict[str, Any]:
        if self._settings.bsc_network != "testnet":
            raise TwakError("Step 4 spot execution is restricted to BSC testnet")
        if not gas_decision.allowed:
            raise TwakError(f"Spot execution blocked by gas guard: {gas_decision.reason}")
        if slippage_pct > Decimal(str(self._settings.risk_max_slippage_pct)):
            raise TwakError("Requested slippage exceeds the configured hard limit")
        quote = await self.quote(
            amount_atomic=amount_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=wallet_address,
            from_domain=from_domain,
            to_domain=to_domain,
            slippage_pct=slippage_pct,
        )
        routes = quote.get("routes") or []
        if not routes:
            raise TwakError("Amber API returned no swap routes")
        route = routes[0]
        steps = route.get("steps") or []
        providers = " ".join(
            str(step.get("provider", {}).get("name", "")) for step in steps
        ).lower()
        if "pancake" not in providers:
            raise TwakError("TWAK quote is not routed through an allowed PancakeSwap provider")
        prepared_steps = [await self.route_step(str(step["id"])) for step in steps]
        return {
            "status": "prepared",
            "route": route,
            "transactions": prepared_steps,
            "requires_wallet_signature": True,
        }

    async def _amber_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._settings.twak_access_id or not self._settings.twak_hmac_secret:
            raise TwakError("TWAK REST credentials are not configured")
        query_string = urlencode(sorted((query or {}).items()))
        url = f"{self._settings.twak_api_base_url.rstrip('/')}{path}"
        if query_string:
            url = f"{url}?{query_string}"
        try:
            headers = _sign_amber_request(
                method,
                path,
                query_string,
                self._settings.twak_access_id,
                self._settings.twak_hmac_secret,
            )
            if self._http_client is not None:
                response = await self._http_client.request(
                    method,
                    url,
                    headers=headers,
                    json=body,
                )
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=body,
                    )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _safe_http_error_detail(exc.response)
            logger.error(
                "twak_rest_request_failed",
                operation=path,
                status_code=exc.response.status_code,
                error_detail=detail,
            )
            raise TwakError(path, exc.response.status_code, detail) from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                "twak_rest_transport_failed",
                operation=path,
                error_type=type(exc).__name__,
            )
            raise TwakError(path, 0, type(exc).__name__) from exc
        logger.info("twak_rest_request_completed", operation=path)
        return payload

    async def competition_status(self, *, wallet_password: str) -> dict[str, Any]:
        return (
            await self._run(
                ["compete", "status", "--json"],
                wallet_password=wallet_password,
            )
        ).payload

    async def competition_register(self, *, wallet_password: str) -> dict[str, Any]:
        if self._settings.bsc_network != "testnet":
            logger.warning("competition_registration_targets_bsc_mainnet_contract")
        return (
            await self._run(
                ["compete", "register", "--json"],
                wallet_password=wallet_password,
            )
        ).payload

    async def x402_request(
        self,
        url: str,
        *,
        max_payment_atomic: int,
        wallet_password: str,
    ) -> dict[str, Any]:
        return (
            await self._run(
                [
                    "x402",
                    "request",
                    url,
                    "--max-payment",
                    str(max_payment_atomic),
                    "--prefer-network",
                    "bsc",
                    "--prefer-method",
                    "eip3009",
                    "--yes",
                    "--json",
                ],
                wallet_password=wallet_password,
            )
        ).payload

    async def _run(
        self,
        arguments: list[str],
        *,
        wallet_password: str | None = None,
    ) -> TwakCommandResult:
        inherited_names = (
            "APPDATA",
            "HOME",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        )
        env = {name: os.environ[name] for name in inherited_names if name in os.environ}
        if self._settings.twak_access_id:
            env["TWAK_ACCESS_ID"] = self._settings.twak_access_id
        if self._settings.twak_hmac_secret:
            env["TWAK_HMAC_SECRET"] = self._settings.twak_hmac_secret
        if wallet_password:
            env["TWAK_WALLET_PASSWORD"] = wallet_password
        executable = _resolve_cli_path(self._settings.twak_cli_path, env)
        command = [executable, *arguments]
        if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
            command = [env.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", executable, *arguments]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            detail = (
                "TWAK CLI executable was not found. Install @trustwallet/cli globally "
                "or set twak.cli_path to the absolute twak.cmd path."
            )
            logger.error(
                "twak_cli_not_found",
                configured_path=self._settings.twak_cli_path,
                chain=self._settings.twak_chain,
            )
            raise TwakError("cli", 127, detail) from exc
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            operation = " ".join(arguments[:2]) if len(arguments) > 1 else arguments[0]
            detail = _safe_error_detail(stderr, stdout)
            logger.error(
                "twak_command_failed",
                operation=operation,
                return_code=process.returncode,
                error_detail=detail,
                chain=self._settings.twak_chain,
                rpc_source="twak_internal",
            )
            raise TwakError(operation, process.returncode, detail)
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TwakError("TWAK returned a non-JSON response") from exc
        logger.info("twak_command_completed", operation=arguments[0])
        return TwakCommandResult(payload=payload, return_code=process.returncode)


def _safe_error_detail(stderr: bytes, stdout: bytes) -> str:
    """Return a bounded CLI error without credentials, URLs, or key material."""

    raw = stderr.decode("utf-8", errors="replace").strip()
    if not raw:
        raw = stdout.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(raw)
        raw = str(payload.get("message") or payload.get("error") or payload.get("code") or raw)
    except (json.JSONDecodeError, AttributeError):
        pass
    raw = re.sub(r"https?://\S+", "[redacted-url]", raw)
    raw = re.sub(r"\b0x[a-fA-F0-9]{64}\b", "[redacted-hex]", raw)
    raw = re.sub(
        r"(?i)(password|passphrase|private[_ -]?key|hmac|access[_ -]?id|token)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        raw,
    )
    single_line = " ".join(raw.split())
    return single_line[:500] or "no diagnostic detail returned"


def _sort_query(query: str) -> str:
    """Replicate TWAK sortQueryRaw: sort query params by key, passthrough empty."""
    if not query:
        return query
    parts = [p for p in query.split("&") if p]
    parts.sort(key=lambda x: x.split("=")[0])
    return "&".join(parts)


def _sign_amber_request(
    method: str,
    path: str,
    query: str,
    access_id: str,
    hmac_secret: str,
    *,
    nonce: str | None = None,
    request_date: str | None = None,
) -> dict[str, str]:
    """Sign a Trust Wallet Amber API request.

    Signing format extracted from @trustwallet/cli dist/index.js signRequest():
        plaintext = [METHOD, path, sortedQuery, accessId, nonce, date].join(";")
        date = new Date().toUTCString()  →  "Mon, 16 Jun 2026 12:34:56 GMT"
        Authorization: "HMAC-SHA256 Signature=<base64(HMAC-SHA256(secret, plaintext))>"
    """
    signed_nonce = nonce or str(uuid4())
    signed_date = request_date or datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
    sorted_query = _sort_query(query)
    plaintext = ";".join([method.upper(), path, sorted_query, access_id, signed_nonce, signed_date])
    signature = base64.b64encode(
        hmac.new(
            hmac_secret.encode("utf-8"),
            plaintext.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    return {
        "X-TW-CREDENTIAL": access_id,
        "X-TW-NONCE": signed_nonce,
        "X-TW-DATE": signed_date,
        "Authorization": f"HMAC-SHA256 Signature={signature}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 AgentKit",
        "X-Origin": "Trust/2.15.0 AgentKit",
    }


def _safe_http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        raw = str(payload.get("message") or payload.get("error") or payload.get("code"))
    except (ValueError, AttributeError):
        raw = response.text
    raw = re.sub(r"https?://\S+", "[redacted-url]", raw)
    return " ".join(raw.split())[:500] or response.reason_phrase


def _resolve_cli_path(configured_path: str, env: dict[str, str]) -> str:
    """Resolve npm launchers, including Windows .cmd wrappers."""

    resolved = shutil.which(configured_path, path=env.get("PATH"))
    return resolved or configured_path
