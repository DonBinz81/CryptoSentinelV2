from backend.app.data.market_data.http import _params_summary


def test_provider_log_summary_contains_counts_but_not_parameter_values() -> None:
    summary = _params_summary(
        {
            "id": "1,2,3",
            "symbol": "BTC,ETH",
            "limit": 200,
            "api_key": "must-not-be-logged",
        }
    )

    assert summary["id_count"] == 3
    assert summary["symbol_count"] == 2
    assert summary["limit"] == 200
    assert "api_key" not in summary["param_keys"]
    assert "1,2,3" not in str(summary)
    assert "BTC,ETH" not in str(summary)
    assert "must-not-be-logged" not in str(summary)
