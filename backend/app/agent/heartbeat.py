"""Internal backend heartbeat state."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AgentHeartbeat:
    """In-memory heartbeat for the backend and future agent loops."""

    component: str = "backend"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_beat_at: datetime | None = None
    beat_count: int = 0
    last_message: str = "not_started"

    def beat(self, message: str = "ok") -> None:
        """Record a heartbeat tick."""

        self.last_beat_at = datetime.now(UTC)
        self.beat_count += 1
        self.last_message = message

    def as_dict(self) -> dict[str, str | int | None]:
        """Serialize heartbeat state for health responses."""

        return {
            "component": self.component,
            "started_at": self.started_at.isoformat(),
            "last_beat_at": self.last_beat_at.isoformat() if self.last_beat_at else None,
            "beat_count": self.beat_count,
            "last_message": self.last_message,
        }


heartbeat = AgentHeartbeat()
