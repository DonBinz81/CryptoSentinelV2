"""Per-device alert separation: each device gets only its own notifications."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.notifications import alert_store as alert_store_module
from backend.app.notifications import price_checker
from backend.app.notifications.alert_store import get_alert_store
from backend.app.api.routes import alerts as alerts_routes
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.alerts import AlertSyncRequest, PriceAlertItem


@pytest.fixture
def db(tmp_path: Path):
    """Fresh sync SQLite DB and clean per-device store cache for each test."""
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'test.db'}")
    create_all_sync()
    alert_store_module._instances.clear()
    yield
    alert_store_module._instances.clear()
    reset_sync_db()


@pytest.mark.asyncio
async def test_alert_sync_persists_off_event_loop(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_run_sync(func, request):
        calls["count"] += 1
        assert func is alerts_routes._save_alert_config
        assert request.device_id == "devA"

    monkeypatch.setattr(alerts_routes.anyio.to_thread, "run_sync", fake_run_sync)

    response = await alerts_routes.sync_alerts(AlertSyncRequest(device_id="devA"), None)

    assert response.status == "synced"
    assert calls["count"] == 1


def _price_config(device_id: str | None, coin_id: str, coin_name: str) -> AlertSyncRequest:
    return AlertSyncRequest(
        device_id=device_id,
        price_alerts=[
            PriceAlertItem(
                coin_id=coin_id,
                coin_name=coin_name,
                direction="above",
                threshold=100.0,
            )
        ],
    )


class _FakeFcm:
    def __init__(self) -> None:
        self.sent: list[tuple[tuple[str, ...], str, str]] = []
        self.payloads: list[dict] = []

    def send(self, tokens, title, body, severity, data, dry_run=False):
        self.sent.append((tuple(tokens), data["type"], data["coin_id"]))
        self.payloads.append(data)
        return SimpleNamespace(success_count=len(tokens))


def _fake_service(pairs: list[tuple[str, str | None]], fcm: _FakeFcm) -> SimpleNamespace:
    store = SimpleNamespace(tokens_with_device=lambda user_id: pairs)
    return SimpleNamespace(store=store, fcm=fcm)


def test_two_devices_keep_independent_configs(db) -> None:
    get_alert_store("devA").save_config(_price_config("devA", "bitcoin", "Bitcoin"))
    get_alert_store("devB").save_config(_price_config("devB", "ethereum", "Ethereum"))

    # Reload from DB to prove persistence keyed by device_id.
    alert_store_module._instances.clear()
    assert get_alert_store("devA").get_config().price_alerts[0].coin_id == "bitcoin"
    assert get_alert_store("devB").get_config().price_alerts[0].coin_id == "ethereum"
    # The legacy global store stays empty and separate.
    assert get_alert_store(None).get_config() is None


def test_sync_request_without_device_id_defaults_to_none(db) -> None:
    config = AlertSyncRequest(price_alerts=[])
    assert config.device_id is None


@pytest.mark.asyncio
async def test_price_checker_notifies_only_each_device_own_alerts(db, monkeypatch) -> None:
    get_alert_store("devA").save_config(_price_config("devA", "bitcoin", "Bitcoin"))
    get_alert_store("devB").save_config(_price_config("devB", "ethereum", "Ethereum"))

    fcm = _FakeFcm()
    monkeypatch.setattr(
        price_checker,
        "get_notification_service",
        lambda: _fake_service([("tokA", "devA"), ("tokB", "devB")], fcm),
    )

    async def _fake_fetch(coins, vs, registry=None):
        return {"bitcoin": {"usd": 120.0}, "ethereum": {"usd": 130.0}}

    monkeypatch.setattr(price_checker, "_fetch_prices", _fake_fetch)

    await price_checker.run_price_check()

    # Each token receives only its own coin.
    assert (("tokA",), "price_alert", "bitcoin") in fcm.sent
    assert (("tokB",), "price_alert", "ethereum") in fcm.sent
    # No cross-delivery.
    assert not any(tok == ("tokA",) and coin == "ethereum" for tok, _, coin in fcm.sent)
    assert not any(tok == ("tokB",) and coin == "bitcoin" for tok, _, coin in fcm.sent)


@pytest.mark.asyncio
async def test_legacy_token_without_device_uses_global_store(db, monkeypatch) -> None:
    # Config saved on the legacy global store (no device_id).
    get_alert_store(None).save_config(_price_config(None, "bitcoin", "Bitcoin"))

    fcm = _FakeFcm()
    monkeypatch.setattr(
        price_checker,
        "get_notification_service",
        lambda: _fake_service([("tokLegacy", None)], fcm),
    )

    async def _fake_fetch(coins, vs, registry=None):
        return {"bitcoin": {"usd": 120.0}}

    monkeypatch.setattr(price_checker, "_fetch_prices", _fake_fetch)

    await price_checker.run_price_check()

    assert (("tokLegacy",), "price_alert", "bitcoin") in fcm.sent


@pytest.mark.asyncio
async def test_crossing_alert_rearms_after_leaving_band(db, monkeypatch) -> None:
    get_alert_store("devA").save_config(
        AlertSyncRequest(
            device_id="devA",
            price_alerts=[
                PriceAlertItem(
                    coin_id="bitcoin",
                    coin_name="Bitcoin",
                    direction="above",
                    threshold=100.0,
                    crossing_only=True,
                    keep_active_after_trigger=True,
                    rearm_percent=1.0,
                    last_observed_price=99.0,
                )
            ],
        )
    )

    fcm = _FakeFcm()
    monkeypatch.setattr(
        price_checker,
        "get_notification_service",
        lambda: _fake_service([("tokA", "devA")], fcm),
    )

    prices = iter([100.2, 99.8, 101.2, 99.8])

    async def _fake_fetch(coins, vs, registry=None):
        return {"bitcoin": {"usd": next(prices)}}

    monkeypatch.setattr(price_checker, "_fetch_prices", _fake_fetch)

    await price_checker.run_price_check()
    await price_checker.run_price_check()
    await price_checker.run_price_check()
    await price_checker.run_price_check()

    assert len(fcm.sent) == 2
    assert [payload["cross_direction"] for payload in fcm.payloads] == ["up", "down"]
