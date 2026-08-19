"""Breach episode tracker: persistence + bypass rule for stop/Smart-SL levels.

NOTE/59 found that the engine's stop check only sees the 5s-sampled price, so
sub-second spikes that pierce a level and snap back are invisible — sometimes
by luck (NEAR, 18/08), sometimes not. NOTE/60's retrospective on real 18-19/08
touches (aggTrades) validated a rule that turns that coin flip into a
deliberate choice: a level only "breaches" once the price has stayed beyond
it for N continuous seconds, OR the moment it goes Z% beyond it (a real
cascade does not wait). Full detail in NOTE/64.

This module is pure: it advances one (position, level) episode by one sampled
price and returns the new state plus any events to log. No I/O, no DB, no
notifications — the caller (service.py) owns persistence and side effects.
Shadow mode only for now: nothing here changes what the engine does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BreachRuleConfig:
    persistence_seconds: float
    bypass_pct: float


@dataclass(frozen=True)
class BreachEvent:
    kind: str  # "started" | "ended" | "rule_fired"
    level: str
    duration_s: float
    max_depth_pct: float
    fired_by: str | None = None  # "persistence" | "bypass" | None


def evaluate_breach(
    *,
    state: dict | None,
    level: str,
    level_price: float,
    current_price: float,
    is_long: bool,
    now: datetime,
    cfg: BreachRuleConfig,
) -> tuple[dict | None, list[BreachEvent]]:
    """Advance one (position, level) episode by one sampled price.

    An episode starts the first sample beyond the level and ends only on a
    sample back inside it — a gap between samples (e.g. a restart) does not
    close it, matching how NOTE/60's retrospective segmented real ticks.
    "fired" latches: the rule is reported once, on the sample that first
    crosses persistence or bypass, not on every following sample.
    """
    events: list[BreachEvent] = []
    beyond = current_price < level_price if is_long else current_price > level_price

    if not beyond:
        if state is not None:
            start = datetime.fromisoformat(state["start"])
            duration = (now - start).total_seconds()
            events.append(BreachEvent("ended", level, duration, state["max_depth_pct"]))
        return None, events

    depth_pct = (
        (level_price - current_price) / level_price * 100
        if is_long
        else (current_price - level_price) / level_price * 100
    )

    if state is None:
        state = {"start": now.isoformat(), "max_depth_pct": depth_pct, "fired": False, "fired_by": None}
        events.append(BreachEvent("started", level, 0.0, depth_pct))
    else:
        state["max_depth_pct"] = max(state["max_depth_pct"], depth_pct)

    start = datetime.fromisoformat(state["start"])
    duration = (now - start).total_seconds()

    if not state["fired"]:
        fired_by = None
        if duration >= cfg.persistence_seconds:
            fired_by = "persistence"
        elif state["max_depth_pct"] >= cfg.bypass_pct:
            fired_by = "bypass"
        if fired_by:
            state["fired"] = True
            state["fired_by"] = fired_by
            events.append(BreachEvent("rule_fired", level, duration, state["max_depth_pct"], fired_by))

    return state, events
