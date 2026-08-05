import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_port_check_rejects_invalid_port():
    resp = client.post("/api/v1/port-check", json={"host": "example.com", "port": 70000})
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_port_check_blocks_loopback_target():
    resp = client.post(
        "/api/v1/port-check", json={"host": "127.0.0.1", "port": 443, "timeout_seconds": 1}
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TARGET_NOT_ALLOWED"


def test_port_check_rejects_disallowed_port():
    resp = client.post(
        "/api/v1/port-check", json={"host": "example.com", "port": 9999, "timeout_seconds": 1}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "TARGET_NOT_ALLOWED"


def test_http_check_rejects_bad_scheme():
    resp = client.post("/api/v1/http-check", json={"url": "ftp://example.com"})
    # pydantic accepts any string for url field; scheme validation happens in service layer
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_http_check_rejects_credentials_in_url():
    resp = client.post("/api/v1/http-check", json={"url": "https://user:pass@example.com"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_dns_lookup_rejects_url_as_domain():
    resp = client.post("/api/v1/dns-lookup", json={"domain": "https://example.com", "record_type": "A"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_info_returns_envelope():
    resp = client.get("/api/v1/client-info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "client_ip" in body["data"]
    assert "protocol" in body["data"]


def test_rate_limit_returns_429_after_threshold():
    # port-check는 enforce_rate_limit 의존성이 걸려 있다.
    # 허용되지 않은 포트를 사용해 네트워크 호출 없이(403) 빠르게 한도를 채운다.
    from app.core.config import get_settings

    limit = get_settings().rate_limit_per_minute
    statuses = []
    for _ in range(limit + 3):
        resp = client.post(
            "/api/v1/port-check",
            json={"host": "example.com", "port": 9999, "timeout_seconds": 1},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses
