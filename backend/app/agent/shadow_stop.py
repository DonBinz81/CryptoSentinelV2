"""Shadow-mode simulation of David's tight-stop + confirmed-reclaim rule (NOTE/91).

Real stops are large sweeps of production data — a single unlucky night of
sweeps convinced no one; validating a rule on 190 real trades before touching
production did. This module runs that same rule LIVE, in parallel with real
trading, on real positions: nothing here ever changes an order, a stop, or a
position. It only measures what would have happened.

Rule under test: stop at a small buffer beyond the signal candle's extreme
(the candle whose close fixed entry) instead of the structural stop; on stop,
wait for one full candle beyond the ORIGINAL entry (confirmation), then arm a
limit at that same entry price; if price retraces there, re-enter with the
same TP1, same rule. Bounded by ``max_reentries`` and a 24h horizon (288 5m
candles) to match the backtest that validated it.

Pure state machine: one call to ``advance`` per newly-closed 5m candle, no I/O,
no DB, mirrors breach.py's purity for the same reason (NOTE/73) — an in-place
mutation there silently broke persistence for a whole episode. The caller
(service.py) owns fetching candles and persisting ``ShadowStopRun`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.agent.signals.common.indicators import Candle


@dataclass(frozen=True)
class ShadowStopConfig:
    buffer_pct: float
    max_reentries: int
    horizon_candles: int = 288  # 24h of 5m candles, matches the backtest


@dataclass(frozen=True)
class ShadowStopEvent:
    kind: str  # signal_candle_set | stopped | confirmed | reentered | tp1_hit | missed_train | horizon_reached | invalid_geometry
    price: float
    pnl_leg_pct: float | None = None


def new_run_state(*, side: str, entry_price: float, tp1: float, cfg: ShadowStopConfig, candle_count_budget: int) -> dict:
    """Initial state for a freshly opened position: waiting on its own signal
    candle to close before a stop level can be fixed."""
    return {
        "phase": "awaiting_signal_candle",
        "side": side,
        "entry_price": entry_price,
        "tp1": tp1,
        "buffer_pct": cfg.buffer_pct,
        "max_reentries": cfg.max_reentries,
        "candles_seen": 0,
        "candle_budget": candle_count_budget,
        "sig_extreme": None,
        "stop_price": None,
        "entry_ref": entry_price,
        "reentries": 0,
        "confirmed": False,
        "pnl_virtual_pct": 0.0,
        "outcome": None,
    }


def advance(state: dict, candle: Candle) -> tuple[dict, list[ShadowStopEvent]]:
    """Advance one shadow-stop run by exactly one newly-closed 5m candle.

    Never mutates ``state`` — the caller detects change and decides what to
    persist; an in-place mutation here would carry the same silent-loss risk
    documented in breach.py. Candles must be fed in chronological order, one
    per call; the horizon is counted in candles seen, not wall-clock time, so
    a gap (e.g. a restart) does not distort it.
    """
    events: list[ShadowStopEvent] = []
    st = dict(state)
    if st["phase"] == "done":
        return st, events

    is_long = st["side"] == "long"
    st["candles_seen"] += 1

    if st["candles_seen"] > st["candle_budget"]:
        if st["phase"] == "in":
            ref = st["entry_ref"]
            leg = (candle.close - ref) / ref * 100
            st["pnl_virtual_pct"] += leg if is_long else -leg
        st["outcome"] = "horizon"
        st["phase"] = "done"
        events.append(ShadowStopEvent("horizon_reached", candle.close))
        return st, events

    phase = st["phase"]

    if phase == "awaiting_signal_candle":
        sig_extreme = candle.low if is_long else candle.high
        stop_price = (
            sig_extreme * (1 - st["buffer_pct"] / 100)
            if is_long
            else sig_extreme * (1 + st["buffer_pct"] / 100)
        )
        # Geometry can break on illiquid pairs (huge signal-candle wick): the
        # buffer would place the stop past the entry itself. No trade to run.
        if (is_long and stop_price >= st["entry_price"]) or (
            not is_long and stop_price <= st["entry_price"]
        ):
            st["outcome"] = "invalid_geometry"
            st["phase"] = "done"
            events.append(ShadowStopEvent("invalid_geometry", stop_price))
            return st, events
        st["sig_extreme"] = sig_extreme
        st["stop_price"] = stop_price
        st["phase"] = "in"
        events.append(ShadowStopEvent("signal_candle_set", stop_price))
        # This candle only fixes the level (matches the backtest, which starts
        # evaluating stop/TP from the candle AFTER the signal one) — no
        # stop/TP check on it.
        return st, events

    if phase == "in":
        st, ev = _evaluate_in(st, candle, is_long)
        events.extend(ev)
        return st, events

    if phase == "waiting_confirm":
        entry_ref = st["entry_price"]  # reclaim reference is always the ORIGINAL entry
        full_candle_beyond = candle.low > entry_ref if is_long else candle.high < entry_ref
        if full_candle_beyond:
            st["confirmed"] = True
            st["phase"] = "waiting_reclaim"
            events.append(ShadowStopEvent("confirmed", entry_ref))
        return st, events

    if phase == "waiting_reclaim":
        entry_ref, tp1 = st["entry_price"], st["tp1"]
        reclaimed = candle.low <= entry_ref if is_long else candle.high >= entry_ref
        missed = candle.high >= tp1 if is_long else candle.low <= tp1
        if reclaimed:
            st["entry_ref"] = entry_ref
            st["reentries"] += 1
            st["phase"] = "in"
            events.append(ShadowStopEvent("reentered", entry_ref))
            # Same candle can already stop or win the re-entry (conservative:
            # stop checked first, matching the backtest's tie-breaking rule).
            st, ev = _evaluate_in(st, candle, is_long)
            events.extend(ev)
        elif missed:
            st["outcome"] = "missed_train"
            st["phase"] = "done"
            events.append(ShadowStopEvent("missed_train", candle.close))
        return st, events

    return st, events


def _evaluate_in(st: dict, candle: Candle, is_long: bool) -> tuple[dict, list[ShadowStopEvent]]:
    """Shared stop/TP1 check for the 'in' phase, used both on a fresh candle
    and on the same candle that just triggered a re-entry."""
    events: list[ShadowStopEvent] = []
    stop_price, ref, tp1 = st["stop_price"], st["entry_ref"], st["tp1"]
    hit_stop = candle.low <= stop_price if is_long else candle.high >= stop_price
    hit_tp1 = candle.high >= tp1 if is_long else candle.low <= tp1
    if hit_stop:
        leg = (stop_price - ref) / ref * 100
        leg = leg if is_long else -leg
        st["pnl_virtual_pct"] += leg
        events.append(ShadowStopEvent("stopped", stop_price, leg))
        if st["reentries"] < st["max_reentries"]:
            st["phase"] = "waiting_confirm"
            st["confirmed"] = False
        else:
            st["outcome"] = "final_stop"
            st["phase"] = "done"
    elif hit_tp1:
        leg = (tp1 - ref) / ref * 100
        leg = leg if is_long else -leg
        st["pnl_virtual_pct"] += leg
        events.append(ShadowStopEvent("tp1_hit", tp1, leg))
        st["outcome"] = "tp1"
        st["phase"] = "done"
    return st, events
