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
        }
        set_runtime_value(self.user_id, GUARDIAN_STATE_KEY, json.dumps(payload))

    # ── queries ──────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        self._load()
        return self._state

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
        return {
            "state": self._state if cfg.enabled else GREEN,
            "enabled": cfg.enabled,
            "stops_in_window": self.stops_in_window(now, cfg),
            "window_hours": cfg.window_hours,
            "last_stop_at": last.isoformat() if last else None,
            "changed_at": self._changed_at.isoformat() if self._changed_at else None,
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

    def _set_state(self, new_state: str, now: datetime, cfg: GuardianConfig) -> GuardianChange:
        previous = self._state
        self._state = new_state
        self._changed_at = now
        self._save()
        change = GuardianChange(
            previous=previous,
            current=new_state,
            stops_in_window=self.stops_in_window(now, cfg),
            window_hours=cfg.window_hours,
            last_stop_at=self.last_stop_at(),
        )
        logger.info(
            "guardian_state_changed",
            previous=previous,
            current=new_state,
            stops_in_window=change.stops_in_window,
        )
        return change

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
