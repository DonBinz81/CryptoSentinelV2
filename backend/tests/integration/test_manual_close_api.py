"""HTTP contract of the manual Perp close endpoint.

Covers what the engine-level tests cannot see: that the route is really behind
the admin dependency, and that each business outcome maps to the status code the
app is told to expect. The economics are tested in ``test_manual_close_perp.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_session, require_admin_access
from backend.app.api.routes import agent as agent_routes
from backend.app.api.routes.agent import router

PATH = "/api/v1/agent/positions/perp/pos_test/close"
BODY = {"percentage": 50, "expected_size": "10", "note": "test"}
HEADERS = {"Idempotency-Key": "key-http-000001"}


class StubAgentService:
    """Records the call and returns a canned outcome."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def manual_close_perp_position(self, session, **kwargs) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.result


def _client(result: dict[str, Any], *, admin_ok: bool = True) -> tuple[TestClient, StubAgentService]:
    app = FastAPI()
    app.include_router(router)

    async def _session():
        yield None

    app.dependency_overrides[get_session] = _session
    if admin_ok:
        app.dependency_overrides[require_admin_access] = lambda: None
    else:
        def _deny():
            raise HTTPException(status_code=403, detail="admin token required")

        app.dependency_overrides[require_admin_access] = _deny

    stub = StubAgentService(result)
    agent_routes.get_agent_service = lambda: stub  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False), stub


CONFIRMED = {
    "status": "confirmed",
    "outcome": "confirmed",
    "position_id": "pos_test",
    "executed_qty": "5",
    "remaining_qty": "5",
    "position_status": "open",
    "close_reason": "manual_partial_close",
}


# ── authentication ─────────────────────────────────────────────────────────


def test_admin_token_is_accepted() -> None:
    client, _ = _client(CONFIRMED)
    response = client.post(PATH, json=BODY, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["outcome"] == "confirmed"


def test_non_admin_is_refused() -> None:
    """The route must sit behind require_admin_access, not merely read access.

    If someone swapped the dependency, this override would no longer apply and
    the call would succeed -- which is exactly the regression to catch.
    """
    client, stub = _client(CONFIRMED, admin_ok=False)
    response = client.post(PATH, json=BODY, headers=HEADERS)
    assert response.status_code == 403
    assert stub.calls == []  # refused before reaching the engine


# ── request validation ─────────────────────────────────────────────────────


def test_missing_idempotency_key_is_refused() -> None:
    client, stub = _client(CONFIRMED)
    response = client.post(PATH, json=BODY)
    assert response.status_code == 422
    assert stub.calls == []


@pytest.mark.parametrize("percentage", [10, 30, 99, 0, 101, -50])
def test_percentages_outside_the_presets_are_refused(percentage: int) -> None:
    client, stub = _client(CONFIRMED)
    response = client.post(
        PATH, json={**BODY, "percentage": percentage}, headers=HEADERS
    )
    assert response.status_code == 422
    assert stub.calls == []


@pytest.mark.parametrize("percentage", [25, 50, 75, 100])
def test_the_four_presets_are_accepted(percentage: int) -> None:
    client, stub = _client(CONFIRMED)
    response = client.post(
        PATH, json={**BODY, "percentage": percentage}, headers=HEADERS
    )
    assert response.status_code == 200
    assert stub.calls[0]["percentage"] == percentage


def test_missing_expected_size_is_refused() -> None:
    """Without it the stale-position guard cannot work, so it is mandatory."""
    client, stub = _client(CONFIRMED)
    response = client.post(PATH, json={"percentage": 50}, headers=HEADERS)
    assert response.status_code == 422
    assert stub.calls == []


def test_the_note_is_length_limited() -> None:
    client, stub = _client(CONFIRMED)
    response = client.post(
        PATH, json={**BODY, "note": "x" * 500}, headers=HEADERS
    )
    assert response.status_code == 422
    assert stub.calls == []


def test_the_request_reaches_the_engine_intact() -> None:
    client, stub = _client(CONFIRMED)
    client.post(PATH, json=BODY, headers=HEADERS)
    call = stub.calls[0]
    assert call["position_id"] == "pos_test"
    assert call["percentage"] == 50
    assert str(call["expected_size"]) == "10"
    assert call["idempotency_key"] == "key-http-000001"
    assert call["note"] == "test"


# ── outcome -> status code ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("confirmed", 200),
        ("stale_position", 409),
        ("already_closed", 409),
        ("key_reused_with_different_payload", 409),
        ("in_progress", 409),
        ("invalid_request", 422),
        ("not_found", 404),
        ("execution_failed", 502),
    ],
)
def test_every_outcome_maps_to_its_status_code(outcome: str, expected_status: int) -> None:
    client, _ = _client({"status": "rejected", "outcome": outcome, "position_id": "pos_test"})
    response = client.post(PATH, json=BODY, headers=HEADERS)
    assert response.status_code == expected_status
    # The precise outcome always travels in the body, whatever the code.
    assert response.json()["outcome"] == outcome


def test_an_unknown_outcome_does_not_break_the_response() -> None:
    """A future outcome with no mapping must still return its body, not a 500."""
    client, _ = _client({"status": "confirmed", "outcome": "something_new"})
    response = client.post(PATH, json=BODY, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["outcome"] == "something_new"
