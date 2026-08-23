"""Unit tests for the shadow-stop rule engine (NOTE/91).

Pure-function tests: feed a sequence of closed 5m candles through ``advance``
and check the state transitions and events it emits. Mirrors test_breach.py's
style — one candle per call, chronological order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.agent.shadow_stop import ShadowStopConfig, advance, new_run_state
from backend.app.agent.signals.common.indicators import Candle

T0 = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
CFG = ShadowStopConfig(buffer_pct=0.1, max_reentries=1, horizon_candles=288)


def _c(o, h, l, c, minute=0):
    return Candle(timestamp=T0 + timedelta(minutes=minute), open=o, high=h, low=l, close=c, volume=1.0)


def _start(side="long", entry=100.0, tp1=105.0, cfg=CFG):
    return new_run_state(side=side, entry_price=entry, tp1=tp1, cfg=cfg, candle_count_budget=cfg.horizon_candles)


class TestSignalCandle:
    def test_first_candle_fixes_the_stop_and_does_not_evaluate_it(self):
        state = _start()
        # signal candle low=98 -> stop = 98 * (1-0.001) = 97.902; even though
        # this same candle's low (98) would not breach anyway, the point is
        # that NO stop/tp check happens on the signal candle itself.
        state, events = advance(state, _c(99, 101, 98, 100.5))
        assert state["phase"] == "in"
        assert [e.kind for e in events] == ["signal_candle_set"]
        assert abs(state["stop_price"] - 97.902) < 1e-6

    def test_invalid_geometry_when_signal_candle_low_is_above_entry(self):
        # By construction the real signal candle always contains the entry
        # price (low <= entry <= high), so sig_extreme < entry for a long and
        # the buffered stop is always < entry too. This guards a live-data
        # edge case: floor_5m() alignment picks the WRONG candle (a network
        # delay, a boundary race) and its low ends up above the real entry.
        state = _start(entry=100.0)
        state, events = advance(state, _c(103, 104, 102, 103.5))
        assert state["phase"] == "done"
        assert state["outcome"] == "invalid_geometry"
        assert [e.kind for e in events] == ["invalid_geometry"]


class TestStopThenTp1NoReentry:
    def test_stop_hit_with_no_reentries_left_is_final(self):
        cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=0)
        state = _start(cfg=cfg)
        state, _ = advance(state, _c(99, 101, 98, 100.5))  # fixes stop ~97.9
        state, events = advance(state, _c(99, 99.5, 97.5, 98))  # low breaches stop
        assert state["phase"] == "done"
        assert state["outcome"] == "final_stop"
        assert [e.kind for e in events] == ["stopped"]
        assert state["pnl_virtual_pct"] < 0


class TestFullSweepAndReclaim:
    """The exact pattern David flagged: stop, confirmed reclaim, re-entry, TP1."""

    def test_sweep_then_confirmed_reclaim_then_tp1(self):
        state = _start(entry=100.0, tp1=105.0)
        state, ev = advance(state, _c(99, 101, 98, 100.5))
        assert ev[0].kind == "signal_candle_set"

        state, ev = advance(state, _c(99, 99.2, 97.5, 98))  # sweeps below stop
        assert ev[0].kind == "stopped"
        assert state["phase"] == "waiting_confirm"

        state, ev = advance(state, _c(99, 100.3, 100.1, 100.2))  # low > entry: confirmed
        assert ev[0].kind == "confirmed"
        assert state["phase"] == "waiting_reclaim"

        state, ev = advance(state, _c(100.2, 100.5, 99.8, 100.0))  # ritraccia sull'entry
        assert ev[0].kind == "reentered"
        assert state["phase"] == "in"
        assert state["reentries"] == 1

        state, ev = advance(state, _c(101, 106, 100.5, 105.5))  # va a TP1
        assert state["phase"] == "done"
        assert state["outcome"] == "tp1"
        assert [e.kind for e in ev] == ["tp1_hit"]
        # Il pnl netto e' la somma delle due gambe: la sweep (piccola perdita)
        # + la vincita fino a TP1 dal prezzo di rientro (che e' l'entry).
        assert state["pnl_virtual_pct"] > 0  # il TP1 vale piu' della sweep stretta

    def test_missed_train_when_tp1_hit_before_reclaim(self):
        state = _start(entry=100.0, tp1=105.0)
        state, _ = advance(state, _c(99, 101, 98, 100.5))
        state, _ = advance(state, _c(99, 99.2, 97.5, 98))  # stop
        state, _ = advance(state, _c(99, 100.3, 100.1, 100.2))  # confirmed
        state, events = advance(state, _c(100.2, 106, 100.1, 105.5))  # TP1 senza ritracciare
        assert state["phase"] == "done"
        assert state["outcome"] == "missed_train"
        assert [e.kind for e in events] == ["missed_train"]

    def test_second_stop_after_reentry_is_final_when_reentries_exhausted(self):
        cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=1)
        state = _start(cfg=cfg, entry=100.0, tp1=105.0)
        state, _ = advance(state, _c(99, 101, 98, 100.5))
        state, _ = advance(state, _c(99, 99.2, 97.5, 98))       # 1st stop
        state, _ = advance(state, _c(99, 100.3, 100.1, 100.2))  # confirmed
        state, ev = advance(state, _c(100.2, 100.4, 97.0, 97.5))  # reclaim + stop stessa candela
        # low=97.0 <= entry (100) -> reclaim; poi low <= stop_price -> stop, in un colpo
        assert [e.kind for e in ev] == ["reentered", "stopped"]
        assert state["phase"] == "done"
        assert state["outcome"] == "final_stop"


class TestHorizon:
    def test_horizon_marks_open_position_to_market_and_stops(self):
        # candle_count_budget counts every candle fed, including the one that
        # fixes the signal level: budget=2 tolerates 2 candles, the 3rd fires.
        cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=0, horizon_candles=2)
        state = _start(cfg=cfg, entry=100.0, tp1=200.0)  # tp1 irraggiungibile
        state, _ = advance(state, _c(99, 101, 98, 100.5))            # candle 1: fixes stop
        state, _ = advance(state, _c(100, 101, 99.9, 100.8))          # candle 2: still "in"
        state, events = advance(state, _c(100.5, 101.5, 100.3, 101))  # candle 3: horizon
        assert state["phase"] == "done"
        assert state["outcome"] == "horizon"
        assert [e.kind for e in events] == ["horizon_reached"]

    def test_immutability_state_never_mutated_in_place(self):
        # Same purity contract as breach.py (NOTE/73): calling advance must
        # not touch the caller's dict, or persistence silently loses state.
        state = _start()
        original = dict(state)
        advance(state, _c(99, 101, 98, 100.5))
        assert state == original


class TestShortSide:
    def test_short_sweep_and_reclaim_mirrors_long(self):
        state = _start(side="short", entry=100.0, tp1=95.0)
        state, ev = advance(state, _c(101, 102, 99, 100.5))  # signal candle high=102
        assert ev[0].kind == "signal_candle_set"
        assert state["stop_price"] > 102  # buffered ABOVE the high for a short

        state, ev = advance(state, _c(101, 102.5, 100, 101))  # high breaches stop
        assert ev[0].kind == "stopped"
        state, ev = advance(state, _c(101, 99.9, 99.5, 99.7))  # high < entry: confirmed
        assert ev[0].kind == "confirmed"
        state, ev = advance(state, _c(99.7, 100.2, 99.5, 100.0))  # ritraccia sull'entry (high>=entry)
        assert ev[0].kind == "reentered"
        assert state["reentries"] == 1
