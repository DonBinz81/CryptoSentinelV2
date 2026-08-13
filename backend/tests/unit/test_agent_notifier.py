"""Test unitari per AgentNotifier — mock di FCM/NotificationService."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.app.notifications.agent_notifier import AgentNotifier
from backend.app.schemas.notification_prefs import NotificationPreferences


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_settings(
    *,
    fcm_enabled: bool = True,
    notify_dry_run_trades: bool = False,
) -> MagicMock:
    s = MagicMock()
    s.fcm_enabled = fcm_enabled
    s.fcm_token_store_path = "backend/storage/fcm_tokens.json"
    s.notify_dry_run_trades = notify_dry_run_trades
    s.fcm_spot_topic = "cryptosentinel-spot"
    s.fcm_perp_topic = "cryptosentinel-perp"
    s.fcm_risk_topic = "cryptosentinel-risk"
    s.fcm_summary_topic = "cryptosentinel-summary"
    s.fcm_critical_topic = "cryptosentinel-critical"
    return s


def _make_fcm_result(success: int = 1, failure: int = 0) -> MagicMock:
    result = MagicMock()
    result.success_count = success
    result.failure_count = failure
    result.status = "sent" if success > 0 else "failed"
    return result


USER_ID = "00000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notifier_with_mocks(settings=None, tokens=None, fcm_result=None):
    """Crea un AgentNotifier con DeviceTokenStore e FCM mockati."""
    settings = settings or _make_settings()
    tokens = tokens if tokens is not None else ["tok1"]
    fcm_result = fcm_result or _make_fcm_result()

    notifier = AgentNotifier(settings)

    mock_store = MagicMock()
    mock_store.tokens_for_user.return_value = tokens
    notifier._store = mock_store

    mock_fcm = MagicMock()
    mock_fcm.send.return_value = fcm_result

    mock_svc = MagicMock()
    mock_svc.fcm = mock_fcm

    return notifier, mock_fcm, mock_svc


# ---------------------------------------------------------------------------
# test_notify_trade_opened
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_trade_opened_spot():
    """Apertura trade spot notifica con topic cryptosentinel-spot."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()

    store: dict[str, str] = {}

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_trade_opened(
            user_id=USER_ID,
            trade_id="trade_001",
            asset="BTC",
            market="spot",
            direction="buy",
            entry_price=Decimal("50000"),
            size_usd=Decimal("100"),
            stop_loss=Decimal("48000"),
            is_dry_run=False,
        )

    assert result is True
    call_kwargs = mock_fcm.send.call_args
    data = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data") or call_kwargs[0][3]
    # Il topic deve essere quello spot
    sent_data = mock_fcm.send.call_args[1].get("data") or mock_fcm.send.call_args.kwargs.get("data") or {}
    assert "cryptosentinel-spot" in str(sent_data)


@pytest.mark.asyncio
async def test_notify_trade_opened_perp():
    """Apertura trade perp usa topic cryptosentinel-perp."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    store: dict[str, str] = {}

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", lambda u, k, v: store.update({k: v})),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_trade_opened(
            user_id=USER_ID,
            trade_id="trade_002",
            asset="ETH",
            market="perp",
            direction="long",
            entry_price=Decimal("3000"),
            size_usd=Decimal("200"),
            stop_loss=None,
            is_dry_run=False,
        )

    assert result is True
    sent_data = mock_fcm.send.call_args.kwargs.get("data") or {}
    assert "cryptosentinel-perp" in str(sent_data)


# ---------------------------------------------------------------------------
# test_notify_dry_run_blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_dry_run_blocked():
    """dry_run non genera notifica (né apertura né chiusura) se notify_dry_run_trades=False."""
    settings = _make_settings(notify_dry_run_trades=False)
    notifier, mock_fcm, mock_svc = _notifier_with_mocks(settings=settings)

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        open_result = await notifier.notify_trade_opened(
            user_id=USER_ID,
            trade_id="dry_001",
            asset="BTC",
            market="spot",
            direction="buy",
            entry_price=Decimal("50000"),
            size_usd=Decimal("100"),
            stop_loss=None,
            is_dry_run=True,
        )
        close_result = await notifier.notify_trade_closed(
            user_id=USER_ID,
            trade_id="dry_cls_001",
            asset="BTC",
            market="spot",
            pnl_usd=Decimal("5"),
            pnl_pct=Decimal("5"),
            close_reason="take_profit_1",
            is_dry_run=True,
        )

    assert open_result is False
    assert close_result is False
    mock_fcm.send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_dry_run_allowed_when_enabled():
    """dry_run notifica quando notify_dry_run_trades=True."""
    settings = _make_settings(notify_dry_run_trades=True)
    notifier, mock_fcm, mock_svc = _notifier_with_mocks(settings=settings)
    store: dict[str, str] = {}

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", lambda u, k: store.get(k)),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", lambda u, k, v: store.update({k: v})),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_trade_opened(
            user_id=USER_ID,
            trade_id="dry_002",
            asset="ETH",
            market="spot",
            direction="buy",
            entry_price=Decimal("3000"),
            size_usd=Decimal("50"),
            stop_loss=None,
            is_dry_run=True,
        )

    assert result is True
    mock_fcm.send.assert_called_once()


# ---------------------------------------------------------------------------
# test_idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotency():
    """Stesso trade_id non genera doppia notifica."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    store: dict[str, str] = {}

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    kwargs = dict(
        user_id=USER_ID,
        trade_id="trade_idem_001",
        asset="ADA",
        market="spot",
        direction="buy",
        entry_price=Decimal("1.5"),
        size_usd=Decimal("75"),
        stop_loss=None,
        is_dry_run=False,
    )

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        r1 = await notifier.notify_trade_opened(**kwargs)
        r2 = await notifier.notify_trade_opened(**kwargs)  # stesso trade_id

    assert r1 is True
    assert r2 is False
    assert mock_fcm.send.call_count == 1


