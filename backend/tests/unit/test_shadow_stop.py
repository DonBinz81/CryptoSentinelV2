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


class TestPreNote92StateCompatibility:
    """Runs created before NOTE/92 have state_json blobs with no
    confirm_candles/reentry_offset_pct/confirm_count keys at all (two real
    open positions in production had exactly this shape when this landed).
    advance() must keep working on them, not KeyError and strand the run.
    """

    def _old_state(self, phase, **overrides):
        # Deliberately built WITHOUT calling new_run_state(), to reproduce a
        # pre-NOTE/92 persisted blob missing the newer keys entirely.
        state = {
            "phase": phase, "side": "short", "entry_price": 1.5108, "tp1": 1.4942,
            "buffer_pct": 0.1, "max_reentries": 1, "candles_seen": 7,
            "candle_budget": 288, "sig_extreme": 1.5174, "stop_price": 1.5189174,
            "entry_ref": 1.5108, "reentries": 0, "confirmed": phase == "waiting_reclaim",
            "pnl_virtual_pct": -0.537, "outcome": None,
        }
        state.update(overrides)
        return state

    def test_waiting_confirm_without_confirm_count_key_does_not_raise(self):
        state = self._old_state("waiting_confirm")
        assert "confirm_count" not in state and "confirm_candles" not in state
        # short: high < entry_ref confirms (mirrors the live pos_0e8a... row)
        state, events = advance(state, _c(1.51, 1.505, 1.5, 1.502))
        assert [e.kind for e in events] == ["confirmed"]
        assert state["phase"] == "waiting_reclaim"

    def test_waiting_reclaim_without_offset_key_reclaims_at_exact_entry(self):
        state = self._old_state("waiting_reclaim")
        assert "reentry_offset_pct" not in state
        # short: high >= entry_ref(1.5108) reclaims (mirrors pos_f44b... row)
        state, events = advance(state, _c(1.505, 1.512, 1.503, 1.51))
        assert events[0].kind == "reentered"
        assert events[0].price == 1.5108  # exact entry: missing key defaults to offset 0.0


class TestConfirmCandlesAndReentryOffset:
    """NOTE/92: the 'optimized' variant needs N consecutive confirmation
    candles (not just one) and a cheaper re-entry level (not exactly entry).
    confirm_candles=1/offset=0.0 (the CFG default above) must keep behaving
    exactly like before — every other test in this file proves that already.
    """

    def test_confirm_count_resets_when_a_candle_falls_back_inside(self):
        cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=1, confirm_candles=2)
        state = _start(cfg=cfg, entry=100.0, tp1=105.0)
        state, _ = advance(state, _c(99, 101, 98, 100.5))         # signal candle
        state, ev = advance(state, _c(99, 99.2, 97.5, 98))        # stop
        assert ev[0].kind == "stopped"

        state, ev = advance(state, _c(99.5, 100.8, 100.5, 100.7))  # beyond: count=1
        assert ev == []
        state, ev = advance(state, _c(100.7, 100.9, 99.9, 100.2))  # NOT beyond: resets to 0
        assert ev == []
        assert state["confirm_count"] == 0
        state, ev = advance(state, _c(100.2, 100.5, 100.3, 100.4))  # beyond: count=1
        assert ev == []
        state, ev = advance(state, _c(100.4, 100.6, 100.35, 100.5))  # beyond: count=2 -> confirmed
        assert ev[0].kind == "confirmed"

    def test_reentry_offset_requires_a_cheaper_price_than_exact_entry(self):
        cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=1, reentry_offset_pct=0.2)
        state = _start(cfg=cfg, entry=100.0, tp1=105.0)
        state, _ = advance(state, _c(99, 101, 98, 100.5))
        state, _ = advance(state, _c(99, 99.2, 97.5, 98))          # stop
        state, ev = advance(state, _c(99, 100.3, 100.1, 100.2))    # confirmed
        assert ev[0].kind == "confirmed"

        # low=99.9 does NOT reach the offset level (99.8): no reclaim yet,
        # whereas offset=0.0 (exact entry) would already have reclaimed here.
        state, ev = advance(state, _c(100.2, 100.4, 99.9, 100.0))
        assert ev == []
        assert state["phase"] == "waiting_reclaim"

        state, ev = advance(state, _c(100.0, 100.5, 99.7, 100.0))  # low=99.7 <= 99.8
        assert ev[0].kind == "reentered"
        assert abs(ev[0].price - 99.8) < 1e-6
        assert state["entry_ref"] == ev[0].price

    def test_default_config_confirm_1_offset_0_matches_original_behavior(self):
        # Explicit regression guard: the new fields must not change anything
        # for confirm_candles=1/reentry_offset_pct=0.0 (the deployed baseline).
        default_cfg = ShadowStopConfig(buffer_pct=0.1, max_reentries=1)
        assert default_cfg.confirm_candles == 1
        assert default_cfg.reentry_offset_pct == 0.0
        state = _start(cfg=default_cfg, entry=100.0, tp1=105.0)
        state, _ = advance(state, _c(99, 101, 98, 100.5))
        state, _ = advance(state, _c(99, 99.2, 97.5, 98))
        state, ev = advance(state, _c(99, 100.3, 100.1, 100.2))  # one candle: confirmed
        assert ev[0].kind == "confirmed"
        state, ev = advance(state, _c(100.2, 100.5, 99.8, 100.0))  # low<=100: reclaim at exact entry
        assert ev[0].kind == "reentered"
        assert ev[0].price == 100.0


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
