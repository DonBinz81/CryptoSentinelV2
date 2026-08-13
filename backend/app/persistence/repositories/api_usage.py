"""Repository for Claude API usage tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.api_usage import ClaudeApiUsage

# Prezzi per milione di token (claude-sonnet-4-x)
_INPUT_COST_PER_MTOK = 3.0
_OUTPUT_COST_PER_MTOK = 15.0


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Stima costo in USD. Usa prezzi Sonnet come default."""
    if "opus" in model:
        inp, out = 15.0, 75.0
    elif "haiku" in model:
        inp, out = 0.80, 4.0
    else:  # sonnet default
        inp, out = _INPUT_COST_PER_MTOK, _OUTPUT_COST_PER_MTOK
    return (input_tokens * inp + output_tokens * out) / 1_000_000


class ApiUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        cost = estimate_cost(model, input_tokens, output_tokens)
        row = ClaudeApiUsage(
            timestamp_utc=datetime.now(timezone.utc),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self._session.add(row)
        await self._session.flush()

    async def summary(self) -> dict:
        result = await self._session.execute(
            select(
                func.count(ClaudeApiUsage.id),
                func.sum(ClaudeApiUsage.input_tokens),
                func.sum(ClaudeApiUsage.output_tokens),
                func.sum(ClaudeApiUsage.cost_usd),
            )
        )
        row = result.one()
        return {
            "call_count": int(row[0] or 0),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "total_cost_usd": float(row[3] or 0.0),
        }
