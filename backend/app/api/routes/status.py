"""Base API status routes."""

from typing import Any

from fastapi import APIRouter

from backend.app.api.dependencies import ReadAccessDep, SettingsDep

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status")
async def status(settings: SettingsDep, _: ReadAccessDep) -> dict[str, Any]:
    """Return authenticated backend status and conservative runtime defaults."""

    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "default_user_id": str(settings.default_user_id),
        "mode": {
            "agent": settings.agent_mode,
            "markets_enabled": settings.markets_enabled,
            "execution": settings.execution_mode,
        },
        "risk_defaults": {
            "daily_loss_limit_pct": settings.risk_daily_loss_limit_pct,
            "max_drawdown_pct": settings.risk_max_drawdown_pct,
            "min_portfolio_value_usd": settings.min_portfolio_value_usd,
        },
        "market_data_provider": settings.market_data_provider,
        "step": "step_3_multi_provider_market_data",
    }
