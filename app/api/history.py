from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth_deps import require_roles
from app.core.config import get_settings
from app.schemas.response import success_response
from app.services.persistence import get_diagnostic, list_diagnostics

router = APIRouter(dependencies=[Depends(require_roles("ADMIN", "OPERATOR", "VIEWER"))])


def ensure_database() -> None:
    if not get_settings().database_enabled:
        raise HTTPException(status_code=503, detail={"code": "DATABASE_UNAVAILABLE", "message": "진단 이력 DB가 비활성화되어 있습니다."})


@router.get("")
async def recent_diagnostics(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context=Depends(require_roles("ADMIN", "OPERATOR", "VIEWER")),
):
    ensure_database()
    items = await list_diagnostics(context.user_id if context else None, bool(context and context.role == "ADMIN"), limit, offset)
    return success_response({"items": items, "limit": limit, "offset": offset}, str(uuid.uuid4()), 0)


@router.get("/{run_id}")
async def diagnostic_detail(run_id: uuid.UUID, context=Depends(require_roles("ADMIN", "OPERATOR", "VIEWER"))):
    ensure_database()
    item = await get_diagnostic(run_id, context.user_id if context else None, bool(context and context.role == "ADMIN"))
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "DIAGNOSTIC_NOT_FOUND", "message": "진단 이력을 찾을 수 없습니다."})
    return success_response(item, str(uuid.uuid4()), 0)
