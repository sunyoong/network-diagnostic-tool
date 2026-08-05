"""SSRF 방지 및 입력 대상 검증.

- 루프백, 링크로컬, 멀티캐스트, 메타데이터 주소, 사설 IP 차단
- URL 인증정보(user:password@host) 차단
- 도메인/호스트 형식 검증
- 요청 횟수 제한(간단한 인메모리 슬라이딩 윈도우, 단일 프로세스 기준)
"""
from __future__ import annotations

import ipaddress
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict
from urllib.parse import urlsplit

from app.core.config import get_settings

# 클라우드 메타데이터 및 기타 알려진 위험 주소
_METADATA_ADDRESSES = {
    "169.254.169.254",  # AWS/GCP/Azure 메타데이터
    "100.100.100.200",  # 알리바바 클라우드 메타데이터
    "fd00:ec2::254",  # AWS IMDSv2 IPv6
}

_DOMAIN_LABEL_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


class TargetNotAllowedError(Exception):
    """대상 주소가 접근 허용 정책을 위반할 때 발생."""


class ValidationError(Exception):
    """입력 형식이 잘못되었을 때 발생."""


def is_blocked_ip(ip_str: str) -> bool:
    """루프백, 링크로컬, 멀티캐스트, 예약, 사설, 메타데이터 주소인지 확인한다."""
    if ip_str in _METADATA_ADDRESSES:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        # IP로 파싱할 수 없으면 상위 로직에서 별도 처리 (DNS 실패 등)
        return True

    if (
        addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or addr.is_private
    ):
        return True

    # IPv4-mapped IPv6 (::ffff:127.0.0.1 등) 처리
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return is_blocked_ip(str(addr.ipv4_mapped))

    return False


def assert_ip_allowed(ip_str: str) -> None:
    settings = get_settings()
    if settings.allow_private_targets:
        return
    if is_blocked_ip(ip_str):
        raise TargetNotAllowedError(f"허용되지 않은 대상 주소입니다: {ip_str}")


def validate_domain(domain: str) -> str:
    """순수 도메인 형식(스킴/경로/포트 없음)을 검증하고 IDNA로 정규화한다."""
    if not domain or len(domain) > 253:
        raise ValidationError("도메인 형식이 올바르지 않습니다.")
    if "://" in domain or "/" in domain or domain.count(":") > 0:
        raise ValidationError("도메인만 입력해야 합니다 (스킴, 경로, 포트 제외).")

    try:
        idna_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("도메인 형식이 올바르지 않습니다.") from exc

    labels = idna_domain.rstrip(".").split(".")
    if len(labels) < 2:
        raise ValidationError("도메인 형식이 올바르지 않습니다.")
    for label in labels:
        if len(label) > 63 or not _DOMAIN_LABEL_RE.match(label):
            raise ValidationError("도메인 형식이 올바르지 않습니다.")

    return idna_domain


def validate_host(host: str) -> str:
    """TCP 포트 확인용 호스트(IPv4/IPv6/도메인)를 검증한다."""
    if not host or len(host) > 253:
        raise ValidationError("호스트 형식이 올바르지 않습니다.")
    if "://" in host or "/" in host:
        raise ValidationError("호스트 형식이 올바르지 않습니다.")

    # IPv6 대괄호 표기 허용
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        pass

    return validate_domain(host)


def validate_url(url: str) -> str:
    """HTTP(S) URL 형식을 검증한다. http/https 스킴만 허용, 인증정보 금지."""
    if not url or len(url) > 2048:
        raise ValidationError("URL은 2,048자를 초과할 수 없습니다.")

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValidationError("http 또는 https 스킴만 허용됩니다.")
    if parts.username or parts.password:
        raise ValidationError("URL에 인증정보를 포함할 수 없습니다.")
    if not parts.hostname:
        raise ValidationError("URL에 호스트가 없습니다.")

    validate_host(parts.hostname)
    return url


def assert_port_allowed(port: int) -> None:
    settings = get_settings()
    if not (1 <= port <= 65535):
        raise ValidationError("포트는 1~65535 범위여야 합니다.")
    if settings.allow_private_targets:
        # 사내/인증된 환경에서는 허용 목록 정책을 완화할 수 있음
        return
    if settings.allowed_tcp_ports and port not in settings.allowed_tcp_ports:
        raise TargetNotAllowedError(
            f"포트 {port}는 공개 서비스에서 허용되지 않습니다."
        )


def assert_domain_allowlisted(domain: str) -> None:
    settings = get_settings()
    if not settings.allowed_target_domains:
        return
    normalized = domain.rstrip(".").lower()
    for allowed in settings.allowed_target_domains:
        allowed_norm = allowed.rstrip(".").lower()
        if normalized == allowed_norm or normalized.endswith("." + allowed_norm):
            return
    raise TargetNotAllowedError(f"허용되지 않은 도메인입니다: {domain}")


# --------------------------------------------------------------------------
# 요청 횟수 제한 (분당 N회, 클라이언트 IP 기준, 인메모리 슬라이딩 윈도우)
# 단일 워커 프로세스 환경을 가정한다. 다중 워커/인스턴스 환경에서는
# Redis 등 공유 저장소 기반 구현으로 교체해야 한다.
# --------------------------------------------------------------------------
@dataclass
class _RateWindow:
    hits: Deque[float]


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._windows: Dict[str, _RateWindow] = defaultdict(lambda: _RateWindow(deque()))

    def check(self, key: str) -> bool:
        """허용되면 True, 초과되면 False를 반환한다."""
        now = time.monotonic()
        window = self._windows[key]
        cutoff = now - 60.0
        while window.hits and window.hits[0] < cutoff:
            window.hits.popleft()
        if len(window.hits) >= self._limit:
            return False
        window.hits.append(now)
        return True


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(get_settings().rate_limit_per_minute)
    return _rate_limiter
