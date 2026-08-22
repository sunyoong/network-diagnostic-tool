import json
import logging

from app.core.logging import JsonLinesFormatter


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

