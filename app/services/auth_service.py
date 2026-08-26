from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

from app.core.auth import (
    AuthContext, generate_token, hash_client_ip, hash_password, hash_token,
    password_needs_rehash, summarize_user_agent, validate_password, verify_password,
)
from app.core.config import get_settings
from app.db.session import get_pool
from app.core.logging import get_logger, log_event

logger = get_logger("ndt.auth_audit")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def add_auth_event(
    connection: asyncpg.Connection, event_type: str, outcome: str, *,
    actor_user_id: uuid.UUID | None = None, target_user_id: uuid.UUID | None = None,
    reason_code: str | None = None, client_key: str | None = None,
    session_id: uuid.UUID | None = None, details: dict | None = None,
) -> None:
    # Audit details are deliberately allow-listed: never persist names, email,
    # passwords, cookies, tokens, request bodies, or arbitrary caller data.
    details = details or {}
    safe_details = {key: details[key] for key in ("role", "status", "count") if key in details}
    log_event(
        logger, 20 if outcome == "SUCCESS" else 30, "auth_audit",
        event_type=event_type, outcome=outcome,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        target_user_id=str(target_user_id) if target_user_id else None,
        reason_code=reason_code, client_key=client_key,
        details=safe_details,
    )
    await connection.execute(
        """INSERT INTO auth_audit_events
        (actor_user_id,target_user_id,event_type,outcome,reason_code,client_key,session_id,details,expires_at)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)""",
        actor_user_id, target_user_id, event_type, outcome, reason_code, client_key,
        session_id, json.dumps(safe_details),
        utcnow() + timedelta(days=get_settings().auth_audit_retention_days),
    )


