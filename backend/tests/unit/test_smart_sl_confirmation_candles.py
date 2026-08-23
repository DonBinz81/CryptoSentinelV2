"""Tests for the Smart SL closed-candle confirmation (NOTE/93).

David flagged that the last two Smart SL sells fired ~14 minutes late,
letting the loss run deeper than the level should have allowed. The cause:
confirmation was a continuous timer since the FIRST touch of the level,
RESET to zero on any single tick where price dipped back below it -- normal
price noise near a threshold kept resetting the timer for ~20 minutes before
it ever completed a full window uninterrupted. The fix replaces that timer
with the same "N consecutive closed candles" pattern already used by
shadow_stop.py and _market_reversal_filter: it looks at the last N *closed*
5m candles and requires ALL of them to have closed beyond the level -- no
persisted state, no reset-on-flicker, recalculated fresh from real candles
every time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.tests.unit.test_agent_step6 import settings


def _closed_candle(minutes_ago: int, close: float) -> Candle:
    # Ancorata all'orologio REALE: _smart_sl_closed_candles confronta contro
    # datetime.now(UTC), quindi una data fissa nel passato falserebbe proprio
    # il test sulla candela "ancora in corso" (< 5 minuti reali fa).
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return Candle(timestamp=ts, open=close, high=close, low=close, close=close, volume=1.0)


class _FakeFeed:
    def __init__(self, candles: list[Candle]):
        self.candles = candles
        self.calls = 0

    async def fetch(self, *, symbol, interval, limit, market):
        self.calls += 1
        return self.candles[-limit:]


def _service(**ms_overrides) -> AgentService:
    return AgentService(settings(**ms_overrides), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())


class _MS:
    """Minimal stand-in for AgentMobileSettings: only the field this code reads."""

    def __init__(self, n: int):
        self.perp_smart_sl_confirmation_candles = n


@pytest.mark.asyncio
class TestSmartSlConfirmed:
    async def test_confirms_when_last_n_closed_candles_are_all_beyond_the_level(self):
        svc = _service()
        # 3 candele chiuse consecutive, tutte >= level (short: adverse = su)
        svc.price_feed = _FakeFeed([
            _closed_candle(20, 100.0),
            _closed_candle(15, 703.5),
            _closed_candle(10, 704.0),
            _closed_candle(5, 703.8),
        ])
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is True

    async def test_not_confirmed_if_even_one_of_the_last_n_dips_back_inside(self):
        # Esattamente il pattern osservato nei log reali: candele oscillano
        # sopra/sotto il livello. Se anche solo una delle ultime N e' rientrata,
        # NON e' confermato -- a differenza del vecchio cronometro, qui non
        # serve "azzerare" nulla: si ricalcola sempre dalle ultime N candele vere.
        svc = _service()
        svc.price_feed = _FakeFeed([
            _closed_candle(20, 703.5),
            _closed_candle(15, 704.0),
            _closed_candle(10, 702.5),  # rientrata sotto il livello 703.0
            _closed_candle(5, 703.8),
        ])
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is False

    async def test_old_dips_do_not_matter_once_the_last_n_are_clean(self):
        # Il vecchio meccanismo azzerava il cronometro per QUALUNQUE rientro,
        # anche minuti prima. Qui conta solo lo stato delle ultime N candele:
        # un rientro vecchio non deve impedire la conferma se le ultime N sono pulite.
        svc = _service()
        svc.price_feed = _FakeFeed([
            _closed_candle(30, 690.0),  # ben sotto il livello, ma e' vecchia
            _closed_candle(25, 695.0),
            _closed_candle(15, 703.5),
            _closed_candle(10, 704.0),
            _closed_candle(5, 703.8),
        ])
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is True

    async def test_direction_down_for_long_positions_requires_close_below_level(self):
        svc = _service()
        svc.price_feed = _FakeFeed([
            _closed_candle(15, 696.0),
            _closed_candle(10, 695.5),
            _closed_candle(5, 695.8),
        ])
        pos = SimpleNamespace(asset="ETH")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("697.0"), _MS(3), direction_down=True)
        assert confirmed is True

    async def test_fails_closed_when_fewer_than_n_closed_candles_are_available(self):
        svc = _service()
        svc.price_feed = _FakeFeed([_closed_candle(10, 704.0), _closed_candle(5, 703.8)])  # solo 2, servono 3
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is False

    async def test_fails_closed_when_the_fetch_raises(self):
        class _BrokenFeed:
            async def fetch(self, **kwargs):
                raise RuntimeError("network down")

        svc = _service()
        svc.price_feed = _BrokenFeed()
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is False

    async def test_excludes_the_still_forming_current_candle(self):
        # Una candela con timestamp negli ultimi 5 minuti non e' ancora chiusa:
        # non deve contare, anche se il suo prezzo sarebbe favorevole.
        svc = _service()
        svc.price_feed = _FakeFeed([
            _closed_candle(15, 703.5),
            _closed_candle(10, 704.0),
            _closed_candle(1, 999.0),  # in corso: DEVE essere esclusa
        ])
        pos = SimpleNamespace(asset="BNB")
        confirmed = await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert confirmed is False  # solo 2 candele davvero chiuse, ne servono 3

    async def test_repeated_calls_within_ttl_reuse_the_cached_fetch(self):
        svc = _service()
        feed = _FakeFeed([
            _closed_candle(15, 703.5),
            _closed_candle(10, 704.0),
            _closed_candle(5, 703.8),
        ])
        svc.price_feed = feed
        pos = SimpleNamespace(asset="BNB")
        await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        await svc._smart_sl_confirmed(pos, Decimal("703.0"), _MS(3), direction_down=False)
        assert feed.calls == 1
