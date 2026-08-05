"""TCP 포트 연결 확인 서비스.

asyncio.open_connection()을 사용하여 TCP 연결 가능 여부를 확인한다.
"""
from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass
from typing import List

from app.core.security import assert_ip_allowed


class DnsFailedError(Exception):
    pass


@dataclass
class PortCheckResult:
    host: str
    resolved_ips: List[str]
    port: int
    open: bool
    result: str  # OPEN, REFUSED, TIMEOUT, DNS_FAILED, BLOCKED
    connection_time_ms: int | None
    message: str


async def _resolve(host: str) -> List[str]:
    try:
        ipaddr = socket_addr_or_none(host)
        if ipaddr:
            return [ipaddr]
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})
    except socket.gaierror as exc:
        raise DnsFailedError(str(exc)) from exc


def socket_addr_or_none(host: str) -> str | None:
    try:
        socket.inet_pton(socket.AF_INET, host)
        return host
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return host
    except OSError:
        pass
    return None


async def perform_port_check(host: str, port: int, timeout_seconds: float) -> PortCheckResult:
    try:
        ips = await _resolve(host)
    except DnsFailedError:
        return PortCheckResult(
            host=host,
            resolved_ips=[],
            port=port,
            open=False,
            result="DNS_FAILED",
            connection_time_ms=None,
            message="도메인을 IP로 변환하지 못했습니다.",
        )

    if not ips:
        return PortCheckResult(
            host=host,
            resolved_ips=[],
            port=port,
            open=False,
            result="DNS_FAILED",
            connection_time_ms=None,
            message="도메인을 IP로 변환하지 못했습니다.",
        )

    target_ip = ips[0]

    # SSRF 방지: 차단 대상 IP는 여기서 BLOCKED로 반환 (예외로 올려서 403을 줄 수도 있으나,
    # 라우터 레벨에서 TargetNotAllowedError로 잡아 403을 반환한다)
    assert_ip_allowed(target_ip)

    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target_ip, port), timeout=timeout_seconds
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return PortCheckResult(
            host=host,
            resolved_ips=ips,
            port=port,
            open=True,
            result="OPEN",
            connection_time_ms=elapsed_ms,
            message=f"{host}:{port} 포트가 열려 있습니다.",
        )
    except asyncio.TimeoutError:
        return PortCheckResult(
            host=host,
            resolved_ips=ips,
            port=port,
            open=False,
            result="TIMEOUT",
            connection_time_ms=None,
            message="제한 시간 내에 응답이 없습니다.",
        )
    except ConnectionRefusedError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return PortCheckResult(
            host=host,
            resolved_ips=ips,
            port=port,
            open=False,
            result="REFUSED",
            connection_time_ms=elapsed_ms,
            message="대상 서버가 연결을 거부했습니다.",
        )
    except OSError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return PortCheckResult(
            host=host,
            resolved_ips=ips,
            port=port,
            open=False,
            result="BLOCKED",
            connection_time_ms=elapsed_ms,
            message="연결이 차단되었거나 네트워크 오류가 발생했습니다.",
        )
