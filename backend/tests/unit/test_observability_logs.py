from types import SimpleNamespace

from backend.app.api.routes.observability import tail_sanitized_logs


def test_tail_sanitized_logs_redacts_sensitive_values(tmp_path):
    log_file = tmp_path / "backend.log"
    log_file.write_text(
        '{"timestamp":"2026-06-19T10:00:00Z","level":"INFO","logger":"test","message":"api_key=abc123 token=secret-token ok"}\n',
        encoding="utf-8",
    )
    settings = SimpleNamespace(log_file_enabled=True, log_file_path=str(log_file))

    response = tail_sanitized_logs(settings, limit=10)

    assert response.available is True
    assert response.entries[0].level == "INFO"
    assert "abc123" not in response.entries[0].message
    assert "secret-token" not in response.entries[0].message
    assert "[REDACTED]" in response.entries[0].message


def test_tail_sanitized_logs_filters_level_and_search(tmp_path):
    log_file = tmp_path / "backend.log"
    log_file.write_text(
        "\n".join(
            [
                '{"level":"INFO","message":"heartbeat ok"}',
                '{"level":"ERROR","message":"provider unavailable"}',
            ]
        ),
        encoding="utf-8",
    )
    settings = SimpleNamespace(log_file_enabled=True, log_file_path=str(log_file))

    response = tail_sanitized_logs(settings, limit=10, level="ERROR", search="provider")

    assert len(response.entries) == 1
    assert response.entries[0].message == "provider unavailable"
