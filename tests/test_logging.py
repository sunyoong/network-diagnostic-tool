import json
import logging
import pytest

from app.core.logging import JsonLinesFormatter
from app.services.auth_service import add_auth_event


def test_json_lines_formatter_emits_required_elastic_fields():
    record = logging.LogRecord("ndt.test", logging.INFO, __file__, 1, "http_check", (), None)
    record.event = "http_check"
    record.event_fields = {
        "request_id": "req-001",
        "api_path": "/api/v1/http-check",
        "target_host": "example.com",
        "success": True,
        "duration_ms": 120,
    }

    line = JsonLinesFormatter("local").format(record)
    parsed = json.loads(line)

    assert "\n" not in line
    assert parsed["timestamp"].endswith("Z")
    assert parsed["level"] == "INFO"
    assert parsed["service"] == "network-diagnostic"
    assert parsed["environment"] == "local"
    assert parsed["event"] == "http_check"
    assert parsed["request_id"] == "req-001"
    assert parsed["success"] is True
    assert parsed["duration_ms"] == 120


def test_http_audit_log_omits_query_and_sensitive_headers(caplog):
    from fastapi.testclient import TestClient
    from app.main import app

    caplog.set_level(logging.INFO, logger="ndt.audit")
    response = TestClient(app).get(
        "/health?token=do-not-log",
        headers={"Authorization": "Bearer secret", "Cookie": "session=secret"},
    )

    record = next(record for record in caplog.records if getattr(record, "event", None) == "http_request")
    fields = record.event_fields
    assert response.headers["X-Request-ID"] == fields["request_id"]
    assert fields["api_path"] == "/health"
    serialized = json.dumps(fields)
    assert "do-not-log" not in serialized
    assert "Bearer secret" not in serialized
    assert "session=secret" not in serialized
    assert "client_ip" not in fields
    assert "client_key" in fields


@pytest.mark.asyncio
async def test_auth_audit_details_are_allow_listed(caplog):
    class Connection:
        values = None

        async def execute(self, _sql, *values):
            self.values = values

    connection = Connection()
    caplog.set_level(logging.INFO, logger="ndt.auth_audit")
    await add_auth_event(
        connection, "ACCOUNT_UPDATED", "SUCCESS",
        details={"role": "VIEWER", "email": "private@example.com", "display_name": "Private"},
    )

    stored_details = json.loads(connection.values[7])
    assert stored_details == {"role": "VIEWER"}
    record = next(record for record in caplog.records if getattr(record, "event", None) == "auth_audit")
    assert "private@example.com" not in json.dumps(record.event_fields)

