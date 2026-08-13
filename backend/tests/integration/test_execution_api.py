from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_admin_access, require_read_access
from backend.app.api.routes.execution import router
from backend.app.execution.service import get_execution_service


class StubExecutionService:
    def status(self) -> dict[str, Any]:
        return {
            "network": "testnet",
            "testnet_only": True,
            "spot": {"provider": "twak"},
            "perp": {"identity": "erc8004", "commerce": "erc8183"},
        }

    async def competition_registration_status(self) -> dict[str, Any]:
        return {"configured": True, "registered": True, "chain_id": 56}


def test_execution_api_response_and_auth_boundaries() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_execution_service] = StubExecutionService
    app.dependency_overrides[require_read_access] = lambda: None
    app.dependency_overrides[require_admin_access] = lambda: None
    client = TestClient(app)

    status = client.get("/api/v1/execution/status")
    assert status.status_code == 200
    assert status.json()["spot"]["provider"] == "twak"
    assert status.json()["perp"]["identity"] == "erc8004"

    competition = client.get("/api/v1/execution/competition/status")
    assert competition.status_code == 200
    assert competition.json() == {"configured": True, "registered": True, "chain_id": 56}
