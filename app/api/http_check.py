from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.auth_deps import require_csrf, require_roles
from app.core.logging import get_request_id
from app.core.security import TargetNotAllowedError, ValidationError
from app.schemas.request import HttpCheckRequest
from app.schemas.response import HttpCheckData, error_response, success_response
from app.services.http_service import (
    DnsFailedError,
    TlsOrTransportError,
    TooManyRedirectsError,
    perform_http_check,
)
from app.services.persistence import persist_diagnostic

router = APIRouter(dependencies=[Depends(require_roles("ADMIN", "OPERATOR")), Depends(require_csrf)])


@router.post("/http-check", dependencies=[Depends(enforce_rate_limit)])
async def http_check(payload: HttpCheckRequest, request: Request):
    request_id = get_request_id(request)
    start = time.monotonic()
    started_at = datetime.now(timezone.utc)

    async def failure(code: str, message: str, status_code: int):
        request.state.result_code = code
        duration_ms = int((time.monotonic() - start) * 1000)
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="HTTP", success=False,
            result_code=code, api_status_code=status_code, duration_ms=duration_ms,
            started_at=started_at, details=payload.model_dump(), error_message=message,
        )
        return JSONResponse(status_code=status_code, content=error_response(code, message, request_id, duration_ms))

    try:
        async with get_diagnostic_semaphore():
            result = await perform_http_check(
                url=payload.url,
                method=payload.method,
                timeout_seconds=payload.timeout_seconds,
                follow_redirects=payload.follow_redirects,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        data = HttpCheckData(
            url=result.url,
            final_url=result.final_url,
            reachable=result.reachable,
            status_code=result.status_code,
            reason_phrase=result.reason_phrase,
            resolved_ip=result.resolved_ip,
            response_time_ms=result.response_time_ms,
            content_length=result.content_length,
            content_type=result.content_type,
            server=result.server,
            redirect_count=result.redirect_count,
        )
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="HTTP", success=True,
            result_code="OK", api_status_code=200, duration_ms=duration_ms,
            started_at=started_at, details={**payload.model_dump(), **data.model_dump()},
        )
        request.state.result_code = "OK"
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        return await failure("VALIDATION_ERROR", str(exc), 422)
    except TargetNotAllowedError as exc:
        return await failure("TARGET_NOT_ALLOWED", str(exc), 403)
    except DnsFailedError as exc:
        return await failure("DNS_RESOLUTION_FAILED", str(exc), 400)
    except TimeoutError as exc:
        return await failure("CONNECTION_TIMEOUT", "대상 서버가 제한 시간 내에 응답하지 않았습니다.", 200)
    except ConnectionRefusedError as exc:
        return await failure("CONNECTION_REFUSED", "대상 서버가 연결을 거부했습니다.", 200)
    except TlsOrTransportError as exc:
        return await failure("TLS_ERROR", "HTTPS 인증서 또는 TLS 연결에 실패했습니다.", 200)
    except TooManyRedirectsError as exc:
        return await failure("TOO_MANY_REDIRECTS", "리다이렉트 횟수 제한을 초과했습니다.", 200)
    except Exception as exc:  # noqa: BLE001
        return await failure("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", 500)
