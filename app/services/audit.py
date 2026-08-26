from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.db.session import get_pool

logger = get_logger("ndt.audit.persistence")


async def persist_http_audit(*, actor_user_id: Any, client_key: str, fields: dict[str, Any]) -> None:
    """Best-effort DB copy of the already sanitized HTTP audit event."""
    settings = get_settings()
    if not settings.database_enabled:
        return
    safe_fields = {
        key: fields.get(key)
        for key in (
            "request_id", "http_method", "api_path", "route_template",
            "http_status_code", "success", "duration_ms", "actor_role", "result_code",
        )
    }
    severity = "INFO" if fields["http_status_code"] < 400 else "WARNING" if fields["http_status_code"] < 500 else "ERROR"
    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO audit_events
                (actor_user_id,event_type,severity,client_key,details,expires_at)
                VALUES($1,'HTTP_REQUEST',$2,$3,$4::jsonb,$5)""",
                actor_user_id, severity, client_key, json.dumps(safe_fields),
                datetime.now(timezone.utc) + timedelta(days=settings.audit_retention_days),
            )
    except Exception as exc:  # audit storage must never break the API
        log_event(logger, logging.ERROR, "database_write_failed",
                  request_id=fields.get("request_id"), operation="persist_http_audit",
                  error_type=type(exc).__name__)
