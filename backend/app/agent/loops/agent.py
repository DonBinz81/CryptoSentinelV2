"""Fast and slow agent runtime loops."""

from __future__ import annotations

import asyncio

from backend.app.agent.service import run_agent_fast_tick, run_agent_slow_tick
from backend.app.core.config import Settings
from backend.app.core.logging import get_logger

logger = get_logger("agent.loops")


async def fast_loop(settings: Settings) -> None:
    """Near real-time position-management loop."""

    interval = max(5, min(settings.heartbeat_interval_seconds, 30))
    logger.info("agent_fast_loop_started", interval_s=interval)
    while True:
        try:
            await run_agent_fast_tick()
        except Exception as exc:
            logger.warning("agent_fast_loop_error", error=str(exc))
        await asyncio.sleep(interval)


async def slow_loop(settings: Settings) -> None:
    """Slow scanning/decision loop, aligned to 5m-candle cadence."""

    interval = max(60, settings.perp_volume_profile_candle_minutes * 60)
    logger.info("agent_slow_loop_started", interval_s=interval)
    while True:
        try:
            await run_agent_slow_tick()
        except Exception as exc:
            logger.warning("agent_slow_loop_error", error=str(exc))
        await asyncio.sleep(interval)
