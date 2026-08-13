from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.core.security.auth import AuthScope, require_scope


def _request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


@pytest.fixture
def settings() -> SimpleNamespace:
    return SimpleNamespace(
        auth_configured=True,
        api_read_token="read-token",
        api_admin_token="admin-token",
        api_device_token="device-token",
        api_alerts_token="alerts-token",
    )


def test_device_and_alert_scopes_are_separate(settings: SimpleNamespace) -> None:
    assert require_scope(_request("device-token"), settings, AuthScope.DEVICE) == AuthScope.DEVICE
    assert require_scope(_request("alerts-token"), settings, AuthScope.ALERTS) == AuthScope.ALERTS

    with pytest.raises(HTTPException) as device_for_alerts:
        require_scope(_request("device-token"), settings, AuthScope.ALERTS)
    assert device_for_alerts.value.status_code == 401

    with pytest.raises(HTTPException) as alerts_for_device:
        require_scope(_request("alerts-token"), settings, AuthScope.DEVICE)
    assert alerts_for_device.value.status_code == 401


def test_admin_satisfies_both_limited_scopes(settings: SimpleNamespace) -> None:
    assert require_scope(_request("admin-token"), settings, AuthScope.DEVICE) == AuthScope.DEVICE
    assert require_scope(_request("admin-token"), settings, AuthScope.ALERTS) == AuthScope.ALERTS
