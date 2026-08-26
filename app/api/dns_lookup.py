from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.deps import enforce_rate_limit, get_diagnostic_semaphore
from app.core.auth_deps import require_csrf, require_roles
from app.core.logging import get_request_id
from app.core.security import ValidationError, validate_domain
from app.schemas.request import DnsLookupRequest
from app.schemas.response import DnsLookupData, error_response, success_response
from app.services.dns_service import DomainNotFoundError, NoRecordsError, perform_dns_lookup
from app.services.persistence import persist_diagnostic

router = APIRouter(dependencies=[Depends(require_roles("ADMIN", "OPERATOR")), Depends(require_csrf)])


@router.post("/dns-lookup", dependencies=[Depends(enforce_rate_limit)])
async def dns_lookup(payload: DnsLookupRequest, request: Request):
    request_id = get_request_id(request)
    start = time.monotonic()
    started_at = datetime.now(timezone.utc)

    async def failure(code: str, message: str, status_code: int):
        request.state.result_code = code
        duration_ms = int((time.monotonic() - start) * 1000)
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="DNS", success=False,
            result_code=code, api_status_code=status_code, duration_ms=duration_ms,
            started_at=started_at, details=payload.model_dump(), error_message=message,
        )
        return JSONResponse(status_code=status_code, content=error_response(code, message, request_id, duration_ms))

    try:
        normalized_domain = validate_domain(payload.domain)

        async with get_diagnostic_semaphore():
            result = await perform_dns_lookup(normalized_domain, payload.record_type)

        duration_ms = int((time.monotonic() - start) * 1000)
        data = DnsLookupData(
            domain=result.domain,
            record_type=result.record_type,
            records=result.records,
            ttl=result.ttl,
            resolver=result.resolver,
            lookup_time_ms=result.lookup_time_ms,
        )
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="DNS", success=True,
            result_code="OK", api_status_code=200, duration_ms=duration_ms,
            started_at=started_at, details={**payload.model_dump(), **data.model_dump()},
        )
        request.state.result_code = "OK"
        return success_response(data.model_dump(), request_id, duration_ms)

    except ValidationError as exc:
        return await failure("VALIDATION_ERROR", str(exc), 422)
    except DomainNotFoundError as exc:
        return await failure("DNS_RESOLUTION_FAILED", str(exc), 400)
    except NoRecordsError as exc:
        # 도메인은 존재하지만 해당 레코드가 없는 경우: 정상적으로 완료된 조회 결과(빈 목록)로 처리
        duration_ms = int((time.monotonic() - start) * 1000)
        data = DnsLookupData(
            domain=normalized_domain if "normalized_domain" in locals() else payload.domain,
            record_type=payload.record_type,
            records=[],
            ttl=None,
            resolver=None,
            lookup_time_ms=duration_ms,
        )
        await persist_diagnostic(
            request, request_id=request_id, diagnostic_type="DNS", success=True,
            result_code="OK_EMPTY", api_status_code=200, duration_ms=duration_ms,
            started_at=started_at, details={**payload.model_dump(), **data.model_dump()},
        )
        request.state.result_code = "OK_EMPTY"
        return success_response(data.model_dump(), request_id, duration_ms)
    except TimeoutError as exc:
        return await failure("CONNECTION_TIMEOUT", "DNS 조회 시간이 초과되었습니다.", 200)
    except Exception as exc:  # noqa: BLE001
        return await failure("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", 500)
