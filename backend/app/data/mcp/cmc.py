"""CoinMarketCap MCP connection metadata for agent clients."""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.core.config import Settings


class CMCMPConnection(BaseModel):
    """Non-secret MCP connection status."""

    enabled: bool
    configured: bool
    server_url: str
    auth_header: str = "X-CMC-MCP-API-KEY"


def cmc_mcp_connection(settings: Settings) -> CMCMPConnection:
    """Describe the official CMC MCP connection without exposing credentials."""

    return CMCMPConnection(
        enabled=settings.cmc_mcp_enabled,
        configured=bool(settings.cmc_api_key),
        server_url=settings.cmc_mcp_server_url or "https://mcp.coinmarketcap.com/mcp",
    )