# ---------------------------------------------------------------------------
# test_risk_no_spam
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risk_no_spam():
    """Stesso alert_type + detail non re-notifica."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    store: dict[str, str] = {}

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        r1 = await notifier.notify_risk_alert(USER_ID, "drawdown", "Drawdown 12.0% supera soglia 10%")
        r2 = await notifier.notify_risk_alert(USER_ID, "drawdown", "Drawdown 12.0% supera soglia 10%")

    assert r1 is True
    assert r2 is False
    assert mock_fcm.send.call_count == 1


@pytest.mark.asyncio
async def test_risk_different_detail_resends():
    """Dettaglio diverso genera nuova notifica rischio."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    store: dict[str, str] = {}

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        r1 = await notifier.notify_risk_alert(USER_ID, "drawdown", "Drawdown 10.5%")
        r2 = await notifier.notify_risk_alert(USER_ID, "drawdown", "Drawdown 11.0%")  # dettaglio diverso

    assert r1 is True
    assert r2 is True
    assert mock_fcm.send.call_count == 2


# ---------------------------------------------------------------------------
# test_preferences_gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preferences_gate_spot_off():
    """Disattivare spot_trades blocca push spot, non tocca perp."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    prefs_json = json.dumps({"spot_trades": False, "perp_trades": True, "risk_alerts": True, "daily_summary": True, "critical": True})
    store: dict[str, str] = {
        f"{USER_ID}:{AgentNotifier.PREFS_KEY}": prefs_json,
    }

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        spot_result = await notifier.notify_trade_opened(
            user_id=USER_ID, trade_id="t_spot", asset="BTC", market="spot",
            direction="buy", entry_price=Decimal("50000"), size_usd=Decimal("100"),
            stop_loss=None, is_dry_run=False,
        )
        perp_result = await notifier.notify_trade_opened(
            user_id=USER_ID, trade_id="t_perp", asset="ETH", market="perp",
            direction="long", entry_price=Decimal("3000"), size_usd=Decimal("100"),
            stop_loss=None, is_dry_run=False,
        )

    assert spot_result is False
    assert perp_result is True
    assert mock_fcm.send.call_count == 1


# ---------------------------------------------------------------------------
# test_preferences_round_trip
# ---------------------------------------------------------------------------

def test_preferences_round_trip():
    """get dopo set ritorna gli stessi valori."""
    notifier = AgentNotifier(_make_settings())
    store: dict[str, str] = {}

    def fake_get(user_id: str, key: str):
        return store.get(f"{user_id}:{key}")

    def fake_set(user_id: str, key: str, value: str):
        store[f"{user_id}:{key}"] = value

    prefs = NotificationPreferences(
        spot_trades=True,
        perp_trades=False,
        risk_alerts=True,
        daily_summary=False,
        critical=True,
    )

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", side_effect=fake_get),
        patch("backend.app.notifications.agent_notifier.set_runtime_value", side_effect=fake_set),
    ):
        notifier.set_preferences(USER_ID, prefs)
        loaded = notifier.get_preferences(USER_ID)

    assert loaded.spot_trades is True
    assert loaded.perp_trades is False
    assert loaded.risk_alerts is True
    assert loaded.daily_summary is False
    assert loaded.critical is True


# ---------------------------------------------------------------------------
# test_daily_summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_summary():
    """Riepilogo giornaliero invia con spot/perp separati e PnL."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_daily_summary(
            user_id=USER_ID,
            spot_trades=5,
            perp_trades=3,
            daily_pnl_usd=Decimal("42.50"),
            win_rate_pct=66.7,
        )

    assert result is True
    call_kwargs = mock_fcm.send.call_args.kwargs
    assert "Riepilogo" in call_kwargs.get("title", "")
    body = call_kwargs.get("body", "")
    assert "5" in body  # spot_trades
    assert "3" in body  # perp_trades
    assert "42.50" in body  # pnl


@pytest.mark.asyncio
async def test_daily_summary_blocked_by_pref():
    """Riepilogo non inviato se daily_summary=False nelle preferenze."""
    notifier, mock_fcm, mock_svc = _notifier_with_mocks()
    prefs_json = json.dumps({
        "spot_trades": True, "perp_trades": True,
        "risk_alerts": True, "daily_summary": False, "critical": True,
    })
    store = {f"{USER_ID}:{AgentNotifier.PREFS_KEY}": prefs_json}

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", lambda u, k: store.get(f"{u}:{k}")),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_daily_summary(
            user_id=USER_ID, spot_trades=1, perp_trades=0,
            daily_pnl_usd=Decimal("10"), win_rate_pct=100.0,
        )

    assert result is False
    mock_fcm.send.assert_not_called()


# ---------------------------------------------------------------------------
# test fcm_disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fcm_disabled_returns_false():
    """Se FCM non abilitato, _send ritorna False senza chiamare il client."""
    settings = _make_settings(fcm_enabled=False)
    notifier, mock_fcm, mock_svc = _notifier_with_mocks(settings=settings)

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
        patch("backend.app.notifications.agent_notifier.get_notification_service", return_value=mock_svc),
    ):
        result = await notifier.notify_daily_summary(
            user_id=USER_ID, spot_trades=1, perp_trades=1,
            daily_pnl_usd=Decimal("5"), win_rate_pct=50.0,
        )

    assert result is False
    mock_fcm.send.assert_not_called()
