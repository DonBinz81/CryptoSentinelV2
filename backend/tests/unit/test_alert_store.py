from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from backend.app.notifications.alert_store import AlertStore, CheckerState
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.alerts import (
    AlertSyncRequest,
    FavCoin,
    PendingFavAlert,
    PriceAlertItem,
    RangeAlertItem,
)


@pytest.fixture
def db(tmp_path: Path):
    """Initialise a fresh sync SQLite DB for each test."""
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'test.db'}")
    create_all_sync()
    yield
    reset_sync_db()


def _config() -> AlertSyncRequest:
    return AlertSyncRequest(
        price_alerts=[
            PriceAlertItem(
                coin_id="bitcoin",
                coin_name="Bitcoin",
                direction="above",
                threshold=100_000,
            )
        ],
        range_alerts=[
            RangeAlertItem(
                coin_id="ethereum",
                coin_name="Ethereum",
                min_price=3_000,
                max_price=4_000,
            )
        ],
        fav_coins=[FavCoin(id="bnb", name="BNB", symbol="BNB")],
        fav_ref_prices={"bnb": 600},
    )


def test_identical_sync_preserves_checker_state(db) -> None:
    store = AlertStore()
    config = _config()
    store.save_config(config)
    store.update_state(
        CheckerState(
            triggered_keys={"bitcoin:above:100000.0"},
            range_last_notified={"ethereum:3000.0:4000.0": 123.0},
            range_is_inside={"ethereum:3000.0:4000.0": True},
            fav_ref_prices={"bnb": 625},
        )
    )

    store.save_config(config)

    state = store.get_state()
    assert state.triggered_keys == {"bitcoin:above:100000.0"}
    assert state.range_last_notified == {"ethereum:3000.0:4000.0": 123.0}
    assert state.range_is_inside == {"ethereum:3000.0:4000.0": True}
    assert state.fav_ref_prices == {"bnb": 625}


def test_removed_alerts_prune_checker_state(db) -> None:
    store = AlertStore()
    store.save_config(_config())
    store.update_state(
        CheckerState(
            triggered_keys={"bitcoin:above:100000.0"},
            range_last_notified={"ethereum:3000.0:4000.0": 123.0},
            range_is_inside={"ethereum:3000.0:4000.0": True},
            fav_ref_prices={"bnb": 625},
        )
    )

    store.save_config(AlertSyncRequest())

    assert store.get_state() == CheckerState()


def test_pending_favorite_alert_survives_sync_until_acknowledged(db) -> None:
    store = AlertStore()
    config = _config()
    store.save_config(config)
    state = store.get_state()
    state.pending_fav_alerts["bnb"] = PendingFavAlert(
        coin_id="bnb",
        coin_name="BNB",
        coin_symbol="BNB",
        direction="up",
        pct=5.0,
        current_price=630,
        ref_price=600,
    )
    store.update_state(state)

    store.save_config(config)

    pending = store.pending_fav_alerts()
    assert len(pending) == 1
    assert pending[0].coin_id == "bnb"
    assert store.dismiss_pending_fav_alert("bnb") is True
    assert store.pending_fav_alerts() == []
    assert store.dismiss_pending_fav_alert("bnb") is False


def test_removed_favorite_prunes_pending_badge(db) -> None:
    store = AlertStore()
    store.save_config(_config())
    state = store.get_state()
    state.pending_fav_alerts["bnb"] = PendingFavAlert(
        coin_id="bnb",
        coin_name="BNB",
        coin_symbol="BNB",
        direction="down",
        pct=4.0,
        current_price=576,
        ref_price=600,
    )
    store.update_state(state)

    store.save_config(AlertSyncRequest())

    assert store.pending_fav_alerts() == []


def test_persist_retries_transient_sqlite_lock(db, monkeypatch) -> None:
    store = AlertStore()
    calls = {"count": 0}

    def flaky_persist_once(**_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OperationalError("UPDATE alert_configs", {}, Exception("database is locked"))

    monkeypatch.setattr(store, "_persist_once", flaky_persist_once)
    monkeypatch.setattr("backend.app.notifications.alert_store.time.sleep", lambda _seconds: None)

    store.save_config(_config())

    assert calls["count"] == 3
