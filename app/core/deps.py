from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.core.security import get_rate_limiter

_semaphore: asyncio.Semaphore | None = None


def get_diagnostic_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_diagnostics)
    return _semaphore


def get_real_client_ip(request: Request) -> str:
    """신뢰 프록시를 통해 들어온 요청일 때만 X-Forwarded-For를 신뢰한다."""
    settings = get_settings()
    direct_ip = request.client.host if request.client else "unknown"

    if direct_ip in settings.trusted_proxy_ips:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # 가장 왼쪽 값이 최초 클라이언트 IP (프록시 체인 규약)
            return forwarded.split(",")[0].strip()

    return direct_ip


def enforce_rate_limit(request: Request) -> None:
    client_ip = get_real_client_ip(request)
    limiter = get_rate_limiter()
    if not limiter.check(client_ip):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "요청 횟수 제한을 초과했습니다. 잠시 후 다시 시도해 주세요.",
            },
        )
