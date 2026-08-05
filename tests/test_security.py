import pytest

from app.core.security import (
    TargetNotAllowedError,
    ValidationError,
    assert_ip_allowed,
    assert_port_allowed,
    is_blocked_ip,
    validate_domain,
    validate_host,
    validate_url,
)


class TestIsBlockedIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",       # 루프백
            "169.254.169.254", # 클라우드 메타데이터/링크로컬
            "10.0.0.5",        # 사설
            "172.16.0.5",      # 사설
            "192.168.1.1",     # 사설
            "224.0.0.1",       # 멀티캐스트
            "::1",             # IPv6 루프백
            "fe80::1",         # IPv6 링크로컬
            "fc00::1",         # IPv6 ULA(사설)
        ],
    )
    def test_blocked_addresses(self, ip):
        assert is_blocked_ip(ip) is True

    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
    def test_public_addresses(self, ip):
        assert is_blocked_ip(ip) is False


class TestValidateUrl:
    def test_accepts_https(self):
        assert validate_url("https://example.com/path") == "https://example.com/path"

    def test_rejects_bad_scheme(self):
        with pytest.raises(ValidationError):
            validate_url("ftp://example.com")

    def test_rejects_credentials(self):
        with pytest.raises(ValidationError):
            validate_url("https://user:pass@example.com")

    def test_rejects_url_without_host(self):
        with pytest.raises(ValidationError):
            validate_url("https:///path-only")


class TestValidateDomain:
    def test_accepts_simple_domain(self):
        assert validate_domain("example.com") == "example.com"

    def test_rejects_scheme(self):
        with pytest.raises(ValidationError):
            validate_domain("https://example.com")

    def test_rejects_path(self):
        with pytest.raises(ValidationError):
            validate_domain("example.com/path")

    def test_rejects_single_label(self):
        with pytest.raises(ValidationError):
            validate_domain("localhost")


class TestValidateHost:
    def test_accepts_ipv4(self):
        assert validate_host("8.8.8.8") == "8.8.8.8"

    def test_accepts_domain(self):
        assert validate_host("example.com") == "example.com"

    def test_rejects_url(self):
        with pytest.raises(ValidationError):
            validate_host("https://example.com")


class TestAssertIpAllowed:
    def test_blocks_private_ip(self):
        with pytest.raises(TargetNotAllowedError):
            assert_ip_allowed("192.168.1.1")

    def test_allows_public_ip(self):
        assert_ip_allowed("8.8.8.8")  # 예외 없이 통과해야 함


class TestAssertPortAllowed:
    def test_allows_listed_port(self):
        assert_port_allowed(443)  # 예외 없이 통과해야 함

    def test_rejects_unlisted_port(self):
        with pytest.raises(TargetNotAllowedError):
            assert_port_allowed(9999)

    def test_rejects_out_of_range_port(self):
        with pytest.raises(ValidationError):
            assert_port_allowed(70000)
