from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.logging import get_logger
from app.core.security import ValidationError, validate_domain
from app.schemas.request import DnsLookupRequest
from app.schemas.response import DnsLookupData, error_response, success_response
from app.services.dns_service import DomainNotFoundError, NoRecordsError, perform_dns_lookup

router = APIRouter()
logger = get_logger("ndt.dns_lookup")


@router.post("/dns-lookup", dependencies=[Depends(enforce_rate_limit)])
async def dns_lookup(payload: DnsLookupRequest, request: Request):
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    try:
        normalized_domain = validate_domain(payload.domain)

        async with get_diagnostic_semaphore():
            result = await perform_dns_lookup(normalized_domain, payload.record_type)

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            f"path=/api/v1/dns-lookup request_id={request_id} result=OK "
            f"duration_ms={duration_ms} domain={payload.domain} type={payload.record_type}"
        )
        data = DnsLookupData(
            domain=result.domain,
            record_type=result.record_type,
            records=result.records,
            ttl=result.ttl,
            resolver=result.resolver,
            lookup_time_ms=result.lookup_time_ms,
        )
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"path=/api/v1/dns-lookup request_id={request_id} result=VALIDATION_ERROR domain={payload.domain}")
        return JSONResponse(
            status_code=422,
            content=error_response("VALIDATION_ERROR", str(exc), request_id, duration_ms),
        )
    except DomainNotFoundError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/dns-lookup request_id={request_id} result=DNS_RESOLUTION_FAILED domain={payload.domain}")
        return JSONResponse(
            status_code=400,
            content=error_response("DNS_RESOLUTION_FAILED", str(exc), request_id, duration_ms),
        )
    except NoRecordsError as exc:
        # 도메인은 존재하지만 해당 레코드가 없는 경우: 정상적으로 완료된 조회 결과(빈 목록)로 처리
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/dns-lookup request_id={request_id} result=OK_EMPTY domain={payload.domain}")
        data = DnsLookupData(
            domain=normalized_domain if "normalized_domain" in locals() else payload.domain,
            record_type=payload.record_type,
            records=[],
            ttl=None,
            resolver=None,
            lookup_time_ms=duration_ms,
        )
        return success_response(data.model_dump(), request_id, duration_ms)
    except TimeoutError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"path=/api/v1/dns-lookup request_id={request_id} result=CONNECTION_TIMEOUT domain={payload.domain}")
        return JSONResponse(
            status_code=200,
            content=error_response("CONNECTION_TIMEOUT", "DNS 조회 시간이 초과되었습니다.", request_id, duration_ms),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"path=/api/v1/dns-lookup request_id={request_id} result=INTERNAL_SERVER_ERROR error={type(exc).__name__}")
        return JSONResponse(
            status_code=500,
            content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", request_id, duration_ms),
        )