async def authenticate(username: str, password: str, client_ip: str, user_agent: str | None) -> tuple[AuthContext, str, str] | None:
    settings = get_settings(); now = utcnow(); client_key = hash_client_ip(client_ip)
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        user = await connection.fetchrow(
            "SELECT * FROM user_accounts WHERE username=$1 AND deleted_at IS NULL FOR UPDATE", username
        )
        if user is None:
            verify_password(password, hash_password("dummy-password-for-timing-only"))
            await add_auth_event(connection, "LOGIN_FAILED", "FAILURE", reason_code="UNKNOWN_USER", client_key=client_key)
            return None
        if user["status"] == "LOCKED" and user["locked_until"] and user["locked_until"] <= now:
            await connection.execute("UPDATE user_accounts SET status='ACTIVE',locked_until=NULL,failed_login_count=0 WHERE id=$1", user["id"])
            user = dict(user); user.update(status="ACTIVE", locked_until=None, failed_login_count=0)
        if user["status"] not in {"ACTIVE", "PENDING"}:
            await add_auth_event(connection, "LOGIN_FAILED", "FAILURE", target_user_id=user["id"], reason_code=user["status"], client_key=client_key)
            return None
        if not verify_password(password, user["password_hash"]):
            failures = user["failed_login_count"] + 1
            locked = failures >= settings.login_max_failures
            await connection.execute(
                "UPDATE user_accounts SET failed_login_count=$2,status=$3,locked_until=$4,updated_at=now() WHERE id=$1",
                user["id"], failures, "LOCKED" if locked else user["status"],
                now + timedelta(minutes=settings.login_lock_minutes) if locked else None,
            )
            await add_auth_event(connection, "LOGIN_FAILED", "FAILURE", target_user_id=user["id"], reason_code="LOCKED" if locked else "BAD_PASSWORD", client_key=client_key)
            return None
        new_hash = hash_password(password) if password_needs_rehash(user["password_hash"]) else user["password_hash"]
        await connection.execute(
            """UPDATE user_accounts SET password_hash=$2,failed_login_count=0,locked_until=NULL,
            last_login_at=$3,status=CASE WHEN status='PENDING' THEN 'ACTIVE' ELSE status END,updated_at=now() WHERE id=$1""",
            user["id"], new_hash, now,
        )
        sessions = await connection.fetch(
            "SELECT id FROM user_sessions WHERE user_id=$1 AND revoked_at IS NULL ORDER BY created_at", user["id"]
        )
        excess = max(0, len(sessions) - settings.max_sessions_per_user + 1)
        if excess:
            await connection.execute(
                "UPDATE user_sessions SET revoked_at=$2,revoke_reason='MAX_SESSIONS' WHERE id=ANY($1::uuid[])",
                [row["id"] for row in sessions[:excess]], now,
            )
        token, csrf_token, session_id = generate_token(), generate_token(), uuid.uuid4()
        absolute_hours = settings.admin_session_absolute_hours if user["role"] == "ADMIN" else settings.session_absolute_hours
        await connection.execute(
            """INSERT INTO user_sessions
            (id,user_id,token_hash,csrf_token_hash,client_key,user_agent_summary,last_seen_at,idle_expires_at,absolute_expires_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            session_id, user["id"], hash_token(token), hash_token(csrf_token), client_key,
            summarize_user_agent(user_agent), now, now + timedelta(minutes=settings.session_idle_minutes),
            now + timedelta(hours=absolute_hours),
        )
        await add_auth_event(connection, "LOGIN_SUCCEEDED", "SUCCESS", actor_user_id=user["id"], target_user_id=user["id"], client_key=client_key, session_id=session_id)
        return AuthContext(user["id"], session_id, user["username"], user["display_name"], user["role"], user["must_change_password"]), token, csrf_token


async def resolve_session(token: str) -> AuthContext | None:
    now = utcnow(); pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            """SELECT s.*,u.username,u.display_name,u.role,u.status,u.must_change_password,u.deleted_at
            FROM user_sessions s JOIN user_accounts u ON u.id=s.user_id
            WHERE s.token_hash=$1 AND s.revoked_at IS NULL FOR UPDATE OF s""", hash_token(token)
        )
        if row is None or row["status"] not in {"ACTIVE", "PENDING"} or row["deleted_at"] is not None:
            return None
        if row["idle_expires_at"] <= now or row["absolute_expires_at"] <= now:
            await connection.execute("UPDATE user_sessions SET revoked_at=$2,revoke_reason='EXPIRED' WHERE id=$1", row["id"], now)
            return None
        if now - row["last_seen_at"] >= timedelta(minutes=5):
            await connection.execute(
                "UPDATE user_sessions SET last_seen_at=$2,idle_expires_at=LEAST($3,absolute_expires_at) WHERE id=$1",
                row["id"], now, now + timedelta(minutes=get_settings().session_idle_minutes),
            )
        return AuthContext(row["user_id"], row["id"], row["username"], row["display_name"], row["role"], row["must_change_password"])


async def csrf_matches(session_id: uuid.UUID, token: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM user_sessions WHERE id=$1 AND csrf_token_hash=$2 AND revoked_at IS NULL)",
            session_id, hash_token(token),
        ))


async def revoke_session(session_id: uuid.UUID, user_id: uuid.UUID, reason: str = "LOGOUT") -> None:
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("UPDATE user_sessions SET revoked_at=$2,revoke_reason=$3 WHERE id=$1 AND revoked_at IS NULL", session_id, utcnow(), reason)
        await add_auth_event(connection, "LOGOUT" if reason == "LOGOUT" else "SESSION_REVOKED", "SUCCESS", actor_user_id=user_id, target_user_id=user_id, session_id=session_id, reason_code=reason)


async def change_password(context: AuthContext, current_password: str, new_password: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        user = await connection.fetchrow("SELECT * FROM user_accounts WHERE id=$1 FOR UPDATE", context.user_id)
        if user is None or not verify_password(current_password, user["password_hash"]):
            return False
        validate_password(new_password, user["username"])
        history = await connection.fetch(
            "SELECT password_hash FROM user_password_history WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
            user["id"], get_settings().password_history_count,
        )
        if verify_password(new_password, user["password_hash"]) or any(verify_password(new_password, row["password_hash"]) for row in history):
            raise ValueError("최근 사용한 비밀번호는 다시 사용할 수 없습니다.")
        await connection.execute("INSERT INTO user_password_history(user_id,password_hash) VALUES($1,$2)", user["id"], user["password_hash"])
        await connection.execute("UPDATE user_accounts SET password_hash=$2,password_changed_at=now(),must_change_password=false,updated_at=now() WHERE id=$1", user["id"], hash_password(new_password))
        await connection.execute("DELETE FROM user_password_history WHERE user_id=$1 AND id NOT IN (SELECT id FROM user_password_history WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2)", user["id"], get_settings().password_history_count)
        await connection.execute("UPDATE user_sessions SET revoked_at=now(),revoke_reason='PASSWORD_CHANGED' WHERE user_id=$1 AND id<>$2 AND revoked_at IS NULL", user["id"], context.session_id)
        await add_auth_event(connection, "PASSWORD_CHANGED", "SUCCESS", actor_user_id=user["id"], target_user_id=user["id"], session_id=context.session_id)
        return True
