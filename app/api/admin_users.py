from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import hash_password, validate_password
from app.core.auth_deps import require_csrf, require_roles
from app.db.session import get_pool
from app.schemas.auth import AdminResetPasswordRequest, UserCreateRequest, UserUpdateRequest
from app.schemas.response import success_response
from app.services.auth_service import add_auth_event

router = APIRouter(dependencies=[Depends(require_roles("ADMIN"))])


def serialize_user(user) -> dict:
    return {key: (str(user[key]) if key == "id" else user[key].isoformat() if key in {"last_login_at", "created_at"} and user[key] else user[key]) for key in (
        "id", "username", "email", "display_name", "role", "status", "must_change_password", "last_login_at", "created_at"
    )}


@router.get("")
async def list_users(role: str | None = None, status: str | None = None, query: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    clauses = ["deleted_at IS NULL"]; values: list[object] = []
    for column, value in (("role", role), ("status", status)):
        if value:
            values.append(value); clauses.append(f"{column}=${len(values)}")
    if query:
        values.append(f"%{query.lower()}%"); n = len(values)
        clauses.append(f"(lower(username) LIKE ${n} OR lower(display_name) LIKE ${n})")
    values.extend([limit, offset]); limit_pos, offset_pos = len(values) - 1, len(values)
    sql = f"SELECT * FROM user_accounts WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ${limit_pos} OFFSET ${offset_pos}"
    pool = await get_pool()
    async with pool.acquire() as connection:
        users = await connection.fetch(sql, *values)
    return success_response({"items": [serialize_user(user) for user in users], "limit": limit, "offset": offset}, str(uuid.uuid4()), 0)


@router.post("", dependencies=[Depends(require_csrf)])
async def create_user(payload: UserCreateRequest, context=Depends(require_roles("ADMIN"))):
    validate_password(payload.temporary_password, payload.username); user_id = uuid.uuid4(); pool = await get_pool()
    try:
        async with pool.acquire() as connection, connection.transaction():
            user = await connection.fetchrow(
                """INSERT INTO user_accounts(id,username,email,display_name,password_hash,role,status,must_change_password,created_by)
                VALUES($1,$2,$3,$4,$5,$6,'PENDING',true,$7) RETURNING *""",
                user_id, payload.username, payload.email.lower().strip() if payload.email else None,
                payload.display_name.strip(), hash_password(payload.temporary_password), payload.role, context.user_id,
            )
            await add_auth_event(connection, "ACCOUNT_CREATED", "SUCCESS", actor_user_id=context.user_id, target_user_id=user_id, details={"role": payload.role})
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, detail={"code": "USERNAME_ALREADY_EXISTS", "message": "이미 사용 중인 아이디 또는 이메일입니다."}) from exc
    return success_response(serialize_user(user), str(uuid.uuid4()), 0)


@router.patch("/{user_id}", dependencies=[Depends(require_csrf)])
async def update_user(user_id: uuid.UUID, payload: UserUpdateRequest, context=Depends(require_roles("ADMIN"))):
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        user = await connection.fetchrow("SELECT * FROM user_accounts WHERE id=$1 AND deleted_at IS NULL FOR UPDATE", user_id)
        if user is None: raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."})
        if user["role"] == "ADMIN" and (payload.role not in {None, "ADMIN"} or payload.status == "DISABLED"):
            count = await connection.fetchval("SELECT count(*) FROM user_accounts WHERE role='ADMIN' AND status IN ('ACTIVE','PENDING') AND deleted_at IS NULL")
            if count <= 1: raise HTTPException(409, detail={"code": "LAST_ADMIN_PROTECTED", "message": "마지막 관리자 계정은 변경할 수 없습니다."})
        updated = await connection.fetchrow(
            """UPDATE user_accounts SET display_name=COALESCE($2,display_name),email=COALESCE($3,email),
            role=COALESCE($4,role),status=COALESCE($5,status),disabled_at=CASE WHEN $5='DISABLED' THEN now() ELSE disabled_at END,
            version=version+1,updated_at=now() WHERE id=$1 RETURNING *""",
            user_id, payload.display_name.strip() if payload.display_name else None,
            payload.email.strip().lower() if payload.email else None, payload.role, payload.status,
        )
        if payload.status == "DISABLED":
            await connection.execute("UPDATE user_sessions SET revoked_at=now(),revoke_reason='ACCOUNT_DISABLED' WHERE user_id=$1 AND revoked_at IS NULL", user_id)
        await add_auth_event(connection, "ACCOUNT_UPDATED", "SUCCESS", actor_user_id=context.user_id, target_user_id=user_id, details=payload.model_dump(exclude_none=True))
    return success_response(serialize_user(updated), str(uuid.uuid4()), 0)


@router.post("/{user_id}/unlock", dependencies=[Depends(require_csrf)])
async def unlock_user(user_id: uuid.UUID, context=Depends(require_roles("ADMIN"))):
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        result = await connection.execute("UPDATE user_accounts SET status='ACTIVE',failed_login_count=0,locked_until=NULL,updated_at=now() WHERE id=$1", user_id)
        if result == "UPDATE 0": raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."})
        await add_auth_event(connection, "ACCOUNT_UNLOCKED", "SUCCESS", actor_user_id=context.user_id, target_user_id=user_id)
    return success_response({"unlocked": True}, str(uuid.uuid4()), 0)


@router.post("/{user_id}/reset-password", dependencies=[Depends(require_csrf)])
async def reset_password(user_id: uuid.UUID, payload: AdminResetPasswordRequest, context=Depends(require_roles("ADMIN"))):
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        user = await connection.fetchrow("SELECT * FROM user_accounts WHERE id=$1 FOR UPDATE", user_id)
        if user is None: raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."})
        validate_password(payload.temporary_password, user["username"])
        await connection.execute("INSERT INTO user_password_history(user_id,password_hash) VALUES($1,$2)", user_id, user["password_hash"])
        await connection.execute("UPDATE user_accounts SET password_hash=$2,password_changed_at=now(),must_change_password=true,updated_at=now() WHERE id=$1", user_id, hash_password(payload.temporary_password))
        await connection.execute("UPDATE user_sessions SET revoked_at=now(),revoke_reason='PASSWORD_RESET' WHERE user_id=$1 AND revoked_at IS NULL", user_id)
        await add_auth_event(connection, "PASSWORD_RESET_BY_ADMIN", "SUCCESS", actor_user_id=context.user_id, target_user_id=user_id)
    return success_response({"password_reset": True}, str(uuid.uuid4()), 0)


@router.post("/{user_id}/revoke-sessions", dependencies=[Depends(require_csrf)])
async def revoke_user_sessions(user_id: uuid.UUID, context=Depends(require_roles("ADMIN"))):
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        rows = await connection.fetch("UPDATE user_sessions SET revoked_at=now(),revoke_reason='ADMIN_REVOKED' WHERE user_id=$1 AND revoked_at IS NULL RETURNING id", user_id)
        await add_auth_event(connection, "SESSION_REVOKED", "SUCCESS", actor_user_id=context.user_id, target_user_id=user_id, details={"count": len(rows)})
    return success_response({"revoked": len(rows)}, str(uuid.uuid4()), 0)
