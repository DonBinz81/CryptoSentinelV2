"""Regime guardian: GREEN/YELLOW/RED driven by the bot's own full stop-losses.

No market variable we measured separates losing entries from winning ones at
entry time (NOTE/60, NOTE/61): the earliest reliable signal that the regime no
longer suits the strategy is the strategy itself taking full stops. The
guardian counts full perp stop-losses on a rolling window:

    GREEN   normal operation
    YELLOW  new entries scaled down by ``yellow_size_factor``
    RED     no new perp entries; open positions keep being managed under the
            Capital Preservation profile (resolved at read time in the agent)

De-escalation is time-based ("clean hours" without new full stops), one step
at a time: RED -> YELLOW -> GREEN. State survives restarts via RuntimeState.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.app.core.logging import get_logger
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

logger = get_logger("agent.guardian")

GUARDIAN_STATE_KEY = "perp_guardian_state"

GREEN = "green"
YELLOW = "yellow"
RED = "red"

_SEVERITY = {GREEN: 0, YELLOW: 1, RED: 2}


@dataclass(frozen=True)
class GuardianConfig:
    """Snapshot of the guardian knobs from the mobile settings."""

    enabled: bool = True
    window_hours: float = 6.0
    yellow_stops: int = 1
    red_stops: int = 2
    reentry_hours: float = 6.0


@dataclass(frozen=True)
class GuardianChange:
    """A state transition, with the context needed to notify and log it."""

    previous: str
    current: str
    stops_in_window: int
    window_hours: float
    last_stop_at: datetime | None
    changed_at: datetime


class RegimeGuardian:
    """In-memory state machine, persisted on change so restarts resume it."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._loaded = False
        self._state: str = GREEN
        self._stop_times: list[datetime] = []
        # Stop events kept for the notification text: (asset, pnl_usd, time).
        self._stop_events: list[tuple[str, float, datetime]] = []
        self._changed_at: datetime | None = None
        # Brain explanation of the LATEST transition (app banner, chat C /
        # NOTE/61 §6-bis). Reset to None on every new transition so a stale
        # explanation from a previous state can never be shown as current;
        # filled in later by record_explanation() once the Brain call returns.
        self._explanation: str | None = None
        self._explained_at: datetime | None = None
        # Manual override (NOTE/107 §13): a layer ON TOP of the automatic state,
        # never a replacement for it. The state machine below keeps running
        # untouched -- it counts stops, moves its own level, advances its
        # timers -- and only the READ of the operational level is redirected.
        # Same idea as ``_eff_ms()`` in service.py: resolve at read time, never
        # write over the underlying value, so leaving the override needs no
        # restore step and nothing can be lost.
        self._override_level: str | None = None
        self._override_at: datetime | None = None

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        raw = get_runtime_value(self.user_id, GUARDIAN_STATE_KEY)
        if not raw:
            return
        try:
            data = json.loads(raw)
            self._state = data.get("state", GREEN)
            self._stop_times = [
                datetime.fromisoformat(t) for t in data.get("stop_times", [])
            ]
            self._stop_events = [
                (str(e[0]), float(e[1]), datetime.fromisoformat(e[2]))
                for e in data.get("stop_events", [])
            ]
            changed = data.get("changed_at")
            self._changed_at = datetime.fromisoformat(changed) if changed else None
            self._explanation = data.get("explanation")
            explained = data.get("explained_at")
            self._explained_at = datetime.fromisoformat(explained) if explained else None
            level = data.get("manual_override_level")
            self._override_level = level if level in _SEVERITY else None
            ov_at = data.get("manual_override_at")
            self._override_at = datetime.fromisoformat(ov_at) if ov_at else None
        except Exception as exc:  # never let a corrupt blob stop the agent
            logger.warning("guardian_state_load_failed", error=str(exc))

    def _save(self) -> None:
        payload = {
            "state": self._state,
            "stop_times": [t.isoformat() for t in self._stop_times],
            "stop_events": [
                (a, p, t.isoformat()) for a, p, t in self._stop_events
            ],
            "changed_at": self._changed_at.isoformat() if self._changed_at else None,
            "explanation": self._explanation,
            "explained_at": self._explained_at.isoformat() if self._explained_at else None,
            "manual_override_level": self._override_level,
            "manual_override_at": self._override_at.isoformat() if self._override_at else None,
        }
        set_runtime_value(self.user_id, GUARDIAN_STATE_KEY, json.dumps(payload))

    # ── queries ──────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        self._load()
        return self._state

    @property
    def effective_state(self) -> str:
        """The level the engine must OBEY: the override when set, else the automatic one.

        This is what the three operational readers use (entry block, yellow
        sizing, capital preservation). ``state`` stays the pure automatic level,
        and the state machine -- ``evaluate``, ``record_stop``, the escalation
        safety net -- keeps reading ``_state`` directly: an override must never
        be able to falsify the machine that computes the automatic level, or
        pressing AUTO would return to a level the market never produced.
        """
        self._load()
        return self._override_level or self._state

    @property
    def manual_override(self) -> str | None:
        self._load()
        return self._override_level

    def last_stop_at(self) -> datetime | None:
        self._load()
        return max(self._stop_times) if self._stop_times else None

    def stops_in_window(self, now: datetime, cfg: GuardianConfig) -> int:
        self._load()
        cutoff = now - timedelta(hours=cfg.window_hours)
        return sum(1 for t in self._stop_times if t >= cutoff)

    def recent_stop_events(self, now: datetime, cfg: GuardianConfig) -> list[tuple[str, float, datetime]]:
        self._load()
        cutoff = now - timedelta(hours=cfg.window_hours)
        return [(a, p, t) for a, p, t in self._stop_events if t >= cutoff]

    def snapshot(self, now: datetime, cfg: GuardianConfig) -> dict:
        """Serializable view for /agent/status and notifications."""
        self._load()
        last = self.last_stop_at()
        automatic = self._state if cfg.enabled else GREEN
        effective = (self._override_level or automatic) if cfg.enabled else GREEN
        return {
            # ``state`` keeps meaning "what the engine is doing", so the existing
            # banner and the V1 client stay correct without changes: with no
            # override the two are identical. The distinct levels are below.
            "state": effective,
            "automatic_level": automatic,
            "effective_level": effective,
            "manual_override": (
                {"level": self._override_level, "at": self._override_at.isoformat() if self._override_at else None}
                if self._override_level else None
            ),
            "enabled": cfg.enabled,
            "stops_in_window": self.stops_in_window(now, cfg),
            "window_hours": cfg.window_hours,
            # De-escalation pace, for the app's countdown (NOTE/95): one step
            # per clean reentry_hours, counted from max(last_stop_at,
            # changed_at) -- both already exposed below. Every new full stop
            # moves that anchor forward, so any client countdown is a
            # projection, not a promise.
            "reentry_hours": cfg.reentry_hours,
            "last_stop_at": last.isoformat() if last else None,
            "changed_at": self._changed_at.isoformat() if self._changed_at else None,
            "explanation": self._explanation,
            "explained_at": self._explained_at.isoformat() if self._explained_at else None,
        }

    # ── transitions ──────────────────────────────────────────────────────

    def _prune(self, now: datetime, cfg: GuardianConfig) -> None:
        # Keep events a bit past the window so a widened window (settings
        # change) still sees recent history; 48h is far beyond any config.
        horizon = now - timedelta(hours=max(cfg.window_hours, 48.0))
        self._stop_times = [t for t in self._stop_times if t >= horizon]
        self._stop_events = self._stop_events[-50:]

    def _escalation_target(self, now: datetime, cfg: GuardianConfig) -> str:
        count = self.stops_in_window(now, cfg)
        if count >= cfg.red_stops:
            return RED
        if count >= cfg.yellow_stops:
            return YELLOW
        return GREEN

    def set_manual_override(self, level: str, now: datetime, *, admin: str = "admin") -> dict:
        """Pin the operational level, leaving the automatic machine untouched.

        Deliberately NOT implemented through ``_set_state``: that would overwrite
        ``_state`` (destroying the automatic level, so AUTO would have nothing to
        return to), move ``changed_at`` (the anchor of the de-escalation
        countdown, which must keep running) and clear the Brain explanation.
        None of those may happen here.
        """
        self._load()
        if level not in _SEVERITY:
            raise ValueError(f"unknown guardian level: {level}")
        previous = self._override_level
        self._override_level = level
        self._override_at = now
        self._save()
        logger.info(
            "perp_protection_manual_override",
            admin=admin,
            from_level=previous or self._state,
            to_level=level,
            automatic_level=self._state,
            effective_level=level,
        )
        return {"automatic_level": self._state, "effective_level": level, "previous": previous}

    def clear_manual_override(self, now: datetime, *, admin: str = "admin") -> dict:
        """Back to AUTO: the effective level returns to the CURRENT automatic one.

        Which may well differ from the one in force when the override was set --
        the machine kept working underneath. That is the point of the feature.
        """
        self._load()
        previous = self._override_level
        self._override_level = None
        self._override_at = None
        self._save()
        logger.info(
            "perp_protection_manual_override_cleared",
            admin=admin,
            from_level=previous,
            to_level=self._state,
            automatic_level=self._state,
            effective_level=self._state,
        )
        return {"automatic_level": self._state, "effective_level": self._state, "previous": previous}

    def _set_state(self, new_state: str, now: datetime, cfg: GuardianConfig) -> GuardianChange:
        previous = self._state
        self._state = new_state
        self._changed_at = now
        # A new transition invalidates any explanation of the previous one:
        # cleared here (not just left for the async Brain call to overwrite),
        # so a slow/failed explain() never leaves a stale text attached to
        # the wrong state. record_explanation() below fills it back in.
        self._explanation = None
        self._explained_at = None
        self._save()
        change = GuardianChange(
            previous=previous,
            current=new_state,
            stops_in_window=self.stops_in_window(now, cfg),
            window_hours=cfg.window_hours,
            last_stop_at=self.last_stop_at(),
            changed_at=now,
        )
        logger.info(
            "guardian_state_changed",
            previous=previous,
            current=new_state,
            stops_in_window=change.stops_in_window,
        )
        return change

    def record_explanation(self, *, text: str, at: datetime, for_change_at: datetime) -> None:
        """Persist the Brain's explanation of a transition (NOTE/61 §6-bis).

        ``for_change_at`` must match the transition's own ``changed_at``: if a
        newer transition already superseded it (the explain() call is async
        and can lag behind a fast-moving guardian), the stale text is
        dropped instead of being attached to the wrong state.
        """
        self._load()
        if self._changed_at is None or self._changed_at != for_change_at:
            logger.info("guardian_explanation_superseded", for_change_at=for_change_at.isoformat())
            return
        self._explanation = text
        self._explained_at = at
        self._save()

    def record_stop(
        self, *, asset: str, pnl_usd: float, now: datetime, cfg: GuardianConfig
    ) -> GuardianChange | None:
        """Register a full perp stop-loss; escalate if the window says so."""
        self._load()
        self._stop_times.append(now)
        self._stop_events.append((asset, pnl_usd, now))
        self._prune(now, cfg)
        if not cfg.enabled:
            self._save()
            return None
        target = self._escalation_target(now, cfg)
        if _SEVERITY[target] > _SEVERITY[self._state]:
            return self._set_state(target, now, cfg)
        self._save()
        return None

    def evaluate(self, *, now: datetime, cfg: GuardianConfig) -> GuardianChange | None:
        """Periodic re-check (slow tick): escalate on backlog, de-escalate on clean hours."""
        self._load()
        if not cfg.enabled:
            # Disabled: force GREEN once so a stale RED never outlives the toggle.
            if self._state != GREEN:
                return self._set_state(GREEN, now, cfg)
            return None
        self._prune(now, cfg)
        # Escalation safety net (e.g. settings tightened, or state blob lost on
        # restart). Only stops NEWER than the last transition may escalate:
        # otherwise a de-escalation would bounce straight back while old stops
        # are still inside a window longer than the reentry time.
        target = self._escalation_target(now, cfg)
        last = self.last_stop_at()
        if (
            _SEVERITY[target] > _SEVERITY[self._state]
            and last is not None
            and (self._changed_at is None or last > self._changed_at)
        ):
            return self._set_state(target, now, cfg)
        # De-escalation: one step per clean ``reentry_hours``, counted from the
        # later of the last stop and the last state change.
        if self._state == GREEN:
            return None
        anchors = [t for t in (self.last_stop_at(), self._changed_at) if t is not None]
        if not anchors:
            return self._set_state(GREEN, now, cfg)
        anchor = max(anchors)
        if now - anchor >= timedelta(hours=cfg.reentry_hours):
            next_state = YELLOW if self._state == RED else GREEN
            return self._set_state(next_state, now, cfg)
        return None
