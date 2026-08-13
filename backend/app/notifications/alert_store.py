"""DB-backed store for user alert configurations and price-checker state.

Source of truth is the ``alert_configs`` table (one row per user, holding the
serialized config and checker state).  The legacy JSON file is migrated into
the DB at startup and is no longer read in normal operation.  The public
interface is unchanged so the alerts route and price checker are unaffected.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.persistence.models.alerts import AlertConfig
from backend.app.persistence.models.device_alert_configs import DeviceAlertConfig
from backend.app.persistence.sync_database import get_sync_session
from backend.app.schemas.alerts import AlertSyncRequest, PendingFavAlert

SQLITE_WRITE_RETRIES = 3
SQLITE_WRITE_RETRY_DELAY_SECONDS = 0.25
_db_write_lock = Lock()


@dataclass
class CheckerState:
    """Runtime state persisted between price-check ticks."""

    triggered_keys: set[str] = field(default_factory=set)
    price_last_observed: dict[str, float] = field(default_factory=dict)
    price_waiting_rearm: set[str] = field(default_factory=set)
    range_last_notified: dict[str, float] = field(default_factory=dict)
    range_is_inside: dict[str, bool | None] = field(default_factory=dict)
    fav_ref_prices: dict[str, float] = field(default_factory=dict)
    pending_fav_alerts: dict[str, PendingFavAlert] = field(default_factory=dict)


class AlertStore:
    """Database-backed store for the latest alert config and checker state."""

    def __init__(self, user_id: str | None = None, device_id: str | None = None) -> None:
        self.user_id = str(user_id) if user_id is not None else str(DEFAULT_SINGLE_USER_ID)
        # Empty string is treated as "no device" (legacy global config).
        self.device_id = device_id or None
        self._lock = Lock()
        self._config: AlertSyncRequest | None = None
        self._state = CheckerState()
        self._load()

    def save_config(self, config: AlertSyncRequest) -> None:
        """Replace stored alert configuration, preserving backend-computed state."""
        with self._lock:
            merged_ref = dict(self._state.fav_ref_prices)
            for coin_id, price in config.fav_ref_prices.items():
                merged_ref.setdefault(coin_id, price)

            active_price_keys = {
                f"{alert.coin_id}:{alert.direction}:{alert.threshold}"
                for alert in config.price_alerts
            }
            active_range_keys = {
                f"{alert.coin_id}:{alert.min_price}:{alert.max_price}"
                for alert in config.range_alerts
            }
            active_fav_ids = {coin.id for coin in config.fav_coins}

            self._config = config
            self._state.triggered_keys.intersection_update(active_price_keys)
            self._state.price_last_observed = {
                key: value
                for key, value in self._state.price_last_observed.items()
                if key in active_price_keys
            }
            for alert in config.price_alerts:
                key = f"{alert.coin_id}:{alert.direction}:{alert.threshold}"
                if key not in self._state.price_last_observed and alert.last_observed_price is not None:
                    self._state.price_last_observed[key] = alert.last_observed_price
            self._state.price_waiting_rearm.intersection_update(active_price_keys)
            self._state.range_last_notified = {
                key: value
                for key, value in self._state.range_last_notified.items()
                if key in active_range_keys
            }
            self._state.range_is_inside = {
                key: value
                for key, value in self._state.range_is_inside.items()
                if key in active_range_keys
            }
            self._state.fav_ref_prices = {
                coin_id: price
                for coin_id, price in merged_ref.items()
                if coin_id in active_fav_ids
            }
            self._state.pending_fav_alerts = {
                coin_id: alert
                for coin_id, alert in self._state.pending_fav_alerts.items()
                if coin_id in active_fav_ids
            }
            self._persist_locked()

    def get_config(self) -> AlertSyncRequest | None:
        with self._lock:
            return self._config

    def get_state(self) -> CheckerState:
        with self._lock:
            return CheckerState(
                triggered_keys=set(self._state.triggered_keys),
                price_last_observed=dict(self._state.price_last_observed),
                price_waiting_rearm=set(self._state.price_waiting_rearm),
                range_last_notified=dict(self._state.range_last_notified),
                range_is_inside=dict(self._state.range_is_inside),
                fav_ref_prices=dict(self._state.fav_ref_prices),
                pending_fav_alerts={
                    coin_id: alert.model_copy()
                    for coin_id, alert in self._state.pending_fav_alerts.items()
                },
            )

    def update_state(self, state: CheckerState) -> None:
        with self._lock:
            self._state = state
            self._persist_locked()

    def pending_fav_alerts(self) -> list[PendingFavAlert]:
        """Return pending favorite alerts without clearing them."""

        with self._lock:
            return [alert.model_copy() for alert in self._state.pending_fav_alerts.values()]

    def dismiss_pending_fav_alert(self, coin_id: str) -> bool:
        """Acknowledge one favorite alert after the user dismisses its badge."""

        with self._lock:
            removed = self._state.pending_fav_alerts.pop(coin_id, None) is not None
            if removed:
                self._persist_locked()
            return removed

    def _state_to_dict(self) -> dict:
        return {
            "triggered_keys": list(self._state.triggered_keys),
            "price_last_observed": self._state.price_last_observed,
            "price_waiting_rearm": list(self._state.price_waiting_rearm),
            "range_last_notified": self._state.range_last_notified,
            "range_is_inside": dict(self._state.range_is_inside),
            "fav_ref_prices": self._state.fav_ref_prices,
            "pending_fav_alerts": {
                coin_id: alert.model_dump()
                for coin_id, alert in self._state.pending_fav_alerts.items()
            },
        }

    def _persist_locked(self) -> None:
        config_json = json.dumps(self._config.model_dump()) if self._config else None
        state_json = json.dumps(self._state_to_dict())
        now = datetime.now(UTC)
        for attempt in range(SQLITE_WRITE_RETRIES):
            try:
                with _db_write_lock:
                    self._persist_once(config_json=config_json, state_json=state_json, now=now)
                return
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt == SQLITE_WRITE_RETRIES - 1:
                    raise
                time.sleep(SQLITE_WRITE_RETRY_DELAY_SECONDS * (attempt + 1))

    def _persist_once(self, *, config_json: str | None, state_json: str, now: datetime) -> None:
        with get_sync_session() as session:
            if self.device_id is not None:
                row = session.execute(
                    select(DeviceAlertConfig)
                    .where(DeviceAlertConfig.user_id == self.user_id)
                    .where(DeviceAlertConfig.device_id == self.device_id)
                ).scalar_one_or_none()
                if row is None:
                    row = DeviceAlertConfig(
                        user_id=self.user_id,
                        device_id=self.device_id,
                        config_json=config_json,
                        state_json=state_json,
                        updated_at=now,
                    )
                    session.add(row)
                else:
                    row.config_json = config_json
                    row.state_json = state_json
                    row.updated_at = now
                session.commit()
                return
            row = session.execute(
                select(AlertConfig).where(AlertConfig.user_id == self.user_id)
            ).scalar_one_or_none()
            if row is None:
                row = AlertConfig(
                    user_id=self.user_id,
                    config_json=config_json,
                    state_json=state_json,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.config_json = config_json
                row.state_json = state_json
                row.updated_at = now
            session.commit()

    def _load(self) -> None:
        try:
            with get_sync_session() as session:
                if self.device_id is not None:
                    row = session.execute(
                        select(DeviceAlertConfig)
                        .where(DeviceAlertConfig.user_id == self.user_id)
                        .where(DeviceAlertConfig.device_id == self.device_id)
                    ).scalar_one_or_none()
                else:
                    row = session.execute(
                        select(AlertConfig).where(AlertConfig.user_id == self.user_id)
                    ).scalar_one_or_none()
            if row is None:
                return
            if row.config_json:
                self._config = AlertSyncRequest.model_validate(json.loads(row.config_json))
            if row.state_json:
                st = json.loads(row.state_json)
                self._state = CheckerState(
                    triggered_keys=set(st.get("triggered_keys", [])),
                    price_last_observed=st.get("price_last_observed", {}),
                    price_waiting_rearm=set(st.get("price_waiting_rearm", [])),
                    range_last_notified=st.get("range_last_notified", {}),
                    range_is_inside=st.get("range_is_inside", {}),
                    fav_ref_prices=st.get("fav_ref_prices", {}),
                    pending_fav_alerts={
                        coin_id: PendingFavAlert.model_validate(alert)
                        for coin_id, alert in st.get("pending_fav_alerts", {}).items()
                    },
                )
        except Exception:
            pass


_instances: dict[str | None, AlertStore] = {}
_instances_lock = Lock()


def get_alert_store(device_id: str | None = None) -> AlertStore:
    """Return the alert store for a device.

    ``device_id=None`` returns the legacy global store (backward compatibility
    for tokens registered before per-device separation). Each distinct device
    gets its own cached store with independent config and checker state.
    """

    key = device_id or None
    with _instances_lock:
        store = _instances.get(key)
        if store is None:
            store = AlertStore(device_id=key)
            _instances[key] = store
        return store
