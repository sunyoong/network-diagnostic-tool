"""HTTP/HTTPS 상태 확인 서비스.

httpx.AsyncClient로 비동기 요청을 수행하되, 리다이렉트를 자동으로 따라가지
않고 단계별로 직접 처리하여 매 홉마다 대상 IP를 재검증한다(SSRF 방지).
"""
from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.security import (
    TargetNotAllowedError,
    ValidationError,
    assert_ip_allowed,
    validate_url,
)


class DnsFailedError(Exception):
    pass


@dataclass
class HttpCheckResult:
    url: str
    final_url: Optional[str]
    reachable: bool
    status_code: Optional[int]
    reason_phrase: Optional[str]
    resolved_ip: Optional[str]
    response_time_ms: int
    content_length: Optional[int]
    content_type: Optional[str]
    server: Optional[str]
    redirect_count: int


async def _resolve_and_validate(hostname: str) -> List[str]:
    """호스트명을 IP로 해석하고 SSRF 정책에 따라 검증한다."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DnsFailedError(f"DNS 조회에 실패했습니다: {hostname}") from exc

    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise DnsFailedError(f"DNS 조회에 실패했습니다: {hostname}")

    for ip in ips:
        assert_ip_allowed(ip)  # 하나라도 차단 대상이면 예외 발생

    return ips


async def perform_http_check(
    url: str,
    method: str,
    timeout_seconds: float,
    follow_redirects: bool,
) -> HttpCheckResult:
    settings = get_settings()
    validate_url(url)  # 스킴, 인증정보, 호스트 형식 검증 (ValidationError 발생 가능)

    start = time.monotonic()
    current_url = url
    redirect_count = 0
    resolved_ip: Optional[str] = None
    limits = httpx.Limits(max_connections=settings.max_concurrent_diagnostics)
    timeout = httpx.Timeout(timeout_seconds)

    async with httpx.AsyncClient(
        limits=limits, timeout=timeout, follow_redirects=False
    ) as client:
        while True:
            parts = urlsplit(current_url)
            ips = await _resolve_and_validate(parts.hostname)
            resolved_ip = ips[0]

            request = client.build_request(method, current_url)
            try:
                response = await client.send(request, stream=True)
            except httpx.ConnectTimeout as exc:
                raise TimeoutError(f"연결 시간 초과: {current_url}") from exc
            except httpx.ReadTimeout as exc:
                raise TimeoutError(f"응답 시간 초과: {current_url}") from exc
            except httpx.ConnectError as exc:
                raise ConnectionRefusedError(f"연결이 거부되었습니다: {current_url}") from exc
            except httpx.TransportError as exc:
                # TLS 오류 등 기타 전송 계층 오류
                raise TlsOrTransportError(str(exc)) from exc

            is_redirect = (
                follow_redirects
                and response.is_redirect
                and "location" in response.headers
                and redirect_count < settings.max_redirects
            )

            if not is_redirect:
                # 본문 크기를 제한하여 수신 (Content-Length 확인용, 저장하지 않음)
                content_length_header = response.headers.get("content-length")
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received >= settings.max_response_bytes:
                        break
                await response.aclose()

                elapsed_ms = int((time.monotonic() - start) * 1000)
                content_length = (
                    int(content_length_header)
                    if content_length_header and content_length_header.isdigit()
                    else (received or None)
                )
                return HttpCheckResult(
                    url=url,
                    final_url=current_url,
                    reachable=True,
                    status_code=response.status_code,
                    reason_phrase=response.reason_phrase,
                    resolved_ip=resolved_ip,
                    response_time_ms=elapsed_ms,
                    content_length=content_length,
                    content_type=response.headers.get("content-type"),
                    server=response.headers.get("server"),
                    redirect_count=redirect_count,
                )

            # 리다이렉트 처리: Location 헤더를 기준으로 다음 URL을 계산하고 루프를 계속한다
            # (다음 반복 시작 시 새 URL의 호스트를 다시 DNS 조회·검증한다).
            location = response.headers["location"]
            await response.aclose()
            current_url = str(httpx.URL(current_url).join(location))
            validate_url(current_url)  # 스킴 다운그레이드·인증정보 삽입 등 재검증
            redirect_count += 1
            if redirect_count > settings.max_redirects:
                raise TooManyRedirectsError("리다이렉트 횟수 제한을 초과했습니다.")


class TlsOrTransportError(Exception):
    pass


class TooManyRedirectsError(Exception):
    pass
