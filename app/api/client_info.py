from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request

from app.core.auth_deps import require_roles
from app.core.config import get_settings
from app.core.deps import get_real_client_ip
from app.schemas.response import ClientInfoData, success_response

router = APIRouter(dependencies=[Depends(require_roles("ADMIN", "OPERATOR", "VIEWER"))])


@router.get("/client-info")
async def client_info(request: Request):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    settings = get_settings()

    direct_ip = request.client.host if request.client else "unknown"
    forwarded_for: list[str] = []
    if direct_ip in settings.trusted_proxy_ips:
        header = request.headers.get("x-forwarded-for")
        if header:
            forwarded_for = [ip.strip() for ip in header.split(",") if ip.strip()]

    data = ClientInfoData(
        client_ip=get_real_client_ip(request),
        forwarded_for=forwarded_for,
        user_agent=request.headers.get("user-agent"),
        accept_language=request.headers.get("accept-language"),
        protocol=request.scope.get("http_version", "1.1"),
        scheme=request.url.scheme,
        host=request.headers.get("host", ""),
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    return success_response(data.model_dump(), request_id, duration_ms)
