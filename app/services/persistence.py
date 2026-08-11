from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request

from app.core.auth import hash_client_ip
from app.core.config import get_settings
from app.core.deps import get_real_client_ip
from app.core.logging import get_logger
from app.db.session import get_pool

logger = get_logger("ndt.persistence")


def utcnow() -> datetime: return datetime.now(timezone.utc)


def redact_url(value: str | None) -> tuple[str | None, bool]:
    if not value: return None, False
    try:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), bool(parts.query or parts.fragment)
    except ValueError:
        return value[:2048], False


async def persist_diagnostic(request: Request, *, request_id: str, diagnostic_type: str, success: bool,
    result_code: str, api_status_code: int, duration_ms: int, started_at: datetime,
    details: dict, error_message: str | None = None) -> None:
    settings = get_settings()
    if not (settings.database_enabled and settings.diagnostic_persistence_enabled): return
    completed_at = utcnow(); run_id = uuid.UUID(request_id); client_ip = get_real_client_ip(request)
    context = getattr(request.state, "current_user", None)
    try:
        pool = await get_pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """INSERT INTO diagnostic_runs
                (id,user_id,diagnostic_type,success,result_code,api_status_code,error_message,duration_ms,client_key,client_ip,source,app_version,started_at,completed_at,expires_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'WEB',$11,$12,$13,$14)""",
                run_id, context.user_id if context else None, diagnostic_type, success, result_code,
                api_status_code, (error_message or "")[:500] or None, max(0, duration_ms), hash_client_ip(client_ip),
                client_ip if settings.store_raw_client_ip and client_ip != "unknown" else None, settings.app_version,
                started_at, completed_at, completed_at + timedelta(days=settings.diagnostic_retention_days),
            )
            if diagnostic_type == "HTTP":
                requested, redacted = redact_url(details.get("url")); final, final_redacted = redact_url(details.get("final_url"))
                await connection.execute(
                    """INSERT INTO http_diagnostic_results
                    (run_id,requested_url,target_host,method,timeout_ms,follow_redirects,query_redacted,final_url,reachable,status_code,
                    reason_phrase,resolved_ip,response_time_ms,content_length,content_type,server_header,redirect_count)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
                    run_id, requested or "invalid", (urlsplit(requested or "").hostname or "invalid")[:253], details.get("method", "GET"),
                    int(float(details.get("timeout_seconds", 5))*1000), bool(details.get("follow_redirects", True)), redacted or final_redacted,
                    final, bool(details.get("reachable", False)), details.get("status_code"), details.get("reason_phrase"), details.get("resolved_ip"),
                    details.get("response_time_ms"), details.get("content_length"), details.get("content_type"), details.get("server"), int(details.get("redirect_count", 0)),
                )
            elif diagnostic_type == "TCP":
                await connection.execute(
                    """INSERT INTO tcp_diagnostic_results
                    (run_id,host,port,timeout_ms,resolved_ips,is_open,connection_result,connection_time_ms,message)
                    VALUES($1,$2,$3,$4,$5::inet[],$6,$7,$8,$9)""",
                    run_id, str(details.get("host", "invalid"))[:253], int(details.get("port", 1)),
                    int(float(details.get("timeout_seconds", 3))*1000), details.get("resolved_ips") or [], bool(details.get("open", False)),
                    details.get("result", result_code), details.get("connection_time_ms"), str(details.get("message", error_message or result_code))[:500],
                )
            else:
                records = list(details.get("records") or []); redact = details.get("record_type") == "TXT"
                await connection.execute(
                    """INSERT INTO dns_diagnostic_results
                    (run_id,domain,record_type,records,record_count,records_redacted,ttl,resolver,lookup_time_ms)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    run_id, str(details.get("domain", "invalid"))[:253], details.get("record_type", "A"), [] if redact else records,
                    len(records), redact, details.get("ttl"), details.get("resolver"), details.get("lookup_time_ms"),
                )
    except Exception as exc:
        logger.error(f"request_id={request_id} result=DATABASE_WRITE_FAILED error={type(exc).__name__}")


async def list_diagnostics(user_id: uuid.UUID | None, is_admin: bool, limit: int, offset: int) -> list[dict]:
    pool = await get_pool()
    sql = """SELECT id,diagnostic_type,success,result_code,api_status_code,duration_ms,started_at,completed_at
             FROM diagnostic_runs WHERE ($1::boolean OR user_id=$2) ORDER BY created_at DESC LIMIT $3 OFFSET $4"""
    async with pool.acquire() as connection:
        rows = await connection.fetch(sql, is_admin, user_id, limit, offset)
    return [{**dict(row), "id": str(row["id"]), "started_at": row["started_at"].isoformat(), "completed_at": row["completed_at"].isoformat()} for row in rows]


async def get_diagnostic(run_id: uuid.UUID, user_id: uuid.UUID | None, is_admin: bool) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        run = await connection.fetchrow("SELECT * FROM diagnostic_runs WHERE id=$1 AND ($2::boolean OR user_id=$3)", run_id, is_admin, user_id)
        if run is None: return None
        table = {"HTTP": "http_diagnostic_results", "TCP": "tcp_diagnostic_results", "DNS": "dns_diagnostic_results"}[run["diagnostic_type"]]
        detail = await connection.fetchrow(f"SELECT * FROM {table} WHERE run_id=$1", run_id)
    detail_data = dict(detail) if detail else {}; detail_data.pop("run_id", None)
    for key, value in list(detail_data.items()):
        if isinstance(value, (datetime, uuid.UUID)): detail_data[key] = str(value)
        elif isinstance(value, list): detail_data[key] = [str(item) for item in value]
        elif value is not None and type(value).__module__ == "ipaddress": detail_data[key] = str(value)
    return {"id": str(run["id"]), "user_id": str(run["user_id"]) if run["user_id"] else None,
        "diagnostic_type": run["diagnostic_type"], "success": run["success"], "result_code": run["result_code"],
        "api_status_code": run["api_status_code"], "error_message": run["error_message"], "duration_ms": run["duration_ms"],
        "started_at": run["started_at"].isoformat(), "completed_at": run["completed_at"].isoformat(), "details": detail_data}
