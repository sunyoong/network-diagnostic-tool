from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.auth_deps import require_csrf, require_roles
from app.core.logging import get_request_id
from app.core.security import (
    TargetNotAllowedError,
    ValidationError,
    assert_port_allowed,
    validate_host,
)
from app.schemas.request import PortCheckRequest
from app.schemas.response import PortCheckData, error_response, success_response
from app.services.tcp_service import perform_port_check
from app.services.persistence import persist_diagnostic

router = APIRouter(dependencies=[Depends(require_roles("ADMIN", "OPERATOR")), Depends(require_csrf)])


@router.post("/port-check", dependencies=[Depends(enforce_rate_limit)])
async def port_check(payload: PortCheckRequest, request: Request):
    request_id = get_request_id(request)
    start = time.monotonic()
    started_at = datetime.now(timezone.utc)

    async def failure(code: str, message: str, status_code: int):
        request.state.result_code = code
        duration_ms = int((time.monotonic() - start) * 1000)
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="TCP", success=False,
            result_code=code, api_status_code=status_code, duration_ms=duration_ms,
            started_at=started_at, details=payload.model_dump(), error_message=message,
        )
        return JSONResponse(status_code=status_code, content=error_response(code, message, request_id, duration_ms))

    try:
        validated_host = validate_host(payload.host)
        assert_port_allowed(payload.port)

        async with get_diagnostic_semaphore():
            result = await perform_port_check(
                host=validated_host, port=payload.port, timeout_seconds=payload.timeout_seconds
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        data = PortCheckData(
            host=result.host,
            resolved_ips=result.resolved_ips,
            port=result.port,
            open=result.open,
            result=result.result,
            connection_time_ms=result.connection_time_ms,
            message=result.message,
        )
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="TCP", success=result.open,
            result_code=result.result, api_status_code=200, duration_ms=duration_ms,
            started_at=started_at, details={**payload.model_dump(), **data.model_dump()},
        )
        request.state.result_code = result.result
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        return await failure("VALIDATION_ERROR", str(exc), 422)
    except TargetNotAllowedError as exc:
        return await failure("TARGET_NOT_ALLOWED", str(exc), 403)
    except Exception as exc:  # noqa: BLE001
        return await failure("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", 500)
