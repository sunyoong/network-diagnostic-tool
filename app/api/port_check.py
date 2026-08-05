from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.logging import get_logger
from app.core.security import (
    TargetNotAllowedError,
    ValidationError,
    assert_port_allowed,
    validate_host,
)
from app.schemas.request import PortCheckRequest
from app.schemas.response import PortCheckData, error_response, success_response
from app.services.tcp_service import perform_port_check

router = APIRouter()
logger = get_logger("ndt.port_check")


@router.post("/port-check", dependencies=[Depends(enforce_rate_limit)])
async def port_check(payload: PortCheckRequest, request: Request):
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    try:
        validated_host = validate_host(payload.host)
        assert_port_allowed(payload.port)

        async with get_diagnostic_semaphore():
            result = await perform_port_check(
                host=validated_host, port=payload.port, timeout_seconds=payload.timeout_seconds
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            f"path=/api/v1/port-check request_id={request_id} result={result.result} "
            f"duration_ms={duration_ms} host={payload.host} port={payload.port}"
        )
        data = PortCheckData(
            host=result.host,
            resolved_ips=result.resolved_ips,
            port=result.port,
            open=result.open,
            result=result.result,
            connection_time_ms=result.connection_time_ms,
            message=result.message,
        )
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/port-check request_id={request_id} result=VALIDATION_ERROR host={payload.host}")
        return JSONResponse(
            status_code=422,
            content=error_response("VALIDATION_ERROR", str(exc), request_id, duration_ms),
        )
    except TargetNotAllowedError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/port-check request_id={request_id} result=TARGET_NOT_ALLOWED host={payload.host}")
        return JSONResponse(
            status_code=403,
            content=error_response("TARGET_NOT_ALLOWED", str(exc), request_id, duration_ms),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"path=/api/v1/port-check request_id={request_id} result=INTERNAL_SERVER_ERROR error={type(exc).__name__}")
        return JSONResponse(
            status_code=500,
            content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", request_id, duration_ms),
        )
