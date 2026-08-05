from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.logging import get_logger, mask_sensitive_query
from app.core.security import TargetNotAllowedError, ValidationError
from app.schemas.request import HttpCheckRequest
from app.schemas.response import HttpCheckData, error_response, success_response
from app.services.http_service import (
    DnsFailedError,
    TlsOrTransportError,
    TooManyRedirectsError,
    perform_http_check,
)

router = APIRouter()
logger = get_logger("ndt.http_check")


@router.post("/http-check", dependencies=[Depends(enforce_rate_limit)])
async def http_check(payload: HttpCheckRequest, request: Request):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    masked_url = mask_sensitive_query(payload.url)

    try:
        async with get_diagnostic_semaphore():
            result = await perform_http_check(
                url=payload.url,
                method=payload.method,
                timeout_seconds=payload.timeout_seconds,
                follow_redirects=payload.follow_redirects,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            f"path=/api/v1/http-check request_id={request_id} result=OK "
            f"duration_ms={duration_ms} url={masked_url}"
        )
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
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/http-check request_id={request_id} result=VALIDATION_ERROR url={masked_url}")
        return JSONResponse(
            status_code=422,
            content=error_response("VALIDATION_ERROR", str(exc), request_id, duration_ms),
        )
    except TargetNotAllowedError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/http-check request_id={request_id} result=TARGET_NOT_ALLOWED url={masked_url}")
        return JSONResponse(
            status_code=403,
            content=error_response("TARGET_NOT_ALLOWED", str(exc), request_id, duration_ms),
        )
    except DnsFailedError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/http-check request_id={request_id} result=DNS_RESOLUTION_FAILED url={masked_url}")
        return JSONResponse(
            status_code=400,
            content=error_response("DNS_RESOLUTION_FAILED", str(exc), request_id, duration_ms),
        )
    except TimeoutError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/http-check request_id={request_id} result=CONNECTION_TIMEOUT url={masked_url}")
        return JSONResponse(
            status_code=200,
            content=error_response("CONNECTION_TIMEOUT", "대상 서버가 제한 시간 내에 응답하지 않았습니다.", request_id, duration_ms),
        )
    except ConnectionRefusedError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/http-check request_id={request_id} result=CONNECTION_REFUSED url={masked_url}")
        return JSONResponse(
            status_code=200,
            content=error_response("CONNECTION_REFUSED", "대상 서버가 연결을 거부했습니다.", request_id, duration_ms),
        )
    except TlsOrTransportError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/http-check request_id={request_id} result=TLS_ERROR url={masked_url}")
        return JSONResponse(
            status_code=200,
            content=error_response("TLS_ERROR", "HTTPS 인증서 또는 TLS 연결에 실패했습니다.", request_id, duration_ms),
        )
    except TooManyRedirectsError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/http-check request_id={request_id} result=TLS_ERROR url={masked_url}")
        return JSONResponse(
            status_code=200,
            content=error_response("CONNECTION_TIMEOUT", "리다이렉트 횟수 제한을 초과했습니다.", request_id, duration_ms),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"path=/api/v1/http-check request_id={request_id} result=INTERNAL_SERVER_ERROR error={type(exc).__name__}")
        return JSONResponse(
            status_code=500,
            content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", request_id, duration_ms),
        )
