"""Tests for the live-chart timeout and failure logging fix (NOTE/93 parte 2).

_build_live_chart used to fail silently: a 1.5s network timeout (too tight
for a real external call under production load, verified directly against
the running server) plus zero logging on failure meant a broken chart looked
identical to a working one from the outside -- no error, just a missing or
stale rendering. This checks the widened budget and that a failure now
leaves a trace.

Two layers matter here, not one: `_build_live_chart`'s own try/except, AND
the OUTER `asyncio.wait_for` wrapper in `_live_chart_if_open`. A timeout that
fires at the outer layer cancels the inner coroutine with CancelledError --
which does NOT subclass Exception since Python 3.8, so the inner function's
own except never runs and never logs. Only the outer wrapper sees it. Missed
this on the first pass of the fix: verifying the deploy against the real
server, curl calls kept coming back "chart: null" instantly with zero log
lines even from the inner logging just added -- exactly the symptom of a
failure happening one layer higher than where the log was.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.api.routes import views as view_routes
from backend.tests.unit.test_agent_step6 import settings


def _position(**overrides):
    base = dict(
        asset="BNB", side="short", status="open",
        entry_price=Decimal("700"), current_price=Decimal("705"),
        stop_loss=Decimal("710"), initial_stop_loss=Decimal("708.48"),
        take_profit_1=Decimal("697"), take_profit_2=Decimal("683"),
        liquidation_price=None,
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestTimeoutBudget:
    def test_feed_timeout_is_realistic_for_an_external_call(self):
        # NOTE/93: era 1.5s, verificato fallire quasi sempre sotto carico
        # reale mentre la stessa chiamata isolata funzionava sempre.
        assert view_routes.TRADE_DETAIL_FEED_TIMEOUT_SECONDS >= 5.0

    def test_outer_chart_budget_leaves_room_for_more_than_one_attempt(self):
        # _build_live_chart puo' tentare 2+ fetch in sequenza (con/senza
        # start_time, piu' l'eventuale fallback CEX): il budget esterno deve
        # coprire piu' di un tentativo al nuovo timeout, non tagliarlo a meta'.
        assert view_routes.TRADE_DETAIL_CHART_TIMEOUT_SECONDS >= 2 * view_routes.TRADE_DETAIL_FEED_TIMEOUT_SECONDS


@pytest.mark.asyncio
class TestFailureIsLogged:
    async def test_logs_a_warning_when_the_feed_raises_on_every_attempt(self):
        class _AlwaysBrokenFeed:
            def __init__(self, timeout_seconds=None):
                pass

            async def fetch(self, **kwargs):
                raise RuntimeError("network down")

        with patch.object(view_routes, "logger") as mock_logger:
            with patch(
                "backend.app.agent.signals.perp.binance_klines.BinanceKlineFeed",
                _AlwaysBrokenFeed,
            ):
                chart = await view_routes._build_live_chart(_position(), "perp", settings=settings())

        assert chart is None
        assert mock_logger.warning.called
        event_names = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert "live_chart_build_failed" in event_names

    async def test_logs_a_warning_when_the_feed_returns_no_candles(self):
        class _EmptyFeed:
            def __init__(self, timeout_seconds=None):
                pass

            async def fetch(self, **kwargs):
                return []

        with patch.object(view_routes, "logger") as mock_logger:
            with patch(
                "backend.app.agent.signals.perp.binance_klines.BinanceKlineFeed",
                _EmptyFeed,
            ):
                chart = await view_routes._build_live_chart(_position(), "perp", settings=settings())

        assert chart is None
        assert mock_logger.warning.called
        event_names = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert "live_chart_no_candles" in event_names

    async def test_no_warning_when_the_feed_succeeds(self):
        from backend.app.agent.signals.common.indicators import Candle

        class _WorkingFeed:
            def __init__(self, timeout_seconds=None):
                pass

            async def fetch(self, **kwargs):
                now = datetime.now(UTC)
                return [
                    Candle(timestamp=now - timedelta(minutes=m), open=700, high=705, low=698, close=702, volume=1.0)
                    for m in (15, 10, 5)
                ]

        with patch.object(view_routes, "logger") as mock_logger:
            with patch(
                "backend.app.agent.signals.perp.binance_klines.BinanceKlineFeed",
                _WorkingFeed,
            ):
                chart = await view_routes._build_live_chart(_position(), "perp", settings=settings())

        assert chart is not None
        assert not mock_logger.warning.called


@pytest.mark.asyncio
class TestWrapperTimeoutIsLogged:
    """_live_chart_if_open: il livello che vede DAVVERO ogni fallimento --
    incluso un timeout che scade PRIMA che la coroutine interna faccia
    progresso, che arriva come CancelledError e non passa mai dal logging
    interno di _build_live_chart."""

    async def test_outer_timeout_is_logged_even_when_inner_never_gets_to_log(self, monkeypatch):
        async def _hangs_forever(*args, **kwargs):
            await asyncio.sleep(10)
            return {"candles": []}

        monkeypatch.setattr(view_routes, "_build_live_chart", _hangs_forever)
        monkeypatch.setattr(view_routes, "TRADE_DETAIL_CHART_TIMEOUT_SECONDS", 0.05)

        with patch.object(view_routes, "logger") as mock_logger:
            result = await view_routes._live_chart_if_open(
                None, _position(), "perp", settings()
            )

        assert result is None
        assert mock_logger.warning.called
        event_names = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert "live_chart_if_open_failed" in event_names

    async def test_no_warning_when_the_wrapper_succeeds_quickly(self, monkeypatch):
        async def _fast_chart(*args, **kwargs):
            return {"candles": [{"t": "x"}], "live": True}

        monkeypatch.setattr(view_routes, "_build_live_chart", _fast_chart)

        with patch.object(view_routes, "logger") as mock_logger:
            result = await view_routes._live_chart_if_open(
                None, _position(), "perp", settings()
            )

        assert result is not None
        assert not mock_logger.warning.called
