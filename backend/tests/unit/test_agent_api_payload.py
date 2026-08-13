from backend.app.api.routes.agent import AgentEvaluateRequest


def test_agent_evaluate_request_accepts_flat_payload() -> None:
    request = AgentEvaluateRequest.model_validate({"asset": "CAKE", "market": "spot"})

    assert request.normalized_payload() == {"asset": "CAKE"}


def test_agent_evaluate_request_nested_payload_wins_over_flat_fields() -> None:
    request = AgentEvaluateRequest.model_validate(
        {
            "asset": "IGNORED",
            "market": "spot",
            "payload": {"asset": "CAKE", "candles": []},
        }
    )

    assert request.normalized_payload()["asset"] == "CAKE"
